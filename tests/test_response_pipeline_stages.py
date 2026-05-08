"""Unit tests for ResponsePipelineStagesMixin."""

import asyncio
import unittest
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

from modules.agent.orchestration.responses.response_pipeline_stages import ResponsePipelineStagesMixin
from modules.agent.orchestration.responses.terminal_answer_models import TerminalAnswerKind, TerminalAnswerSemanticResult
from modules.agent.orchestration.shared.decision_models import ParsedModelOutput, ResponsePipelineOutcome


class TestResponsePipelineStages(unittest.TestCase):
    def setUp(self):
        # Minimal harness to test the mixin
        class Harness(ResponsePipelineStagesMixin):
            def __init__(self):
                self.state = SimpleNamespace(active_intent=None)
                self.semantics = SimpleNamespace(
                    has_any_action_proposal=MagicMock(return_value=False),
                    is_plaintext_answer_path=MagicMock(return_value=False),
                    is_reflection_only_repair_turn=MagicMock(return_value=False),
                    is_durable_state_repair_turn=MagicMock(return_value=False),
                )
                self.guards = SimpleNamespace(
                    set_reflection_repair_pending=MagicMock(),
                    set_nonproductive_thinking_state=MagicMock(),
                    is_nonproductive_thinking_turn=MagicMock(return_value=False),
                )
                self.stage_logger = SimpleNamespace(log=MagicMock())
                self.prompt_builder = SimpleNamespace(
                    build_leaked_system_result_recovery_prompt=MagicMock(return_value="recovery_prompt")
                )
                self.output_recovery = SimpleNamespace(
                    decide=AsyncMock(
                        return_value=SimpleNamespace(
                            handled=True,
                            next_query="other_recovery_prompt",
                            reason="other_recovery",
                            malformed_action_retries=0,
                            audit_marker_retries=0,
                        )
                    )
                )

        self.harness = Harness()

    @patch("modules.agent.orchestration.responses.response_pipeline_stages.is_leaked_system_result")
    def test_typed_leaked_system_result_triggers_recovery(self, mock_is_leaked):
        """Typed LEAKED_SYSTEM_RESULT is the primary signal for leaked-result recovery."""
        mock_is_leaked.return_value = False

        ctx = SimpleNamespace(malformed_action_retries=0, audit_marker_retries=0)
        step = SimpleNamespace(response="SYSTEM RESULT: ...")
        checkpoint_state = SimpleNamespace(
            reflection_repair_pending=False,
            reflection_repair_kind="",
            memory_checkpoint_and_text=False,
            memory_checkpoint_and_action=False,
            memory_board_decision=SimpleNamespace(),
        )
        parsed_output = ParsedModelOutput(
            response="",
            terminal_answer_semantic_result=TerminalAnswerSemanticResult(
                kind=TerminalAnswerKind.LEAKED_SYSTEM_RESULT,
                source="legacy_compatible_rule",
                reason_code="looks_like_leaked_system_result",
            ),
        )
        classified = SimpleNamespace(
            response="SYSTEM RESULT: ...",
            parsed_output=parsed_output,
            segments=[],
            parsed_action_count=0,
        )

        outcome = asyncio.run(self.harness._run_post_classification_stage(ctx, step, checkpoint_state, classified))

        mock_is_leaked.assert_not_called()
        self.assertIsInstance(outcome, ResponsePipelineOutcome)
        self.assertEqual(outcome.next_query, "recovery_prompt")
        self.harness.semantics.has_any_action_proposal.assert_called_once()

    @patch("modules.agent.orchestration.responses.response_pipeline_stages.is_leaked_system_result")
    def test_legacy_fallback_triggers_when_typed_result_absent(self, mock_is_leaked):
        """Legacy accessor remains the fallback when no typed result is present."""
        mock_is_leaked.return_value = True

        ctx = SimpleNamespace(malformed_action_retries=0, audit_marker_retries=0)
        step = SimpleNamespace(response="SYSTEM RESULT: ...")
        checkpoint_state = SimpleNamespace(
            reflection_repair_pending=False,
            reflection_repair_kind="",
            memory_checkpoint_and_text=False,
            memory_checkpoint_and_action=False,
            memory_board_decision=SimpleNamespace(),
        )
        classified = SimpleNamespace(
            response="SYSTEM RESULT: ...",
            parsed_output=ParsedModelOutput(response=""),
            segments=[],
            parsed_action_count=0,
        )

        outcome = asyncio.run(self.harness._run_post_classification_stage(ctx, step, checkpoint_state, classified))

        mock_is_leaked.assert_called_once_with("SYSTEM RESULT: ...")
        self.assertIsInstance(outcome, ResponsePipelineOutcome)
        self.assertEqual(outcome.next_query, "recovery_prompt")
        self.harness.semantics.has_any_action_proposal.assert_called_once()

    @patch("modules.agent.orchestration.responses.response_pipeline_stages.is_leaked_system_result")
    def test_legacy_fallback_triggers_when_typed_result_is_not_leak(self, mock_is_leaked):
        """Legacy accessor remains fallback when typed result is present but not leaked."""
        mock_is_leaked.return_value = True

        ctx = SimpleNamespace(malformed_action_retries=0, audit_marker_retries=0)
        step = SimpleNamespace(response="SYSTEM RESULT for tool_xyz")
        checkpoint_state = SimpleNamespace(
            reflection_repair_pending=False,
            reflection_repair_kind="",
            memory_checkpoint_and_text=False,
            memory_checkpoint_and_action=False,
            memory_board_decision=SimpleNamespace(),
        )
        parsed_output = ParsedModelOutput(
            response="",
            terminal_answer_semantic_result=TerminalAnswerSemanticResult(
                kind=TerminalAnswerKind.PLAINTEXT_TERMINAL_ANSWER,
                source="compiler_fact",
                reason_code="visible_text_source_is_pure_plaintext",
            ),
        )
        classified = SimpleNamespace(
            response="SYSTEM RESULT for tool_xyz",
            parsed_output=parsed_output,
            segments=[],
            parsed_action_count=0,
        )

        outcome = asyncio.run(self.harness._run_post_classification_stage(ctx, step, checkpoint_state, classified))

        mock_is_leaked.assert_called_once_with("SYSTEM RESULT for tool_xyz")
        self.assertIsInstance(outcome, ResponsePipelineOutcome)
        self.assertEqual(outcome.next_query, "recovery_prompt")

    @patch("modules.agent.orchestration.responses.response_pipeline_stages.is_leaked_system_result")
    def test_no_action_guard_prevents_leak_recovery(self, mock_is_leaked):
        """Leak recovery must not trigger when there is an action proposal."""
        mock_is_leaked.return_value = True
        self.harness.semantics.has_any_action_proposal.return_value = True

        ctx = SimpleNamespace(malformed_action_retries=0, audit_marker_retries=0)
        step = SimpleNamespace(response="SYSTEM RESULT: ...")
        checkpoint_state = SimpleNamespace(
            reflection_repair_pending=False,
            reflection_repair_kind="",
            memory_checkpoint_and_text=False,
            memory_checkpoint_and_action=False,
            memory_board_decision=SimpleNamespace(),
        )
        parsed_output = ParsedModelOutput(
            response="",
            terminal_answer_semantic_result=TerminalAnswerSemanticResult(
                kind=TerminalAnswerKind.LEAKED_SYSTEM_RESULT,
                source="legacy_compatible_rule",
                reason_code="looks_like_leaked_system_result",
            ),
        )
        classified = SimpleNamespace(
            response="SYSTEM RESULT: ...",
            parsed_output=parsed_output,
            segments=[],
            parsed_action_count=1,
        )

        outcome = asyncio.run(self.harness._run_post_classification_stage(ctx, step, checkpoint_state, classified))

        mock_is_leaked.assert_not_called()
        self.assertIsInstance(outcome, ResponsePipelineOutcome)
        self.assertEqual(outcome.next_query, "other_recovery_prompt")


if __name__ == "__main__":
    unittest.main()
