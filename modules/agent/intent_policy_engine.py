from __future__ import annotations

import logging
import re
from typing import Any

try:
    from modules.agent.intent_policy_models import (
        BlockedActionPolicyContext,
        IntentPolicyContext,
        IntentPolicyDecision,
    )
except ImportError:
    try:
        from .intent_policy_models import (
            BlockedActionPolicyContext,
            IntentPolicyContext,
            IntentPolicyDecision,
        )
    except ImportError:
        from intent_policy_models import (
            BlockedActionPolicyContext,
            IntentPolicyContext,
            IntentPolicyDecision,
        )


class IntentPolicyEngine:
    """
    Centralized policy reducer for intent transitions and blocked-action semantics.
    """

    def __init__(self, config: Any):
        self.config = config
        from modules.logger import get_debug_logger
        self.log = get_debug_logger()
    def _normalize_goal(self, goal: str) -> str:
        goal = str(goal or "").lower().strip()
        goal = re.sub(r"[^a-zа-яіїє0-9]+", " ", goal)
        return re.sub(r"\s+", " ", goal).strip()

    def _goal_tokens(self, goal: str) -> list[str]:
        return [t for t in self._normalize_goal(goal).split() if t]

    def _goal_similarity(self, a: str, b: str) -> float:
        na = set(self._goal_tokens(a))
        nb = set(self._goal_tokens(b))
        if not na or not nb:
            return 0.0
        return len(na & nb) / max(1, len(na | nb))

    def _allowed_actions_overlap(self, a: list[str], b: list[str]) -> float:
        sa = set(a or [])
        sb = set(b or [])
        if not sa or not sb:
            return 0.0
        return len(sa & sb) / max(1, len(sa | sb))

    def _looks_like_local_step_goal(self, goal: str) -> bool:
        normalized = self._normalize_goal(goal)
        if not normalized:
            return True
        local_markers = {
            "inspect", "read", "find", "locate", "analyze", "examine", "search",
            "прочитати", "читати", "знайти", "пошук", "проаналізувати", "дослідити",
            "переглянути", "локалізувати", "оглянути",
        }
        tokens = set(normalized.split())
        has_local_marker = bool(tokens & local_markers)
        if len(tokens) <= 5 and has_local_marker:
            return True
        bad_prefixes = (
            "inspect ", "read ", "find ", "locate ", "analyze ", "examine ", "search ",
            "прочитати ", "знайти ", "проаналізувати ", "дослідити ", "переглянути ",
        )
        return normalized.startswith(bad_prefixes)

    def _goal_core_loss(self, old_goal: str, new_goal: str) -> bool:
        old_tokens = set(self._goal_tokens(old_goal))
        new_tokens = set(self._goal_tokens(new_goal))
        if not new_tokens:
            return True
        if not old_tokens:
            return False
        overlap = len(old_tokens & new_tokens) / max(1, len(old_tokens))
        threshold = float(getattr(self.config, "INTENT_RELABEL_GOAL_CORE_OVERLAP_THRESHOLD", 0.45))
        return overlap < threshold or self._looks_like_local_step_goal(new_goal)

    def _same_lineage(self, active: Any | None, proposed: Any | None, transition_info: dict) -> bool:
        if isinstance(transition_info, dict) and "same_lineage" in transition_info:
            return bool(transition_info.get("same_lineage"))
        if active is None or proposed is None:
            return False
        if proposed.intent_id == active.intent_id:
            return True
        if proposed.intent_type != active.intent_type:
            return False
        baseline_goal = getattr(active, "canonical_goal", "") or getattr(active, "goal", "")
        candidate_goal = getattr(proposed, "canonical_goal", "") or getattr(proposed, "goal", "")
        goal_sim = self._goal_similarity(candidate_goal, baseline_goal)
        actions_overlap = self._allowed_actions_overlap(
            getattr(proposed, "allowed_actions", []) or [],
            getattr(active, "allowed_actions", []) or [],
        )
        return (
            goal_sim >= float(getattr(self.config, "INTENT_RELABEL_GOAL_SIMILARITY_THRESHOLD", 0.6))
            and actions_overlap >= float(getattr(self.config, "INTENT_RELABEL_ACTION_OVERLAP_THRESHOLD", 0.6))
        )


    def _decision_log_payload(
        self,
        *,
        stage: str,
        decision: IntentPolicyDecision,
        ctx: IntentPolicyContext | None = None,
        extra: dict | None = None,
    ) -> dict:
        active = getattr(ctx, "active_intent", None) if ctx is not None else None
        proposed = getattr(ctx, "proposed_intent", None) if ctx is not None else None
        transition_info = dict(getattr(ctx, "transition_info", {}) or {}) if ctx is not None else {}

        payload = {
            "stage": stage,
            "allowed": decision.allowed,
            "reason": decision.reason,
            "error_code": decision.error_code,
            "message_key": decision.message_key,
            "recoverable": decision.recoverable,
            "keep_current_intent": decision.keep_current_intent,
            "allow_user_handoff": decision.allow_user_handoff,
            "allow_once_via_state_method": decision.allow_once_via_state_method or "",
            "active_intent_id": getattr(active, "intent_id", "") if active is not None else "",
            "proposed_intent_id": getattr(proposed, "intent_id", "") if proposed is not None else "",
            "active_goal": getattr(active, "canonical_goal", "") or getattr(active, "goal", "") if active is not None else "",
            "proposed_goal": getattr(proposed, "goal", "") if proposed is not None else "",
            "mode": getattr(proposed, "mode", "") if proposed is not None else "",
            "same_lineage": bool(transition_info.get("same_lineage")),
            "goal_similarity": transition_info.get("goal_similarity", ""),
            "actions_overlap": transition_info.get("actions_overlap", ""),
            "next_actions": list(decision.next_actions or []),
        }
        if extra:
            payload.update(extra)
        if decision.metadata:
            payload["metadata"] = dict(decision.metadata)
        return payload

    def _log_decision(
        self,
        *,
        stage: str,
        decision: IntentPolicyDecision,
        ctx: IntentPolicyContext | None = None,
        extra: dict | None = None,
    ) -> None:
        payload = self._decision_log_payload(stage=stage, decision=decision, ctx=ctx, extra=extra)
        level = logging.INFO if decision.allowed else logging.WARNING
        msg = (
            "IntentPolicy.%s allowed=%s reason=%s message_key=%s active_intent_id=%s "
            "proposed_intent_id=%s mode=%s same_lineage=%s"
        ) % (
            payload["stage"],
            payload["allowed"],
            payload["reason"],
            payload["message_key"],
            payload["active_intent_id"],
            payload["proposed_intent_id"],
            payload["mode"],
            payload["same_lineage"],
        )
        self.log.log(level, msg, extra={"intent_policy": payload})

    def evaluate_goal_change(self, ctx: IntentPolicyContext) -> IntentPolicyDecision | None:
        active = ctx.active_intent
        proposed = ctx.proposed_intent
        if active is None or proposed is None:
            return None

        same_lineage = self._same_lineage(active, proposed, ctx.transition_info or {})
        if not same_lineage:
            return None

        active_goal = getattr(active, "canonical_goal", "") or getattr(active, "goal", "")
        proposed_goal = getattr(proposed, "goal", "")
        if self._normalize_goal(active_goal) == self._normalize_goal(proposed_goal):
            return None

        if getattr(proposed, "mode", "") == "retry":
            decision = IntentPolicyDecision(
                allowed=False,
                reason="retry_goal_change_forbidden",
                error_code="RETRY_GOAL_CHANGE_FORBIDDEN",
                message_key="retry_goal_change_forbidden",
                keep_current_intent=True,
                preserve_goal=True,
                preserve_intent_id=True,
                next_actions=list(getattr(active, "allowed_actions", []) or []),
                metadata={"old_goal": active_goal, "new_goal": proposed_goal},
            )
            self._log_decision(stage="goal_change", decision=decision, ctx=ctx)
            return decision

        if self._goal_core_loss(active_goal, proposed_goal):
            decision = IntentPolicyDecision(
                allowed=False,
                reason="suspect_intent_goal_drift",
                error_code="SUSPECT_INTENT_GOAL_DRIFT",
                message_key="suspect_intent_goal_drift",
                keep_current_intent=True,
                preserve_goal=True,
                preserve_intent_id=True,
                allow_user_handoff=True,
                allow_once_via_state_method="allow_pending_goal_drift_once",
                next_actions=list(getattr(active, "allowed_actions", []) or []),
                metadata={
                    "old_goal": active_goal,
                    "new_goal": proposed_goal,
                    "goal_similarity": self._goal_similarity(active_goal, proposed_goal),
                },
            )
            self._log_decision(stage="goal_change", decision=decision, ctx=ctx)
            return decision

        return None

    def evaluate_retry(self, ctx: IntentPolicyContext) -> IntentPolicyDecision | None:
        active = ctx.active_intent
        proposed = ctx.proposed_intent
        if active is None or proposed is None:
            return None
        if getattr(proposed, "mode", "") != "retry":
            return None

        active_goal = getattr(active, "canonical_goal", "") or getattr(active, "goal", "")
        proposed_goal = getattr(proposed, "goal", "")
        if self._normalize_goal(active_goal) != self._normalize_goal(proposed_goal):
            decision = IntentPolicyDecision(
                allowed=False,
                reason="retry_goal_change_forbidden",
                error_code="RETRY_GOAL_CHANGE_FORBIDDEN",
                message_key="retry_goal_change_forbidden",
                keep_current_intent=True,
                preserve_goal=True,
                preserve_intent_id=True,
                next_actions=list(getattr(active, "allowed_actions", []) or []),
                metadata={"old_goal": active_goal, "new_goal": proposed_goal},
            )
            self._log_decision(stage="goal_change", decision=decision, ctx=ctx)
            return decision
        return None

    def evaluate_same_lineage_relabel(self, ctx: IntentPolicyContext) -> IntentPolicyDecision | None:
        active = ctx.active_intent
        proposed = ctx.proposed_intent
        if active is None or proposed is None:
            return None
        if getattr(proposed, "mode", "") not in {"activate", "replace"}:
            return None

        same_lineage = self._same_lineage(active, proposed, ctx.transition_info or {})
        if not same_lineage:
            return None

        old_id = getattr(active, "intent_id", "")
        new_id = getattr(proposed, "intent_id", "")
        old_goal = getattr(active, "canonical_goal", "") or getattr(active, "goal", "")
        new_goal = getattr(proposed, "goal", "")
        overlap = self._allowed_actions_overlap(
            getattr(active, "allowed_actions", []) or [],
            getattr(proposed, "allowed_actions", []) or [],
        )

        if old_id == new_id:
            decision = IntentPolicyDecision(
                allowed=False,
                reason="unnecessary_intent_reactivation_or_replace",
                error_code="UNNECESSARY_INTENT_REACTIVATION_OR_REPLACE",
                message_key="unnecessary_intent_reactivation_or_replace",
                keep_current_intent=True,
                preserve_goal=True,
                preserve_intent_id=True,
                next_actions=list(getattr(active, "allowed_actions", []) or []),
                metadata={
                    "intent_id": old_id,
                    "old_goal": old_goal,
                    "new_goal": new_goal,
                    "proposed_mode": getattr(proposed, "mode", ""),
                    "actions_overlap": overlap,
                },
            )
            self._log_decision(stage="same_lineage_relabel", decision=decision, ctx=ctx)
            return decision

        if old_id != new_id and self._normalize_goal(old_goal) == self._normalize_goal(new_goal):
            decision = IntentPolicyDecision(
                allowed=False,
                reason="suspect_intent_relabel_repeat",
                error_code="SUSPECT_INTENT_RELABEL_REPEAT",
                message_key="suspect_intent_relabel_repeat",
                keep_current_intent=True,
                preserve_goal=True,
                preserve_intent_id=True,
                allow_user_handoff=True,
                allow_once_via_state_method="allow_pending_suspect_intent_once",
                next_actions=list(getattr(active, "allowed_actions", []) or []),
                metadata={
                    "old_intent_id": old_id,
                    "new_intent_id": new_id,
                    "old_goal": old_goal,
                    "new_goal": new_goal,
                    "actions_overlap": overlap,
                },
            )
            self._log_decision(stage="same_lineage_relabel", decision=decision, ctx=ctx)
            return decision

        if old_id != new_id and overlap >= float(getattr(self.config, "INTENT_RELABEL_ACTION_OVERLAP_THRESHOLD", 0.6)):
            decision = IntentPolicyDecision(
                allowed=False,
                reason="suspect_intent_relabel_repeat",
                error_code="SUSPECT_INTENT_RELABEL_REPEAT",
                message_key="suspect_intent_relabel_repeat",
                keep_current_intent=True,
                preserve_goal=True,
                allow_user_handoff=True,
                allow_once_via_state_method="allow_pending_suspect_intent_once",
                next_actions=list(getattr(active, "allowed_actions", []) or []),
                metadata={
                    "old_intent_id": old_id,
                    "new_intent_id": new_id,
                    "old_goal": old_goal,
                    "new_goal": new_goal,
                    "actions_overlap": overlap,
                },
            )
            self._log_decision(stage="same_lineage_relabel", decision=decision, ctx=ctx)
            return decision

        return None

    def evaluate_transition(self, ctx: IntentPolicyContext) -> IntentPolicyDecision:
        proposed = ctx.proposed_intent
        active = ctx.active_intent

        if proposed is None:
            decision = IntentPolicyDecision(
                allowed=False,
                reason="intent_missing",
                error_code="INTENT_MISSING",
                message_key="intent_missing",
            )
            self._log_decision(stage="transition", decision=decision, ctx=ctx)
            return decision

        for checker in (
            self.evaluate_retry,
            self.evaluate_goal_change,
            self.evaluate_same_lineage_relabel,
        ):
            decision = checker(ctx)
            if decision is not None:
                return decision

        mode = getattr(proposed, "mode", "activate")
        message_key = {
            "activate": "allow_activate",
            "replace": "allow_replace",
            "retry": "allow_retry",
            "complete": "allow_complete",
        }.get(mode, "allow_activate")

        decision = IntentPolicyDecision(
            allowed=True,
            reason=f"allow_{mode}",
            error_code=f"ALLOW_{mode.upper()}",
            message_key=message_key,
            keep_current_intent=bool(active is not None and mode in {"retry"}),
            metadata={
                "mode": mode,
                "same_lineage": self._same_lineage(active, proposed, ctx.transition_info or {}),
            },
        )
        self._log_decision(stage="transition", decision=decision, ctx=ctx)
        return decision

    def evaluate_blocked_action(self, ctx: BlockedActionPolicyContext) -> IntentPolicyDecision:
        active = ctx.active_intent
        next_actions = list(getattr(active, "allowed_actions", []) or []) if active is not None else []
        decision = IntentPolicyDecision(
            allowed=False,
            reason="intent_blocked_action_signature",
            error_code="INTENT_BLOCKED_ACTION_SIGNATURE",
            message_key="blocked_action_keep_current_intent",
            recoverable=True,
            keep_current_intent=True,
            preserve_goal=True,
            preserve_intent_id=True,
            next_actions=next_actions,
            metadata={
                "blocked_reason": str(ctx.blocked_reason or "").strip(),
                "command": dict(ctx.command or {}),
            },
        )
        payload = {
            "stage": "blocked_action",
            "allowed": decision.allowed,
            "reason": decision.reason,
            "error_code": decision.error_code,
            "message_key": decision.message_key,
            "active_intent_id": getattr(active, "intent_id", "") if active is not None else "",
            "command_type": str((ctx.command or {}).get("type") or (ctx.command or {}).get("action") or ""),
            "path": str((ctx.command or {}).get("path") or ""),
            "blocked_reason": str(ctx.blocked_reason or "").strip(),
            "next_actions": list(next_actions or []),
            "metadata": dict(decision.metadata or {}),
        }
        self.log.warning(
            "IntentPolicy.%s allowed=%s reason=%s message_key=%s active_intent_id=%s command_type=%s path=%s",
            payload["stage"],
            payload["allowed"],
            payload["reason"],
            payload["message_key"],
            payload["active_intent_id"],
            payload["command_type"],
            payload["path"],
            extra={"intent_policy": payload},
        )
        return decision
