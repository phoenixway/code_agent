import json
import re
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
from modules.logger import get_comm_logger, get_debug_logger, setup_loggers

class AngelicaAgent:
    def __init__(self, ui=None):
        self._ui = ui
        self.settings = load_settings()
        
        # Стан та запобіжники для TUI
        self.is_awaiting_model_selection = False 
        self.current_task = None
        self.main_task = None
        self.MAX_CONSECUTIVE_CALLS = 5

        # Налаштування логування
        setup_loggers(clear_communication_log=True)
        self.comm_log = get_comm_logger()
        self.log = get_debug_logger()

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
        self.history = HistoryManager(self.chat, logger=self.log, max_tokens=self.settings.get("max_history_tokens", 4000))
        self.session_manager = SessionManager(self.history, self.context_manager, self._ui)
        self.session_manager.load_session()
        
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

    async def get_response(self, query):
        """Отримує стрімінгову відповідь від ШІ."""
        full_text = ""
        self.comm_log.info(f"--- OUTGOING ---\n{query}\n")
        try:
            async for chunk in self.chat.get_streaming_response(query, self.history.get_history_for_api()):
                full_text += chunk
        except Exception as e:
            self.log.error(f"Chat error: {e}")
            return f"Error: {e}"
        
        self.comm_log.info(f"--- INCOMING ---\n{full_text}\n")
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

        # Список операцій, що змінюють стан
        STATE_CHANGING_OPS = ["run_shell", "create_file", "replace", "edit_file", "git_add", "git_commit", "git_checkout", "delete_file"]

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
                
                segments = self.parser.parse(response)
                
                processed_segments = []
                system_results = []
                active_loop = False # За замовчуванням цикл завершується, якщо не буде знайдено дій
                
                for segment in segments:
                    processed_segments.append(segment)

                    if segment.type == 'thought':
                        await self.ui.print_thought(segment.content)
                    
                    elif segment.type == 'text':
                        await self.ui.print_message(segment.content, role="assistant")
                        
                    elif segment.type == 'action':
                        command = segment.content
                        cmd_name = command.get("type") or command.get("action", "unknown")

                        # --- LOOP DETECTION ---
                        fingerprint = self._get_action_fingerprint(command)
                        if fingerprint == self.last_action_fingerprint and self.last_action_status in ["failed", "error"]:
                            self.consecutive_failed_repeats += 1
                        else:
                            self.consecutive_failed_repeats = 0
                        
                        if self.consecutive_failed_repeats >= 1:
                            warn_msg = "⚠️ Loop detected: You are repeating the same action that just failed."
                            await self.ui.print_error(warn_msg)
                            self.history.add_message("system", f"CRITICAL: {warn_msg} Change your strategy.")

                        # --- Branch for run_shell display ---
                        if cmd_name == 'run_shell':
                            shell_widget = await self.ui.print_shell_start(command)
                            await self.ui.start_action(command.get("during_execution", f"Executing {cmd_name}..."))
                            result = await self.processor.process_single_action(command)
                            await self.ui.update_shell_result(shell_widget, result)
                        else:
                            # Default display for all other tools
                            await self.ui.print_tool_call(command)
                            if command.get("before_execution"):
                                await self.ui.print_plan(command['before_execution'])
                            
                            await self.ui.start_action(command.get("during_execution", f"Executing {cmd_name}..."))
                            result = await self.processor.process_single_action(command)

                            if result.get("status") == "success" and command.get("after_execution"):
                                await self.ui.print_confirmation(command['after_execution'])
                            
                            output_text_for_print = result.get('output', '')
                            await self.ui.print_command_result(output_text_for_print)

                        # --- COMMON POST-ACTION LOGIC ---
                        self.last_action_fingerprint = fingerprint
                        self.last_action_status = result.get("status")
                        
                        output_text = result.get('output', '')
                        full_command_name = command.get('command') if cmd_name == 'run_shell' else None
                        
                        # --- SMART STOP & TRUNCATION LOGIC ---
                        is_state_changing = any(op in cmd_name for op in STATE_CHANGING_OPS)
                        execution_failed = result.get("status") in ["failed", "error"]
                        should_return_control = command.get("return_control") is True

                        if execution_failed:
                            output_text += "\n\n[SYSTEM INSTRUCTION: The action failed. Analyze this error in a <think> block to determine the root cause, then propose a corrected action.]"
                        
                        system_results.append(f"SYSTEM RESULT for `{cmd_name}`: {output_text}")
                        
                        # Зупиняємо виконання, якщо дія провалилася, змінює стан, або явно вимагає цього
                        if execution_failed or is_state_changing or should_return_control:
                            break # Зупиняємо обробку подальших сегментів

                # Реконструюємо повідомлення асистента ЛИШЕ з оброблених сегментів
                reconstructed_message = self.parser.reconstruct(processed_segments)
                if reconstructed_message:
                    self.history.add_message("assistant", reconstructed_message)

                # Додаємо всі результати виконаних дій в історію
                if system_results:
                    for res in system_results:
                        self.history.add_message("system", res)
                    
                    # Визначаємо, чи продовжувати цикл
                    last_action_segment = next((s for s in reversed(processed_segments) if s.type == 'action'), None)
                    if last_action_segment:
                        last_command = last_action_segment.content
                        last_result_failed = self.last_action_status in ["failed", "error"]
                        should_return_control_to_user = last_command.get("return_control") is True
                        
                        # Продовжуємо цикл, якщо дія була успішною І не вимагала повернення контролю користувачу
                        if not last_result_failed and not should_return_control_to_user:
                            active_loop = True
                            current_query = "\n---\n".join(system_results)
                        else:
                            active_loop = False # Зупиняємось при помилці або за вимогою `return_control`
                    else:
                        active_loop = False
                else:
                    active_loop = False # Немає дій, немає циклу

            await self.history.check_and_summarize(self.ui)
        except asyncio.CancelledError:
            pass
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
            self.history = HistoryManager(self.chat, logger=self.log, max_tokens=self.settings.get("max_history_tokens", 4000))
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