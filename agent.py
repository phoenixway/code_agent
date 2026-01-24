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
            policy=self.policy,
            history=self.history
        )
        
        # 6. Parser
        self.parser = ResponseParser()
        
        # 7. Loop Detection
        self.last_action_fingerprint = None
        self.last_action_status = None
        self.consecutive_failed_repeats = 0

        # 8. Token tracking
        self.session_tokens = 0

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

                # --- TOKEN CALCULATION & UI UPDATE ---
                try:
                    if self.ui and hasattr(self.ui, 'update_token_status'):
                        prompt_tokens = 0
                        completion_tokens = 0
                        tokenizer = self.chat.get_tokenizer()

                        if tokenizer:
                            prompt_tokens = len(tokenizer.encode(current_query))
                            completion_tokens = len(tokenizer.encode(response))
                        else:
                            # Fallback to character-based estimation
                            prompt_tokens = len(current_query) // 4
                            completion_tokens = len(response) // 4
                        
                        self.session_tokens += prompt_tokens + completion_tokens

                        self.log.info(f"Updating token status: history={self.history.current_token_count}, max={self.history.max_tokens}, session={self.session_tokens}")
                        await self.ui.update_token_status(
                            history_tokens=self.history.current_token_count,
                            max_tokens=self.history.max_tokens,
                            session_tokens=self.session_tokens
                        )
                except Exception as e:
                    self.log.error(f"Failed to update token status: {e}")
                # --- END TOKEN CALCULATION ---
                
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
                    if segment.type == 'thought':
                        await self.ui.print_thought(segment.content)
                        processed_segments.append(segment)
                    
                    elif segment.type == 'text':
                        await self.ui.print_message(segment.content, role="assistant")
                        processed_segments.append(segment)
                        
                    elif segment.type == 'action':
                        processed_segments.append(segment)
                        
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
                        elif cmd_name == 'read_file':
                            read_file_widget = await self.ui.print_read_file_start(command)
                            await self.ui.start_action(f"Reading {command.get('path', 'file')}...")
                            result = await self.processor.process_single_action(command)
                            await self.ui.update_read_file_result(read_file_widget, result)
                        elif cmd_name == 'edit_file':
                            edit_file_widget = await self.ui.print_edit_file_start(command)
                            await self.ui.start_action(f"Editing {command.get('path', 'file')}...")
                            result = await self.processor.process_single_action(command)
                            await self.ui.update_edit_file_result(edit_file_widget, result)
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

                        
                        # --- SMART STOP & TRUNCATION LOGIC ---
                        is_state_changing = any(op in cmd_name for op in STATE_CHANGING_OPS)
                        execution_failed = result.get("status") in ["failed", "error"]
                        action_denied = result.get("status") == "denied" # Assuming "denied" is the status for denied actions

                        if execution_failed:
                            output_text += "\n\n[SYSTEM INSTRUCTION: The action failed. Analyze this error in a <think> block to determine the root cause, then propose a corrected action.]"
                        elif action_denied: # New condition
                            output_text += "\n\n[SYSTEM INSTRUCTION: The user denied the action. Re-evaluate your plan and propose an alternative action or explanation.]"
                        
                        system_results.append(f"SYSTEM RESULT for `{cmd_name}`: {output_text}")
                        
                        # Stop processing further segments if the action failed, changed state, OR was denied
                        if execution_failed or is_state_changing or action_denied:
                            break

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
                        last_action_denied = self.last_action_status == "denied"

                        # After an error, control is immediately returned to the AI, allowing it to make corrections.
                        # The rest of the AI's message after the failed call is cut off.
                        if not last_action_denied:
                            active_loop = True
                            current_query = "\n---\n".join(system_results)
                        else:
                            active_loop = False  # Stop if the user denied the action
                    else:
                        active_loop = False
                else:
                    active_loop = False # Немає дій, немає циклу

            try:
                await self.history.check_and_summarize(self.ui)
            except Exception as e:
                self.log.warning(f"History summarization was skipped or failed: {e}")
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
            self.processor.history = self.history # Update processor with new history
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