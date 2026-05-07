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


def test_validate_with_no_input_returns_unknown():
    """
    Tests that `validate` returns UNKNOWN when no parsed_output is provided.
    """
    validator = BundleSemanticValidator()
    result = validator.validate()
    assert isinstance(result, BundleValidationResult)
    assert result.kind == BundleResultKind.UNKNOWN


class MockParsedOutput:
    """A mock ParsedModelOutput for testing."""

    def __init__(self, **kwargs):
        self.compiler_error_code = ""
        self.invalid_kind = ""
        self.compiler_shape = ""
        self.runtime_protocol_semantics = None
        for key, value in kwargs.items():
            setattr(self, key, value)


@pytest.mark.parametrize(
    "compiler_error_code, invalid_kind, expected_kind",
    [
        # Step 2A: Error-code-driven classifications
        (
            "E_ATOMIC_BUNDLE_REQUIRES_EXACTLY_ONE_ACTION",
            "action_payload_array",
            BundleResultKind.INVALID_ACTION_ARRAY,
        ),
        (
            "E_ATOMIC_BUNDLE_REQUIRES_EXACTLY_ONE_ACTION",
            "multiple_actions",
            BundleResultKind.INVALID_MULTIPLE_ACTIONS,
        ),
        (
            "E_FILE_CONTENT_REQUIRES_ACTION",
            "file_content_must_follow_action",
            BundleResultKind.INVALID_FILE_CONTENT_PAIRING,
        ),
        (
            "E_FILE_CONTENT_ACTION_MISMATCH",
            "file_content_must_follow_action",
            BundleResultKind.INVALID_FILE_CONTENT_PAIRING,
        ),
        # Fallback cases
        (None, None, BundleResultKind.UNKNOWN),
        ("", "", BundleResultKind.UNKNOWN),
        ("SOME_OTHER_ERROR", "some_kind", BundleResultKind.UNKNOWN),
        ("E_ATOMIC_BUNDLE_REQUIRES_EXACTLY_ONE_ACTION", None, BundleResultKind.UNKNOWN),
        ("E_ATOMIC_BUNDLE_REQUIRES_EXACTLY_ONE_ACTION", "", BundleResultKind.UNKNOWN),
        ("E_ATOMIC_BUNDLE_REQUIRES_EXACTLY_ONE_ACTION", "unknown_kind", BundleResultKind.UNKNOWN),
        # Deferred classifications should return UNKNOWN
        (
            "E_INTENT_COMPLETE_WITH_ACTION",
            "intent_complete_with_action_not_allowed",
            BundleResultKind.UNKNOWN,
        ),
    ],
)
def test_bundle_semantic_validator_step2a_error_code_logic(compiler_error_code, invalid_kind, expected_kind):
    """Tests the error-code-driven classification logic from Step 2A."""
    validator = BundleSemanticValidator()
    parsed_output = MockParsedOutput(compiler_error_code=compiler_error_code, invalid_kind=invalid_kind)

    result = validator.validate(parsed_output=parsed_output)

    assert isinstance(result, BundleValidationResult)
    assert result.kind == expected_kind


def test_validate_returns_unknown_for_empty_parsed_output():
    """Tests that validate handles an empty parsed_output gracefully."""
    validator = BundleSemanticValidator()
    assert validator.validate(parsed_output=MockParsedOutput()).kind == BundleResultKind.UNKNOWN


def test_validate_ignores_shape_only_metadata_in_step2a():
    """
    Tests that shape-only metadata is ignored in Step 2A, returning UNKNOWN.
    """
    validator = BundleSemanticValidator()
    parsed_output = MockParsedOutput(compiler_shape="INTENT_ACTION_BUNDLE")
    result = validator.validate(parsed_output=parsed_output)
    assert result.kind == BundleResultKind.UNKNOWN


def test_validate_ignores_segments_argument():
    """
    Tests that the `segments` argument is accepted but ignored, proving it's
    not used in Step 2A.
    """
    validator = BundleSemanticValidator()
    parsed_output = MockParsedOutput(
        compiler_error_code="E_ATOMIC_BUNDLE_REQUIRES_EXACTLY_ONE_ACTION",
        invalid_kind="action_payload_array",
    )
    # The result should be the same with or without segments
    result_with_segments = validator.validate(parsed_output=parsed_output, segments=[object()])
    result_without_segments = validator.validate(parsed_output=parsed_output)
    assert result_with_segments.kind == BundleResultKind.INVALID_ACTION_ARRAY
    assert result_with_segments.kind == result_without_segments.kind


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
