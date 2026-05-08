import unittest
from dataclasses import dataclass

from modules.agent.orchestration.responses.terminal_answer_classifier import TerminalAnswerClassifier
from modules.agent.orchestration.responses.terminal_answer_models import (
    TerminalAnswerClassifierInput,
    TerminalAnswerKind,
)


@dataclass(frozen=True)
class MockRuntimeSemantics:
    """A mock for RuntimeProtocolSemantics for testing the classifier."""

    visible_text_source: str = "UNKNOWN"
    has_memory_tags: bool = False
    has_subgoal_tags: bool = False
    has_memory_checkpoint: bool = False
    has_visible_answer: bool = False
    has_pre_action_text: bool = False
    visible_text: str | None = None
    pre_action_text: str | None = None


class TestTerminalAnswerClassifier(unittest.TestCase):
    def setUp(self):
        self.classifier = TerminalAnswerClassifier()

    def test_classify_pre_action_text(self):
        semantics = MockRuntimeSemantics(
            visible_text_source="PRE_ACTION_TEXT",
            has_pre_action_text=True,
            pre_action_text="Thinking out loud.",
        )
        input_data = TerminalAnswerClassifierInput(semantics, "")
        result = self.classifier.classify(input_data)
        self.assertEqual(result.kind, TerminalAnswerKind.PRE_ACTION_VISIBLE_TEXT_WITH_ACTION)
        self.assertEqual(result.source, "compiler_fact")
        self.assertEqual(result.visible_text, "Thinking out loud.")

    def test_classify_intent_completion_text(self):
        semantics = MockRuntimeSemantics(
            visible_text_source="INTENT_COMPLETION_TEXT",
            has_visible_answer=True,
            visible_text="All done.",
        )
        input_data = TerminalAnswerClassifierInput(semantics, "")
        result = self.classifier.classify(input_data)
        self.assertEqual(result.kind, TerminalAnswerKind.INTENT_COMPLETE_WITH_VISIBLE_TEXT)
        self.assertEqual(result.source, "compiler_fact")
        self.assertEqual(result.visible_text, "All done.")

    def test_classify_checkpoint_with_visible_text(self):
        semantics = MockRuntimeSemantics(
            visible_text_source="CHECKPOINT_ACCOMPANYING_TEXT",
            has_visible_answer=True,
            visible_text="Here is a summary.",
        )
        input_data = TerminalAnswerClassifierInput(semantics, "")
        result = self.classifier.classify(input_data)
        self.assertEqual(result.kind, TerminalAnswerKind.CHECKPOINT_WITH_VISIBLE_TEXT)
        self.assertEqual(result.source, "compiler_fact")

    def test_classify_checkpoint_only(self):
        semantics = MockRuntimeSemantics(has_memory_tags=True)
        input_data = TerminalAnswerClassifierInput(semantics, "")
        result = self.classifier.classify(input_data)
        self.assertEqual(result.kind, TerminalAnswerKind.CHECKPOINT_ONLY)
        self.assertEqual(result.source, "compiler_fact")

    def test_classify_pure_plaintext(self):
        semantics = MockRuntimeSemantics(
            visible_text_source="PURE_PLAINTEXT",
            has_visible_answer=True,
            visible_text="This is a final answer.",
        )
        input_data = TerminalAnswerClassifierInput(semantics, "")
        result = self.classifier.classify(input_data)
        self.assertEqual(result.kind, TerminalAnswerKind.PLAINTEXT_TERMINAL_ANSWER)
        self.assertEqual(result.source, "compiler_fact")

    def test_classify_no_visible_text(self):
        semantics = MockRuntimeSemantics()
        input_data = TerminalAnswerClassifierInput(semantics, "")
        result = self.classifier.classify(input_data)
        self.assertEqual(result.kind, TerminalAnswerKind.NO_VISIBLE_TEXT)
        self.assertEqual(result.source, "compiler_fact")

    def test_classify_unknown_fallback(self):
        semantics = MockRuntimeSemantics(
            visible_text_source="UNKNOWN",
            has_visible_answer=True,
            visible_text="Some text.",
        )
        input_data = TerminalAnswerClassifierInput(semantics, "")
        result = self.classifier.classify(input_data)
        self.assertEqual(result.kind, TerminalAnswerKind.UNKNOWN)
        self.assertEqual(result.source, "fallback")

    def test_classify_leaked_system_result(self):
        """Tests that a leaked system result is correctly classified."""
        raw_text = "SYSTEM RESULT: The tool output is..."
        semantics = MockRuntimeSemantics(
            visible_text_source="PURE_PLAINTEXT",
            has_visible_answer=True,
            visible_text=raw_text,
        )
        input_data = TerminalAnswerClassifierInput(semantics, raw_text)
        result = self.classifier.classify(input_data)
        self.assertEqual(result.kind, TerminalAnswerKind.LEAKED_SYSTEM_RESULT)
        self.assertEqual(result.source, "legacy_compatible_rule")

    def test_leaked_system_result_has_priority(self):
        """Tests that leaked system result has priority over plaintext."""
        raw_text = "SYSTEM RESULT: The tool output is..."
        # Even if compiler facts say PURE_PLAINTEXT, the legacy rule should win.
        semantics = MockRuntimeSemantics(
            visible_text_source="PURE_PLAINTEXT",
            has_visible_answer=True,
            visible_text=raw_text,
        )
        input_data = TerminalAnswerClassifierInput(semantics, raw_text)
        result = self.classifier.classify(input_data)
        self.assertEqual(result.kind, TerminalAnswerKind.LEAKED_SYSTEM_RESULT)

    def test_normal_text_is_not_leaked_system_result(self):
        """Tests that normal text is not misclassified as a leaked system result."""
        raw_text = "This is a normal final answer."
        semantics = MockRuntimeSemantics(
            visible_text_source="PURE_PLAINTEXT",
            has_visible_answer=True,
            visible_text=raw_text,
        )
        input_data = TerminalAnswerClassifierInput(semantics, raw_text)
        result = self.classifier.classify(input_data)
        self.assertEqual(result.kind, TerminalAnswerKind.PLAINTEXT_TERMINAL_ANSWER)

    def test_classify_invalid_or_truncated_text(self):
        """Tests that truncated text is correctly classified."""
        raw_text = "This is too short"
        semantics = MockRuntimeSemantics(
            visible_text_source="PURE_PLAINTEXT",
            has_visible_answer=True,
            visible_text=raw_text,
        )
        input_data = TerminalAnswerClassifierInput(semantics, raw_text)
        result = self.classifier.classify(input_data)
        self.assertEqual(result.kind, TerminalAnswerKind.INVALID_OR_TRUNCATED_TERMINAL_TEXT)
        self.assertEqual(result.source, "legacy_compatible_rule")
        self.assertIn("terminal_plaintext_too_short", result.reason_code)

    def test_truncated_text_has_priority(self):
        """Tests that truncated text has priority over other classifications."""
        # This text is both truncated and looks like a leaked system result.
        # The truncated rule should win due to priority.
        raw_text = "SYSTEM RESULT"
        semantics = MockRuntimeSemantics(
            visible_text_source="PURE_PLAINTEXT",
            has_visible_answer=True,
            visible_text=raw_text,
        )
        input_data = TerminalAnswerClassifierInput(semantics, raw_text)
        result = self.classifier.classify(input_data)
        self.assertEqual(result.kind, TerminalAnswerKind.INVALID_OR_TRUNCATED_TERMINAL_TEXT)
