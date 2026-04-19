"""Canonical resolver for allowed/recommended action hints."""

from __future__ import annotations

from dataclasses import dataclass, field


KEEP_CURRENT_INTENT_REASONS = {
    "action_not_allowed_in_phase",
    "intent_step_limit_soft_exceeded",
    "intent_step_limit_exceeded",
    "intent_step_limit_exceeded_repeated",
    "intent_blocked_action_signature",
    "intent_action_not_allowed",
    "intent_blocked_action",
    "retry_or_continuation_after_failure",
    "user_approved_more_steps_after_hard_limit",
    "unnecessary_intent_reactivation_or_replace",
    "suspect_intent_relabel_repeat",
}


@dataclass
class AllowedActionsContext:
    reason: str = ""
    source: str = ""
    next_actions: list[str] = field(default_factory=list)
    intent_actions: list[str] = field(default_factory=list)
    recommended_actions: list[str] = field(default_factory=list)
    active_intent_allowed_actions: list[str] = field(default_factory=list)
    active_intent_type: str = ""


@dataclass
class ResolvedAllowedActions:
    allowed_actions: list[str] = field(default_factory=list)
    recommended_actions: list[str] = field(default_factory=list)
    blocked_actions: list[str] = field(default_factory=list)
    authoritative_source: str = ""
    intent_actions: list[str] = field(default_factory=list)
    recovery_actions: list[str] = field(default_factory=list)
    keep_current_intent: bool = False


class AllowedActionsResolver:
    def normalize_action_list(self, actions) -> list[str]:
        if not isinstance(actions, list):
            return []
        normalized: list[str] = []
        seen: set[str] = set()
        for item in actions:
            value = str(item or "").strip()
            if not value or value in seen:
                continue
            seen.add(value)
            normalized.append(value)
        return normalized

    def should_enforce_current_intent_constraints(
        self,
        reason: str,
        active_intent_type: str = "",
    ) -> bool:
        reason_value = str(reason or "").strip().lower()
        active_type = str(active_intent_type or "").strip().upper()
        if not active_type:
            return False
        if active_type == "MODIFY":
            return False
        return reason_value in KEEP_CURRENT_INTENT_REASONS

    def resolve_stop_info(self, ctx: AllowedActionsContext) -> ResolvedAllowedActions:
        source_value = str(ctx.source or "").strip().lower()
        active_allowed = self.normalize_action_list(ctx.active_intent_allowed_actions)

        resolved_intent = self.normalize_action_list(ctx.intent_actions)
        resolved_recommended = self.normalize_action_list(ctx.recommended_actions)
        legacy = self.normalize_action_list(ctx.next_actions)

        if not resolved_intent and source_value == "intent":
            resolved_intent = legacy
        if not resolved_recommended and source_value == "recommended":
            resolved_recommended = legacy
        if not resolved_recommended and source_value == "phase":
            resolved_recommended = legacy

        keep_current_intent = self.should_enforce_current_intent_constraints(
            ctx.reason,
            ctx.active_intent_type,
        )

        if active_allowed:
            if resolved_intent:
                resolved_intent = [action for action in resolved_intent if action in active_allowed]
            if keep_current_intent and resolved_recommended:
                resolved_recommended = [action for action in resolved_recommended if action in active_allowed]

        if not resolved_intent and source_value == "intent" and active_allowed:
            resolved_intent = active_allowed[:]

        if not resolved_recommended and source_value in {"recommended", "phase"} and active_allowed and keep_current_intent:
            resolved_recommended = active_allowed[:]

        authoritative_source = source_value
        if resolved_intent:
            authoritative_source = "intent"
        elif resolved_recommended:
            authoritative_source = "recommended"

        allowed_actions = resolved_intent or resolved_recommended or active_allowed[:]
        blocked_actions = []
        if active_allowed and authoritative_source == "recommended":
            union = set(resolved_recommended)
            blocked_actions = [action for action in active_allowed if action not in union]

        return ResolvedAllowedActions(
            allowed_actions=allowed_actions,
            recommended_actions=resolved_recommended,
            blocked_actions=blocked_actions,
            authoritative_source=authoritative_source,
            intent_actions=resolved_intent,
            recovery_actions=legacy,
            keep_current_intent=keep_current_intent,
        )
