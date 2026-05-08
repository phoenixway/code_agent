"""Unit tests for action_policy_models."""

from modules.agent.orchestration.runtime.action_policy_models import (
    AtomicBundleActionValidationResult,
    AtomicBundlePolicyResultKind,
)


def test_atomic_bundle_policy_result_kind_values():
    """Tests that the enum values are stable strings."""
    assert AtomicBundlePolicyResultKind.OK == "ok"
    assert AtomicBundlePolicyResultKind.REJECTED_MULTIPLE_ACTIONS == "rejected_multiple_actions"
    assert AtomicBundlePolicyResultKind.REJECTED_INVALID_SHAPE == "rejected_invalid_shape"
    assert AtomicBundlePolicyResultKind.REJECTED_MISSING_FILE_CONTENT == "rejected_missing_file_content"
    assert AtomicBundlePolicyResultKind.REJECTED_INTENT_REQUIRED == "rejected_intent_required"
    assert (
        AtomicBundlePolicyResultKind.REJECTED_INTENT_ACTION_NOT_ALLOWED == "rejected_intent_action_not_allowed"
    )
    assert AtomicBundlePolicyResultKind.REJECTED_PRE_ACTION_CHECK == "rejected_pre_action_check"
    assert AtomicBundlePolicyResultKind.UNKNOWN == "unknown"


def test_atomic_bundle_action_validation_result_ok():
    """Tests that the dataclass can represent an OK result."""
    result = AtomicBundleActionValidationResult(
        kind=AtomicBundlePolicyResultKind.OK,
        ok=True,
    )
    assert result.kind == AtomicBundlePolicyResultKind.OK
    assert result.ok is True
    assert result.reason == ""
    assert result.details is None


def test_atomic_bundle_action_validation_result_rejection():
    """Tests that the dataclass can represent a rejection with legacy fields."""
    rejection_details = {
        "message": "Some error message",
        "blocked_action": "some_action",
    }
    result = AtomicBundleActionValidationResult(
        kind=AtomicBundlePolicyResultKind.REJECTED_INVALID_SHAPE,
        ok=False,
        reason="legacy_reason_string",
        details=rejection_details,
    )
    assert result.kind == AtomicBundlePolicyResultKind.REJECTED_INVALID_SHAPE
    assert result.ok is False
    assert result.reason == "legacy_reason_string"
    assert result.details == rejection_details
    assert result.details["message"] == "Some error message"
