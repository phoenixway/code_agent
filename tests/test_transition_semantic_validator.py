"""Unit tests for transition_semantic_validator.py scaffolding."""

import unittest

from modules.agent.orchestration.transitions.transition_semantic_validator import (
    TransitionResultKind,
    TransitionSemanticValidator,
    TransitionValidationResult,
)


class TestTransitionSemanticValidatorScaffolding(unittest.TestCase):
    """Tests for the Phase 5, Step 1 scaffolding of TransitionSemanticValidator."""

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

    def test_validator_scaffold_returns_unknown(self):
        """Tests that the initial validator scaffold returns UNKNOWN."""
        validator = TransitionSemanticValidator()
        result = validator.validate("any response text")

        self.assertIsInstance(result, TransitionValidationResult)
        self.assertEqual(result.kind, TransitionResultKind.UNKNOWN)

    def test_validator_scaffold_accepts_all_arguments(self):
        """Tests that the validate method accepts all its arguments without error."""
        validator = TransitionSemanticValidator()
        result = validator.validate(
            response_text="any response text",
            intent_payload={"mode": "reuse"},
            transition_only_required=True,
            reuse_only_required=True,
        )
        self.assertEqual(result.kind, TransitionResultKind.UNKNOWN)

    def test_validator_scaffold_does_not_require_optional_arguments(self):
        """Tests that the validate method can be called with only required arguments."""
        validator = TransitionSemanticValidator()
        result = validator.validate(response_text="any response text")
        self.assertEqual(result.kind, TransitionResultKind.UNKNOWN)


if __name__ == "__main__":
    unittest.main()
