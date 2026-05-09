"""Unified post-dispatch orchestration pipeline."""

from __future__ import annotations

import asyncio
from dataclasses import dataclass

from ..responses.stage_logging import OrchestrationStageLogger
from ..shared.decision_models import ExecutionCommit
from ..shared.trace import compact_execution_commit, compact_execution_plan
from .dependencies import RuntimeCollaborators
from .execution_commit_observer import ExecutionCommitObserverAdapter


@dataclass(frozen=True)
class PlanDispatchCandidate:
    action_type: str
    payload: dict
    action_summary: str
    source: str
    matched_segment_index: int
    compiler_shape: str = ""
    transaction_kind: str = ""
    pre_action_text: str | None = None


class DispatchPipeline:
    def __init__(self, agent, dispatch_outcome):
        self.agent = agent
        self.runtime = RuntimeCollaborators.from_agent(agent, needs_history=True, needs_dispatcher=True)
        self.state = self.runtime.state
        self.history = self.runtime.history
        self.dispatcher = self.runtime.dispatcher
        self.dispatch_outcome = dispatch_outcome
        self.execution_commit_observer = ExecutionCommitObserverAdapter(self.state)
        self.stage_logger = OrchestrationStageLogger(self.runtime.logger, self.state)

    @property
    def ui(self):
        return getattr(self.agent, "ui", None)

    def _dispatch_equivalent_action_summary(self, payload: dict | None, *, action_type: str = "") -> str:
        action_kind = str(
            action_type
            or (payload or {}).get("type")
            or (payload or {}).get("action")
            or ""
        ).strip()
        target = ""
        if isinstance(payload, dict):
            target = str(payload.get("path") or payload.get("command") or "").strip()
        summary = action_kind or "action"
        if target:
            summary = f"{summary}:{target}"
        return summary

    def _build_single_action_plan_dispatch_candidate(self, iteration):
        execution_plan = getattr(iteration, "execution_plan", None)
        if execution_plan is None:
            return None, "no_execution_plan"

        parsed_output = getattr(iteration, "parsed_output", None)
        compiler_ir = getattr(parsed_output, "compiler_ir", None)
        if compiler_ir is None:
            return None, "no_compiler_ir"

        action_ops = list(getattr(compiler_ir, "action_ops", ()) or ())
        if len(action_ops) != 1:
            return None, "ir_action_count_not_one"

        action_op = action_ops[0]
        payload = getattr(action_op, "payload", None)
        if not isinstance(payload, dict):
            return None, "unsupported_action_shape"
        if isinstance(getattr(action_op, "file_content", None), str):
            return None, "unsupported_action_shape"

        segments = getattr(iteration, "segments", None) or []
        action_segments = [
            (idx, seg)
            for idx, seg in enumerate(segments)
            if getattr(seg, "type", None) == "action" and isinstance(getattr(seg, "content", None), dict)
        ]
        if len(action_segments) != 1:
            return None, "no_matching_segment_action"

        matched_segment_index, matched_segment = action_segments[0]
        segment_payload = dict(getattr(matched_segment, "content", None) or {})
        payload_copy = dict(payload)
        if segment_payload != payload_copy:
            return None, "payload_mismatch"

        action_type = str(getattr(action_op, "action_type", "") or payload_copy.get("type") or payload_copy.get("action") or "").strip()
        payload_action_type = str(payload_copy.get("type") or payload_copy.get("action") or "").strip()
        if action_type and payload_action_type and action_type != payload_action_type:
            return None, "unsupported_action_shape"

        expected_summary = self._dispatch_equivalent_action_summary(
            payload_copy,
            action_type=action_type,
        )
        plan_effects = list(getattr(execution_plan, "action_effects", []) or [])
        if len(plan_effects) != 1 or plan_effects[0] != expected_summary:
            return None, "action_effect_mismatch"

        pre_action_text = None
        if bool(getattr(compiler_ir, "has_pre_action_text", False)):
            raw_pre_action_text = str(getattr(compiler_ir, "pre_action_text", "") or "")
            pre_action_text = raw_pre_action_text or None

        return PlanDispatchCandidate(
            action_type=action_type or payload_action_type,
            payload=payload_copy,
            action_summary=expected_summary,
            source="compiler_ir",
            matched_segment_index=matched_segment_index,
            compiler_shape=str(getattr(parsed_output, "compiler_shape", "") or ""),
            transaction_kind=str(getattr(execution_plan, "transaction_kind", "") or ""),
            pre_action_text=pre_action_text,
        ), "single_action_ir_candidate"

    def _single_action_plan_parity_probe(self, iteration):
        candidate, reason = self._build_single_action_plan_dispatch_candidate(iteration)
        if candidate is None:
            return None, reason, None
        segments = getattr(iteration, "segments", None) or []
        return segments, "single_action_ir_parity", candidate

    def _resolve_dispatch_segments(self, iteration):
        bridged_segments, bridge_reason, candidate = self._single_action_plan_parity_probe(iteration)
        if bridged_segments is not None:
            return bridged_segments, True, bridge_reason, candidate
        return getattr(iteration, "segments", None) or [], False, bridge_reason, None

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

    async def run_iteration(self, ctx, iteration):
        execution_plan = getattr(iteration, "execution_plan", None)
        dispatch_segments, bridge_used, bridge_reason, bridge_candidate = self._resolve_dispatch_segments(iteration)
        pre_action_text_emitted = False
        pre_action_text_chars = 0
        ui = getattr(self, "ui", None)
        if execution_plan and ui:
            for effect in execution_plan.output_effects:
                if isinstance(effect, str) and effect.startswith("pre_action_text:"):
                    text_to_print = effect.split(":", 1)[1]
                    if text_to_print:
                        await ui.print_message(text_to_print, role="assistant")
                        pre_action_text_emitted = True
                        pre_action_text_chars = len(text_to_print)
                        break

        self.stage_logger.log(
            "post_dispatch_pipeline",
            "start",
            action_count=iteration.parsed_action_count,
            pre_action_text_emitted=pre_action_text_emitted,
            pre_action_text_chars=pre_action_text_chars,
            dispatch_bridge_used=bridge_used,
            dispatch_bridge_reason=bridge_reason,
            dispatch_bridge_candidate=(
                {
                    "action_type": bridge_candidate.action_type,
                    "action_summary": bridge_candidate.action_summary,
                    "source": bridge_candidate.source,
                    "matched_segment_index": bridge_candidate.matched_segment_index,
                    "compiler_shape": bridge_candidate.compiler_shape,
                    "transaction_kind": bridge_candidate.transaction_kind,
                    "pre_action_text": bridge_candidate.pre_action_text or "",
                }
                if bridge_candidate is not None
                else None
            ),
        )
        processed_segs, sys_results, should_stop = await self._dispatch_segments(ctx, dispatch_segments)
        decision = await self.dispatch_outcome.handle(ctx, processed_segs, sys_results, should_stop)
        decision.execution_commit = self._build_execution_commit(
            getattr(iteration, "execution_plan", None),
            processed_segs,
            sys_results,
            should_stop,
        )
        self.execution_commit_observer.observe_execution_commit(
            getattr(iteration, "execution_plan", None),
            getattr(decision, "execution_commit", None),
            sys_results=sys_results,
        )
        self.stage_logger.log(
            "post_dispatch_pipeline",
            "continue" if decision.continue_loop else ("stop" if decision.stop_loop else "pass"),
            reason=decision.reason,
            source=decision.source,
            execution_plan=compact_execution_plan(getattr(iteration, "execution_plan", None)),
            execution_commit=compact_execution_commit(getattr(decision, "execution_commit", None)),
        )
        self._log_iteration_health(ctx, iteration.parsed_action_count)
        return decision
