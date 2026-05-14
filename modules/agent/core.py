"""Ядро агента - ініціалізація компонентів."""

import asyncio
from modules.agent.orchestration.runtime.core import Orchestrator
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
        reset_memory_board = getattr(self.memory_board_store, "reset_for_new_session", None)
        if callable(reset_memory_board):
            reset_memory_board()
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

        reset_turn_guards = getattr(self.state, "reset_turn_scoped_repeat_guards", None)
        if callable(reset_turn_guards):
            reset_turn_guards()

        return await self.orchestrator.process(user_input)

    def _build_resume_control_query(self) -> str:
        interruption = getattr(self.state, "last_technical_interruption", None)
        if interruption is None:
            return ""

        recent_intent_id = str(
            getattr(interruption, "resumable_intent_id", None)
            or getattr(self.state, "last_resumable_intent_id", "")
            or ""
        ).strip()
        completion_reason = str(
            getattr(self.state, "last_resumable_intent_completion_reason", "")
            or getattr(self.state, "last_resumable_completion_reason", "")
            or ""
        ).strip()
        pending_query = str(getattr(self.state, "pending_resume_query", "") or "").strip()
        interruption_message = str(getattr(interruption, "message", "") or "Technical interruption").strip()

        lines = [
            "SYSTEM: Resume the interrupted work from the last safe state.",
            "This interruption was technical, not a successful completion.",
            "Do NOT restart from zero.",
        ]
        if recent_intent_id:
            lines.extend([
                f"Most recent resumable intent_id: {recent_intent_id}",
                "Reuse the same intent lineage if the work is the same.",
            ])
            if completion_reason in {"technical_interruption", "step_timeout", "exhausted_resumable"}:
                lines.append(
                    f"If no active contract exists, emit EXACTLY ONE <intent> JSON block with mode=\"reuse\" for intent_id {recent_intent_id} before any further action."
                )
        if interruption_message:
            lines.append(f"Technical interruption: {interruption_message}")
        if pending_query:
            lines.append("Resume target:")
            lines.append(pending_query)
        return "\n".join(lines)

    async def resume_interrupted_work(self) -> bool:
        if self.orchestrator.ui is None and self._ui is not None:
            self.orchestrator.ui = self._ui

        resume_query = self._build_resume_control_query()
        if not resume_query:
            if self.ui:
                await self.ui.print_system("No resumable interrupted work is available.")
            return False

        await self.orchestrator.process(
            resume_query,
            add_user_history=False,
            user_history_meta={"type": "control_resume"},
        )
        return True

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
