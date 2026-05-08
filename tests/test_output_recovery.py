"""Unit tests for ModelOutputRecoveryHandler."""

import unittest
from dataclasses import dataclass
from types import SimpleNamespace
from typing import Any
from unittest.mock import MagicMock, patch

from modules.agent.orchestration.responses.output_recovery import ModelOutputRecoveryHandler
from modules.agent.orchestration.shared.decision_models import ParsedModelOutput


# Minimal test doubles for nested objects
@dataclass
class _MockOp:
    kind: str


@dataclass
class _MockCompilerIR:
    action_ops: tuple[Any, ...] = ()


class TestModelOutputRecoveryHandler(unittest.TestCase):
    def setUp(self):
        self.agent = SimpleNamespace(
            state=SimpleNamespace(),
            config=SimpleNamespace(),
            logger=MagicMock(),
        )
        self.prompt_builder = MagicMock()
        self.handler = ModelOutputRecoveryHandler(self.agent, self.prompt_builder)

    # --- Tests for _has_any_action_proposal delegation ---

    def test_has_any_action_proposal_true_from_legacy_count(self):
        """_has_any_action_proposal is True if parsed_action_count > 0."""
        p_out = ParsedModelOutput(response="")
        self.assertTrue(self.handler._has_any_action_proposal(p_out, parsed_action_count=1))

    def test_has_any_action_proposal_true_from_compiler_ir(self):
        """_has_any_action_proposal is True if compiler_ir.action_ops is non-empty."""
        p_out = ParsedModelOutput(response="", compiler_ir=_MockCompilerIR(action_ops=(_MockOp("tool"),)))
        self.assertTrue(self.handler._has_any_action_proposal(p_out))

    def test_has_any_action_proposal_true_from_legacy_segment(self):
        """_has_any_action_proposal is True if has_action_segment is True."""
        p_out = ParsedModelOutput(response="", has_action_segment=True)
        self.assertTrue(self.handler._has_any_action_proposal(p_out))

    def test_has_any_action_proposal_false_when_no_evidence(self):
        """_has_any_action_proposal is False if there is no evidence of an action proposal."""
        p_out = ParsedModelOutput(response="")
        self.assertFalse(self.handler._has_any_action_proposal(p_out, parsed_action_count=0))

    @patch("modules.agent.orchestration.responses.output_recovery.has_any_action_proposal_compat")
    def test_has_any_action_proposal_delegates_to_accessor(self, mock_accessor):
        """_has_any_action_proposal delegates its call to the semantic accessor."""
        mock_accessor.return_value = "delegation_sentinel"
        p_out = ParsedModelOutput(response="test response")
        result = self.handler._has_any_action_proposal(p_out, parsed_action_count=5)

        self.assertIs(result, True)
        mock_accessor.assert_called_once_with(p_out, 5)

    @patch("modules.agent.orchestration.responses.output_recovery.has_any_action_proposal_compat")
    def test_has_any_action_proposal_uses_legacy_fallback_on_exception(self, mock_accessor):
        """_has_any_action_proposal uses legacy fallback if accessor raises."""
        mock_accessor.side_effect = Exception("Accessor failed")

        # Case 1: Fallback returns True due to has_action_segment
        p_out_segment = ParsedModelOutput(response="", has_action_segment=True)
        self.assertTrue(self.handler._has_any_action_proposal(p_out_segment, parsed_action_count=0))

        # Case 2: Fallback returns True due to parsed_action_count
        p_out_count = ParsedModelOutput(response="")
        self.assertTrue(self.handler._has_any_action_proposal(p_out_count, parsed_action_count=1))

        # Case 3: Fallback returns False
        p_out_none = ParsedModelOutput(response="")
        self.assertFalse(self.handler._has_any_action_proposal(p_out_none, parsed_action_count=0))

        # Verify accessor was called
        self.assertEqual(mock_accessor.call_count, 3)

    # --- Characterization tests for visible text semantics ---

    def test_is_internal_summary_instead_of_final_answer(self):
        """
        Characterizes `_is_internal_summary_instead_of_final_answer` behavior.
        This covers scenario 8.
        """
        # Case 1: A response that looks like a plan.
        # Current behavior: This is NOT classified as an internal summary.
        # This test characterizes that current actual behavior.
        p_out_summary = ParsedModelOutput(
            response="Okay, I will do that. The plan is to first read the file, then edit it.",
            has_action_segment=False,
            visible_text="Okay, I will do that. The plan is to first read the file, then edit it.",
            invalid_kind="",
        )
        self.assertFalse(self.handler._is_internal_summary_instead_of_final_answer(p_out_summary))

        # Case 2: A normal plaintext answer
        p_out_normal = ParsedModelOutput(
            response="The file has been updated successfully.",
            has_action_segment=False,
            visible_text="The file has been updated successfully.",
            invalid_kind="",
        )
        self.assertFalse(self.handler._is_internal_summary_instead_of_final_answer(p_out_normal))

        # Case 3: Has an action, so it's not a final answer path
        p_out_action = ParsedModelOutput(
            response='<action>{"type":"read_file"}</action>',
            has_action_segment=True,
            visible_text="",
            invalid_kind="",
        )
        self.assertFalse(self.handler._is_internal_summary_instead_of_final_answer(p_out_action))

        # Case 4: Has another invalid_kind, which takes precedence
        p_out_invalid = ParsedModelOutput(
            response="Okay, I will do that. The plan is to first read the file, then edit it.",
            has_action_segment=False,
            visible_text="Okay, I will do that. The plan is to first read the file, then edit it.",
            invalid_kind="some_other_error",
        )
        self.assertFalse(self.handler._is_internal_summary_instead_of_final_answer(p_out_invalid))


if __name__ == "__main__":
    unittest.main()
