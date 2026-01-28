"""Оркестратор основного циклу."""

import asyncio
from modules.defaults import DEFAULT_SYSTEM_PROMPT

class Orchestrator:
    def __init__(self, agent):
        self.agent = agent
        # Скорочення для зручності
        self.ui = agent.ui
        self.state = agent.state
        self.history = agent.history
        self.model = agent.model_client
        self.dispatcher = agent.action_dispatcher
        self.parser = agent.parser
        self.config = agent.config
        
    async def process(self, user_input):
        """Головний цикл: Think -> Act -> Loop."""
        
        # 1. Підготовка контексту
        tools_prompt = self.agent.tool_manager.get_tools_prompt()
        ctx_prompt = self.agent.context_manager.get_context_prompt()
        system_msg = f"{DEFAULT_SYSTEM_PROMPT.format(tools_description=tools_prompt)}\n\n{ctx_prompt}"
        
        self.history.add_message("system", system_msg)
        self.history.add_message("user", user_input)
        
        active_loop = True
        consecutive_calls = 0
        current_query = user_input
        
        try:
            while active_loop:
                consecutive_calls += 1
                if consecutive_calls > self.config.MAX_CONSECUTIVE_CALLS:
                    await self.ui.stop_loading()
                    if not await self.ui.confirm_continue("Агент зробив багато кроків. Продовжити?"):
                        break
                
                await self.ui.start_thinking()
                
                # 2. Запит до AI
                self.state.current_task = asyncio.create_task(
                    self.model.get_streaming_response(
                        current_query, self.history, self.ui, self.state
                    )
                )
                response = await self.state.current_task
                
                if not response or response.startswith("Error:"):
                    break
                    
                # 3. Парсинг
                segments = self.parser.parse(response)
                
                # 4. Виконання дій (через Dispatcher)
                processed_segs, sys_results, should_stop = await self.dispatcher.dispatch_segments(
                    segments, self.state
                )
                
                # 5. Оновлення історії
                # Асистент "пам'ятає" свої дії (але create_file може бути стиснутий)
                recon_msg = self.parser.reconstruct(processed_segs)
                if recon_msg:
                    self.history.add_message("assistant", recon_msg)
                
                # Результати системи
                if sys_results:
                    for res in sys_results:
                        self.history.add_message("system", res)
                    
                    if should_stop:
                        active_loop = False
                    else:
                        # Продовжуємо цикл з результатами
                        current_query = "\n---\n".join(sys_results)
                else:
                    active_loop = False # Немає дій = кінець розмови
            
            # 6. Summarization
            try:
                await self.history.check_and_summarize(self.ui)
            except Exception as e:
                if self.agent.log: self.agent.log.warning(f"Summarization error: {e}")
                
        finally:
            self.state.current_task = None
            await self.ui.stop_loading()
