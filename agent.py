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

class AngelicaAgent:
    def __init__(self, ui=None):
        self._ui = ui
        self.settings = load_settings()
        
        # Стан та запобіжники для TUI
        self.is_awaiting_model_selection = False 
        self.current_task = None
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
        
        # Ініціалізація розміру контексту з налаштувань
        initial_context_size = self.settings.get("context_size", "small")
        self.set_context_size(initial_context_size)

        # 5. Політика безпеки та Процесор дій
        policy_mode = self.settings.get("permission_policy", "ask")
        self.policy = PermissionPolicy(self._ui, policy_mode)
        
        self.processor = ResponseProcessor(
            ui=self._ui, 
            tool_manager=self.tool_manager, 
            chat=self.chat, 
            policy=self.policy
        )

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

    def _parse_output(self, text: str):
        """
        Надзвичайно стійкий парсер:
        1. Витягує роздуми з <think>.
        2. Шукає JSON від НАЙПЕРШОЇ '{' до НАЙОСТАННЬОЇ '}'.
        """
        thoughts = []
        command = None
        
        # 1. Витягуємо блок роздумів
        thought_match = re.search(r'<think>(.*?)</think>', text, re.DOTALL | re.IGNORECASE)
        if thought_match:
            thoughts.append(thought_match.group(1).strip())
            # Беремо все, що ПІСЛЯ блоку думок
            payload = text[thought_match.end():].strip()
        else:
            payload = text.strip()

        if not payload:
            return thoughts, None, ""

        # 2. ШУКАЄМО JSON: Жадібний пошук від першої { до останньої }
        # Це дозволяє ігнорувати сміття навколо і правильно збирати вкладені JSON
        json_match = re.search(r'(\{.*\})', payload, re.DOTALL)
        
        if json_match:
            json_str = json_match.group(1).strip()
            try:
                parsed = json.loads(json_str)
                # Якщо це словник і в ньому є ознаки команди
                if isinstance(parsed, dict) and any(k in parsed for k in ["type", "command", "action"]):
                    return thoughts, parsed, ""
            except json.JSONDecodeError as e:
                # Якщо JSON невалідний, логуємо помилку для відладки
                self.comm_log.error(f"JSON Parse Error: {e} | Content: {json_str}")
                # Якщо не вдалося розпарсити, вважаємо це текстом
                pass
        
        # 3. Якщо JSON не знайдено або він "битий" — повертаємо як текст
        return thoughts, None, payload

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
        """Головний цикл обробки вводу: Промпт -> ШІ -> Дія -> Результат -> ШІ."""
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
                thoughts, command, plain_text = self._parse_output(response)

                # Відображення думок в UI
                for thought in thoughts:
                    await self.ui.print_thought(thought)

                # ВИБІР: АБО Команда, АБО Текстова відповідь
                if command:
                    if command.get("before_execution"):
                        await self.ui.print_plan(command['before_execution'])
                    
                    await self.ui.start_action(command.get("during_execution", "Processing..."))
                    
                    # Виконання дії (тут може з'явитися MiniPicker)
                    result = await self.processor.process_single_action(command)
                    
                    if result.get("status") == "success" and command.get("after_execution"):
                        await self.ui.print_confirmation(command['after_execution'])
                    
                    # Друкуємо результат в історії
                    output_text = result.get('output', '')
                    cmd_name = command.get("type") or command.get("action") or "command"
                    await self.ui.print_command_result(output_text, command_name=cmd_name)

                    # Якщо ШІ потрібен результат для наступного кроку (loop)
                    if command.get("return_control") is True:
                        res_msg = f"SYSTEM RESULT: {output_text}"
                        self.history.add_message("system", res_msg)
                        current_query = res_msg # Передаємо результат на наступну ітерацію
                    else:
                        active_loop = False
                
                elif plain_text:
                    await self.ui.print_message(plain_text, role="assistant")
                    active_loop = False
                else:
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
    
    def set_context_size(self, size_name: str):
        """Встановлює розмір контекстного вікна."""
        CONTEXT_SIZES = {
            "small": 4096,
            "medium": 16384,
            "large": 32768
        }
        
        size_key = size_name.lower()
        if size_key not in CONTEXT_SIZES:
            # Fallback for unknown values
            token_limit = 4096
            size_key = "small"
        else:
            token_limit = CONTEXT_SIZES[size_key]
            
        # Update history manager if initialized
        if hasattr(self, 'history'):
            self.history.max_tokens = token_limit
            
        # Save current state (runtime only, doesn't persist to yaml unless we want to)
        self.context_size = size_key
        if self.ui:
            asyncio.create_task(self.ui.print_system(f"Context size set to {size_key.upper()} ({token_limit} tokens limit)"))

