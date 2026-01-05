import json
import re
import logging
import asyncio

# Імпорт нових та стандартних модулів
from modules.defaults import DEFAULT_SYSTEM_PROMPT
from modules.tools.manager import ToolManager
from modules.config_loader import load_settings, CONFIG_DIR
from modules.context import ContextManager
from modules.history import HistoryManager
from modules.session import SessionManager
from modules.processor import ResponseProcessor
from modules.policy import PermissionPolicy
from modules.chat import get_chat_provider, ProviderAPIError
from modules.tui_ui import TuiUI

class AngelicaAgent:
    def __init__(self, ui=None):
        self.ui = ui
        self.settings = load_settings()
        
        # 1. Нова архітектура інструментів
        self.tool_manager = ToolManager()
        self.tool_manager.load_tools()
        
        # 2. Твої менеджери (зберігаємо FileModule для ContextManager, якщо треба)
        from modules.files import FileModule
        self.files = FileModule()
        self.context_manager = ContextManager(self.files)
        
        # 3. Твої запобіжники та стан
        self.MAX_CONSECUTIVE_CALLS = 3
        self.current_task = None
        
        # 4. AI Provider
        model_name = self.settings.get("default_model", "ollama/qwen2.5-coder:7b")
        self.chat = get_chat_provider(model_name)
        
        # 5. History & Session
        self.comm_log = self._setup_logger()
        self.history = HistoryManager(self.chat, logger=self.comm_log, max_tokens=self.settings.get("max_history_tokens", 4000))
        self.session_manager = SessionManager(CONFIG_DIR, self.history, self.context_manager, self.ui)
        
        # 6. Policy & Processor (Нова версія)
        policy_mode = self.settings.get("permission_policy", "ask")
        if isinstance(ui, TuiUI) and policy_mode == "ask":
            policy_mode = "always" 
            
        self.policy = PermissionPolicy(self.ui, policy_mode)
        self.processor = ResponseProcessor(
            ui=self.ui, 
            tool_manager=self.tool_manager, 
            chat=self.chat, 
            policy=self.policy
        )

    def _setup_logger(self):
        logger = logging.getLogger('communication')
        logger.setLevel(logging.INFO)
        if not logger.handlers:
            handler = logging.FileHandler("communication.log", encoding="utf-8")
            handler.setFormatter(logging.Formatter('%(asctime)s - %(message)s'))
            logger.addHandler(handler)
        return logger

    def _parse_output(self, text: str):
        """Покращений парсер: розуміє <think> та JSON (як в блоках, так і сирий)."""
        thoughts = []
        command = None
        
        # Витягуємо думки
        thought_match = re.search(r'<think>(.*?)</think>', text, re.DOTALL | re.IGNORECASE)
        if thought_match:
            thoughts.append(thought_match.group(1).strip())
            text = text.replace(thought_match.group(0), "")

        remaining_text = text.strip()

        # Шукаємо JSON: спочатку в markdown блоках, потім просто в тексті
        json_match = re.search(r'```json\s*(\{.*?\})\s*```', remaining_text, re.DOTALL)
        if not json_match:
            json_match = re.search(r'(\{.*?\})', remaining_text, re.DOTALL)

        if json_match:
            try:
                command = json.loads(json_match.group(1))
                remaining_text = remaining_text.replace(json_match.group(0), "").strip()
            except json.JSONDecodeError:
                pass
        
        return thoughts, command, remaining_text

    async def get_response(self, query):
        full_text = ""
        self.comm_log.info(f"OUTGOING TO AI:\n{query}")
        try:
            async for chunk in self.chat.get_streaming_response(query, self.history.get_history_for_api()):
                full_text += chunk
        except Exception as e:
            self.comm_log.error(f"Chat error: {e}")
            return f"Error: {e}"
        return full_text

    async def interrupt(self):
        if self.current_task and not self.current_task.done():
            self.current_task.cancel()
            await self.ui.print_system("🛑 Перервано.")

    async def process_user_input(self, user_input):
        # ГЕНЕРУЄМО ПРОМПТ: вставляємо описи інструментів у шаблон
        tools_desc = self.tool_manager.get_tools_prompt()
        system_prompt = DEFAULT_SYSTEM_PROMPT.format(tools_description=tools_desc)
        
        # ОТРИМУЄМО КОНТЕКСТ: дерево проекту з .gitignore + відкриті файли
        context_info = self.context_manager.get_context_prompt()
        
        # Оновлюємо історію для ШІ
        self.history.add_message("system", f"{system_prompt}\n\n{context_info}")
        self.history.add_message("user", user_input)
        
        active_loop = True
        consecutive_calls = 0
        current_query = user_input

        try:
            await self.ui.start_thinking()
            while active_loop:
                consecutive_calls += 1
                if consecutive_calls > self.MAX_CONSECUTIVE_CALLS:
                    await self.ui.stop_loading()
                    if not await self.ui.confirm_continue("Агент зробив забагато кроків. Продовжити?"):
                        break
                    await self.ui.start_thinking()

                # Запускаємо як задачу для можливості переривання
                self.current_task = asyncio.create_task(self.get_response(current_query))
                response = await self.current_task
                
                if not response: break
                self.history.add_message("assistant", response)
                
                thoughts, command, plain_text = self._parse_output(response)

                for thought in thoughts:
                    await self.ui.print_thought(thought)

                if command:
                    if command.get("before_execution"):
                        await self.ui.print_plan(command['before_execution'])
                    
                    await self.ui.start_action(command.get("during_execution", "Виконую..."))
                    
                    # Виконання через новий процесор (з підтримкою PermissionPolicy)
                    result = await self.processor.process_single_action(command)
                    
                    if result.get("status") == "success" and command.get("after_execution"):
                        await self.ui.print_confirmation(command['after_execution'])
                    
                    await self.ui.print_command_result(result.get('output', ''))

                    if command.get("return_control") is True:
                        current_query = f"SYSTEM RESULT: {result.get('output')}"
                        self.history.add_message("system", current_query)
                    else:
                        active_loop = False
                
                elif plain_text:
                    await self.ui.print_message(plain_text, role="assistant")
                    active_loop = False

            await self.history.check_and_summarize(self.ui)
        except asyncio.CancelledError:
            pass
        finally:
            self.current_task = None
            await self.ui.stop_loading()
