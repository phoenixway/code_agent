"""
Phase 8: Typed models for terminal answer semantics.

These models support the TerminalAnswerClassifier, which is currently running in
a shadow-only mode. The results are for diagnostic logging and do not affect
production behavior, dispatch, or policy decisions.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from .runtime_protocol_semantics import RuntimeProtocolSemantics


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
class TerminalAnswerClassifierInput:
    """An immutable snapshot of inputs for the TerminalAnswerClassifier."""

    runtime_semantics: "RuntimeProtocolSemantics"
    raw_response_text: str
    is_internal_summary: bool = False


@dataclass(frozen=True)
class TerminalAnswerSemanticResult:
    """A structured result from classifying terminal answer semantics."""

    kind: TerminalAnswerKind
    source: str
    reason_code: str
    evidence: tuple[str, ...] = field(default_factory=tuple)
    visible_text: str | None = None
    details: dict[str, object] | None = field(default=None, compare=False)
