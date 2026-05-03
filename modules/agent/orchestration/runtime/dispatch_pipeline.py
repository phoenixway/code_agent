"""Unified post-dispatch orchestration pipeline."""

from __future__ import annotations

import asyncio

from ..responses.stage_logging import OrchestrationStageLogger
from .dependencies import RuntimeCollaborators


class DispatchPipeline:
    def __init__(self, agent, dispatch_outcome):
        self.agent = agent
        self.runtime = RuntimeCollaborators.from_agent(agent, needs_history=True, needs_dispatcher=True)
        self.state = self.runtime.state
        self.history = self.runtime.history
        self.dispatcher = self.runtime.dispatcher
        self.dispatch_outcome = dispatch_outcome
        self.stage_logger = OrchestrationStageLogger(self.runtime.logger, self.state)

    @property
    def ui(self):
        return getattr(self.agent, "ui", None)

    async def _dispatch_segments(self, ctx, segments):
        if ctx.state_machine is not None:
            ctx.state_machine.intent_runtime = getattr(self.state, "intent_runtime", None)
        self.state.current_task = asyncio.create_task(
            self.dispatcher.dispatch_segments(segments, self.state)
        )
        return await self.state.current_task

    def _log_iteration_health(self, ctx, action_count: int):
        if self.runtime.logger:
            elapsed = asyncio.get_running_loop().time() - ctx.session_started_at
            self.runtime.logger.info(
                "Health.iteration "
                f"step={ctx.consecutive_calls} "
                f"elapsed_sec={elapsed:.2f} "
                f"history_tokens={self.history.current_token_count}/{self.history.max_tokens} "
                f"actions_in_step={action_count} "
                f"batch_actions_executed={getattr(self.state, 'last_batch_actions_executed', 0)}/"
                f"{getattr(self.state, 'last_batch_actions_total', 0)} "
                f"same_action_streak={getattr(self.state, 'consecutive_same_action_count', 0)} "
                f"confirmations={self.state.confirmation_count} "
                f"session_tokens={self.state.session_tokens}"
            )

    async def run_iteration(self, ctx, iteration):
        self.stage_logger.log(
            "post_dispatch_pipeline",
            "start",
            action_count=iteration.parsed_action_count,
        )
        processed_segs, sys_results, should_stop = await self._dispatch_segments(ctx, iteration.segments)
        decision = await self.dispatch_outcome.handle(ctx, processed_segs, sys_results, should_stop)
        self.stage_logger.log(
            "post_dispatch_pipeline",
            "continue" if decision.continue_loop else ("stop" if decision.stop_loop else "pass"),
            reason=decision.reason,
            source=decision.source,
        )
        self._log_iteration_health(ctx, iteration.parsed_action_count)
        return decision
