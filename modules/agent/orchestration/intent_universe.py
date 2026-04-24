"""Resolve the current intent orchestration universe.

The system must always be in one of two explicit runtime states:
- active formal intent contract
- no active contract, with bounded intentless short mode
"""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class IntentUniverseState:
    kind: str
    has_active_contract: bool
    intent_required_now: bool
    intent_requirement_reason: str = ""
    active_intent_id: str = ""
    active_intent_type: str = ""
    active_goal: str = ""
    allowed_actions: list[str] = field(default_factory=list)
    intentless_steps_used: int = 0
    intentless_steps_limit: int = 2


class IntentUniverseResolver:
    ACTIVE_CONTRACT = "active_contract"
    INTENTLESS_SHORT_MODE = "intentless_short_mode"

    def resolve(self, state, config) -> IntentUniverseState:
        active_intent = getattr(state, "active_intent", None)
        if active_intent is not None:
            return IntentUniverseState(
                kind=self.ACTIVE_CONTRACT,
                has_active_contract=True,
                intent_required_now=bool(getattr(state, "intent_required_until_activated", False)),
                intent_requirement_reason=str(getattr(state, "intent_required_reason", "") or ""),
                active_intent_id=str(getattr(active_intent, "intent_id", "") or ""),
                active_intent_type=str(getattr(active_intent, "intent_type", "") or ""),
                active_goal=str(getattr(active_intent, "goal", "") or ""),
                allowed_actions=list(getattr(active_intent, "allowed_actions", []) or []),
                # Once a formal contract is active, intentless short-mode accounting
                # should stop surfacing in prompt/runtime views.
                intentless_steps_used=0,
                intentless_steps_limit=max(1, int(getattr(config, "INTENTLESS_SHORT_MODE_MAX_STEPS", 2) or 2)),
            )

        return IntentUniverseState(
            kind=self.INTENTLESS_SHORT_MODE,
            has_active_contract=False,
            intent_required_now=bool(getattr(state, "intent_required_until_activated", False)),
            intent_requirement_reason=str(getattr(state, "intent_required_reason", "") or ""),
            intentless_steps_used=int(getattr(state, "readonly_steps_this_turn", 0) or 0),
            intentless_steps_limit=max(1, int(getattr(config, "INTENTLESS_SHORT_MODE_MAX_STEPS", 2) or 2)),
        )