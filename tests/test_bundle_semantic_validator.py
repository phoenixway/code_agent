"""Unit tests for the BundleSemanticValidator scaffold."""

import pytest

from modules.agent.orchestration.responses.bundle_semantic_validator import (
    BundleResultKind,
    BundleSemanticValidator,
    BundleValidationResult,
)


def test_bundle_result_kind_enum_members_exist():
    """Ensures all expected enum members are present."""
    expected_members = {
        "NO_BUNDLE_SHAPE",
        "INTENT_ACTION_BUNDLE_CANDIDATE",
        "READONLY_ACTION_BATCH_CANDIDATE",
        "INVALID_MULTIPLE_ACTIONS",
        "INVALID_ACTION_ARRAY",
        "INVALID_FILE_CONTENT_PAIRING",
        "INVALID_INTENT_COMPLETE_WITH_ACTION",
        "INVALID_MIXED_VISIBLE_TEXT",
        "UNKNOWN",
    }
    actual_members = {member.name for member in BundleResultKind}
    assert actual_members == expected_members


def test_bundle_validation_result_dataclass_defaults():
    """Tests the default factory for the result dataclass."""
    result1 = BundleValidationResult(kind=BundleResultKind.UNKNOWN)
    result2 = BundleValidationResult(kind=BundleResultKind.UNKNOWN)

    assert result1.kind == BundleResultKind.UNKNOWN
    assert result1.reason == ""
    assert result1.details == {}

    # Ensure the default `details` dict is not shared between instances
    result1.details["key"] = "value"
    assert result1.details == {"key": "value"}
    assert result2.details == {}


def test_bundle_semantic_validator_scaffold_returns_unknown():
    """
    Tests that the scaffold implementation of `validate` always returns UNKNOWN.
    """
    validator = BundleSemanticValidator()

    # Test with no arguments
    result = validator.validate()
    assert isinstance(result, BundleValidationResult)
    assert result.kind == BundleResultKind.UNKNOWN
    assert result.reason == ""
    assert result.details == {}


def test_bundle_semantic_validator_scaffold_accepts_args_but_returns_unknown():
    """
    Tests that the scaffold `validate` method accepts arguments but still
    returns UNKNOWN without processing them.
    """
    validator = BundleSemanticValidator()

    # Mock objects to simulate real arguments
    mock_parsed_output = object()
    mock_segments = [object()]
    mock_context = {"some_key": "some_value"}

    result = validator.validate(
        parsed_output=mock_parsed_output,
        segments=mock_segments,
        **mock_context,
    )

    assert isinstance(result, BundleValidationResult)
    assert result.kind == BundleResultKind.UNKNOWN


def test_invalid_mixed_visible_text_is_placeholder_only():
    """
    Confirms that INVALID_MIXED_VISIBLE_TEXT exists as a deferred enum member
    but is not returned by the current scaffold implementation.
    """
    # Check that the member exists
    assert "INVALID_MIXED_VISIBLE_TEXT" in BundleResultKind.__members__

    # Check that the scaffold does not return it
    validator = BundleSemanticValidator()
    result = validator.validate()
    assert result.kind != BundleResultKind.INVALID_MIXED_VISIBLE_TEXT
