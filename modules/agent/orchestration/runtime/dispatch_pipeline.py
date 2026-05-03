"""Unified post-dispatch orchestration pipeline."""

from __future__ import annotations

import asyncio

from ..responses.stage_logging import OrchestrationStageLogger
from ..shared.decision_models import ExecutionCommit
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

    def _build_execution_commit(self, execution_plan, processed_segs, sys_results, should_stop: bool):
        if execution_plan is None:
            return None

        committed_actions = 0
        for seg in processed_segs or []:
            if getattr(seg, "type", None) != "action":
                continue
            if isinstance(getattr(seg, "content", None), dict):
                committed_actions += 1

        return ExecutionCommit(
            shape=execution_plan.shape,
            transaction_kind=execution_plan.transaction_kind,
            state_effects=list(execution_plan.state_effects),
            action_effects=list(execution_plan.action_effects),
            output_effects=list(execution_plan.output_effects),
            bundle_validated=execution_plan.bundle_validated,
            transition_applied=execution_plan.transition_applied,
            action_dispatched=committed_actions > 0,
            active_intent_unchanged=execution_plan.active_intent_unchanged,
            before_active_intent_id=execution_plan.before_active_intent_id,
            after_active_intent_id=execution_plan.after_active_intent_id,
            committed_action_count=committed_actions,
            committed_system_result_count=len(sys_results or []),
            dispatch_stop_requested=bool(should_stop),
        )

    def _compact_execution_plan(self, execution_plan):
        if execution_plan is None:
            return None
        return {
            "shape": execution_plan.shape,
            "transaction_kind": execution_plan.transaction_kind,
            "bundle_validated": execution_plan.bundle_validated,
            "transition_applied": execution_plan.transition_applied,
            "action_dispatched": execution_plan.action_dispatched,
            "before_active_intent_id": execution_plan.before_active_intent_id,
            "after_active_intent_id": execution_plan.after_active_intent_id,
            "action_effects": list(execution_plan.action_effects),
        }

    def _compact_execution_commit(self, execution_commit):
        if execution_commit is None:
            return None
        return {
            "shape": execution_commit.shape,
            "transaction_kind": execution_commit.transaction_kind,
            "bundle_validated": execution_commit.bundle_validated,
            "transition_applied": execution_commit.transition_applied,
            "action_dispatched": execution_commit.action_dispatched,
            "before_active_intent_id": execution_commit.before_active_intent_id,
            "after_active_intent_id": execution_commit.after_active_intent_id,
            "committed_action_count": execution_commit.committed_action_count,
            "committed_system_result_count": execution_commit.committed_system_result_count,
            "dispatch_stop_requested": execution_commit.dispatch_stop_requested,
            "action_effects": list(execution_commit.action_effects),
        }

    async def run_iteration(self, ctx, iteration):
        self.stage_logger.log(
            "post_dispatch_pipeline",
            "start",
            action_count=iteration.parsed_action_count,
        )
        processed_segs, sys_results, should_stop = await self._dispatch_segments(ctx, iteration.segments)
        decision = await self.dispatch_outcome.handle(ctx, processed_segs, sys_results, should_stop)
        decision.execution_commit = self._build_execution_commit(
            getattr(iteration, "execution_plan", None),
            processed_segs,
            sys_results,
            should_stop,
        )
        self.stage_logger.log(
            "post_dispatch_pipeline",
            "continue" if decision.continue_loop else ("stop" if decision.stop_loop else "pass"),
            reason=decision.reason,
            source=decision.source,
            execution_plan=self._compact_execution_plan(getattr(iteration, "execution_plan", None)),
            execution_commit=self._compact_execution_commit(getattr(decision, "execution_commit", None)),
        )
        self._log_iteration_health(ctx, iteration.parsed_action_count)
        return decision
