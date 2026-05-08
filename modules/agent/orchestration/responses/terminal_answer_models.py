"""
Phase 8: Typed models for terminal answer semantics.

This is a scaffolding-only implementation. The classifier that produces these
models is not yet implemented, and no consumers have been migrated.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum


class TerminalAnswerKind(str, Enum):
    """A classification of the semantic meaning of a model response's terminal answer."""

    UNKNOWN = "unknown"
    NO_VISIBLE_TEXT = "no_visible_text"
    PLAINTEXT_TERMINAL_ANSWER = "plaintext_terminal_answer"
    CHECKPOINT_ONLY = "checkpoint_only"
    CHECKPOINT_WITH_VISIBLE_TEXT = "checkpoint_with_visible_text"
    INTENT_COMPLETE_WITH_VISIBLE_TEXT = "intent_complete_with_visible_text"
    PRE_ACTION_VISIBLE_TEXT_WITH_ACTION = "pre_action_visible_text_with_action"
    LEAKED_SYSTEM_RESULT = "leaked_system_result"
    INTERNAL_SUMMARY_LIKE_TEXT = "internal_summary_like_text"
    INVALID_OR_TRUNCATED_TERMINAL_TEXT = "invalid_or_truncated_terminal_text"


@dataclass(frozen=True)
class TerminalAnswerSemanticResult:
    """A structured result from classifying terminal answer semantics."""

    kind: TerminalAnswerKind
    has_visible_text: bool
    is_terminal: bool
    visible_text: str = ""
    reason: str = ""
    source: str = ""
    details: dict[str, object] | None = field(default=None, compare=False)
