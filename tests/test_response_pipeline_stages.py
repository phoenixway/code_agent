"""Unit tests for ResponsePipelineStagesMixin."""

import asyncio
import unittest
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

from modules.agent.orchestration.responses.response_pipeline_stages import ResponsePipelineStagesMixin
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
                )
                self.stage_logger = SimpleNamespace(log=MagicMock())
                self.prompt_builder = SimpleNamespace(
                    build_leaked_system_result_recovery_prompt=MagicMock(return_value="recovery_prompt")
                )

        self.harness = Harness()

    @patch("modules.agent.orchestration.responses.response_pipeline_stages.is_leaked_system_result")
    def test_leaked_system_result_check_delegates_to_accessor(self, mock_is_leaked):
        """_run_post_classification_stage delegates leaked system result check to accessor."""
        mock_is_leaked.return_value = True

        # Mock necessary inputs
        ctx = SimpleNamespace()
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

        # Run the stage
        outcome = asyncio.run(self.harness._run_post_classification_stage(ctx, step, checkpoint_state, classified))

        # Assertions
        mock_is_leaked.assert_called_once_with("SYSTEM RESULT: ...")
        self.assertIsInstance(outcome, ResponsePipelineOutcome)
        self.assertEqual(outcome.next_query, "recovery_prompt")
        self.harness.semantics.has_any_action_proposal.assert_called_once()


if __name__ == "__main__":
    unittest.main()
