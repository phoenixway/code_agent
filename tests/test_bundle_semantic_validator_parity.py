"""
Parity tests for the BundleSemanticValidator.

Phase 6, Step 2C: Parity Testing.
These tests prove that the validator's classifications are behaviorally
equivalent to the documented legacy logic for all classifications implemented
through Step 2B.

These tests are based on the explicit mappings defined in the design document
and do not re-implement or simulate complex legacy logic.
"""

import pytest

from modules.agent.orchestration.responses.bundle_semantic_validator import (
    BundleResultKind,
    BundleSemanticValidator,
    BundleValidationResult,
)


class MockParsedOutput:
    """A minimal mock ParsedModelOutput for parity testing."""

    def __init__(self, **kwargs):
        self.compiler_error_code = ""
        self.invalid_kind = ""
        self.compiler_shape = ""
        self.runtime_protocol_semantics = None
        self.compiler_ir = None
        for key, value in kwargs.items():
            setattr(self, key, value)


# --- Parity Tests for Step 2A: Error-Code-Driven Classification ---


@pytest.mark.parametrize(
    "compiler_error_code, invalid_kind, expected_kind",
    [
        # Documented mappings
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
        # Deferred classification should return UNKNOWN
        (
            "E_INTENT_COMPLETE_WITH_ACTION",
            "intent_complete_with_action_not_allowed",
            BundleResultKind.UNKNOWN,
        ),
        # Fallback cases for unknown or incomplete error codes
        (None, None, BundleResultKind.UNKNOWN),
        ("", "", BundleResultKind.UNKNOWN),
        ("SOME_OTHER_ERROR", "some_kind", BundleResultKind.UNKNOWN),
        ("E_ATOMIC_BUNDLE_REQUIRES_EXACTLY_ONE_ACTION", None, BundleResultKind.UNKNOWN),
        ("E_ATOMIC_BUNDLE_REQUIRES_EXACTLY_ONE_ACTION", "unknown_kind", BundleResultKind.UNKNOWN),
    ],
)
def test_parity_step2a_error_code_mappings(compiler_error_code, invalid_kind, expected_kind):
    """
    Tests parity with the documented error-code-driven classification mappings.
    """
    validator = BundleSemanticValidator()
    parsed_output = MockParsedOutput(compiler_error_code=compiler_error_code, invalid_kind=invalid_kind)
    result = validator.validate(parsed_output=parsed_output)
    assert isinstance(result, BundleValidationResult)
    assert result.kind == expected_kind


# --- Parity Tests for Step 2B: Shape-Driven Classification ---


@pytest.mark.parametrize(
    "compiler_shape, expected_kind",
    [
        # Documented mappings
        ("INTENT_ACTION_BUNDLE", BundleResultKind.INTENT_ACTION_BUNDLE_CANDIDATE),
        ("READ_ONLY_BATCH_CANDIDATE", BundleResultKind.READONLY_ACTION_BATCH_CANDIDATE),
        ("INTENT_ONLY", BundleResultKind.NO_BUNDLE_SHAPE),
        # Deferred shapes must return UNKNOWN
        ("ACTION_ONLY", BundleResultKind.UNKNOWN),
        ("PLAINTEXT_ONLY", BundleResultKind.UNKNOWN),
        ("INTENT_COMPLETE_WITH_TEXT", BundleResultKind.UNKNOWN),
        ("MEMORY_TEXT", BundleResultKind.UNKNOWN),
        ("PRE_ACTION_TEXT_AND_ACTION", BundleResultKind.UNKNOWN),
        # Fallback cases for unknown or missing shape
        ("UNKNOWN_SHAPE", BundleResultKind.UNKNOWN),
        ("", BundleResultKind.UNKNOWN),
        (None, BundleResultKind.UNKNOWN),
    ],
)
def test_parity_step2b_shape_mappings(compiler_shape, expected_kind):
    """
    Tests parity with the documented shape-driven classification mappings.
    """
    validator = BundleSemanticValidator()
    parsed_output = MockParsedOutput(compiler_shape=compiler_shape)
    result = validator.validate(parsed_output=parsed_output)
    assert isinstance(result, BundleValidationResult)
    assert result.kind == expected_kind


# --- Parity Tests for Precedence ---


@pytest.mark.parametrize(
    "compiler_shape, compiler_error_code, invalid_kind, expected_kind",
    [
        (
            "INTENT_ACTION_BUNDLE",
            "E_ATOMIC_BUNDLE_REQUIRES_EXACTLY_ONE_ACTION",
            "action_payload_array",
            BundleResultKind.INVALID_ACTION_ARRAY,
        ),
        (
            "READ_ONLY_BATCH_CANDIDATE",
            "E_ATOMIC_BUNDLE_REQUIRES_EXACTLY_ONE_ACTION",
            "multiple_actions",
            BundleResultKind.INVALID_MULTIPLE_ACTIONS,
        ),
        (
            "INTENT_ONLY",
            "E_FILE_CONTENT_REQUIRES_ACTION",
            "file_content_must_follow_action",
            BundleResultKind.INVALID_FILE_CONTENT_PAIRING,
        ),
    ],
)
def test_parity_precedence_error_code_over_shape(
    compiler_shape, compiler_error_code, invalid_kind, expected_kind
):
    """
    Tests that Step 2A error-code logic takes precedence over Step 2B shape logic.
    """
    validator = BundleSemanticValidator()
    parsed_output = MockParsedOutput(
        compiler_shape=compiler_shape,
        compiler_error_code=compiler_error_code,
        invalid_kind=invalid_kind,
    )
    result = validator.validate(parsed_output=parsed_output)
    assert result.kind == expected_kind
    # Also assert it's not the shape-based kind
    if expected_kind == BundleResultKind.INVALID_ACTION_ARRAY:
        assert result.kind != BundleResultKind.INTENT_ACTION_BUNDLE_CANDIDATE
    elif expected_kind == BundleResultKind.INVALID_MULTIPLE_ACTIONS:
        assert result.kind != BundleResultKind.READONLY_ACTION_BATCH_CANDIDATE
    elif expected_kind == BundleResultKind.INVALID_FILE_CONTENT_PAIRING:
        assert result.kind != BundleResultKind.NO_BUNDLE_SHAPE


def test_parity_unknown_if_no_compiler_metadata():
    """
    Tests that the result is UNKNOWN if no compiler metadata is present.
    """
    validator = BundleSemanticValidator()
    parsed_output = MockParsedOutput()
    result = validator.validate(parsed_output=parsed_output)
    assert result.kind == BundleResultKind.UNKNOWN
