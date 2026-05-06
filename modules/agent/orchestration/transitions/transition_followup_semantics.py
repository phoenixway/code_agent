"""Compiler-backed followup-surface analysis for intent transitions."""

from __future__ import annotations

from dataclasses import dataclass

from ..protocol.models import ActionNode, IntentNode, VisibleTextNode


@dataclass(frozen=True)
class FollowupSurfaceSummary:
    analysis: object | None
    intent_count: int = 0
    action_count: int = 0
    visible_count: int = 0
    has_substantive_nodes: bool = False
    has_any_action: bool = False
    conflict_reason: str = ""
    bundle_too_dense: bool = False


@dataclass(frozen=True)
class PostAcceptanceFollowupDecision:
    kind: str
    conflict_reason: str = ""
    has_any_action: bool = False


@dataclass(frozen=True)
class RejectedTransitionDecision:
    kind: str
    strict: bool = False


@dataclass(frozen=True)
class TransitionSemanticDecision:
    phase: str
    kind: str
    conflict_reason: str = ""
    has_any_action: bool = False
    strict: bool = False


class TransitionFollowupSemantics:
    def summarize(self, analysis) -> FollowupSurfaceSummary:
        if analysis is None or getattr(analysis, "ast", None) is None:
            return FollowupSurfaceSummary(analysis=analysis)

        intent_count = 0
        action_count = 0
        visible_count = 0
        for node in list(getattr(analysis.ast, "nodes", ()) or ()):
            if isinstance(node, IntentNode):
                intent_count += 1
                continue
            if isinstance(node, ActionNode):
                action_count += 1
                continue
            if isinstance(node, VisibleTextNode) and str(getattr(node, "text", "") or "").strip():
                visible_count += 1

        error_code = str(getattr(getattr(analysis, "error", None), "code", "") or "").strip()
        has_any_action = action_count > 0 or error_code == "E_ATOMIC_BUNDLE_REQUIRES_EXACTLY_ONE_ACTION"

        conflict_reason = ""
        if intent_count >= 1:
            conflict_reason = "conflicting_intent_transitions"
        elif action_count >= 2 or error_code == "E_ATOMIC_BUNDLE_REQUIRES_EXACTLY_ONE_ACTION":
            conflict_reason = "multiple_actions"

        return FollowupSurfaceSummary(
            analysis=analysis,
            intent_count=intent_count,
            action_count=action_count,
            visible_count=visible_count,
            has_substantive_nodes=bool(intent_count or action_count or visible_count),
            has_any_action=has_any_action,
            conflict_reason=conflict_reason,
            bundle_too_dense=bool(
                intent_count >= 1
                or action_count >= 2
                or error_code == "E_ATOMIC_BUNDLE_REQUIRES_EXACTLY_ONE_ACTION"
            ),
        )

    def evaluate_transition(
        self,
        *,
        phase: str,
        summary: FollowupSurfaceSummary,
        payload_mode: str = "",
        completion_requested: bool = False,
        transition_only_required: bool = False,
        reuse_only_required: bool = False,
        rejection_reason: str = "",
        defect_count: int = 0,
        has_active_intent: bool = False,
    ) -> TransitionSemanticDecision:
        if phase == "accepted":
            if transition_only_required and summary.has_any_action:
                return TransitionSemanticDecision(
                    phase=phase,
                    kind="transition_only_recovery_cannot_bundle_action",
                    has_any_action=summary.has_any_action,
                )
            if payload_mode == "reuse" and reuse_only_required and summary.has_any_action:
                return TransitionSemanticDecision(
                    phase=phase,
                    kind="reuse_only_transition_cannot_bundle_action",
                    has_any_action=summary.has_any_action,
                )
            if not summary.has_substantive_nodes:
                return TransitionSemanticDecision(
                    phase=phase,
                    kind="no_followup",
                    has_any_action=summary.has_any_action,
                )
            if completion_requested and summary.has_any_action:
                return TransitionSemanticDecision(
                    phase=phase,
                    kind="intent_complete_with_action_not_allowed",
                    has_any_action=summary.has_any_action,
                )
            if completion_requested and summary.conflict_reason:
                return TransitionSemanticDecision(
                    phase=phase,
                    kind="followup_conflict",
                    conflict_reason=summary.conflict_reason,
                    has_any_action=summary.has_any_action,
                )
            if (
                payload_mode == "reuse"
                and summary.intent_count == 0
                and summary.action_count == 0
                and summary.visible_count > 0
            ):
                return TransitionSemanticDecision(
                    phase=phase,
                    kind="intent_reuse_applied_with_inline_plaintext_answer",
                    has_any_action=summary.has_any_action,
                )
            if (
                payload_mode == "reuse"
                and summary.intent_count == 0
                and summary.action_count == 1
                and summary.visible_count == 0
                and getattr(getattr(summary.analysis, "shape", None), "name", "") == "ACTION_ONLY"
                and getattr(summary.analysis, "error", None) is None
            ):
                return TransitionSemanticDecision(
                    phase=phase,
                    kind="intent_reuse_applied_with_inline_followup_action",
                    has_any_action=summary.has_any_action,
                )
            if (
                summary.intent_count == 0
                and summary.action_count == 1
                and summary.visible_count == 0
                and getattr(getattr(summary.analysis, "shape", None), "name", "") == "ACTION_ONLY"
                and getattr(summary.analysis, "error", None) is None
            ):
                return TransitionSemanticDecision(
                    phase=phase,
                    kind="intent_applied_with_followup_action",
                    has_any_action=summary.has_any_action,
                )
            if summary.conflict_reason:
                return TransitionSemanticDecision(
                    phase=phase,
                    kind="followup_conflict",
                    conflict_reason=summary.conflict_reason,
                    has_any_action=summary.has_any_action,
                )
            return TransitionSemanticDecision(
                phase=phase,
                kind="intent_accepted_awaiting_next_output",
                has_any_action=summary.has_any_action,
            )

        if defect_count >= 3 and rejection_reason in {
            "intent_reuse_without_active_intent",
            "intent_switch_reason_required",
            "conflicting_intent_transitions",
        }:
            return TransitionSemanticDecision(
                phase=phase,
                kind="terminal_repeated_intent_transition_defect",
            )

        if rejection_reason == "intent_reuse_without_active_intent":
            return TransitionSemanticDecision(
                phase=phase,
                kind="intent_reuse_without_active_intent",
                strict=defect_count >= 2,
            )

        if (
            rejection_reason == "unnecessary_intent_reactivation_or_replace"
            and has_active_intent
            and summary.intent_count == 0
            and summary.action_count == 1
            and summary.visible_count == 0
            and getattr(getattr(summary.analysis, "shape", None), "name", "") == "ACTION_ONLY"
            and getattr(summary.analysis, "error", None) is None
        ):
            return TransitionSemanticDecision(
                phase=phase,
                kind="ignored_redundant_intent_reactivation_with_followup_action",
            )

        return TransitionSemanticDecision(phase=phase, kind="generic_rejected_transition")

    def evaluate_post_acceptance(
        self,
        *,
        payload_mode: str,
        completion_requested: bool,
        transition_only_required: bool,
        reuse_only_required: bool,
        summary: FollowupSurfaceSummary,
    ) -> PostAcceptanceFollowupDecision:
        decision = self.evaluate_transition(
            phase="accepted",
            payload_mode=payload_mode,
            completion_requested=completion_requested,
            transition_only_required=transition_only_required,
            reuse_only_required=reuse_only_required,
            summary=summary,
        )
        return PostAcceptanceFollowupDecision(
            kind=decision.kind,
            conflict_reason=decision.conflict_reason,
            has_any_action=decision.has_any_action,
        )

    def evaluate_rejected_transition(
        self,
        *,
        rejection_reason: str,
        defect_count: int,
        has_active_intent: bool,
        summary: FollowupSurfaceSummary,
    ) -> RejectedTransitionDecision:
        decision = self.evaluate_transition(
            phase="rejected",
            rejection_reason=rejection_reason,
            defect_count=defect_count,
            has_active_intent=has_active_intent,
            summary=summary,
        )
        return RejectedTransitionDecision(
            kind=decision.kind,
            strict=decision.strict,
        )
