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
from modules.memory_board_store import MemoryBoardStore
from modules.memory_board_engine import MemoryBoardEngine

# Імпорт підмодулів
from .config import AgentConfig
from .state_manager import AgentState
from .state_machine import AgentStateMachine
from .model_client import ModelClient
from .action_dispatcher import ActionDispatcher
from .orchestration import Orchestrator
from .planner import TaskBoardPlanner


class AngelicaAgent:
    def __init__(self, ui=None):
        self._ui = ui
        self.config = AgentConfig()
        self.state = AgentState(self.config)
        self.state.state_machine = AgentStateMachine(self.config)
        self.state.set_retry_budgets(
            self.config.RECOVERABLE_ERROR_RETRY_BUDGET,
            self.config.CRITICAL_ERROR_RETRY_BUDGET,
        )

        # Логування
        setup_loggers(clear_communication_log=True)
        self.comm_log = get_comm_logger()
        self.log = get_debug_logger()
        self.planner = TaskBoardPlanner(self.config, logger=self.log)

        # Основні модулі
        self.tool_manager = ToolManager()
        self.tool_manager.load_tools()

        self.files = FileModule()
        self.context_manager = ContextManager(self.files)

        # Підсистеми агента
        self.model_client = ModelClient(self.config, logger=self.log, comm_logger=self.comm_log)
        self.chat = self.model_client.chat  # Legacy alias

        self.history = HistoryManager(
            self.chat,
            logger=self.log,
            max_tokens=self.config.max_history_tokens,
            autosummarize_requires_confirmation=self.config.autosummarize_requires_confirmation,
        )
        self.memory_board_store = MemoryBoardStore(storage_path=".angelica/memory_board.json")
        self.memory_board_engine = MemoryBoardEngine(
            self.memory_board_store,
            logger=self.log,
        )
        if hasattr(self.history, "set_memory_board_store"):
            self.history.set_memory_board_store(self.memory_board_store)
        self.state.memory_board_store = self.memory_board_store
        self.state.memory_board_engine = self.memory_board_engine
        self.state.state_machine.history = self.history

        self.session_manager = SessionManager(
            self.history,
            self.context_manager,
            self._ui,
            state=self.state,
        )
        self.session_manager.load_session()

        self.policy = PermissionPolicy(self._ui, self.config.permission_policy)

        # Processor (поки що залишається зовнішнім, бо він використовується ActionDispatcher)
        self.processor = ResponseProcessor(
            ui=self._ui,
            tool_manager=self.tool_manager,
            chat=self.chat,
            policy=self.policy,
            history=self.history,
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
        if hasattr(self, "processor"):
            self.processor.ui = value
        if hasattr(self, "policy"):
            self.policy.ui = value
        if hasattr(self, "session_manager"):
            self.session_manager.ui = value
        if hasattr(self, "session_manager") and hasattr(self.session_manager, "_emit_load_notice"):
            self.session_manager._emit_load_notice()

        if hasattr(self, "action_dispatcher"):
            self.action_dispatcher.ui = value

    async def process_user_input(self, user_input):
        """Делегування до Orchestrator."""
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
            self.chat = self.model_client.chat
            self.processor.chat = self.chat
            self.history = HistoryManager(
                self.chat,
                logger=self.log,
                max_tokens=self.config.max_history_tokens,
                autosummarize_requires_confirmation=self.config.autosummarize_requires_confirmation,
            )
            self.processor.history = self.history
            self.session_manager.history = self.history
            if hasattr(self.orchestrator, "history"):
                self.orchestrator.history = self.history
            if hasattr(self.state, "state_machine") and self.state.state_machine is not None:
                self.state.state_machine.history = self.history

            # Re-apply user-configured history size after recreating HistoryManager.
            self.set_history_size(self.config.history_size)

    def _resolve_history_limit(self, size_value) -> tuple[int, str]:
        """Приймає і строкові пресети, і пряме числове значення токенів."""
        limits = {"small": 4096, "medium": 16384, "large": 32768}

        if isinstance(size_value, int):
            limit = max(256, size_value)
            return limit, f"custom:{limit}"

        if isinstance(size_value, str):
            raw = size_value.strip()
            if not raw:
                return 4096, "small"

            lowered = raw.lower()
            if lowered in limits:
                return limits[lowered], lowered

            if raw.isdigit():
                limit = max(256, int(raw))
                return limit, f"custom:{limit}"

        return 4096, "small"

    def set_history_size(self, size_name):
        """Встановлює ліміт історії. Підтримує preset name або прямий int."""
        limit, label = self._resolve_history_limit(size_name)

        if hasattr(self, "history"):
            self.history.max_tokens = limit

        if self.ui:
            display = label.upper() if not str(label).startswith("custom:") else label
            asyncio.create_task(
                self.ui.print_system(f"History limit: {display} ({limit} tokens)")
            )
