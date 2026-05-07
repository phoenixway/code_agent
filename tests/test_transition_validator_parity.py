"""
Parity tests for TransitionSemanticValidator against IntentTransitionHandler.

Ensures that the replicated logic in the validator behaves identically to the
original helpers in IntentTransitionHandler for the migrated Step 2A cases.
"""

import unittest
from types import SimpleNamespace
from unittest.mock import MagicMock

from modules.agent.orchestration.transitions.intent_transitions import IntentTransitionHandler
from modules.agent.orchestration.transitions.transition_followup_semantics import TransitionFollowupSemantics
from modules.agent.orchestration.transitions.transition_semantic_validator import (
    TransitionResultKind,
    TransitionSemanticValidator,
)


class TransitionValidatorParityTests(unittest.TestCase):
    """Parity tests for Phase 5, Step 2A."""

    def setUp(self):
        """Set up the validator and a mocked IntentTransitionHandler."""
        self.validator = TransitionSemanticValidator()
        self.followup_semantics = TransitionFollowupSemantics()

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


    def _run_context_parity_check(
        self,
        response: str,
        payload: dict,
        *,
        transition_only_required: bool = False,
        reuse_only_required: bool = False,
        completion_requested: bool = False,
    ):
        """
        Runs a parity check for context-sensitive classifications against
        TransitionFollowupSemantics.evaluate_transition.
        """
        # New validator logic
        new_result = self.validator.validate(
            response,
            payload,
            transition_only_required=transition_only_required,
            reuse_only_required=reuse_only_required,
            completion_requested=completion_requested,
        )

        # Old logic from TransitionFollowupSemantics
        stripped = self.handler._strip_matching_current_intent_block(response, payload)
        analysis = self.handler._analyze_followup_surface(stripped)
        summary = self.followup_semantics.summarize(analysis)
        payload_mode = str((payload or {}).get("mode") or "").strip().lower()

        old_decision = self.followup_semantics.evaluate_transition(
            phase="accepted",
            summary=summary,
            payload_mode=payload_mode,
            completion_requested=completion_requested,
            transition_only_required=transition_only_required,
            reuse_only_required=reuse_only_required,
        )

        # Map old decision kind to new result kind
        expected_kind = TransitionResultKind.UNKNOWN
        if old_decision.kind == "transition_only_recovery_cannot_bundle_action":
            expected_kind = TransitionResultKind.TRANSITION_ONLY_VIOLATION
        elif old_decision.kind == "reuse_only_transition_cannot_bundle_action":
            expected_kind = TransitionResultKind.REUSE_ONLY_VIOLATION
        elif old_decision.kind == "intent_complete_with_action_not_allowed":
            expected_kind = TransitionResultKind.COMPLETE_WITH_ACTION_VIOLATION
        elif old_decision.kind in (
            "intent_reuse_applied_with_inline_followup_action",
            "intent_applied_with_followup_action",
        ):
            expected_kind = TransitionResultKind.FOLLOWUP_ACTION

        self.assertEqual(new_result.kind, expected_kind)

    def test_parity_transition_only_violation(self):
        """Parity test for TRANSITION_ONLY_VIOLATION."""
        response = '<intent mode="activate">{}</intent><action>{}</action>'
        payload = {"mode": "activate"}
        self._run_context_parity_check(response, payload, transition_only_required=True)

    def test_parity_reuse_only_violation(self):
        """Parity test for REUSE_ONLY_VIOLATION."""
        response = '<intent mode="reuse">{}</intent><action>{}</action>'
        payload = {"mode": "reuse"}
        self._run_context_parity_check(response, payload, reuse_only_required=True)

    def test_parity_complete_with_action_violation(self):
        """Parity test for COMPLETE_WITH_ACTION_VIOLATION."""
        response = '<intent mode="complete">{}</intent><action>{}</action>'
        payload = {"mode": "complete"}
        self._run_context_parity_check(response, payload, completion_requested=True)

    def test_parity_context_priority_order(self):
        """Parity test for the priority order of context flags."""
        response = '<intent mode="reuse">{}</intent><action>{}</action>'
        payload = {"mode": "reuse"}
        self._run_context_parity_check(
            response,
            payload,
            transition_only_required=True,
            reuse_only_required=True,
            completion_requested=True,
        )


if __name__ == "__main__":
    unittest.main()
