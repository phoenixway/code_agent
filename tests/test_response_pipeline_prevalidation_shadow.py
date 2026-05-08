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

            def _compiler_invalid_kind(self, compiler_analysis):
                return ""

        self.harness = Harness()

    @patch("modules.agent.orchestration.responses.response_pipeline_prevalidation.TerminalAnswerClassifier")
    def test_shadow_classifier_is_invoked(self, MockClassifier):
        """Tests that the shadow classifier is invoked during diagnosis."""
        mock_instance = MockClassifier.return_value
        mock_instance.classify.return_value = TerminalAnswerSemanticResult(
            kind=TerminalAnswerKind.PLAINTEXT_TERMINAL_ANSWER,
            source="compiler_fact",
            reason_code="test",
        )

        parsed_output = ParsedModelOutput(response="")
        self.harness._apply_compiler_diagnosis(parsed_output, "Hello world")

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

    @patch("modules.agent.orchestration.responses.response_pipeline_prevalidation.TerminalAnswerClassifier")
    def test_shadow_classifier_exception_is_caught(self, MockClassifier):
        """Tests that an exception in the shadow classifier is caught and logged."""
        mock_instance = MockClassifier.return_value
        test_exception = ValueError("Classifier failed")
        mock_instance.classify.side_effect = test_exception

        parsed_output = ParsedModelOutput(response="")

        # This call should not raise an exception
        analysis_result = self.harness._apply_compiler_diagnosis(parsed_output, "Hello world")

        # Assert the main return value is still valid
        self.assertIsNotNone(analysis_result)

        # Assert the error was logged
        self.harness.stage_logger.log.assert_any_call(
            "terminal_answer_classifier_shadow",
            "error",
            error_class="ValueError",
            error_message="Classifier failed",
        )

    @patch("modules.agent.orchestration.responses.response_pipeline_prevalidation.TerminalAnswerClassifier")
    def test_shadow_logging_exception_is_caught(self, MockClassifier):
        """Tests that an exception in the shadow logger is caught and logged."""
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
        analysis_result = self.harness._apply_compiler_diagnosis(parsed_output, "Hello world")

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
