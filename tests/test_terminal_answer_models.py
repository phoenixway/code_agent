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
        has_visible_text=False,
        is_terminal=False,
    )
    assert result.kind == TerminalAnswerKind.UNKNOWN
    assert result.has_visible_text is False
    assert result.is_terminal is False
    assert result.visible_text == ""
    assert result.reason == ""
    assert result.source == ""
    assert result.details is None


def test_can_represent_no_visible_text():
    """Tests representation of a response with no visible text."""
    result = TerminalAnswerSemanticResult(
        kind=TerminalAnswerKind.NO_VISIBLE_TEXT,
        has_visible_text=False,
        is_terminal=False,
        source="test_classifier",
    )
    assert result.kind == TerminalAnswerKind.NO_VISIBLE_TEXT
    assert result.has_visible_text is False
    assert result.is_terminal is False
    assert result.visible_text == ""
    assert result.source == "test_classifier"


def test_can_represent_plaintext_terminal_answer():
    """Tests representation of a valid terminal answer."""
    result = TerminalAnswerSemanticResult(
        kind=TerminalAnswerKind.PLAINTEXT_TERMINAL_ANSWER,
        has_visible_text=True,
        is_terminal=True,
        visible_text="This is the final answer.",
        source="test_classifier",
    )
    assert result.kind == TerminalAnswerKind.PLAINTEXT_TERMINAL_ANSWER
    assert result.has_visible_text is True
    assert result.is_terminal is True
    assert result.visible_text == "This is the final answer."
    assert result.source == "test_classifier"


def test_can_represent_invalid_text_with_details():
    """Tests representation of an invalid/truncated answer with details."""
    details = {"original_text": "This is too short"}
    result = TerminalAnswerSemanticResult(
        kind=TerminalAnswerKind.INVALID_OR_TRUNCATED_TERMINAL_TEXT,
        has_visible_text=True,
        is_terminal=False,
        visible_text="This is too short",
        reason="terminal_plaintext_too_short",
        source="legacy_guard",
        details=details,
    )
    assert result.kind == TerminalAnswerKind.INVALID_OR_TRUNCATED_TERMINAL_TEXT
    assert result.has_visible_text is True
    assert result.is_terminal is False
    assert result.visible_text == "This is too short"
    assert result.reason == "terminal_plaintext_too_short"
    assert result.source == "legacy_guard"
    assert result.details == details
