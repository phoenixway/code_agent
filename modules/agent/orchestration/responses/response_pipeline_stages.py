"""Execution stages for the pre-dispatch response pipeline."""

from __future__ import annotations

from dataclasses import dataclass

from ..shared.decision_models import ExecutionPlan
from ..shared.decision_models import ResponsePipelineOutcome
from ..shared.trace import compact_compiler_replay
from .board_checkpoint_semantics import build_board_checkpoint_semantic_result
from .board_checkpoint_semantics import checkpoint_outcome_category
from .board_checkpoint_semantics import resolve_legacy_derived_checkpoint_effective_flags
from .board_checkpoint_semantics import resolve_memory_checkpoint_and_action_typed_primary
from .board_checkpoint_semantics import resolve_memory_checkpoint_and_text_typed_primary
from .board_checkpoint_semantics import resolve_memory_checkpoint_only_typed_primary
from ..config.switch_registry import get_switch
from .board_checkpoint_semantics import resolve_plan_checkpoint_and_action_authority
from .board_checkpoint_semantics import resolve_plan_checkpoint_and_text_authority
from .board_checkpoint_semantics import resolve_plan_checkpoint_only_authority
from .board_checkpoint_semantics import resolve_plan_checkpoint_only_typed_primary
from .memory_commit_authority import (
    resolve_memory_checkpoint_only_commit_authority,
    resolve_memory_checkpoint_with_text_commit_authority,
)
from .protocol_decision_bridge import compiler_invalid_kind_for_output, resolve_protocol_authority
from .semantic_accessors import is_leaked_system_result
from .terminal_answer_authority import (
    resolve_checkpoint_only_terminal_authority,
    resolve_plaintext_terminal_answer_authority,
)
from .recovery_authority import (
    resolve_invalid_truncated_terminal_text_recovery_authority,
    resolve_leaked_system_result_recovery_authority,
)
from .terminal_answer_models import TerminalAnswerKind
from ..parsers.visible_text import terminal_plaintext_completion_status


@dataclass
class CheckpointStageState:
    response: str
    reflection_repair_pending: bool
    reflection_repair_kind: str
    plan_checkpoint_only: bool
    plan_checkpoint_and_text: bool
    plan_checkpoint_and_action: bool
    memory_checkpoint_only: bool
    memory_checkpoint_and_text: bool
    memory_checkpoint_and_action: bool
    memory_board_decision: object
    compiler_analysis: object | None = None
    board_checkpoint_semantic_result: object | None = None


@dataclass
class ClassifiedStageState:
    response: str
    parsed_output: object
    segments: list
    parsed_action_count: int
    checkpoint_has_think: bool
    checkpoint_has_marker: bool
    checkpoint_has_tags: bool
    checkpoint_has_board_commit: bool
    checkpoint_satisfied: bool


class ResponsePipelineStagesMixin:
    def _checkpoint_outcome_category(self, *, checkpoint_only: bool, checkpoint_and_text: bool, checkpoint_and_action: bool) -> str:
        return checkpoint_outcome_category(
            checkpoint_only=checkpoint_only,
            checkpoint_and_text=checkpoint_and_text,
            checkpoint_and_action=checkpoint_and_action,
        )

    def _log_board_checkpoint_structural_parity(
        self,
        compiler_analysis,
        *,
        plan_checkpoint_only: bool,
        plan_checkpoint_and_text: bool,
        plan_checkpoint_and_action: bool,
        memory_checkpoint_only: bool,
        memory_checkpoint_and_text: bool,
        memory_checkpoint_and_action: bool,
    ) -> None:
        stage_logger = getattr(self, "stage_logger", None)
        if not stage_logger:
            return

        try:
            ir = getattr(compiler_analysis, "ir", None) if compiler_analysis is not None else None
            compiler_shape = str(getattr(getattr(compiler_analysis, "shape", None), "name", "") or "")
            compiler_error_code = str(getattr(getattr(compiler_analysis, "error", None), "code", "") or "")
            compiler_recovery_id = str(getattr(getattr(compiler_analysis, "error", None), "recovery_id", "") or "")
            compiler_visible_text_source = str(getattr(ir, "visible_text_source", "") or "")
            compiler_has_action = bool(getattr(ir, "has_action", False))
            compiler_action_count = int(getattr(ir, "action_count", 0) or 0)
            compiler_has_checkpoint = bool(getattr(ir, "has_checkpoint", False))
            compiler_has_memory_tags = bool(getattr(ir, "has_memory_tags", False))
            compiler_has_subgoal_tags = bool(getattr(ir, "has_subgoal_tags", False))
            compiler_has_memory_checkpoint = bool(getattr(ir, "has_memory_checkpoint", False))
            compiler_has_visible_answer = bool(getattr(ir, "has_visible_answer", False))
            compiler_has_pre_action_text = bool(getattr(ir, "has_pre_action_text", False))

            plan_category = self._checkpoint_outcome_category(
                checkpoint_only=plan_checkpoint_only,
                checkpoint_and_text=plan_checkpoint_and_text,
                checkpoint_and_action=plan_checkpoint_and_action,
            )
            memory_category = self._checkpoint_outcome_category(
                checkpoint_only=memory_checkpoint_only,
                checkpoint_and_text=memory_checkpoint_and_text,
                checkpoint_and_action=memory_checkpoint_and_action,
            )

            legacy_has_checkpoint = any(
                (
                    plan_checkpoint_only,
                    plan_checkpoint_and_text,
                    plan_checkpoint_and_action,
                    memory_checkpoint_only,
                    memory_checkpoint_and_text,
                    memory_checkpoint_and_action,
                )
            )
            legacy_checkpoint_with_action = bool(plan_checkpoint_and_action or memory_checkpoint_and_action)
            legacy_checkpoint_with_text = bool(plan_checkpoint_and_text or memory_checkpoint_and_text)
            legacy_checkpoint_only = bool(plan_checkpoint_only or memory_checkpoint_only)

            parity_available = compiler_analysis is not None and ir is not None
            aligned = False
            mismatch_reason = ""
            if not parity_available:
                mismatch_reason = "compiler_analysis_unavailable"
            elif compiler_error_code:
                mismatch_reason = "compiler_invalid_prepass"
            elif legacy_has_checkpoint != compiler_has_checkpoint:
                mismatch_reason = "checkpoint_presence_mismatch"
            elif legacy_has_checkpoint and legacy_checkpoint_with_action != compiler_has_action:
                mismatch_reason = "checkpoint_action_mismatch"
            elif legacy_has_checkpoint and legacy_checkpoint_with_text != (compiler_has_visible_answer or compiler_has_pre_action_text):
                mismatch_reason = "checkpoint_visible_text_mismatch"
            else:
                aligned = True

            stage_logger.log(
                "protocol_shadow",
                "board_checkpoint_structural_parity",
                parity_available=parity_available,
                parity_aligned=aligned,
                mismatch_reason=mismatch_reason,
                compiler_shape=compiler_shape,
                compiler_code=compiler_error_code,
                compiler_recovery_id=compiler_recovery_id,
                compiler_visible_text_source=compiler_visible_text_source,
                compiler_has_action=compiler_has_action,
                compiler_action_count=compiler_action_count,
                compiler_has_checkpoint=compiler_has_checkpoint,
                compiler_has_memory_tags=compiler_has_memory_tags,
                compiler_has_subgoal_tags=compiler_has_subgoal_tags,
                compiler_has_memory_checkpoint=compiler_has_memory_checkpoint,
                compiler_has_visible_answer=compiler_has_visible_answer,
                compiler_has_pre_action_text=compiler_has_pre_action_text,
                plan_checkpoint_category=plan_category,
                memory_checkpoint_category=memory_category,
                legacy_checkpoint_only=legacy_checkpoint_only,
                legacy_checkpoint_with_text=legacy_checkpoint_with_text,
                legacy_checkpoint_with_action=legacy_checkpoint_with_action,
                shadow_only=True,
            )
        except Exception:
            return

    def _build_execution_plan(self, step, parsed_output, *, parsed_action_count: int):
        if parsed_output is None:
            return None
        payload = getattr(step, "intent_payload", None)
        if not isinstance(payload, dict):
            return None
        payload_mode = str(payload.get("mode") or "").strip().lower()
        if payload_mode not in {"activate", "reuse", "replace"}:
            return None
        compiler_shape = str(getattr(parsed_output, "compiler_shape", "") or "").strip().upper()
        if compiler_shape not in {"ACTION_ONLY", "INTENT_ACTION_BUNDLE", "PRE_ACTION_TEXT_AND_ACTION"}:
            return None
        if not self.semantics.has_any_action_proposal(parsed_output, parsed_action_count):
            return None
        ir = getattr(parsed_output, "compiler_ir", None)
        if ir is None:
            # This path is not plan-first eligible without compiler IR.
            # The plan builder could be enriched to handle this, but for now
            # it's an explicit non-goal.
            return None

        action_ops = list(getattr(ir, "action_ops", ()) or ())
        action_op_count = len(action_ops)
        action_payload_snapshot = [dict(op.payload) for op in action_ops if isinstance(getattr(op, "payload", None), dict)]

        candidate_eligibility_status = "unknown"
        if action_op_count == 0:
            candidate_eligibility_status = "no_action_ops"
        elif action_op_count == 1:
            candidate_eligibility_status = "single_action_candidate_possible"
        else:
            candidate_eligibility_status = "multi_action_not_migrated"

        output_effects: list[str] = []
        pre_action_text_source = ""
        if compiler_shape == "PRE_ACTION_TEXT_AND_ACTION" and ir.has_pre_action_text and ir.pre_action_text:
            output_effects.append(f"pre_action_text:{ir.pre_action_text}")
            pre_action_text_source = "compiler_ir"

        active_intent = getattr(self.state, "active_intent", None)
        after_intent_id = str(getattr(active_intent, "intent_id", "") or "").strip()
        transition_info = dict(getattr(getattr(self.state, "intent_runtime", None), "last_transition_info", {}) or {})
        before_intent_id = str(
            transition_info.get("before_active_intent_id")
            or payload.get("intent_id")
            or after_intent_id
        ).strip()
        action_effects: list[str] = []
        for action in action_ops:
            action_type = str(getattr(action, "action_type", "") or "").strip()
            payload_obj = getattr(action, "payload", None)
            target = ""
            if isinstance(payload_obj, dict):
                target = str(payload_obj.get("path") or payload_obj.get("command") or "").strip()
            summary = action_type or "action"
            if target:
                summary = f"{summary}:{target}"
            action_effects.append(summary)
        state_effects = [f"{payload_mode}_intent:{after_intent_id or str(payload.get('intent_id') or '').strip()}"]
        return ExecutionPlan(
            shape=str(getattr(parsed_output, "compiler_shape", "") or ""),
            transaction_kind="atomic_intent_action_bundle",
            state_effects=state_effects,
            action_effects=action_effects,
            output_effects=output_effects,
            bundle_validated=True,
            transition_applied=True,
            action_dispatched=False,
            active_intent_unchanged=bool(before_intent_id and after_intent_id and before_intent_id == after_intent_id),
            before_active_intent_id=before_intent_id,
            after_active_intent_id=after_intent_id,
            plan_source="compiler_ir",
            action_op_count=action_op_count,
            action_payload_snapshot=action_payload_snapshot,
            candidate_eligibility_status=candidate_eligibility_status,
            pre_action_text_source=pre_action_text_source,
        )

    def _log_board_checkpoint_authority_resolution(self, diagnostic) -> None:
        stage_logger = getattr(self, "stage_logger", None)
        if not stage_logger or diagnostic is None:
            return
        try:
            stage_logger.log(
                "protocol_shadow",
                "board_checkpoint_authority_resolution",
                branch=diagnostic.branch,
                switch_value=diagnostic.switch_value,
                authority_source=diagnostic.authority_source,
                legacy_active=diagnostic.legacy_active,
                typed_kind=diagnostic.typed_kind,
                legacy_kind=diagnostic.legacy_kind,
                agreement=diagnostic.agreement,
                fallback_used=diagnostic.fallback_used,
                behavior_changed=diagnostic.behavior_changed,
                branch_active=diagnostic.branch_active,
                compiler_eligible=diagnostic.compiler_eligible,
                effective_value=diagnostic.effective_value,
                shadow_only=True,
            )
        except Exception:
            return

    def _log_board_memory_commit_authority_resolution(self, diagnostic) -> None:
        stage_logger = getattr(self, "stage_logger", None)
        if not stage_logger or diagnostic is None:
            return
        try:
            stage_logger.log(
                "protocol_shadow",
                "board_memory_commit_authority_resolution",
                branch=diagnostic.branch,
                switch_value=diagnostic.switch_value,
                authority_source=diagnostic.authority_source,
                selected_by_switch=diagnostic.selected_by_switch,
                candidate_available=diagnostic.candidate_available,
                commit_equivalent=diagnostic.commit_equivalent,
                fallback_used=diagnostic.fallback_used,
                behavior_changed=diagnostic.behavior_changed,
                commit_attempted_agreement=getattr(diagnostic, "commit_attempted_agreement", False),
                accepted_count_agreement=getattr(diagnostic, "accepted_count_agreement", False),
                rejected_count_agreement=getattr(diagnostic, "rejected_count_agreement", False),
                handled_agreement=getattr(diagnostic, "handled_agreement", False),
                reason_agreement=getattr(diagnostic, "reason_agreement", False),
                source_agreement=getattr(diagnostic, "source_agreement", False),
                next_query_agreement=getattr(diagnostic, "next_query_agreement", False),
                state_flags_agreement=getattr(diagnostic, "state_flags_agreement", False),
                response_text_agreement=getattr(diagnostic, "response_text_agreement", False),
                visible_text_preserved_agreement=getattr(diagnostic, "visible_text_preserved_agreement", False),
                checkpoint_removed_agreement=getattr(diagnostic, "checkpoint_removed_agreement", False),
                pass_through_agreement=getattr(diagnostic, "pass_through_agreement", False),
                final_answer_preserved_agreement=getattr(diagnostic, "final_answer_preserved_agreement", False),
                shadow_only=True,
            )
        except Exception:
            return

    def _log_terminal_answer_authority_resolution(self, diagnostic) -> None:
        stage_logger = getattr(self, "stage_logger", None)
        if not stage_logger or diagnostic is None:
            return
        try:
            stage_logger.log(
                "protocol_shadow",
                "terminal_answer_authority_resolution",
                branch=diagnostic.branch,
                switch_value=diagnostic.switch_value,
                authority_source=diagnostic.authority_source,
                legacy_active=diagnostic.legacy_active,
                typed_kind=diagnostic.typed_kind,
                legacy_kind=diagnostic.legacy_kind,
                agreement=diagnostic.agreement,
                fallback_used=diagnostic.fallback_used,
                behavior_changed=diagnostic.behavior_changed,
                branch_active=diagnostic.branch_active,
                typed_eligible=diagnostic.typed_eligible,
                typed_plaintext_eligible=diagnostic.typed_plaintext_eligible,
                effective_value=diagnostic.effective_value,
                invalid_kind=diagnostic.invalid_kind,
                compiler_shape=diagnostic.compiler_shape,
                terminal_answer_kind=diagnostic.terminal_answer_kind,
                has_action=diagnostic.has_action,
                has_checkpoint=diagnostic.has_checkpoint,
                has_visible_text=diagnostic.has_visible_text,
                is_leaked_system_result=diagnostic.is_leaked_system_result,
                invalid_or_truncated_terminal_text=diagnostic.invalid_or_truncated_terminal_text,
                checkpoint_with_visible_text_overlap=diagnostic.checkpoint_with_visible_text_overlap,
                leaked_system_result_overlap=diagnostic.leaked_system_result_overlap,
                action_or_pre_action_overlap=diagnostic.action_or_pre_action_overlap,
                clean_plaintext_candidate=diagnostic.clean_plaintext_candidate,
                clean_checkpoint_only_candidate=diagnostic.clean_checkpoint_only_candidate,
                blocking_reasons=diagnostic.blocking_reasons,
                mismatch_reason=diagnostic.mismatch_reason,
                shadow_only=True,
            )
        except Exception:
            return

    def _log_recovery_authority_resolution(self, diagnostic) -> None:
        stage_logger = getattr(self, "stage_logger", None)
        if not stage_logger or diagnostic is None:
            return
        try:
            stage_logger.log(
                "protocol_shadow",
                "recovery_authority_resolution",
                branch=diagnostic.branch,
                switch_value=diagnostic.switch_value,
                authority_source=diagnostic.authority_source,
                effective_source=diagnostic.effective_source,
                selected_by_switch=diagnostic.selected_by_switch,
                legacy_kind=diagnostic.legacy_kind,
                compiler_kind=diagnostic.compiler_kind,
                typed_kind=diagnostic.typed_kind,
                parsed_invalid_kind=diagnostic.parsed_invalid_kind,
                effective_invalid_kind=diagnostic.effective_invalid_kind,
                agreement=diagnostic.agreement,
                fallback_used=diagnostic.fallback_used,
                behavior_changed=diagnostic.behavior_changed,
                branch_active=diagnostic.branch_active,
                recovery_action=diagnostic.recovery_action,
                recovery_reason=diagnostic.recovery_reason,
                recovery_prompt_kind=diagnostic.recovery_prompt_kind,
                compiler_recovery_action=diagnostic.compiler_recovery_action,
                compiler_recovery_reason=diagnostic.compiler_recovery_reason,
                compiler_recovery_prompt_kind=diagnostic.compiler_recovery_prompt_kind,
                compiler_decision_available=diagnostic.compiler_decision_available,
                decision_agreement=diagnostic.decision_agreement,
                prompt_equivalent=diagnostic.prompt_equivalent,
                candidate_source=diagnostic.candidate_source,
                blocking_reasons=diagnostic.blocking_reasons,
                compiler_error_code=diagnostic.compiler_error_code,
                terminal_answer_kind=diagnostic.terminal_answer_kind,
                legacy_leak_active=diagnostic.legacy_leak_active,
                typed_leak_eligible=diagnostic.typed_leak_eligible,
                typed_invalid_truncated_eligible=diagnostic.typed_invalid_truncated_eligible,
                parsed_action_count=diagnostic.parsed_action_count,
                has_action=diagnostic.has_action,
                has_checkpoint=diagnostic.has_checkpoint,
                has_visible_text=diagnostic.has_visible_text,
                is_leaked_system_result=diagnostic.is_leaked_system_result,
                is_internal_summary=diagnostic.is_internal_summary,
                retry_count=diagnostic.retry_count,
                guard_name=diagnostic.guard_name,
                guard_triggered=diagnostic.guard_triggered,
                guard_state=diagnostic.guard_state,
                shadow_only=True,
            )
        except Exception:
            return

    async def _run_initial_stages(self, ctx, step):
        raw_response = str(step.response or "")
        normalized = self._normalize_response_stage(
            raw_response,
            allow_autorepair=getattr(step, "intent_payload", None) is None,
            source="run_step",
        )
        raw_response = normalized.normalized_response

        preclassified = None
        payload = getattr(step, "intent_payload", None)
        payload_mode = str((payload or {}).get("mode") or "").strip().lower() if isinstance(payload, dict) else ""
        if payload_mode == "complete":
            preclassified = self._classify_response_for_prevalidation(
                raw_response,
                allow_think_autorepair=False,
            )

        terminal_completion_decision = self._reject_truncated_terminal_completion_before_transition(
            raw_response,
            step,
            parsed_output=preclassified[1] if preclassified is not None else None,
        )
        if terminal_completion_decision is not None:
            return raw_response, None, terminal_completion_decision

        atomicity_decision = await self._reject_invalid_intent_followup_before_transition(
            ctx,
            raw_response,
            step,
            preclassified=preclassified,
        )
        if atomicity_decision is not None:
            return raw_response, None, atomicity_decision

        intent_decision = await self.intent_transitions.handle_model_step(
            intent_payload=step.intent_payload,
            intent_error=step.intent_error,
            response_text=raw_response,
            state_machine=ctx.state_machine,
        )
        if intent_decision.handled:
            self.guards.set_nonproductive_thinking_state(False)
            self.stage_logger.log(
                "response_pipeline",
                "continue",
                reason=intent_decision.reason,
                source="intent_transition",
            )
            return raw_response, None, ResponsePipelineOutcome.continue_with(
                intent_decision.next_query,
                reason=intent_decision.reason,
                source="intent_transition",
            )

        reflection_repair_pending = self.guards.reflection_repair_pending()
        reflection_repair_kind = self.guards.reflection_repair_kind()

        if getattr(self.state, "intent_required_until_activated", False) and "<action" in raw_response.lower():
            self.stage_logger.log(
                "response_pipeline",
                "continue",
                reason=getattr(self.state, "intent_required_reason", "intent_required"),
                source="intent_requirement_gate",
            )
            return raw_response, None, ResponsePipelineOutcome.continue_with(
                self.prompt_builder.build_intent_required_prompt(
                    getattr(self.state, "intent_required_reason", "intent_required")
                ),
                reason=getattr(self.state, "intent_required_reason", "intent_required"),
                source="intent_requirement_gate",
            )

        return raw_response, (reflection_repair_pending, reflection_repair_kind), None

    async def _run_checkpoint_stage(self, ctx, raw_response: str, *, reflection_repair_pending: bool, reflection_repair_kind: str):
        compiler_analysis = self._run_structural_diagnosis_prepass(raw_response)

        plan_board_decision = await self.plan_board_stage.apply(ctx, raw_response)
        response_after_plan = plan_board_decision.response_text
        plan_checkpoint_only = bool(getattr(plan_board_decision, "plan_checkpoint_only", False))
        plan_checkpoint_and_text = bool(getattr(plan_board_decision, "plan_checkpoint_and_text", False))
        plan_checkpoint_and_action = bool(getattr(plan_board_decision, "plan_checkpoint_and_action", False))
        plan_semantic_result = build_board_checkpoint_semantic_result(
            compiler_analysis,
            raw_response=raw_response,
            response_text=response_after_plan,
            plan_checkpoint_only=plan_checkpoint_only,
            plan_checkpoint_and_text=plan_checkpoint_and_text,
            plan_checkpoint_and_action=plan_checkpoint_and_action,
            memory_checkpoint_only=False,
            memory_checkpoint_and_text=False,
            memory_checkpoint_and_action=False,
        )
        switch_value = get_switch("board_checkpoint.plan_checkpoint_only")
        plan_checkpoint_only_authority = resolve_plan_checkpoint_only_authority(
            plan_semantic_result,
            legacy_plan_checkpoint_only=plan_checkpoint_only,
            switch_value=switch_value,
        )
        self._log_board_checkpoint_authority_resolution(plan_checkpoint_only_authority)
        # Step 22: First compiler-authority switch for plan-checkpoint-only
        effective_plan_checkpoint_only = plan_checkpoint_only_authority.effective_value
        if effective_plan_checkpoint_only and not plan_board_decision.handled:
            plan_board_decision.handled = True
            plan_board_decision.reason = "plan_checkpoint_only"
            plan_board_decision.source = "compiler_authority"
            plan_board_decision.next_query = None

        plan_checkpoint_with_text_switch = get_switch("board_checkpoint.plan_checkpoint_with_text")
        plan_checkpoint_and_text_authority = resolve_plan_checkpoint_and_text_authority(
            plan_semantic_result,
            legacy_plan_checkpoint_and_text=plan_checkpoint_and_text,
            switch_value=plan_checkpoint_with_text_switch,
        )
        self._log_board_checkpoint_authority_resolution(plan_checkpoint_and_text_authority)
        effective_plan_checkpoint_and_text = plan_checkpoint_and_text_authority.effective_value
        plan_checkpoint_with_action_switch = get_switch("board_checkpoint.plan_checkpoint_with_action")
        plan_checkpoint_and_action_authority = resolve_plan_checkpoint_and_action_authority(
            plan_semantic_result,
            legacy_plan_checkpoint_and_action=plan_checkpoint_and_action,
            switch_value=plan_checkpoint_with_action_switch,
        )
        self._log_board_checkpoint_authority_resolution(plan_checkpoint_and_action_authority)
        effective_plan_checkpoint_and_action = plan_checkpoint_and_action_authority.effective_value
        if plan_board_decision.handled:
            self._log_board_checkpoint_structural_parity(
                compiler_analysis,
                plan_checkpoint_only=effective_plan_checkpoint_only,
                plan_checkpoint_and_text=effective_plan_checkpoint_and_text,
                plan_checkpoint_and_action=effective_plan_checkpoint_and_action,
                memory_checkpoint_only=False,
                memory_checkpoint_and_text=False,
                memory_checkpoint_and_action=False,
            )
            return CheckpointStageState(
                response=response_after_plan,
                reflection_repair_pending=reflection_repair_pending,
                reflection_repair_kind=reflection_repair_kind,
                plan_checkpoint_only=effective_plan_checkpoint_only,
                plan_checkpoint_and_text=effective_plan_checkpoint_and_text,
                plan_checkpoint_and_action=effective_plan_checkpoint_and_action,
                memory_checkpoint_only=False,
                memory_checkpoint_and_text=False,
                memory_checkpoint_and_action=False,
                memory_board_decision=None,
                compiler_analysis=compiler_analysis,
                board_checkpoint_semantic_result=plan_semantic_result,
            ), ResponsePipelineOutcome.continue_with(
                plan_board_decision.next_query,
                response_text=response_after_plan,
                reason=plan_board_decision.reason,
                source=plan_board_decision.source,
            )

        memory_board_decision = await self.memory_board_stage.apply(ctx, response_after_plan)
        response = memory_board_decision.response_text
        memory_checkpoint_only = bool(getattr(memory_board_decision, "memory_checkpoint_only", False))
        memory_checkpoint_and_text = bool(getattr(memory_board_decision, "memory_checkpoint_and_text", False))
        memory_checkpoint_and_action = bool(getattr(memory_board_decision, "memory_checkpoint_and_action", False))
        board_checkpoint_semantic_result = build_board_checkpoint_semantic_result(
            compiler_analysis,
            raw_response=raw_response,
            response_text=response,
            plan_checkpoint_only=plan_checkpoint_only,
            plan_checkpoint_and_text=plan_checkpoint_and_text,
            plan_checkpoint_and_action=plan_checkpoint_and_action,
            memory_checkpoint_only=memory_checkpoint_only,
            memory_checkpoint_and_text=memory_checkpoint_and_text,
            memory_checkpoint_and_action=memory_checkpoint_and_action,
        )
        plan_checkpoint_only_authority = resolve_plan_checkpoint_only_authority(
            board_checkpoint_semantic_result,
            legacy_plan_checkpoint_only=plan_checkpoint_only,
            switch_value=switch_value,
        )
        self._log_board_checkpoint_authority_resolution(plan_checkpoint_only_authority)
        # Step 22: First compiler-authority switch for plan-checkpoint-only
        effective_plan_checkpoint_only = plan_checkpoint_only_authority.effective_value
        if effective_plan_checkpoint_only and not plan_board_decision.handled and not memory_board_decision.handled:
            plan_board_decision.handled = True
            plan_board_decision.reason = "plan_checkpoint_only"
            plan_board_decision.source = "compiler_authority"
            plan_board_decision.next_query = None

        plan_checkpoint_and_text_authority = resolve_plan_checkpoint_and_text_authority(
            board_checkpoint_semantic_result,
            legacy_plan_checkpoint_and_text=plan_checkpoint_and_text,
            switch_value=plan_checkpoint_with_text_switch,
        )
        self._log_board_checkpoint_authority_resolution(plan_checkpoint_and_text_authority)
        effective_plan_checkpoint_and_text = plan_checkpoint_and_text_authority.effective_value
        plan_checkpoint_and_action_authority = resolve_plan_checkpoint_and_action_authority(
            board_checkpoint_semantic_result,
            legacy_plan_checkpoint_and_action=plan_checkpoint_and_action,
            switch_value=plan_checkpoint_with_action_switch,
        )
        self._log_board_checkpoint_authority_resolution(plan_checkpoint_and_action_authority)
        effective_plan_checkpoint_and_action = plan_checkpoint_and_action_authority.effective_value

        # Step 18: First true authority candidate for memory-checkpoint-only
        effective_memory_checkpoint_only = resolve_memory_checkpoint_only_typed_primary(
            board_checkpoint_semantic_result,
            legacy_memory_checkpoint_only=memory_checkpoint_only,
            legacy_memory_checkpoint_and_text=memory_checkpoint_and_text,
            legacy_memory_checkpoint_and_action=memory_checkpoint_and_action,
        )
        # Step 19: Extend typed-primary candidate to remaining memory branches
        effective_memory_checkpoint_and_text = resolve_memory_checkpoint_and_text_typed_primary(
            board_checkpoint_semantic_result,
            legacy_memory_checkpoint_only=memory_checkpoint_only,
            legacy_memory_checkpoint_and_text=memory_checkpoint_and_text,
            legacy_memory_checkpoint_and_action=memory_checkpoint_and_action,
        )
        effective_memory_checkpoint_and_action = resolve_memory_checkpoint_and_action_typed_primary(
            board_checkpoint_semantic_result,
            legacy_memory_checkpoint_only=memory_checkpoint_only,
            legacy_memory_checkpoint_and_text=memory_checkpoint_and_text,
            legacy_memory_checkpoint_and_action=memory_checkpoint_and_action,
        )

        mco_switch_value = get_switch("board_memory.memory_checkpoint_only")

        # Phase 30 Step 9: Harden commit field extraction for real handler state.
        # The real MemoryBoardStageHandler may expose commit results via state fields.
        # This logic safely falls back to state fields if the decision object lacks them.
        legacy_commit_attempted = bool(
            getattr(memory_board_decision, "memory_commit_attempted", False)
            or int(getattr(self.state, "last_memory_board_parsed_count", 0) or 0) > 0
            or int(getattr(self.state, "last_memory_board_accepted_count", 0) or 0) > 0
            or int(getattr(self.state, "last_memory_board_rejected_count", 0) or 0) > 0
        )
        accepted_count_from_decision = getattr(memory_board_decision, "memory_commit_accepted_count", None)
        legacy_accepted_count = int(
            accepted_count_from_decision
            if accepted_count_from_decision is not None
            else getattr(self.state, "last_memory_board_accepted_count", 0)
            or 0
        )
        rejected_count_from_decision = getattr(memory_board_decision, "memory_commit_rejected_count", None)
        legacy_rejected_count = int(
            rejected_count_from_decision
            if rejected_count_from_decision is not None
            else getattr(self.state, "last_memory_board_rejected_count", 0)
            or 0
        )
        legacy_last_memory_update_done = bool(getattr(self.state, "last_memory_update_done", False))

        mco_authority_decision = resolve_memory_checkpoint_only_commit_authority(
            semantic_result=board_checkpoint_semantic_result,
            legacy_branch=board_checkpoint_semantic_result.kind.name,
            legacy_handled=bool(getattr(memory_board_decision, "handled", False)),
            legacy_reason=str(getattr(memory_board_decision, "reason", "") or ""),
            legacy_source=str(getattr(memory_board_decision, "source", "") or ""),
            legacy_response_text=str(getattr(memory_board_decision, "response_text", "") or ""),
            legacy_next_query=getattr(memory_board_decision, "next_query", None),
            legacy_commit_attempted=legacy_commit_attempted,
            legacy_accepted_count=legacy_accepted_count,
            legacy_rejected_count=legacy_rejected_count,
            legacy_last_memory_update_done=legacy_last_memory_update_done,
            switch_value=mco_switch_value,
        )
        self._log_board_memory_commit_authority_resolution(mco_authority_decision.diagnostic)

        mct_switch_value = get_switch("board_memory.memory_checkpoint_with_text")
        # Diagnostic-only evidence for MCT
        mct_before_text = str(response_after_plan or "")
        mct_after_text = str(getattr(memory_board_decision, "response_text", "") or response or "")
        legacy_checkpoint_removed = (
            "<memory_update_done />" in mct_before_text.lower()
            and "<memory_update_done />" not in mct_after_text.lower()
        )
        stripped_before = mct_before_text.replace("<memory_update_done />", "").strip()
        stripped_after = mct_after_text.strip()
        legacy_visible_text_preserved = stripped_before == stripped_after
        legacy_pass_through_preserved = (
            board_checkpoint_semantic_result is not None
            and getattr(board_checkpoint_semantic_result.kind, "name", "") == "MEMORY_CHECKPOINT_WITH_TEXT"
            and not bool(getattr(memory_board_decision, "handled", False))
            and bool(mct_after_text.strip())
        )

        mct_legacy_commit_attempted = legacy_commit_attempted
        if (
            board_checkpoint_semantic_result is not None
            and getattr(board_checkpoint_semantic_result.kind, "name", "") == "MEMORY_CHECKPOINT_WITH_TEXT"
            and legacy_accepted_count == 0
            and legacy_rejected_count == 0
        ):
            mct_legacy_commit_attempted = False

        mct_authority_decision = resolve_memory_checkpoint_with_text_commit_authority(
            semantic_result=board_checkpoint_semantic_result,
            legacy_branch=board_checkpoint_semantic_result.kind.name,
            legacy_handled=bool(getattr(memory_board_decision, "handled", False)),
            legacy_reason=str(getattr(memory_board_decision, "reason", "") or ""),
            legacy_source=str(getattr(memory_board_decision, "source", "") or ""),
            legacy_response_text=mct_after_text,
            legacy_next_query=getattr(memory_board_decision, "next_query", None),
            legacy_commit_attempted=mct_legacy_commit_attempted,
            legacy_accepted_count=legacy_accepted_count,
            legacy_rejected_count=legacy_rejected_count,
            legacy_last_memory_update_done=legacy_last_memory_update_done,
            legacy_visible_text_preserved=legacy_visible_text_preserved,
            legacy_pass_through_preserved=legacy_pass_through_preserved,
            legacy_checkpoint_removed=legacy_checkpoint_removed,
            switch_value=mct_switch_value,
        )
        self._log_board_memory_commit_authority_resolution(mct_authority_decision.diagnostic)

        self._log_board_checkpoint_structural_parity(
            compiler_analysis,
            plan_checkpoint_only=effective_plan_checkpoint_only,
            plan_checkpoint_and_text=effective_plan_checkpoint_and_text,
            plan_checkpoint_and_action=effective_plan_checkpoint_and_action,
            memory_checkpoint_only=effective_memory_checkpoint_only,
            memory_checkpoint_and_text=effective_memory_checkpoint_and_text,
            memory_checkpoint_and_action=effective_memory_checkpoint_and_action,
        )

        def _repair_checkpoint_completed() -> bool:
            if not bool(getattr(self.state, "last_memory_update_done", False)):
                return False
            if reflection_repair_kind == "missing_memory_update_done":
                return True
            memory_committed = int(getattr(self.state, "last_memory_board_accepted_count", 0) or 0) > 0
            plan_committed = (
                effective_plan_checkpoint_only
                or effective_plan_checkpoint_and_text
                or effective_plan_checkpoint_and_action
            )
            return memory_committed or plan_committed

        if reflection_repair_pending and effective_memory_checkpoint_only:
            if _repair_checkpoint_completed():
                self.stage_logger.log_architecture_defect(
                    reflection_repair_kind or "missing_think_reflection",
                    "repair_completed",
                    source_stage="memory_board",
                )
                self.guards.set_reflection_repair_pending(False)
                self.guards.set_nonproductive_thinking_state(False)
                self.stage_logger.log(
                    "response_pipeline",
                    "continue",
                    reason="think_reflection_repair_completed",
                    source="think_reflection_guard",
                )
                return CheckpointStageState(
                    response=response,
                    reflection_repair_pending=reflection_repair_pending,
                    reflection_repair_kind=reflection_repair_kind,
                    plan_checkpoint_only=effective_plan_checkpoint_only,
                    plan_checkpoint_and_text=effective_plan_checkpoint_and_text,
                    plan_checkpoint_and_action=effective_plan_checkpoint_and_action,
                    memory_checkpoint_only=effective_memory_checkpoint_only,
                    memory_checkpoint_and_text=effective_memory_checkpoint_and_text,
                    memory_checkpoint_and_action=effective_memory_checkpoint_and_action,
                    memory_board_decision=memory_board_decision,
                    compiler_analysis=compiler_analysis,
                    board_checkpoint_semantic_result=board_checkpoint_semantic_result,
                ), ResponsePipelineOutcome.continue_with(
                    self.prompt_builder.build_reflection_repair_accepted_prompt(),
                    response_text=response,
                    reason="think_reflection_repair_completed",
                    source="think_reflection_guard",
                )
            self.stage_logger.log_architecture_defect(
                reflection_repair_kind or "missing_think_reflection",
                "repair_enforced",
                source_stage="memory_board",
            )
            self.stage_logger.log(
                "response_pipeline",
                "continue",
                reason=reflection_repair_kind or "missing_think_reflection",
                source="think_reflection_guard",
            )
            return CheckpointStageState(
                response=response,
                reflection_repair_pending=reflection_repair_pending,
                reflection_repair_kind=reflection_repair_kind,
                plan_checkpoint_only=effective_plan_checkpoint_only,
                plan_checkpoint_and_text=effective_plan_checkpoint_and_text,
                plan_checkpoint_and_action=effective_plan_checkpoint_and_action,
                memory_checkpoint_only=effective_memory_checkpoint_only,
                memory_checkpoint_and_text=effective_memory_checkpoint_and_text,
                memory_checkpoint_and_action=effective_memory_checkpoint_and_action,
                memory_board_decision=memory_board_decision,
                compiler_analysis=compiler_analysis,
                board_checkpoint_semantic_result=board_checkpoint_semantic_result,
            ), ResponsePipelineOutcome.continue_with(
                self.prompt_builder.build_durable_state_repair_prompt(reflection_repair_kind),
                response_text=response,
                reason=reflection_repair_kind or "missing_think_reflection",
                source="think_reflection_guard",
                memory_checkpoint_only=effective_memory_checkpoint_only,
                memory_checkpoint_and_text=effective_memory_checkpoint_and_text,
                memory_checkpoint_and_action=effective_memory_checkpoint_and_action,
            )

        if memory_board_decision.handled and (effective_memory_checkpoint_and_text or effective_memory_checkpoint_and_action):
            self.guards.set_nonproductive_thinking_state(False)
            memory_board_decision.handled = False

        if memory_board_decision.handled:
            if effective_memory_checkpoint_only:
                self.guards.set_reflection_repair_pending(False)
                streak = self.guards.memory_checkpoint_streak()
                if streak >= self.memory_checkpoint_hard_stop_streak:
                    message = (
                        "Execution stopped: repeated memory-checkpoint-only turns without a substantive continuation. "
                        "The model kept updating memory but did not converge to a concrete action or final answer."
                    )
                    try:
                        await self.ui.print_error(message)
                    except Exception:
                        pass
                    self.stage_logger.log(
                        "response_pipeline",
                        "stop",
                        reason="memory_checkpoint_only_hard_stop",
                        source="memory_board",
                        streak=streak,
                    )
                    return CheckpointStageState(
                        response=response,
                        reflection_repair_pending=reflection_repair_pending,
                        reflection_repair_kind=reflection_repair_kind,
                        plan_checkpoint_only=effective_plan_checkpoint_only,
                        plan_checkpoint_and_text=effective_plan_checkpoint_and_text,
                        plan_checkpoint_and_action=effective_plan_checkpoint_and_action,
                        memory_checkpoint_only=effective_memory_checkpoint_only,
                        memory_checkpoint_and_text=effective_memory_checkpoint_and_text,
                        memory_checkpoint_and_action=effective_memory_checkpoint_and_action,
                        memory_board_decision=memory_board_decision,
                        compiler_analysis=compiler_analysis,
                        board_checkpoint_semantic_result=board_checkpoint_semantic_result,
                    ), ResponsePipelineOutcome.stop(
                        response_text=response,
                        reason="memory_checkpoint_only_hard_stop",
                        source="memory_board",
                        malformed_action_retries=0,
                        audit_marker_retries=0,
                        memory_checkpoint_only=effective_memory_checkpoint_only,
                        memory_checkpoint_and_text=effective_memory_checkpoint_and_text,
                        memory_checkpoint_and_action=effective_memory_checkpoint_and_action,
                    )
                if self.semantics.has_substantial_think(raw_response):
                    nonproductive_streak = self.guards.set_nonproductive_thinking_state(
                        True, "repeated_thinking_without_valid_output"
                    )
                    if nonproductive_streak >= self.nonproductive_thinking_hard_stop_streak:
                        self.stage_logger.log(
                            "response_pipeline",
                            "continue",
                            reason="repeated_thinking_without_valid_output",
                            source="thinking_guard",
                            streak=nonproductive_streak,
                        )
                        return CheckpointStageState(
                            response=response,
                            reflection_repair_pending=reflection_repair_pending,
                            reflection_repair_kind=reflection_repair_kind,
                            plan_checkpoint_only=effective_plan_checkpoint_only,
                            plan_checkpoint_and_text=effective_plan_checkpoint_and_text,
                            plan_checkpoint_and_action=effective_plan_checkpoint_and_action,
                            memory_checkpoint_only=effective_memory_checkpoint_only,
                            memory_checkpoint_and_text=effective_memory_checkpoint_and_text,
                            memory_checkpoint_and_action=effective_memory_checkpoint_and_action,
                            memory_board_decision=memory_board_decision,
                            compiler_analysis=compiler_analysis,
                            board_checkpoint_semantic_result=board_checkpoint_semantic_result,
                        ), ResponsePipelineOutcome.continue_with(
                            self.prompt_builder.build_repeated_thinking_without_valid_output_prompt(
                                {"reason": "repeated_thinking_without_valid_output"}
                            ),
                            response_text=response,
                            reason="repeated_thinking_without_valid_output",
                            source="thinking_guard",
                            memory_checkpoint_only=effective_memory_checkpoint_only,
                            memory_checkpoint_and_text=effective_memory_checkpoint_and_text,
                            memory_checkpoint_and_action=effective_memory_checkpoint_and_action,
                        )
            return CheckpointStageState(
                response=response,
                reflection_repair_pending=reflection_repair_pending,
                reflection_repair_kind=reflection_repair_kind,
                plan_checkpoint_only=effective_plan_checkpoint_only,
                plan_checkpoint_and_text=effective_plan_checkpoint_and_text,
                plan_checkpoint_and_action=effective_plan_checkpoint_and_action,
                memory_checkpoint_only=effective_memory_checkpoint_only,
                memory_checkpoint_and_text=effective_memory_checkpoint_and_text,
                memory_checkpoint_and_action=effective_memory_checkpoint_and_action,
                memory_board_decision=memory_board_decision,
                compiler_analysis=compiler_analysis,
                board_checkpoint_semantic_result=board_checkpoint_semantic_result,
            ), ResponsePipelineOutcome.continue_with(
                memory_board_decision.next_query,
                response_text=response,
                reason=memory_board_decision.reason,
                source=memory_board_decision.source,
                memory_checkpoint_only=effective_memory_checkpoint_only,
                memory_checkpoint_and_text=effective_memory_checkpoint_and_text,
                memory_checkpoint_and_action=effective_memory_checkpoint_and_action,
            )

        return CheckpointStageState(
            response=response,
            reflection_repair_pending=reflection_repair_pending,
            reflection_repair_kind=reflection_repair_kind,
            plan_checkpoint_only=effective_plan_checkpoint_only,
            plan_checkpoint_and_text=effective_plan_checkpoint_and_text,
            plan_checkpoint_and_action=effective_plan_checkpoint_and_action,
            memory_checkpoint_only=effective_memory_checkpoint_only,
            memory_checkpoint_and_text=effective_memory_checkpoint_and_text,
            memory_checkpoint_and_action=effective_memory_checkpoint_and_action,
            memory_board_decision=memory_board_decision,
            compiler_analysis=compiler_analysis,
            board_checkpoint_semantic_result=board_checkpoint_semantic_result,
        ), None

    def _log_semantic_shadow_disagreements(
        self, raw_response: str, parsed_output, parsed_action_count: int, compiler_analysis
    ):
        config = getattr(self, "config", None)
        if not config:
            return

        is_enabled = False
        if isinstance(config, dict):
            is_enabled = bool(config.get("enable_semantic_shadow_logging", False))
        else:
            is_enabled = bool(getattr(config, "enable_semantic_shadow_logging", False))

        if not is_enabled:
            return

        ir = getattr(compiler_analysis, "ir", None)
        if not ir:
            return

        legacy_values = {
            "action_count": parsed_action_count,
            "has_think": self.semantics.has_substantial_think(raw_response),
            "has_checkpoint": self.semantics.has_checkpoint_tags(raw_response),
            "has_visible_answer": self.semantics.is_plaintext_answer_path(
                raw_response, parsed_output, parsed_action_count
            ),
        }

        compiler_values = {
            "action_count": ir.action_count,
            "has_think": ir.has_think,
            "has_checkpoint": ir.has_checkpoint,
            "has_visible_answer": ir.has_visible_answer,
        }

        for field, legacy_val in legacy_values.items():
            compiler_val = compiler_values.get(field)
            if legacy_val != compiler_val:
                self.stage_logger.log(
                    "protocol_shadow",
                    "semantic_disagreement",
                    field=field,
                    legacy_value=legacy_val,
                    compiler_value=compiler_val,
                    compiler_shape=compiler_analysis.shape.name,
                    compiler_code=getattr(compiler_analysis.error, "code", None),
                    response_len=len(raw_response),
                    shadow_only=True,
                )

    def _run_classification_stage(self, step, raw_response: str, checkpoint_state: CheckpointStageState):
        normalized = self._normalize_response_stage(
            checkpoint_state.response,
            allow_autorepair=True,
            source="classification_stage",
        )
        response = normalized.normalized_response
        segments = self.parser.parse(response)
        parsed_output = self._classify_intent_output(response, segments, allow_think_autorepair=True)
        self._merge_normalization_metadata(parsed_output, normalized)
        compiler_analysis = self._apply_compiler_diagnosis(parsed_output, response)
        parsed_output.model_stop_reason = str(getattr(step, "model_stop_reason", "") or "").strip()
        checkpoint_has_think = self.semantics.has_complete_think_before_action(raw_response)
        checkpoint_has_marker = bool(
            getattr(self.state, "last_memory_update_done", False)
            or self.semantics.has_memory_update_done_before_action(raw_response)
        )
        checkpoint_has_tags = self.semantics.has_checkpoint_before_action(raw_response)
        checkpoint_has_board_commit = bool(checkpoint_state.memory_checkpoint_and_action or checkpoint_state.plan_checkpoint_and_action)
        checkpoint_source_satisfied = bool(
            checkpoint_has_board_commit
            or checkpoint_has_marker
        )
        checkpoint_satisfied = bool(
            checkpoint_has_think
            and checkpoint_source_satisfied
        )
        parsed_output.operational_checkpoint_has_think = checkpoint_has_think
        parsed_output.operational_checkpoint_has_marker = checkpoint_has_marker
        parsed_output.operational_checkpoint_has_board_commit = checkpoint_has_board_commit
        parsed_output.operational_checkpoint_has_tags = checkpoint_has_tags
        parsed_output.operational_checkpoint_satisfied = checkpoint_satisfied
        parsed_action_count = sum(1 for seg in segments if getattr(seg, "type", "") == "action")
        self.stage_logger.log(
            "response_pipeline",
            "classified",
            segment_count=len(segments),
            invalid_kind=parsed_output.invalid_kind or "",
            has_action_segment=parsed_output.has_action_segment,
            model_stop_reason=parsed_output.model_stop_reason,
            operational_checkpoint_satisfied=checkpoint_satisfied,
            operational_checkpoint_has_think=checkpoint_has_think,
            operational_checkpoint_has_marker=checkpoint_has_marker,
            operational_checkpoint_has_board_commit=checkpoint_has_board_commit,
            operational_checkpoint_has_tags=checkpoint_has_tags,
            think_repair_applied=bool(getattr(parsed_output, "auto_closed_think", False)),
            think_repair_reason=str(getattr(parsed_output, "auto_closed_think_reason", "") or ""),
            think_repair_tag=str(getattr(parsed_output, "auto_closed_think_tag", "") or ""),
            compiler_shape=compiler_analysis.shape.name,
            compiler_code=str(getattr(compiler_analysis.error, "code", "") or ""),
            compiler_recovery_id=str(getattr(compiler_analysis.error, "recovery_id", "") or ""),
            compiler_replay=compact_compiler_replay(compiler_analysis),
        )
        legacy_invalid = str(parsed_output.invalid_kind or "").strip()
        compiler_invalid = str(getattr(compiler_analysis.error, "code", "") or "").strip()
        if legacy_invalid or compiler_invalid:
            if legacy_invalid != compiler_invalid:
                span_excerpt = ""
                if getattr(compiler_analysis.error, "span", None) is not None:
                    span_excerpt = str(compiler_analysis.error.span.excerpt or "")
                self.stage_logger.log(
                    "protocol_shadow",
                    "disagreement",
                    legacy_invalid_kind=legacy_invalid,
                    compiler_phase=str(getattr(compiler_analysis.error, "phase", "") or ""),
                    compiler_code=compiler_invalid,
                    compiler_shape=compiler_analysis.shape.name,
                    recovery_id=str(getattr(compiler_analysis.error, "recovery_id", "") or ""),
                    span_excerpt=span_excerpt,
                    shadow_only=True,
                )
        self._log_semantic_shadow_disagreements(raw_response, parsed_output, parsed_action_count, compiler_analysis)
        return ClassifiedStageState(
            response=response,
            parsed_output=parsed_output,
            segments=segments,
            parsed_action_count=parsed_action_count,
            checkpoint_has_think=checkpoint_has_think,
            checkpoint_has_marker=checkpoint_has_marker,
            checkpoint_has_tags=checkpoint_has_tags,
            checkpoint_has_board_commit=checkpoint_has_board_commit,
            checkpoint_satisfied=checkpoint_satisfied,
        )

    async def _run_post_classification_stage(self, ctx, step, checkpoint_state: CheckpointStageState, classified: ClassifiedStageState):
        response = classified.response
        parsed_output = classified.parsed_output
        segments = classified.segments
        parsed_action_count = classified.parsed_action_count
        raw_response = str(step.response or "")
        reflection_repair_pending = checkpoint_state.reflection_repair_pending
        reflection_repair_kind = checkpoint_state.reflection_repair_kind
        memory_checkpoint_and_text = checkpoint_state.memory_checkpoint_and_text
        memory_checkpoint_and_action = checkpoint_state.memory_checkpoint_and_action
        memory_board_decision = checkpoint_state.memory_board_decision

        active_intent = getattr(self.state, "active_intent", None)
        if (
            active_intent is not None
            and bool(getattr(active_intent, "force_plaintext_completion", False))
            and self.semantics.has_any_action_proposal(parsed_output, parsed_action_count)
        ):
            self.guards.set_nonproductive_thinking_state(False)
            self.stage_logger.log(
                "response_pipeline",
                "continue",
                reason="intent_force_plaintext_completion",
                source="force_plaintext_gate",
            )
            return ResponsePipelineOutcome.continue_with(
                self.prompt_builder.build_plain_text_completion_prompt(
                    ctx.state_machine,
                    {
                        "reason": "intent_force_plaintext_completion",
                        "recoverable": True,
                        "error_code": "INTENT_FORCE_PLAINTEXT_COMPLETION",
                        "next_actions": [],
                        "intent_allowed_actions": [],
                        "next_actions_source": "intent",
                    },
                ),
                response_text=response,
                segments=segments,
                parsed_output=parsed_output,
                parsed_action_count=0,
                malformed_action_retries=0,
                audit_marker_retries=0,
                reason="intent_force_plaintext_completion",
                source="force_plaintext_gate",
            )

        if reflection_repair_pending and self.semantics.is_reflection_only_repair_turn(
            raw_response, parsed_output, parsed_action_count
        ):
            self.guards.set_reflection_repair_pending(False)
            self.guards.set_nonproductive_thinking_state(False)
            self.stage_logger.log(
                "response_pipeline",
                "continue",
                reason="think_reflection_repair_completed",
                source="think_reflection_guard",
            )
            return ResponsePipelineOutcome.continue_with(
                self.prompt_builder.build_reflection_repair_accepted_prompt(),
                response_text=response,
                segments=segments,
                parsed_output=parsed_output,
                parsed_action_count=0,
                malformed_action_retries=0,
                audit_marker_retries=0,
                reason="think_reflection_repair_completed",
                source="think_reflection_guard",
            )

        legacy_plaintext_answer_path = self.semantics.is_plaintext_answer_path(
            raw_response,
            parsed_output,
            parsed_action_count,
        )
        terminal_answer_switch = get_switch("terminal_answer.plaintext_terminal_answer")
        terminal_answer_authority = resolve_plaintext_terminal_answer_authority(
            parsed_output,
            legacy_plaintext_answer_path=legacy_plaintext_answer_path,
            switch_value=terminal_answer_switch,
        )
        self._log_terminal_answer_authority_resolution(terminal_answer_authority)
        has_memory_update_done = getattr(self.semantics, "has_memory_update_done", None)
        looks_like_leaked_system_result = getattr(
            self.semantics,
            "looks_like_leaked_system_result",
            None,
        )
        legacy_checkpoint_only_active = bool(
            callable(has_memory_update_done)
            and has_memory_update_done(raw_response)
            and not legacy_plaintext_answer_path
            and not self.semantics.has_any_action_proposal(parsed_output, parsed_action_count)
            and not (
                callable(looks_like_leaked_system_result)
                and looks_like_leaked_system_result(raw_response)
            )
            and not str(getattr(parsed_output, "invalid_kind", "") or "").strip()
        )
        checkpoint_only_switch = get_switch("terminal_answer.checkpoint_only")
        checkpoint_only_authority = resolve_checkpoint_only_terminal_authority(
            parsed_output,
            legacy_checkpoint_only_active=legacy_checkpoint_only_active,
            switch_value=checkpoint_only_switch,
        )
        self._log_terminal_answer_authority_resolution(checkpoint_only_authority)

        is_invalid_truncated, _, _ = terminal_plaintext_completion_status(raw_response)
        invalid_truncated_authority = resolve_invalid_truncated_terminal_text_recovery_authority(
            parsed_output,
            legacy_invalid_truncated_active=is_invalid_truncated,
            legacy_decision=None,
            switch_value=get_switch("recovery.invalid_truncated_terminal_text"),
            parsed_action_count=parsed_action_count,
        )
        self._log_recovery_authority_resolution(invalid_truncated_authority.diagnostic)

        effective_plaintext_answer_path = legacy_plaintext_answer_path
        if (
            terminal_answer_switch == "compiler"
            and terminal_answer_authority.authority_source == "compiler"
            and terminal_answer_authority.clean_plaintext_candidate
            and terminal_answer_authority.agreement
            and not terminal_answer_authority.blocking_reasons
            and not terminal_answer_authority.behavior_changed
        ):
            effective_plaintext_answer_path = bool(terminal_answer_authority.effective_value)
        reflection_only_repair = self.semantics.is_reflection_only_repair_turn(
            raw_response, parsed_output, parsed_action_count
        )

        durable_state_repair = self.semantics.is_durable_state_repair_turn(
            raw_response,
            parsed_output,
            parsed_action_count,
            required_kind=reflection_repair_kind,
        )

        if reflection_repair_pending:
            if durable_state_repair:
                self.stage_logger.log_architecture_defect(
                    reflection_repair_kind or "missing_think_reflection",
                    "repair_completed",
                    source_stage="response_pipeline",
                )
                self.guards.set_reflection_repair_pending(False)
                self.guards.set_nonproductive_thinking_state(False)
                self.stage_logger.log(
                    "response_pipeline",
                    "continue",
                    reason="think_reflection_repair_completed",
                    source="think_reflection_guard",
                )
                return ResponsePipelineOutcome.continue_with(
                    self.prompt_builder.build_reflection_repair_accepted_prompt(),
                    response_text=response,
                    segments=segments,
                    parsed_output=parsed_output,
                    parsed_action_count=0,
                    malformed_action_retries=0,
                    audit_marker_retries=0,
                    reason="think_reflection_repair_completed",
                    source="think_reflection_guard",
                )
            self.stage_logger.log_architecture_defect(
                reflection_repair_kind or "missing_think_reflection",
                "repair_enforced",
                source_stage="response_pipeline",
            )
            self.stage_logger.log(
                "response_pipeline",
                "continue",
                reason=reflection_repair_kind or "missing_think_reflection",
                source="think_reflection_guard",
            )
            return ResponsePipelineOutcome.continue_with(
                self.prompt_builder.build_durable_state_repair_prompt(reflection_repair_kind),
                response_text=response,
                segments=segments,
                parsed_output=parsed_output,
                parsed_action_count=0,
                malformed_action_retries=0,
                audit_marker_retries=0,
                reason=reflection_repair_kind or "missing_think_reflection",
                source="think_reflection_guard",
            )

        if (
            memory_checkpoint_and_text
            and not self.semantics.has_any_action_proposal(parsed_output, parsed_action_count)
        ):
            self.guards.set_reflection_repair_pending(False)
            self.guards.set_nonproductive_thinking_state(False)
            self.stage_logger.log(
                "response_pipeline",
                "dispatch",
                reason="memory_checkpoint_and_text",
                source="memory_board",
                action_count=0,
            )
            return ResponsePipelineOutcome.dispatch_ready(
                response_text=response,
                segments=segments,
                parsed_output=parsed_output,
                parsed_action_count=0,
                malformed_action_retries=0,
                audit_marker_retries=0,
                reason="dispatch_ready",
                source="response_pipeline",
                memory_checkpoint_and_text=True,
            )

        if not self.semantics.has_any_action_proposal(parsed_output, parsed_action_count):
            typed_result = getattr(parsed_output, "terminal_answer_semantic_result", None)
            is_typed_leak = (
                typed_result is not None
                and typed_result.kind == TerminalAnswerKind.LEAKED_SYSTEM_RESULT
            )
            legacy_leak_active = True if is_typed_leak else is_leaked_system_result(response)
            if is_typed_leak or legacy_leak_active:
                legacy_outcome = ResponsePipelineOutcome.continue_with(
                    self.prompt_builder.build_leaked_system_result_recovery_prompt(),
                    response_text=response,
                    segments=segments,
                    parsed_output=parsed_output,
                    parsed_action_count=0,
                    malformed_action_retries=0,
                    audit_marker_retries=0,
                    reason="leaked_system_result_in_assistant_text",
                    source="output_recovery",
                )
                authority_resolution = resolve_leaked_system_result_recovery_authority(
                    parsed_output,
                    legacy_leak_active=legacy_leak_active,
                    legacy_decision=legacy_outcome,
                    switch_value=get_switch("recovery.leaked_system_result"),
                    parsed_action_count=parsed_action_count,
                )
                self._log_recovery_authority_resolution(authority_resolution.diagnostic)
                self.guards.set_reflection_repair_pending(False)
                self.guards.set_nonproductive_thinking_state(False)
                self.stage_logger.log(
                    "response_pipeline",
                    "continue",
                    reason="leaked_system_result_in_assistant_text",
                    source="output_recovery",
                )
                return authority_resolution.effective_decision

        authority = resolve_protocol_authority(parsed_output, parsed_action_count)
        if authority.suppress_legacy_invalid_kind:
            self.stage_logger.log(
                "response_pipeline",
                "pass",
                reason=f"compiler_authority_override:{authority.reason}",
                source=f"protocol_authority:{authority.source}",
            )
            parsed_output.invalid_kind = ""
        elif authority.dispatch_allowed is False:
            compiler_invalid_kind = compiler_invalid_kind_for_output(parsed_output)
            if compiler_invalid_kind:
                parsed_output.invalid_kind = compiler_invalid_kind

        recovery_decision = await self.output_recovery.decide(
            parsed_output,
            malformed_action_retries=ctx.malformed_action_retries,
            audit_marker_retries=ctx.audit_marker_retries,
        )
        if recovery_decision.handled:
            if bool(getattr(self.state, "terminal_plaintext_completion_pending", False)):
                self.stage_logger.log(
                    "response_pipeline",
                    "stop",
                    reason=recovery_decision.reason or "terminal_plaintext_completion",
                    source="output_recovery",
                )
                return ResponsePipelineOutcome.stop(
                    response_text=response,
                    malformed_action_retries=recovery_decision.malformed_action_retries,
                    audit_marker_retries=recovery_decision.audit_marker_retries,
                    reason=recovery_decision.reason or "terminal_plaintext_completion",
                    source="output_recovery",
                )
            self.stage_logger.log(
                "response_pipeline",
                "continue",
                reason=recovery_decision.reason,
                source="output_recovery",
            )
            return ResponsePipelineOutcome.continue_with(
                recovery_decision.next_query,
                response_text=response,
                segments=segments,
                parsed_output=parsed_output,
                parsed_action_count=parsed_action_count,
                malformed_action_retries=recovery_decision.malformed_action_retries,
                audit_marker_retries=recovery_decision.audit_marker_retries,
                reason=recovery_decision.reason,
                source="output_recovery",
            )

        # The thinking guard runs *after* specific output recovery. This ensures
        # that a response with a specific structural flaw (e.g., action_inside_think)
        # is handled by its specific recovery logic, rather than being masked by
        # the more general non-productive thinking check.
        if self.guards.is_nonproductive_thinking_turn(
            self.semantics,
            raw_response,
            parsed_output,
            parsed_action_count,
            plaintext_answer_path=effective_plaintext_answer_path,
            intent_transition_handled=False,
            memory_checkpoint_and_action=memory_checkpoint_and_action,
            memory_checkpoint_and_text=memory_checkpoint_and_text,
            reflection_only_repair=reflection_only_repair,
        ):
            nonproductive_streak = self.guards.set_nonproductive_thinking_state(
                True, "repeated_thinking_without_valid_output"
            )
            if nonproductive_streak >= self.nonproductive_thinking_hard_stop_streak:
                self.stage_logger.log(
                    "response_pipeline",
                    "continue",
                    reason="repeated_thinking_without_valid_output",
                    source="thinking_guard",
                    streak=nonproductive_streak,
                )
                return ResponsePipelineOutcome.continue_with(
                    self.prompt_builder.build_repeated_thinking_without_valid_output_prompt(
                        {"reason": "repeated_thinking_without_valid_output"}
                    ),
                    response_text=response,
                    segments=segments,
                    parsed_output=parsed_output,
                    parsed_action_count=parsed_action_count,
                    malformed_action_retries=0,
                    audit_marker_retries=0,
                    reason="repeated_thinking_without_valid_output",
                    source="thinking_guard",
                )
        else:
            self.guards.set_nonproductive_thinking_state(False)

        if str(getattr(parsed_output, "invalid_kind", "") or "").strip() in self.STRUCTURAL_INVALID_KINDS:
            if authority.suppress_legacy_invalid_kind:
                self.stage_logger.log(
                    "response_pipeline",
                    "pass",
                    reason=authority.reason,
                    source=f"protocol_authority:{authority.source}",
                )
            else:
                self.stage_logger.log(
                    "response_pipeline",
                    "continue",
                    reason=parsed_output.invalid_kind,
                    source="structural_invalid_guard",
                )
                return ResponsePipelineOutcome.continue_with(
                    self.prompt_builder.build_missing_action_or_answer_prompt(),
                    response_text=response,
                    segments=segments,
                    parsed_output=parsed_output,
                    parsed_action_count=0,
                    malformed_action_retries=0,
                    audit_marker_retries=0,
                    reason=parsed_output.invalid_kind,
                    source="structural_invalid_guard",
                )

        try:
            action_policy_decision = await self.action_policy.decide(
                ctx,
                segments,
                intent_payload=step.intent_payload,
                parsed_output=parsed_output,
            )
        except TypeError:
            action_policy_decision = await self.action_policy.decide(
                ctx,
                segments,
                intent_payload=step.intent_payload,
            )
        parsed_action_count = action_policy_decision.parsed_action_count
        if parsed_action_count > 1 and not self._multiple_actions_are_pure_read_only(segments):
            self.stage_logger.log(
                "response_pipeline",
                "continue",
                reason="multiple_actions",
                source="transaction_guard",
                action_count=parsed_action_count,
            )
            return ResponsePipelineOutcome.continue_with(
                self.prompt_builder.build_multiple_actions_prompt(),
                response_text=response,
                segments=segments,
                parsed_output=parsed_output,
                parsed_action_count=parsed_action_count,
                malformed_action_retries=0,
                audit_marker_retries=0,
                reason="multiple_actions",
                source="transaction_guard",
            )
        if parsed_action_count > 1:
            self.stage_logger.log(
                "response_pipeline",
                "pass",
                reason="pure_readonly_batch_allowed",
                source="transaction_guard",
                action_count=parsed_action_count,
            )
        if self._has_any_action_proposal(parsed_output, parsed_action_count=parsed_action_count):
            self.guards.set_nonproductive_thinking_state(False)

        if action_policy_decision.handled:
            if bool(getattr(self.state, "terminal_plaintext_completion_pending", False)):
                terminal_text = self._terminal_plaintext_text_or_empty(
                    str(getattr(self.state, "terminal_plaintext_completion_text", "") or response or "")
                )
                setattr(self.state, "terminal_plaintext_completion_text", terminal_text)
                self.stage_logger.log(
                    "response_pipeline",
                    "stop",
                    reason=action_policy_decision.reason or "terminal_plaintext_completion",
                    source=action_policy_decision.source or "action_policy",
                )
                return ResponsePipelineOutcome.stop(
                    response_text=response,
                    malformed_action_retries=0,
                    audit_marker_retries=0,
                    reason=action_policy_decision.reason or "terminal_plaintext_completion",
                    source=action_policy_decision.source or "action_policy",
                )
            return ResponsePipelineOutcome.continue_with(
                action_policy_decision.next_query,
                response_text=response,
                segments=segments,
                parsed_output=parsed_output,
                parsed_action_count=parsed_action_count,
                reason=action_policy_decision.reason,
                source=action_policy_decision.source,
            )

        if self.semantics.has_any_action_proposal(parsed_output, parsed_action_count):
            self.guards.clear_terminal_plaintext_completion()

        zero_action_invalid = (
            not self.semantics.has_any_action_proposal(parsed_output, parsed_action_count)
            and bool(str(parsed_output.invalid_kind or "").strip())
        )
        if zero_action_invalid:
            self.stage_logger.log(
                "response_pipeline",
                "continue",
                reason=parsed_output.invalid_kind,
                source="zero_action_invalid_guard",
            )
            return ResponsePipelineOutcome.continue_with(
                self.prompt_builder.build_missing_action_or_answer_prompt(),
                response_text=response,
                segments=segments,
                parsed_output=parsed_output,
                parsed_action_count=0,
                malformed_action_retries=0,
                audit_marker_retries=0,
                reason=parsed_output.invalid_kind,
                source="zero_action_invalid_guard",
            )

        self.guards.set_reflection_repair_pending(False)
        self.guards.set_nonproductive_thinking_state(False)
        self.stage_logger.log(
            "response_pipeline",
            "dispatch",
            action_count=parsed_action_count,
            execution_plan=(
                {
                    "shape": execution_plan.shape,
                    "transaction_kind": execution_plan.transaction_kind,
                    "bundle_validated": execution_plan.bundle_validated,
                    "transition_applied": execution_plan.transition_applied,
                    "action_dispatched": execution_plan.action_dispatched,
                    "before_active_intent_id": execution_plan.before_active_intent_id,
                    "after_active_intent_id": execution_plan.after_active_intent_id,
                    "action_effects": list(execution_plan.action_effects),
                }
                if (execution_plan := self._build_execution_plan(step, parsed_output, parsed_action_count=parsed_action_count)) is not None
                else None
            ),
        )
        return ResponsePipelineOutcome.dispatch_ready(
            response_text=response,
            segments=segments,
            parsed_output=parsed_output,
            parsed_action_count=parsed_action_count,
            execution_plan=execution_plan,
            malformed_action_retries=0,
            audit_marker_retries=0,
            reason="dispatch_ready",
            source="response_pipeline",
            memory_checkpoint_and_text=bool(getattr(memory_board_decision, "memory_checkpoint_and_text", False)),
        )
