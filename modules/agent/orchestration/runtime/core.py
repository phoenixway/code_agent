"""Оркестратор основного циклу."""

from __future__ import annotations

import asyncio
from dataclasses import dataclass

from ...allowed_actions_resolver import AllowedActionsResolver
from .action_policy import ActionPolicyHandler
from .core_state import OrchestratorCoreStateAdapter
from .dispatch_pipeline import DispatchPipeline
from .dispatch_outcome import DispatchOutcomeHandler
from .lifecycle import TurnLifecycle
from .loop_gate import LoopGateHandler
from .memory_board_stage import MemoryBoardStageHandler
from .plan_board_stage import PlanBoardStageHandler
from .policy import IntentGuard
from .recovery import RecoveryCoordinator
from ..parsers import IntentResponseParser
from ..prompts import OrchestratorPromptBuilder
from ..responses import ModelOutputRecoveryHandler, ModelResponsePipeline
from ..shared.recovery_policy import RecoveryPolicyResolver
from ..transitions import IntentTransitionHandler
from .pipeline import OrchestrationPipeline


@dataclass
class LoopContext:
    user_input: str
    tools_prompt: str
    ctx_prompt: str
    state_machine: object
    current_query: str
    consecutive_calls: int
    malformed_action_retries: int
    audit_marker_retries: int
    active_loop: bool
    session_started_at: float


@dataclass(frozen=True)
class OrchestratorDependencies:
    state: object
    history: object
    model: object
    dispatcher: object
    parser: object
    config: object
    log: object
    tool_manager: object
    context_manager: object
    allowed_actions_resolver: object
    recovery_policy_resolver: object


class _EmptyToolManager:
    def get_tools_prompt(self) -> str:
        return ""


class _EmptyContextManager:
    def get_context_prompt(self) -> str:
        return ""


class Orchestrator:
    def __init__(self, agent):
        self.agent = agent
        self.dependencies = self._resolve_dependencies(agent)
        self.state = self.dependencies.state
        self.history = self.dependencies.history
        self.model = self.dependencies.model
        self.dispatcher = self.dependencies.dispatcher
        self.parser = self.dependencies.parser
        self.config = self.dependencies.config
        self.log = self.dependencies.log
        self.allowed_actions_resolver = self.dependencies.allowed_actions_resolver
        self.recovery_policy_resolver = self.dependencies.recovery_policy_resolver
        self.memory_board_store = getattr(agent, "memory_board_store", None)
        self.memory_board_engine = getattr(agent, "memory_board_engine", None)
        self.state_view = OrchestratorCoreStateAdapter(self.state)

        self._build_runtime_components(agent)

    def _resolve_dependencies(self, agent) -> OrchestratorDependencies:
        allowed_actions_resolver = getattr(agent, "allowed_actions_resolver", None) or AllowedActionsResolver()
        recovery_policy_resolver = getattr(agent, "recovery_policy_resolver", None) or RecoveryPolicyResolver(
            allowed_actions_resolver
        )
        agent.allowed_actions_resolver = allowed_actions_resolver
        agent.recovery_policy_resolver = recovery_policy_resolver
        return OrchestratorDependencies(
            state=agent.state,
            history=agent.history,
            model=agent.model_client,
            dispatcher=agent.action_dispatcher,
            parser=agent.parser,
            config=agent.config,
            log=getattr(agent, "log", None),
            tool_manager=getattr(agent, "tool_manager", None) or _EmptyToolManager(),
            context_manager=getattr(agent, "context_manager", None) or _EmptyContextManager(),
            allowed_actions_resolver=allowed_actions_resolver,
            recovery_policy_resolver=recovery_policy_resolver,
        )

    def _build_runtime_components(self, agent) -> None:
        self.intent_guard = IntentGuard()
        self.intent_response_parser = IntentResponseParser(self.log)
        self.prompt_builder = OrchestratorPromptBuilder(agent)
        self.output_recovery = ModelOutputRecoveryHandler(agent, self.prompt_builder)
        self.recovery = RecoveryCoordinator(agent, self.prompt_builder)
        self.intent_transitions = IntentTransitionHandler(agent, self.prompt_builder, self.recovery)
        self.action_policy = ActionPolicyHandler(agent, self.intent_guard, self.prompt_builder)
        self.loop_gate = LoopGateHandler(agent)
        self.plan_board_stage = PlanBoardStageHandler(agent, self.prompt_builder)
        self.memory_board_stage = MemoryBoardStageHandler(agent, self.prompt_builder)
        self.dispatch_outcome = DispatchOutcomeHandler(agent, self.parser, self.recovery)
        self.response_pipeline = ModelResponsePipeline(
            agent,
            self.parser,
            self.intent_response_parser,
            self.prompt_builder,
            self.intent_transitions,
            self.output_recovery,
            self.action_policy,
            self.plan_board_stage,
            self.memory_board_stage,
        )
        self.pipeline = OrchestrationPipeline(
            agent,
            self.prompt_builder,
            self.intent_response_parser,
            self.loop_gate,
            self.response_pipeline,
        )
        self.dispatch_pipeline = DispatchPipeline(agent, self.dispatch_outcome)
        self.turn_lifecycle = TurnLifecycle(agent)

    @property
    def ui(self):
        return self.agent.ui

    @ui.setter
    def ui(self, value):
        self.agent.ui = value

    @property
    def logger(self):
        return getattr(self, "log", getattr(self.agent, "log", None))

    @property
    def core_state(self) -> OrchestratorCoreStateAdapter:
        state_view = getattr(self, "state_view", None)
        if state_view is None:
            state_view = OrchestratorCoreStateAdapter(self.state)
            self.state_view = state_view
        return state_view

    def _start_turn(self, user_input: str, *, add_user_history: bool = True, user_history_meta: dict | None = None):
        return self.turn_lifecycle.start_turn(
            user_input,
            add_user_history=add_user_history,
            user_history_meta=user_history_meta,
        )

    def _create_loop_context(self, user_input: str, *, add_user_history: bool = True, user_history_meta: dict | None = None) -> LoopContext:
        loop = asyncio.get_running_loop()
        return LoopContext(
            user_input=user_input,
            tools_prompt=self.dependencies.tool_manager.get_tools_prompt(),
            ctx_prompt=self.dependencies.context_manager.get_context_prompt(),
            state_machine=self._start_turn(
                user_input,
                add_user_history=add_user_history,
                user_history_meta=user_history_meta,
            ),
            current_query=user_input,
            consecutive_calls=0,
            malformed_action_retries=0,
            audit_marker_retries=0,
            active_loop=True,
            session_started_at=loop.time(),
        )

    async def _render_final_assistant_text(self, text: str) -> bool:
        rendered = str(text or "").strip()
        if not rendered:
            return False

        ui = self.ui

        print_message = getattr(ui, "print_message", None)
        if callable(print_message):
            try:
                await print_message(rendered, role="assistant")
                return True
            except Exception:
                if self.logger:
                    self.logger.warning("Failed to render terminal assistant text via print_message", exc_info=True)

        candidate_calls = [
            ("print_assistant", (rendered,), {}),
            ("print_ai", (rendered,), {}),
            ("add_chat_message", (), {"role": "assistant", "text": rendered}),
            ("add_chat_message", ("assistant", rendered), {}),
            ("print_markdown", (rendered,), {}),
            ("print_system", (rendered,), {}),
        ]
        for method_name, args, kwargs in candidate_calls:
            method = getattr(ui, method_name, None)
            if not callable(method):
                continue
            try:
                await method(*args, **kwargs)
                return True
            except TypeError:
                continue
            except Exception:
                if self.logger:
                    self.logger.warning(
                        "Failed to render terminal assistant text via %s",
                        method_name,
                        exc_info=True,
                    )
                continue
        return False

    async def _flush_terminal_plaintext_completion_if_present(self) -> bool:
        terminal_text = self.core_state.terminal_plaintext_completion_text()
        if not terminal_text:
            return False

        rendered = await self._render_final_assistant_text(terminal_text)
        if not rendered and self.logger:
            self.logger.warning("Terminal plaintext completion text was present but could not be rendered in UI.")

        self.core_state.clear_terminal_plaintext_completion()
        return True


    def _finalize_intent_after_terminal_plaintext_completion_if_needed(self) -> None:
        if not self.core_state.pending_finalize_after_terminal_plaintext_completion():
            return

        self.core_state.close_active_intent_as_resumable(
            self.core_state.pending_finalize_completion_reason(),
            clear_pending_stop=True,
        )
        self.core_state.clear_pending_finalize_after_terminal_plaintext_completion()

    async def _complete_terminal_plaintext_if_needed(self) -> None:
        await self._flush_terminal_plaintext_completion_if_present()
        self._finalize_intent_after_terminal_plaintext_completion_if_needed()

    async def _stop_ui_loading_if_present(self) -> None:
        ui = self.ui
        stop_loading = getattr(ui, "stop_loading", None)
        if callable(stop_loading):
            await stop_loading()

    async def process(self, user_input, *, add_user_history: bool = True, user_history_meta: dict | None = None):
        """Головний цикл: Think -> Act -> Loop."""
        if self.logger:
            self.logger.info("Orchestrator.start")
            self.logger.debug(f"User input: {user_input[:300]}")

        try:
            ctx = self._create_loop_context(
                user_input,
                add_user_history=add_user_history,
                user_history_meta=user_history_meta,
            )
        except TypeError:
            ctx = self._create_loop_context(user_input)

        try:
            while ctx.active_loop:
                iteration = await self.pipeline.run_iteration(ctx)
                if iteration.stop_loop:
                    await self._complete_terminal_plaintext_if_needed()
                    break
                if iteration.continue_loop:
                    continue

                if not iteration.proceed_to_dispatch:
                    break

                await self.dispatch_pipeline.run_iteration(ctx, iteration)

                if not ctx.active_loop:
                    await self._complete_terminal_plaintext_if_needed()
                    break

            try:
                await self.history.check_and_summarize(self.ui, self.state)
            except Exception as exc:
                if self.logger:
                    self.logger.warning(f"Summarization error: {exc}")
        except asyncio.CancelledError:
            if self.logger:
                self.logger.info("Orchestrator interrupted by user.")
            self.core_state.close_active_intent_as_resumable("user_requested_stop", clear_pending_stop=True)
        finally:
            if self.logger:
                total_elapsed = asyncio.get_running_loop().time() - ctx.session_started_at
                self.logger.info(
                    "Health.summary "
                    f"elapsed_sec={total_elapsed:.2f} "
                    f"history_tokens={self.history.current_token_count}/{self.history.max_tokens} "
                    f"confirmations={self.state.confirmation_count} "
                    f"session_tokens={self.state.session_tokens}"
                )
                self.logger.info("Orchestrator.finish")
            self.state.current_task = None
            await self._stop_ui_loading_if_present()
