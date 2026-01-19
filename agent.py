import json
import re
import logging
import asyncio
import os

# Імпорт системних та кастомних модулів
from modules.defaults import DEFAULT_SYSTEM_PROMPT
from modules.tools.manager import ToolManager
from modules.config_loader import load_settings, CONFIG_DIR
from modules.context import ContextManager
from modules.history import HistoryManager
from modules.session import SessionManager
from modules.processor import ResponseProcessor
from modules.policy import PermissionPolicy
from modules.chat import get_chat_provider, ProviderAPIError
from modules.parser import ResponseParser, Segment

class AngelicaAgent:
    def __init__(self, ui=None):
        self._ui = ui
        self.settings = load_settings()
        
        # Стан та запобіжники для TUI
        self.is_awaiting_model_selection = False 
        self.current_task = None
        self.main_task = None
        self.MAX_CONSECUTIVE_CALLS = 5

        # Налаштування логування комунікації
        self.comm_log = self._setup_logger()

        # 1. Ініціалізація ToolManager та завантаження інструментів
        self.tool_manager = ToolManager()
        self.tool_manager.load_tools()
        
        # 2. Менеджери даних (ContextManager використовує старий FileModule для читання)
        from modules.files import FileModule
        self.files = FileModule()
        self.context_manager = ContextManager(self.files)
        
        # 3. Налаштування AI Провайдера
        model_name = self.settings.get("default_model", "ollama/qwen2.5-coder:7b")
        self.chat = get_chat_provider(model_name)
        
        # 4. Управління історією та сесіями
        self.history = HistoryManager(self.chat, logger=self.comm_log, max_tokens=self.settings.get("max_history_tokens", 4000))
        self.session_manager = SessionManager(CONFIG_DIR, self.history, self.context_manager, self._ui)
        
        # Ініціалізація розміру історії з налаштувань
        initial_history_size = self.settings.get("history_size", "small")
        self.set_history_size(initial_history_size)

        # 5. Політика безпеки та Процесор дій
        policy_mode = self.settings.get("permission_policy", "ask")
        self.policy = PermissionPolicy(self._ui, policy_mode)
        
        self.processor = ResponseProcessor(
            ui=self._ui, 
            tool_manager=self.tool_manager, 
            chat=self.chat, 
            policy=self.policy
        )
        
        # 6. Parser
        self.parser = ResponseParser()
        
        # 7. Loop Detection
        self.last_action_fingerprint = None
        self.last_action_status = None
        self.consecutive_failed_repeats = 0

    def _get_action_fingerprint(self, command: dict) -> str:
        """Creates a unique string for an action based on type and arguments."""
        cmd_type = command.get("type") or command.get("action") or "unknown"
        # Extract arguments, ignoring service fields
        service_fields = {"before_execution", "during_execution", "after_execution", "return_control"}
        args = {k: v for k, v in command.items() if k not in service_fields}
        # Stable string representation
        args_str = json.dumps(args, sort_keys=True)
        return f"{cmd_type}:{args_str}"

    @property
    def ui(self):
        return self._ui

    @ui.setter
    def ui(self, value):
        """Синхронізує посилання на UI у всіх залежних модулях при підключенні TUI."""
        self._ui = value
        if hasattr(self, 'processor'): self.processor.ui = value
        if hasattr(self, 'policy'): self.policy.ui = value
        if hasattr(self, 'session_manager'): self.session_manager.ui = value

    def _setup_logger(self):
        logger = logging.getLogger('communication')
        logger.setLevel(logging.INFO)
        if not logger.handlers:
            handler = logging.FileHandler("communication.log", encoding="utf-8")
            handler.setFormatter(logging.Formatter('%(asctime)s - %(message)s'))
            logger.addHandler(handler)
        return logger

    async def get_response(self, query):
        """Отримує стрімінгову відповідь від ШІ."""
        full_text = ""
        self.comm_log.info(f"OUTGOING:\n{query}")
        try:
            async for chunk in self.chat.get_streaming_response(query, self.history.get_history_for_api()):
                full_text += chunk
        except Exception as e:
            self.comm_log.error(f"Chat error: {e}")
            return f"Error: {e}"
        
        self.comm_log.info(f"INCOMING:\n{full_text}")
        return full_text

    async def process_user_input(self, user_input):
        """Головний цикл обробки вводу: Промпт -> ШІ -> Парсинг -> Послідовне виконання -> ШІ."""
        # Підготовка контексту та інструментів
        tools_desc = self.tool_manager.get_tools_prompt()
        system_prompt = DEFAULT_SYSTEM_PROMPT.format(tools_description=tools_desc)
        context_info = self.context_manager.get_context_prompt()
        
        # Додаємо в історію актуальні дані про проект
        self.history.add_message("system", f"{system_prompt}\n\n{context_info}")
        self.history.add_message("user", user_input)
        
        active_loop = True
        consecutive_calls = 0
        current_query = user_input

        try:
            while active_loop:
                consecutive_calls += 1
                if consecutive_calls > self.MAX_CONSECUTIVE_CALLS:
                    await self.ui.stop_loading()
                    if not await self.ui.confirm_continue("Агент виконав багато кроків. Продовжити?"):
                        break

                await self.ui.start_thinking() 
                
                # Запускаємо задачу з можливістю переривання
                self.current_task = asyncio.create_task(self.get_response(current_query))
                response = await self.current_task
                
                if not response:
                    break
                
                if response.startswith("Error:"):
                    await self.ui.print_error(response)
                    break
                
                self.history.add_message("assistant", response)
                
                # --- NEW PARSING & EXECUTION LOOP ---
                segments = self.parser.parse(response)
                
                execution_results = []
                should_return_control = False
                found_action = False
                
                for segment in segments:
                    if segment.type == 'thought':
                        await self.ui.print_thought(segment.content)
                    
                    elif segment.type == 'text':
                        # Only print text if we haven't found an action yet, 
                        # or if we want to stream text mixed with actions.
                        await self.ui.print_message(segment.content, role="assistant")
                        
                    elif segment.type == 'action':
                        found_action = True
                        command = segment.content
                        
                        # --- LOOP DETECTION ---
                        fingerprint = self._get_action_fingerprint(command)
                        if fingerprint == self.last_action_fingerprint and self.last_action_status in ["failed", "error"]:
                            self.consecutive_failed_repeats += 1
                        else:
                            self.consecutive_failed_repeats = 0
                        
                        if self.consecutive_failed_repeats >= 1: # Already one failure, now repeating
                            warn_msg = "⚠️ Loop detected: You are repeating the same action that just failed."
                            await self.ui.print_error(warn_msg)
                            # Inject warning into history for AI
                            self.history.add_message("system", f"CRITICAL: {warn_msg} Change your strategy.")
                        
                        if command.get("before_execution"):
                            await self.ui.print_plan(command['before_execution'])
                        
                        await self.ui.start_action(command.get("during_execution", "Processing..."))
                        
                        # Execute
                        result = await self.processor.process_single_action(command)
                        
                        # Update Loop Detection State
                        self.last_action_fingerprint = fingerprint
                        self.last_action_status = result.get("status")
                        
                        if result.get("status") == "success" and command.get("after_execution"):
                            await self.ui.print_confirmation(command['after_execution'])
                        
                        output_text = result.get('output', '')
                        cmd_name = command.get("type") or command.get("action") or "command"
                        await self.ui.print_command_result(output_text, command_name=cmd_name)
                        
                        # Accumulate result
                        if result.get("status") in ["failed", "error"]:
                            # Self-Healing Injection
                            output_text += "\n\n[SYSTEM INSTRUCTION: The action failed. Analyze this error in a <think> block to determine the root cause, then propose a corrected action.]"
                        
                        execution_results.append(f"Command: {cmd_name}\nResult: {output_text}")
                        
                        # Check return_control
                        if command.get("return_control") is True:
                            should_return_control = True
                            break 
                        
                        # Check for critical failure? User said "stop if current block gives error"
                        if result.get("status") == "failed" or result.get("status") == "error":
                            # Stop chain execution
                            should_return_control = True # Implicitly return control so AI knows it failed
                            break

                # End of Segment Loop
                
                if found_action:
                    # Construct system message with all results
                    full_result_msg = "SYSTEM RESULTS:\n" + "\n---".join(execution_results)
                    self.history.add_message("system", full_result_msg)
                    current_query = full_result_msg
                    
                    if should_return_control:
                        # Continue loop (call AI again with results)
                        active_loop = True
                    else:
                        # If actions were executed but no explicit return control, 
                        # assume we are done for now unless we loop automatically.
                        # Given the user wants sequential execution, if we finished all blocks
                        # and no return_control=True was explicit, we usually stop.
                        # However, if one of them FAILED, we set should_return_control=True above, so we loop.
                        # If all SUCCESS and no return_control, we stop.
                        active_loop = False
                else:
                    # No actions found, just text/thoughts.
                    active_loop = False

            await self.history.check_and_summarize(self.ui)
        except asyncio.CancelledError:
            pass # Переривання вже оброблене в interrupt()
        finally:
            self.current_task = None
            await self.ui.stop_loading()

    async def interrupt(self):
        """Перериває поточну асинхронну задачу агента."""
        if self.current_task and not self.current_task.done():
            self.current_task.cancel()
            await self.ui.print_system("🛑 Операцію перервано.")

    async def switch_model(self, model_name: str):
        """Гаряче перемикання моделі ШІ з оновленням історії та процесора."""
        if hasattr(self.chat, 'model_name') and self.chat.model_name == model_name:
            await self.ui.print_system(f"Модель {model_name} вже активна.")
            return

        await self.ui.print_system(f"Перемикаюсь на {model_name}...")
        new_chat_provider = get_chat_provider(model_name)
        
        if new_chat_provider:
            self.chat = new_chat_provider
            self.history = HistoryManager(self.chat, logger=self.comm_log, max_tokens=self.settings.get("max_history_tokens", 4000))
            self.processor.chat = self.chat
            await self.ui.update_header(f"{self.chat.model_name}")
            await self.ui.print_system(f"✅ Модель змінено на {model_name}")
    
    def set_history_size(self, size_name: str):
        """Встановлює ліміт токенів історії (колишній context_size)."""
        HISTORY_LIMITS = {
            "small": 4096,
            "medium": 16384,
            "large": 32768
        }
        
        size_key = size_name.lower()
        if size_key not in HISTORY_LIMITS:
            # Fallback for unknown values
            token_limit = 4096
            size_key = "small"
        else:
            token_limit = HISTORY_LIMITS[size_key]
            
        # Update history manager if initialized
        if hasattr(self, 'history'):
            self.history.max_tokens = token_limit
            
        # Save current state (runtime only, doesn't persist to yaml unless we want to)
        self.history_size = size_key
        if self.ui:
            asyncio.create_task(self.ui.print_system(f"History limit set to {size_key.upper()} ({token_limit} tokens)"))