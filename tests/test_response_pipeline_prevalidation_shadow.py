"""
Tests for the TerminalAnswerClassifier shadow-mode wiring.

These tests verify that:
- The shadow classifier is invoked during the response pipeline.
- The shadow path is safe and does not affect production behavior.
- Exceptions in the shadow path are caught and do not break the pipeline.
- Diagnostic logs include both the new classifier's output and a comparable
  legacy classification for parity analysis.
"""
import unittest
from unittest.mock import MagicMock, patch

from modules.agent.orchestration.protocol.classifier import ProtocolCompiler
from modules.agent.orchestration.responses.response_pipeline_prevalidation import ResponsePipelinePrevalidationMixin
from modules.agent.orchestration.responses.terminal_answer_models import TerminalAnswerKind, TerminalAnswerSemanticResult
from modules.agent.orchestration.shared.decision_models import ParsedModelOutput


class TestResponsePipelinePrevalidationShadow(unittest.TestCase):
    def setUp(self):
        # Create a harness class that inherits the mixin
        class Harness(ResponsePipelinePrevalidationMixin):
            def __init__(self):
                self.protocol_compiler = ProtocolCompiler()
                self.stage_logger = MagicMock()
                self.parser = MagicMock()
                self.semantics = MagicMock()
                self._is_internal_summary_instead_of_final_answer = MagicMock(return_value=False)

            def _compiler_invalid_kind(self, compiler_analysis):
                return ""

        self.harness = Harness()
        # Default mock behaviors
        self.harness.parser.parse.return_value = []
        self.harness.semantics.looks_like_leaked_system_result.return_value = False
        if hasattr(self.harness.semantics, "is_plaintext_answer_path"):
            self.harness.semantics.is_plaintext_answer_path.return_value = False

    @patch("modules.agent.orchestration.responses.response_pipeline_prevalidation.terminal_plaintext_completion_status")
    @patch("modules.agent.orchestration.responses.response_pipeline_prevalidation.TerminalAnswerClassifier")
    def test_shadow_classifier_is_invoked(self, MockClassifier, mock_status):
        """Tests that the shadow classifier is invoked during diagnosis."""
        mock_status.return_value = (True, "", "")
        mock_instance = MockClassifier.return_value
        mock_instance.classify.return_value = TerminalAnswerSemanticResult(
            kind=TerminalAnswerKind.PLAINTEXT_TERMINAL_ANSWER,
            source="compiler_fact",
            reason_code="test",
        )

        parsed_output = ParsedModelOutput(response="")
        self.harness._apply_compiler_diagnosis(parsed_output, "Hello world.")

        # Assert classifier was instantiated and classify was called
        MockClassifier.assert_called_once()
        mock_instance.classify.assert_called_once()

        # Assert logger was called with the shadow result
        self.harness.stage_logger.log.assert_any_call(
            "terminal_answer_classifier_shadow",
            "snapshot",
            classifier_kind="plaintext_terminal_answer",
            classifier_source="compiler_fact",
            classifier_reason_code="test",
            classifier_evidence=[],
            classifier_visible_text_present=False,
            legacy_kind=None,
            is_match=None,
        )

    @patch("modules.agent.orchestration.responses.response_pipeline_prevalidation.TerminalAnswerClassifier")
    def test_shadow_classifier_does_not_change_behavior(self, MockClassifier):
        """Tests that the shadow classifier does not alter the return value or parsed_output."""
        mock_instance = MockClassifier.return_value
        mock_instance.classify.return_value = TerminalAnswerSemanticResult(
            kind=TerminalAnswerKind.UNKNOWN, source="fallback", reason_code="test"
        )

        parsed_output = ParsedModelOutput(response="", invalid_kind="initial_kind")

        analysis_result = self.harness._apply_compiler_diagnosis(parsed_output, "Hello world")

        # Assert the main return value is valid
        self.assertIsNotNone(analysis_result)

        # Assert that the shadow result is not attached to the production object
        self.assertFalse(hasattr(parsed_output, "shadow_classification"))

        # Assert that production-relevant fields are not mutated by the shadow call
        self.assertEqual(parsed_output.invalid_kind, "initial_kind")
        self.assertIsNotNone(parsed_output.runtime_protocol_semantics)

    @patch("modules.agent.orchestration.responses.response_pipeline_prevalidation.terminal_plaintext_completion_status")
    @patch("modules.agent.orchestration.responses.response_pipeline_prevalidation.TerminalAnswerClassifier")
    def test_shadow_classifier_exception_is_caught(self, MockClassifier, mock_status):
        """Tests that an exception in the shadow classifier is caught and logged."""
        mock_status.return_value = (True, "", "")
        mock_instance = MockClassifier.return_value
        test_exception = ValueError("Classifier failed")
        mock_instance.classify.side_effect = test_exception

        parsed_output = ParsedModelOutput(response="")

        # This call should not raise an exception
        analysis_result = self.harness._apply_compiler_diagnosis(parsed_output, "Hello world.")

        # Assert the main return value is still valid
        self.assertIsNotNone(analysis_result)

        # Assert the error was logged
        self.harness.stage_logger.log.assert_any_call(
            "terminal_answer_classifier_shadow",
            "error",
            error_class="ValueError",
            error_message="Classifier failed",
        )

    @patch("modules.agent.orchestration.responses.response_pipeline_prevalidation.terminal_plaintext_completion_status")
    @patch("modules.agent.orchestration.responses.response_pipeline_prevalidation.TerminalAnswerClassifier")
    def test_shadow_logging_exception_is_caught(self, MockClassifier, mock_status):
        """Tests that an exception in the shadow logger is caught and logged."""
        mock_status.return_value = (True, "", "")
        mock_instance = MockClassifier.return_value
        mock_instance.classify.return_value = TerminalAnswerSemanticResult(
            kind=TerminalAnswerKind.UNKNOWN, source="fallback", reason_code="test"
        )

        def log_side_effect(stage, event, **kwargs):
            if stage == "terminal_answer_classifier_shadow" and event == "snapshot":
                raise ValueError("Logger failed")
            return None

        self.harness.stage_logger.log.side_effect = log_side_effect

        parsed_output = ParsedModelOutput(response="")

        # This call should not raise an exception
        analysis_result = self.harness._apply_compiler_diagnosis(parsed_output, "Hello world.")

        # Assert the main return value is still valid
        self.assertIsNotNone(analysis_result)

        # Assert that the snapshot log was attempted
        self.harness.stage_logger.log.assert_any_call(
            "terminal_answer_classifier_shadow", "snapshot", classifier_kind="unknown",
            classifier_source="fallback", classifier_reason_code="test",
            classifier_evidence=[], classifier_visible_text_present=False,
            legacy_kind=None, is_match=None
        )

        # Assert that the subsequent error was logged
        self.harness.stage_logger.log.assert_any_call(
            "terminal_answer_classifier_shadow",
            "error",
            error_class="ValueError",
            error_message="Logger failed",
        )

    @patch("modules.agent.orchestration.responses.response_pipeline_prevalidation.terminal_plaintext_completion_status")
    @patch("modules.agent.orchestration.responses.response_pipeline_prevalidation.TerminalAnswerClassifier")
    def test_shadow_classifier_logs_legacy_kind_and_match(self, MockClassifier, mock_status):
        """Tests that legacy_kind and is_match are computed and logged."""
        mock_status.return_value = (True, "", "")
        mock_instance = MockClassifier.return_value
        mock_instance.classify.return_value = TerminalAnswerSemanticResult(
            kind=TerminalAnswerKind.LEAKED_SYSTEM_RESULT,
            source="compiler_fact",
            reason_code="test",
        )

        # Configure legacy semantics to match
        self.harness.semantics.looks_like_leaked_system_result.return_value = True

        parsed_output = ParsedModelOutput(response="")
        self.harness._apply_compiler_diagnosis(parsed_output, "SYSTEM RESULT: ...")

        # Assert logger was called with correct legacy kind and match status
        self.harness.stage_logger.log.assert_any_call(
            "terminal_answer_classifier_shadow",
            "snapshot",
            classifier_kind="leaked_system_result",
            classifier_source="compiler_fact",
            classifier_reason_code="test",
            classifier_evidence=[],
            classifier_visible_text_present=False,
            legacy_kind="leaked_system_result",
            is_match=True,
        )

        # Configure legacy semantics to mismatch
        self.harness.semantics.looks_like_leaked_system_result.return_value = False
        if hasattr(self.harness.semantics, "is_plaintext_answer_path"):
            self.harness.semantics.is_plaintext_answer_path.return_value = True

        self.harness._apply_compiler_diagnosis(parsed_output, "Just text.")

        # Assert logger was called with correct legacy kind and mismatch status
        self.harness.stage_logger.log.assert_any_call(
            "terminal_answer_classifier_shadow",
            "snapshot",
            classifier_kind="leaked_system_result",
            classifier_source="compiler_fact",
            classifier_reason_code="test",
            classifier_evidence=[],
            classifier_visible_text_present=False,
            legacy_kind="plaintext_terminal_answer",
            is_match=False,
        )

    @patch("modules.agent.orchestration.responses.response_pipeline_prevalidation.terminal_plaintext_completion_status")
    def test_shadow_classifier_logs_legacy_truncated_kind_match(self, mock_status):
        """
        Tests that legacy_kind and classifier_kind match for truncated text.
        """
        mock_status.return_value = (False, "truncated", "Hello")

        parsed_output = ParsedModelOutput(response="")
        self.harness._apply_compiler_diagnosis(parsed_output, "Hello")

        # The real classifier should now also identify this as truncated.
        self.harness.stage_logger.log.assert_any_call(
            "terminal_answer_classifier_shadow",
            "snapshot",
            classifier_kind="invalid_or_truncated_terminal_text",
            classifier_source="legacy_compatible_rule",
            classifier_reason_code="terminal_plaintext_completion_status:terminal_plaintext_too_short",
            classifier_evidence=["raw_response_text", "visible_text"],
            classifier_visible_text_present=True,
            legacy_kind="invalid_or_truncated_terminal_text",
            is_match=True,
        )

    @patch("modules.agent.orchestration.responses.response_pipeline_prevalidation.terminal_plaintext_completion_status")
    def test_shadow_classifier_logs_internal_summary_kind_match(self, mock_status):
        """Tests that internal summary parity is logged when the helper returns True."""
        mock_status.return_value = (True, "", "")
        self.harness._is_internal_summary_instead_of_final_answer.return_value = True

        parsed_output = ParsedModelOutput(response="")
        self.harness._apply_compiler_diagnosis(parsed_output, "Execution snapshot style text.")

        self.harness.stage_logger.log.assert_any_call(
            "terminal_answer_classifier_shadow",
            "snapshot",
            classifier_kind="internal_summary_like_text",
            classifier_source="runtime_policy",
            classifier_reason_code="legacy_internal_summary_helper",
            classifier_evidence=["is_internal_summary"],
            classifier_visible_text_present=True,
            legacy_kind="internal_summary_like_text",
            is_match=True,
        )
