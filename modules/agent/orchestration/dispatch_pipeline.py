"""Unified post-dispatch orchestration pipeline."""

from __future__ import annotations

import asyncio

from .responses.stage_logging import OrchestrationStageLogger


class DispatchPipeline:
    def __init__(self, agent, dispatch_outcome):
        self.agent = agent
        self.state = agent.state
        self.history = agent.history
        self.dispatcher = agent.action_dispatcher
        self.dispatch_outcome = dispatch_outcome
        self.stage_logger = OrchestrationStageLogger(getattr(agent, "log", None), self.state)

    @property
    def ui(self):
        return self.agent.ui

    async def _dispatch_segments(self, ctx, segments):
        if ctx.state_machine is not None:
            ctx.state_machine.intent_runtime = getattr(self.state, "intent_runtime", None)
        self.state.current_task = asyncio.create_task(
            self.dispatcher.dispatch_segments(segments, self.state)
        )
        return await self.state.current_task

    def _log_iteration_health(self, ctx, action_count: int):
        if self.agent.log:
            elapsed = asyncio.get_running_loop().time() - ctx.session_started_at
            self.agent.log.info(
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
