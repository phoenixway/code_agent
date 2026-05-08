"""Unit tests for the terminal answer semantic models."""

import pytest

from modules.agent.orchestration.responses.terminal_answer_models import (
    TerminalAnswerKind,
    TerminalAnswerSemanticResult,
)


def test_terminal_answer_kind_enum_has_stable_string_values():
    """Ensures the enum values are stable strings for serialization."""
    assert TerminalAnswerKind.UNKNOWN.value == "unknown"
    assert TerminalAnswerKind.NO_VISIBLE_TEXT.value == "no_visible_text"
    assert TerminalAnswerKind.PLAINTEXT_TERMINAL_ANSWER.value == "plaintext_terminal_answer"
    assert TerminalAnswerKind.CHECKPOINT_ONLY.value == "checkpoint_only"
    assert TerminalAnswerKind.CHECKPOINT_WITH_VISIBLE_TEXT.value == "checkpoint_with_visible_text"
    assert TerminalAnswerKind.INTENT_COMPLETE_WITH_VISIBLE_TEXT.value == "intent_complete_with_visible_text"
    assert TerminalAnswerKind.PRE_ACTION_VISIBLE_TEXT_WITH_ACTION.value == "pre_action_visible_text_with_action"
    assert TerminalAnswerKind.LEAKED_SYSTEM_RESULT.value == "leaked_system_result"
    assert TerminalAnswerKind.INTERNAL_SUMMARY_LIKE_TEXT.value == "internal_summary_like_text"
    assert TerminalAnswerKind.INVALID_OR_TRUNCATED_TERMINAL_TEXT.value == "invalid_or_truncated_terminal_text"


def test_terminal_answer_semantic_result_dataclass_defaults():
    """Tests the default values of the result dataclass."""
    result = TerminalAnswerSemanticResult(
        kind=TerminalAnswerKind.UNKNOWN,
        source="test",
        reason_code="test_default",
    )
    assert result.kind == TerminalAnswerKind.UNKNOWN
    assert result.source == "test"
    assert result.reason_code == "test_default"
    assert result.evidence == ()
    assert result.visible_text is None
    assert result.details is None


def test_can_represent_no_visible_text():
    """Tests representation of a response with no visible text."""
    result = TerminalAnswerSemanticResult(
        kind=TerminalAnswerKind.NO_VISIBLE_TEXT,
        source="compiler_fact",
        reason_code="no_visible_answer",
    )
    assert result.kind == TerminalAnswerKind.NO_VISIBLE_TEXT
    assert result.source == "compiler_fact"
    assert result.reason_code == "no_visible_answer"
    assert result.visible_text is None


def test_can_represent_plaintext_terminal_answer():
    """Tests representation of a valid terminal answer."""
    result = TerminalAnswerSemanticResult(
        kind=TerminalAnswerKind.PLAINTEXT_TERMINAL_ANSWER,
        source="compiler_fact",
        reason_code="pure_plaintext",
        visible_text="This is the final answer.",
    )
    assert result.kind == TerminalAnswerKind.PLAINTEXT_TERMINAL_ANSWER
    assert result.source == "compiler_fact"
    assert result.reason_code == "pure_plaintext"
    assert result.visible_text == "This is the final answer."


def test_can_represent_invalid_text_with_details():
    """Tests representation of an invalid/truncated answer with details."""
    details = {"original_text": "This is too short"}
    result = TerminalAnswerSemanticResult(
        kind=TerminalAnswerKind.INVALID_OR_TRUNCATED_TERMINAL_TEXT,
        source="legacy_guard",
        reason_code="terminal_plaintext_too_short",
        visible_text="This is too short",
        details=details,
    )
    assert result.kind == TerminalAnswerKind.INVALID_OR_TRUNCATED_TERMINAL_TEXT
    assert result.source == "legacy_guard"
    assert result.reason_code == "terminal_plaintext_too_short"
    assert result.visible_text == "This is too short"
    assert result.details == details
