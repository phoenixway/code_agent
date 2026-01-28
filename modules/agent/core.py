"""Ядро агента - ініціалізація компонентів."""

import asyncio
from modules.tools.manager import ToolManager
from modules.context import ContextManager
from modules.history import HistoryManager
from modules.session import SessionManager
from modules.processor import ResponseProcessor
from modules.policy import PermissionPolicy
from modules.parser import ResponseParser
from modules.logger import setup_loggers, get_comm_logger, get_debug_logger
from modules.files import FileModule

# Імпорт підмодулів
from .config import AgentConfig
from .state_manager import AgentState
from .model_client import ModelClient
from .action_dispatcher import ActionDispatcher
from .orchestrator import Orchestrator

class AngelicaAgent:
    def __init__(self, ui=None):
        self._ui = ui
        self.config = AgentConfig()
        self.state = AgentState()
        
        # Логування
        setup_loggers(clear_communication_log=True)
        self.comm_log = get_comm_logger()
        self.log = get_debug_logger()
        
        # Основні модулі
        self.tool_manager = ToolManager()
        self.tool_manager.load_tools()
        
        self.files = FileModule()
        self.context_manager = ContextManager(self.files)
        
        # Підсистеми агента
        self.model_client = ModelClient(self.config, logger=self.log, comm_logger=self.comm_log)
        self.chat = self.model_client.chat # Legacy alias
        
        self.history = HistoryManager(
            self.chat, 
            logger=self.log, 
            max_tokens=self.config.max_history_tokens
        )
        
        self.session_manager = SessionManager(self.history, self.context_manager, self._ui)
        self.session_manager.load_session()
        
        self.policy = PermissionPolicy(self._ui, self.config.permission_policy)
        
        # Processor (поки що залишається зовнішнім, бо він використовується ActionDispatcher)
        self.processor = ResponseProcessor(
            ui=self._ui,
            tool_manager=self.tool_manager,
            chat=self.chat,
            policy=self.policy,
            history=self.history
        )
        
        self.parser = ResponseParser()
        
        # Нові модулі
        self.action_dispatcher = ActionDispatcher(self)
        self.orchestrator = Orchestrator(self)
        
        self.set_history_size(self.config.history_size)

    @property
    def ui(self):
        return self._ui

    @ui.setter
    def ui(self, value):
        """Синхронізує посилання на UI у всіх залежних модулях."""
        self._ui = value
        # Legacy modules
        if hasattr(self, 'processor'): self.processor.ui = value
        if hasattr(self, 'policy'): self.policy.ui = value
        if hasattr(self, 'session_manager'): self.session_manager.ui = value
        
        # New modular architecture FIX
        if hasattr(self, 'orchestrator'): self.orchestrator.ui = value
        if hasattr(self, 'action_dispatcher'): self.action_dispatcher.ui = value
        # Model client зазвичай не потребує прямого посилання на UI, але для switch_model може знадобитись,
        # проте switch_model отримує ui як аргумент.

    async def process_user_input(self, user_input):
        """Делегування до Orchestrator."""
        # Безпосередньо перед виконанням переконаємось, що оркестратор має UI
        if self.orchestrator.ui is None and self._ui is not None:
             self.orchestrator.ui = self._ui
             
        return await self.orchestrator.process(user_input)

    async def interrupt(self):
        """Переривання задач."""
        if self.state.current_task and not self.state.current_task.done():
            self.state.current_task.cancel()
            if self.ui:
                await self.ui.print_system("🛑 Операцію перервано.")

    async def switch_model(self, model_name: str):
        success = await self.model_client.switch_model(model_name, self.ui)
        if success:
            # Оновлюємо залежності, якщо модель змінилась
            self.chat = self.model_client.chat
            self.processor.chat = self.chat
            # Перестворюємо історію з новим токенізатором (зберігаючи налаштування)
            self.history = HistoryManager(
                self.chat, 
                logger=self.log, 
                max_tokens=self.config.max_history_tokens
            )
            # Важливо оновити посилання в інших модулях
            self.processor.history = self.history
            self.session_manager.history = self.history
            if hasattr(self.orchestrator, 'history'): self.orchestrator.history = self.history

    def set_history_size(self, size_name: str):
        """Встановлює ліміт історії."""
        limits = {"small": 4096, "medium": 16384, "large": 32768}
        limit = limits.get(size_name.lower(), 4096)
        
        if hasattr(self, 'history'):
            self.history.max_tokens = limit
            
        if self.ui:
            asyncio.create_task(self.ui.print_system(f"History limit: {size_name.upper()} ({limit} tokens)"))
