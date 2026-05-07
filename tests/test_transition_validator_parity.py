"""
Parity tests for TransitionSemanticValidator against IntentTransitionHandler.

Ensures that the replicated logic in the validator behaves identically to the
original helpers in IntentTransitionHandler for the migrated Step 2A cases.
"""

import unittest
from types import SimpleNamespace
from unittest.mock import MagicMock

from modules.agent.orchestration.transitions.intent_transitions import IntentTransitionHandler
from modules.agent.orchestration.transitions.transition_semantic_validator import (
    TransitionResultKind,
    TransitionSemanticValidator,
)


class TransitionValidatorParityTests(unittest.TestCase):
    """Parity tests for Phase 5, Step 2A."""

    def setUp(self):
        """Set up the validator and a mocked IntentTransitionHandler."""
        self.validator = TransitionSemanticValidator()

        # Mock dependencies for IntentTransitionHandler
        mock_agent = MagicMock()
        mock_agent.state = SimpleNamespace(active_intent=None)
        # Mock the logger to avoid errors on attribute access
        mock_agent.logger = MagicMock()
        # Mock config to satisfy TransitionLayerCollaborators.from_agent
        mock_agent.config = SimpleNamespace()
        mock_prompt_builder = MagicMock()
        mock_recovery = MagicMock()

        self.handler = IntentTransitionHandler(mock_agent, mock_prompt_builder, mock_recovery)

    def _run_parity_check(self, response: str, payload: dict):
        """
        Runs a parity check by comparing the output of the new validator
        against the logic of the old IntentTransitionHandler helpers.
        """
        # Old logic from IntentTransitionHandler
        summary = self.handler._followup_surface_summary_after_current_transition(payload, response)
        old_conflict = str(summary.get("conflict_reason") or "")

        analysis = summary.get("analysis")
        old_action_only = False
        if analysis is not None and getattr(analysis, "ast", None) is not None:
            if getattr(analysis, "error", None) is None:
                if (
                    getattr(analysis.shape, "name", "") == "ACTION_ONLY"
                    and summary.get("intent_count") == 0
                    and summary.get("action_count") == 1
                    and summary.get("visible_count") == 0
                ):
                    old_action_only = True

        old_no_followup = not summary.get("has_substantive_nodes")

        # New logic from TransitionSemanticValidator
        new_result = self.validator.validate(response, payload)

        # Assertions
        if old_conflict:
            self.assertEqual(new_result.kind, TransitionResultKind.FOLLOWUP_CONFLICT)
            self.assertEqual(new_result.conflict_reason, old_conflict)
        elif old_action_only:
            self.assertEqual(new_result.kind, TransitionResultKind.FOLLOWUP_ACTION)
        elif old_no_followup:
            self.assertEqual(new_result.kind, TransitionResultKind.NO_FOLLOWUP)
        else:
            # For Step 2A, other cases (like plaintext) should be UNKNOWN
            self.assertEqual(new_result.kind, TransitionResultKind.UNKNOWN)

    def test_parity_no_followup(self):
        """Parity test for a response with no followup content."""
        response = '<intent mode="activate">{"mode": "activate", "goal": "test"}</intent>'
        payload = {"mode": "activate", "goal": "test"}
        self._run_parity_check(response, payload)

    def test_parity_followup_action(self):
        """Parity test for a response with a single followup action."""
        response = (
            '<intent mode="activate">{"mode": "activate"}</intent>'
            '<action>{"type": "run_shell", "command": "ls"}</action>'
        )
        payload = {"mode": "activate"}
        self._run_parity_check(response, payload)

    def test_parity_followup_conflict_multiple_actions(self):
        """Parity test for a response with multiple conflicting actions."""
        response = (
            '<intent mode="activate">{"mode": "activate"}</intent>'
            '<action>{"type": "run_shell"}</action>'
            '<action>{"type": "run_shell"}</action>'
        )
        payload = {"mode": "activate"}
        self._run_parity_check(response, payload)

    def test_parity_followup_conflict_mixed_content(self):
        """Parity test for a response with mixed action and text."""
        response = (
            '<intent mode="activate">{"mode": "activate"}</intent>'
            '<action>{"type": "run_shell"}</action>Some text.'
        )
        payload = {"mode": "activate"}
        self._run_parity_check(response, payload)

    def test_parity_plaintext_is_unknown(self):
        """Parity test for a plaintext response, which should be UNKNOWN in Step 2A."""
        response = '<intent mode="activate">{"mode": "activate"}</intent>This is a plaintext answer.'
        payload = {"mode": "activate"}
        self._run_parity_check(response, payload)


if __name__ == "__main__":
    unittest.main()
