"""Canonical normalization of recovery policy and allowed-action hints."""

from __future__ import annotations

from ..allowed_actions_resolver import AllowedActionsContext, AllowedActionsResolver
from .decision_models import RecoveryContext


class RecoveryPolicyResolver:
    def __init__(self, allowed_actions_resolver: AllowedActionsResolver | None = None):
        self.allowed_actions_resolver = allowed_actions_resolver or AllowedActionsResolver()

    def normalize_context(
        self,
        stop_info: dict | RecoveryContext | None,
        *,
        active_intent=None,
    ) -> RecoveryContext:
        ctx = stop_info if isinstance(stop_info, RecoveryContext) else RecoveryContext.from_stop_info(stop_info)
        if ctx.resolved_action_policy() is not None:
            return ctx

        resolved = self.allowed_actions_resolver.resolve_stop_info(
            AllowedActionsContext(
                reason=ctx.reason,
                source=ctx.next_actions_source,
                next_actions=ctx.next_actions,
                intent_actions=ctx.intent_allowed_actions,
                recommended_actions=ctx.recommended_next_actions,
                active_intent_allowed_actions=getattr(active_intent, "allowed_actions", []) if active_intent is not None else [],
                active_intent_type=getattr(active_intent, "intent_type", "") if active_intent is not None else "",
            )
        )
        ctx.policy_allowed_actions = list(resolved.allowed_actions)
        ctx.policy_recommended_actions = list(resolved.recommended_actions)
        ctx.policy_blocked_actions = list(resolved.blocked_actions)
        ctx.policy_intent_actions = list(resolved.intent_actions)
        ctx.policy_authoritative_source = str(resolved.authoritative_source or "")
        ctx.policy_keep_current_intent = bool(resolved.keep_current_intent)
        return ctx

    def should_prefer_current_intent_recovery(self, ctx: RecoveryContext, *, active_intent=None) -> bool:
        reason = str(ctx.reason or "").strip()
        if active_intent is None:
            return False
        if reason in {
            "intent_step_limit_soft_exceeded",
            "user_approved_more_steps_after_hard_limit",
            "intent_blocked_action_signature",
            "retry_or_continuation_after_failure",
            "unnecessary_intent_reactivation_or_replace",
            "suspect_intent_relabel_repeat",
        }:
            return True

        if reason != "action_not_allowed_in_phase":
            return False

        resolved = ctx.resolved_action_policy()
        active_allowed = {
            str(action).strip()
            for action in (getattr(active_intent, "allowed_actions", []) or [])
            if str(action).strip()
        }
        if not active_allowed:
            return False

        active_type = str(getattr(active_intent, "intent_type", "") or "").strip().upper()
        if active_type == "MODIFY":
            return False

        source = str((resolved.authoritative_source if resolved is not None else ctx.next_actions_source) or "").strip().lower()
        recommended_actions = list((resolved.recommended_actions if resolved is not None else ctx.recommended_next_actions) or [])

        if source == "recommended" and not recommended_actions:
            return True

        next_set = {str(action).strip() for action in recommended_actions if str(action).strip()}
        if next_set and not next_set.issubset(active_allowed):
            return True

        return self.allowed_actions_resolver.should_enforce_current_intent_constraints(reason, active_type) and source == "recommended"
