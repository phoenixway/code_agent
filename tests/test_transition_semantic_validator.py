"""Unit tests for transition_semantic_validator.py scaffolding."""

import unittest

from modules.agent.orchestration.transitions.transition_semantic_validator import (
    TransitionResultKind,
    TransitionSemanticValidator,
    TransitionValidationResult,
)


class TestTransitionSemanticValidator(unittest.TestCase):
    """Tests for the Phase 5, Step 1 scaffolding of TransitionSemanticValidator."""

    def setUp(self):
        """Set up the test case."""
        self.validator = TransitionSemanticValidator()

    def test_result_kind_enum_values_exist(self):
        """Tests that the key enum values are defined."""
        self.assertEqual(TransitionResultKind.NO_FOLLOWUP, "no_followup")
        self.assertEqual(TransitionResultKind.FOLLOWUP_ACTION, "followup_action")
        self.assertEqual(TransitionResultKind.FOLLOWUP_PLAINTEXT, "followup_plaintext")
        self.assertEqual(TransitionResultKind.FOLLOWUP_CONFLICT, "followup_conflict")
        self.assertEqual(TransitionResultKind.TRANSITION_ONLY_VIOLATION, "transition_only_violation")
        self.assertEqual(TransitionResultKind.REUSE_ONLY_VIOLATION, "reuse_only_violation")
        self.assertEqual(TransitionResultKind.COMPLETE_WITH_ACTION_VIOLATION, "complete_with_action_violation")
        self.assertEqual(TransitionResultKind.UNKNOWN, "unknown")

    def test_validation_result_dataclass_defaults(self):
        """Tests the default values of the TransitionValidationResult dataclass."""
        result = TransitionValidationResult(kind=TransitionResultKind.NO_FOLLOWUP)
        self.assertEqual(result.kind, TransitionResultKind.NO_FOLLOWUP)
        self.assertEqual(result.conflict_reason, "")
        self.assertEqual(result.reason, "")
        self.assertEqual(result.details, {})

    def test_validation_result_details_are_not_shared(self):
        """Tests that the 'details' field default_factory provides unique dicts."""
        result1 = TransitionValidationResult(kind=TransitionResultKind.UNKNOWN)
        result2 = TransitionValidationResult(kind=TransitionResultKind.UNKNOWN)

        result1.details["key"] = "value"

        self.assertNotEqual(result1.details, result2.details)
        self.assertIn("key", result1.details)
        self.assertNotIn("key", result2.details)

    def test_validate_no_followup(self):
        """Tests that a response with only a matching intent returns NO_FOLLOWUP."""
        response = '<intent mode="activate">{"mode": "activate"}</intent>'
        payload = {"mode": "activate"}
        result = self.validator.validate(response, payload)
        self.assertEqual(result.kind, TransitionResultKind.NO_FOLLOWUP)

    def test_validate_followup_action(self):
        """Tests that a response with an intent and a single action returns FOLLOWUP_ACTION."""
        response = '<intent mode="activate">{"mode": "activate"}</intent><action>{"type": "run_shell", "command": "ls"}</action>'
        payload = {"mode": "activate"}
        result = self.validator.validate(response, payload)
        self.assertEqual(result.kind, TransitionResultKind.FOLLOWUP_ACTION)

    def test_validate_followup_conflict(self):
        """Tests that a response with multiple actions returns FOLLOWUP_CONFLICT."""
        response = '<intent mode="activate">{"mode": "activate"}</intent><action>{}</action><action>{}</action>'
        payload = {"mode": "activate"}
        result = self.validator.validate(response, payload)
        self.assertEqual(result.kind, TransitionResultKind.FOLLOWUP_CONFLICT)
        self.assertIn("multiple_actions", result.conflict_reason)

    def test_validate_plaintext_is_unknown_in_step2a(self):
        """Tests that a response with plaintext followup returns UNKNOWN in Step 2A."""
        response = '<intent mode="activate">{"mode": "activate"}</intent>This is some text.'
        payload = {"mode": "activate"}
        result = self.validator.validate(response, payload)
        self.assertEqual(result.kind, TransitionResultKind.UNKNOWN)

    def test_validate_transition_only_violation(self):
        """Tests FOLLOWUP_ACTION is re-classified with transition_only_required=True."""
        response = '<intent mode="activate">{"mode": "activate"}</intent><action>{}</action>'
        payload = {"mode": "activate"}
        result = self.validator.validate(response, payload, transition_only_required=True)
        self.assertEqual(result.kind, TransitionResultKind.TRANSITION_ONLY_VIOLATION)

    def test_validate_reuse_only_violation(self):
        """Tests FOLLOWUP_ACTION is re-classified with reuse_only_required=True."""
        response = '<intent mode="reuse">{"mode": "reuse"}</intent><action>{}</action>'
        payload = {"mode": "reuse"}
        result = self.validator.validate(response, payload, reuse_only_required=True)
        self.assertEqual(result.kind, TransitionResultKind.REUSE_ONLY_VIOLATION)

    def test_validate_complete_with_action_violation(self):
        """Tests FOLLOWUP_ACTION is re-classified with completion_requested=True."""
        response = '<intent mode="complete">{"mode": "complete"}</intent><action>{}</action>'
        payload = {"mode": "complete"}
        result = self.validator.validate(response, payload, completion_requested=True)
        self.assertEqual(result.kind, TransitionResultKind.COMPLETE_WITH_ACTION_VIOLATION)

    def test_validate_context_flags_do_not_affect_non_action_followup(self):
        """Tests that context flags do not affect non-action results."""
        # No followup
        response_no_followup = '<intent mode="activate">{"mode": "activate"}</intent>'
        result = self.validator.validate(response_no_followup, {"mode": "activate"}, transition_only_required=True)
        self.assertEqual(result.kind, TransitionResultKind.NO_FOLLOWUP)

        # Conflict
        response_conflict = '<intent mode="activate">{"mode": "activate"}</intent><action>{}</action><action>{}</action>'
        result = self.validator.validate(response_conflict, {"mode": "activate"}, transition_only_required=True)
        self.assertEqual(result.kind, TransitionResultKind.FOLLOWUP_CONFLICT)

    def test_validate_context_flag_priority_order(self):
        """Tests that the priority of context flags matches legacy behavior."""
        response = '<intent mode="reuse">{"mode": "reuse"}</intent><action>{}</action>'
        payload = {"mode": "reuse"}

        # transition_only_required should have the highest priority
        result = self.validator.validate(
            response,
            payload,
            transition_only_required=True,
            reuse_only_required=True,
            completion_requested=True,
        )
        self.assertEqual(result.kind, TransitionResultKind.TRANSITION_ONLY_VIOLATION)

        # reuse_only_required is next
        result = self.validator.validate(
            response,
            payload,
            transition_only_required=False,
            reuse_only_required=True,
            completion_requested=True,
        )
        self.assertEqual(result.kind, TransitionResultKind.REUSE_ONLY_VIOLATION)


if __name__ == "__main__":
    unittest.main()
