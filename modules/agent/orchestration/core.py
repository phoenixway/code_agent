"""Оркестратор основного циклу."""

from __future__ import annotations

import asyncio
from dataclasses import dataclass

from ..allowed_actions_resolver import AllowedActionsResolver
from .action_policy import ActionPolicyHandler
from .dispatch_pipeline import DispatchPipeline
from .dispatch_outcome import DispatchOutcomeHandler
from .intent_transitions import IntentTransitionHandler
from .lifecycle import TurnLifecycle
from .loop_gate import LoopGateHandler
from .memory_board_stage import MemoryBoardStageHandler
from .output_recovery import ModelOutputRecoveryHandler
from .parsing import IntentResponseParser
from .policy import IntentGuard
from .prompting import OrchestratorPromptBuilder
from .pipeline import OrchestrationPipeline
from .recovery_policy import RecoveryPolicyResolver
from .recovery import RecoveryCoordinator
from .response_pipeline import ModelResponsePipeline


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

    def _start_turn(self, user_input: str):
        return self.turn_lifecycle.start_turn(user_input)

    def _create_loop_context(self, user_input: str) -> LoopContext:
        loop = asyncio.get_running_loop()
        return LoopContext(
            user_input=user_input,
            tools_prompt=self.agent.tool_manager.get_tools_prompt(),
            ctx_prompt=self.agent.context_manager.get_context_prompt(),
            state_machine=self._start_turn(user_input),
            current_query=user_input,
            consecutive_calls=0,
            malformed_action_retries=0,
            audit_marker_retries=0,
            active_loop=True,
            session_started_at=loop.time(),
        )

    async def process(self, user_input):
        """Головний цикл: Think -> Act -> Loop."""
        if self.agent.log:
            self.agent.log.info("Orchestrator.start")
            self.agent.log.debug(f"User input: {user_input[:300]}")

        ctx = self._create_loop_context(user_input)

        try:
            while ctx.active_loop:
                iteration = await self.pipeline.run_iteration(ctx)
                if iteration.stop_loop:
                    break
                if iteration.continue_loop:
                    continue

                if not iteration.proceed_to_dispatch:
                    break

                await self.dispatch_pipeline.run_iteration(ctx, iteration)

            try:
                await self.history.check_and_summarize(self.ui, self.state)
            except Exception as exc:
                if self.agent.log:
                    self.agent.log.warning(f"Summarization error: {exc}")
        except asyncio.CancelledError:
            if self.agent.log:
                self.agent.log.info("Orchestrator interrupted by user.")
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