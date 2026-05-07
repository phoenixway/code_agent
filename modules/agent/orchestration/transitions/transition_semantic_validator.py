"""
Structural validator for the followup surface after an intent transition.

This is the scaffolding for Phase 5, Step 1.
It contains only type definitions and a placeholder implementation.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum


class TransitionResultKind(str, Enum):
    """Strongly-typed classification of the post-intent followup surface."""

    # Intent applied, no meaningful followup
    NO_FOLLOWUP = "no_followup"
    # Intent applied, followed by a valid single action
    FOLLOWUP_ACTION = "followup_action"
    # Intent applied, followed by a valid plaintext answer
    FOLLOWUP_PLAINTEXT = "followup_plaintext"
    # Intent applied, but followup is invalid (e.g., multiple actions)
    FOLLOWUP_CONFLICT = "followup_conflict"
    # A `transition_only` intent was bundled with an action
    TRANSITION_ONLY_VIOLATION = "transition_only_violation"
    # A `reuse_only` intent was bundled with an action
    REUSE_ONLY_VIOLATION = "reuse_only_violation"
    # A `complete` intent was bundled with an action
    COMPLETE_WITH_ACTION_VIOLATION = "complete_with_action_violation"
    # Fallback for unclassifiable cases
    UNKNOWN = "unknown"


@dataclass(frozen=True)
class TransitionValidationResult:
    """
    Strongly-typed result of a transition followup validation.

    This is a structural classification, not a policy decision.
    """

    kind: TransitionResultKind
    conflict_reason: str = ""
    reason: str = ""
    details: dict[str, object] = field(default_factory=dict)


class TransitionSemanticValidator:
    """
    Centralizes and classifies the followup surface of a model response after
    an intent transition has been applied.
    """

    def validate(
        self,
        response_text: str,
        intent_payload: dict | None = None,
        *,
        transition_only_required: bool = False,
        reuse_only_required: bool = False,
    ) -> TransitionValidationResult:
        """
        Analyzes the followup surface and returns a typed classification.

        This is the scaffolding for Phase 5, Step 1.
        It does not contain any logic yet.
        """
        # This is a placeholder implementation for Step 1.
        # Logic migration will occur in Step 2.
        return TransitionValidationResult(kind=TransitionResultKind.UNKNOWN)
