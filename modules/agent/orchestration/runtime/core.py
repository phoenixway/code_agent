"""Оркестратор основного циклу."""

from __future__ import annotations

import asyncio
from dataclasses import dataclass

from ...allowed_actions_resolver import AllowedActionsResolver
from .action_policy import ActionPolicyHandler
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


class Orchestrator:
    def __init__(self, agent):
        self.agent = agent
        self.state = agent.state
        self.history = agent.history
        self.model = agent.model_client
        self.dispatcher = agent.action_dispatcher
        self.parser = agent.parser
        self.config = agent.config
        self.memory_board_store = getattr(agent, "memory_board_store", None)
        self.memory_board_engine = getattr(agent, "memory_board_engine", None)
        self.allowed_actions_resolver = getattr(agent, "allowed_actions_resolver", None) or AllowedActionsResolver()
        self.agent.allowed_actions_resolver = self.allowed_actions_resolver
        self.recovery_policy_resolver = getattr(agent, "recovery_policy_resolver", None) or RecoveryPolicyResolver(
            self.allowed_actions_resolver
        )
        self.agent.recovery_policy_resolver = self.recovery_policy_resolver

        self.intent_guard = IntentGuard()
        self.intent_response_parser = IntentResponseParser(getattr(agent, "log", None))
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
        self.dispatch_pipeline = DispatchPipeline(
            agent,
            self.dispatch_outcome,
        )
        self.turn_lifecycle = TurnLifecycle(agent)

    @property
    def ui(self):
        return self.agent.ui

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
            tools_prompt=self.agent.tool_manager.get_tools_prompt(),
            ctx_prompt=self.agent.context_manager.get_context_prompt(),
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
                if self.agent.log:
                    self.agent.log.warning("Failed to render terminal assistant text via print_message", exc_info=True)

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
                if self.agent.log:
                    self.agent.log.warning(
                        "Failed to render terminal assistant text via %s",
                        method_name,
                        exc_info=True,
                    )
                continue
        return False

    async def _flush_terminal_plaintext_completion_if_present(self) -> bool:
        terminal_text = str(getattr(self.state, "terminal_plaintext_completion_text", "") or "").strip()
        if not terminal_text:
            return False

        rendered = await self._render_final_assistant_text(terminal_text)
        if not rendered and self.agent.log:
            self.agent.log.warning("Terminal plaintext completion text was present but could not be rendered in UI.")

        try:
            setattr(self.state, "terminal_plaintext_completion_pending", False)
            setattr(self.state, "terminal_plaintext_completion_text", "")
        except Exception:
            pass
        return True


    def _finalize_intent_after_terminal_plaintext_completion_if_needed(self) -> None:
        if not bool(getattr(self.state, "pending_finalize_after_terminal_plaintext_completion", False)):
            return

        closer = getattr(self.state, "close_active_intent_as_resumable", None)
        if callable(closer):
            try:
                closer(
                    str(getattr(self.state, "pending_finalize_completion_reason", "forced_plaintext_completion") or "forced_plaintext_completion"),
                    clear_pending_stop=True,
                )
            except Exception:
                pass
        try:
            setattr(self.state, "pending_finalize_after_terminal_plaintext_completion", False)
            setattr(self.state, "pending_finalize_completion_reason", "")
            setattr(self.state, "pending_finalize_completion_source", "")
        except Exception:
            pass

    async def process(self, user_input, *, add_user_history: bool = True, user_history_meta: dict | None = None):
        """Головний цикл: Think -> Act -> Loop."""
        if self.agent.log:
            self.agent.log.info("Orchestrator.start")
            self.agent.log.debug(f"User input: {user_input[:300]}")

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
                    await self._flush_terminal_plaintext_completion_if_present()
                    self._finalize_intent_after_terminal_plaintext_completion_if_needed()
                    break
                if iteration.continue_loop:
                    continue

                if not iteration.proceed_to_dispatch:
                    break

                await self.dispatch_pipeline.run_iteration(ctx, iteration)

                if not ctx.active_loop:
                    await self._flush_terminal_plaintext_completion_if_present()
                    self._finalize_intent_after_terminal_plaintext_completion_if_needed()
                    break

            try:
                await self.history.check_and_summarize(self.ui, self.state)
            except Exception as exc:
                if self.agent.log:
                    self.agent.log.warning(f"Summarization error: {exc}")
        except asyncio.CancelledError:
            if self.agent.log:
                self.agent.log.info("Orchestrator interrupted by user.")
            closer = getattr(self.state, "close_active_intent_as_resumable", None)
            if callable(closer):
                try:
                    closer("user_requested_stop", clear_pending_stop=True)
                except Exception:
                    pass
        finally:
            if self.agent.log:
                total_elapsed = asyncio.get_running_loop().time() - ctx.session_started_at
                self.agent.log.info(
                    "Health.summary "
                    f"elapsed_sec={total_elapsed:.2f} "
                    f"history_tokens={self.history.current_token_count}/{self.history.max_tokens} "
                    f"confirmations={self.state.confirmation_count} "
                    f"session_tokens={self.state.session_tokens}"
                )
                self.agent.log.info("Orchestrator.finish")
            self.state.current_task = None
            await self.ui.stop_loading()
