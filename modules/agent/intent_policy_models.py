from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass
class IntentPolicyContext:
    active_intent: Any | None
    proposed_intent: Any | None
    transition_info: dict
    recent_problem_actions: list[dict]
    blocked_action_signatures: set[str]
    blocked_action_reasons: dict[str, str]
    pending_loop_stop_info: dict | None = None
    current_user_input: str = ""


@dataclass
class IntentPolicyDecision:
    allowed: bool
    reason: str
    error_code: str
    message_key: str
    recoverable: bool = True

    keep_current_intent: bool = False
    allow_user_handoff: bool = False
    allow_once_via_state_method: str | None = None

    next_actions: list[str] = field(default_factory=list)

    preserve_goal: bool = False
    preserve_intent_id: bool = False

    metadata: dict = field(default_factory=dict)


@dataclass
class BlockedActionPolicyContext:
    active_intent: Any | None
    command: dict
    blocked_reason: str