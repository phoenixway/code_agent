"""Unit tests for ResponsePipelinePrevalidationMixin to prove behavior preservation."""

from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest

from modules.agent.orchestration.responses.response_pipeline_prevalidation import ResponsePipelinePrevalidationMixin
from modules.agent.orchestration.shared.decision_models import AtomicBundlePlan, ResponsePipelineOutcome


class MockParsedOutput:
    """A mock ParsedModelOutput for testing."""

    def __init__(self, **kwargs):
        self.compiler_error_code = ""
        self.invalid_kind = ""
        self.compiler_shape = ""
        self.runtime_protocol_semantics = None
        self.compiler_ir = None
        for key, value in kwargs.items():
            setattr(self, key, value)


class PrevalidationTestHarness(ResponsePipelinePrevalidationMixin):
    """A test harness for the mixin."""

    def __init__(self):
        self.state = SimpleNamespace(active_intent=None)
        self.intent_transitions = SimpleNamespace(
            preview_payload_decision=MagicMock(
                return_value=SimpleNamespace(
                    applied=True,
                    active_intent=SimpleNamespace(intent_type="test_intent", allowed_actions=[]),
                )
            )
        )
        self.stage_logger = SimpleNamespace(log=MagicMock())
        self.prompt_builder = SimpleNamespace(
            build_atomic_bundle_rejected_prompt=MagicMock(return_value="recovery_prompt")
        )

    def _atomic_bundle_plan_from_preview(self, payload: dict, preview) -> AtomicBundlePlan:
        return AtomicBundlePlan(
            bundle_validated=False,
            invalid_part=None,
            bundle_reason="",
            transition_applied=False,
            active_intent_unchanged=False,
            action_dispatched=False,
            before_active_intent_id="before",
            after_active_intent_id="after",
            proposed_intent_id="proposed",
            blocked_action="",
        )


@pytest.fixture
def harness():
    return PrevalidationTestHarness()


def test_reject_compiler_invalid_bundle_action_payload_array(harness):
    """Tests rejection for action_payload_array is behavior-preserving."""
    parsed_output = MockParsedOutput(
        compiler_error_code="E_ATOMIC_BUNDLE_REQUIRES_EXACTLY_ONE_ACTION",
        invalid_kind="action_payload_array",
    )
    payload = {"mode": "activate"}

    outcome = harness._reject_compiler_invalid_atomic_bundle_before_transition(
        ctx=None, payload=payload, parsed_output=parsed_output, response=""
    )

    assert isinstance(outcome, ResponsePipelineOutcome)
    assert outcome.reason == "atomic_bundle_action_invalid"
    assert outcome.atomic_bundle_plan.bundle_reason == "action_payload_array"
    harness.prompt_builder.build_atomic_bundle_rejected_prompt.assert_called_once()
    call_kwargs = harness.prompt_builder.build_atomic_bundle_rejected_prompt.call_args.kwargs
    assert call_kwargs["invalid_part"] == "action"
    assert "Do not return an action array" in call_kwargs["reason"]


def test_reject_compiler_invalid_bundle_multiple_actions(harness):
    """Tests rejection for multiple_actions is behavior-preserving."""
    parsed_output = MockParsedOutput(
        compiler_error_code="E_ATOMIC_BUNDLE_REQUIRES_EXACTLY_ONE_ACTION",
        invalid_kind="multiple_actions",
    )
    payload = {"mode": "activate"}

    outcome = harness._reject_compiler_invalid_atomic_bundle_before_transition(
        ctx=None, payload=payload, parsed_output=parsed_output, response=""
    )

    assert isinstance(outcome, ResponsePipelineOutcome)
    assert outcome.reason == "atomic_bundle_action_invalid"
    assert outcome.atomic_bundle_plan.bundle_reason == "multiple_actions"
    harness.prompt_builder.build_atomic_bundle_rejected_prompt.assert_called_once()
    call_kwargs = harness.prompt_builder.build_atomic_bundle_rejected_prompt.call_args.kwargs
    assert call_kwargs["invalid_part"] == "action"
    assert "Do not return multiple <action> blocks" in call_kwargs["reason"]


def test_reject_compiler_invalid_bundle_file_content_pairing(harness):
    """Tests rejection for file_content_must_follow_action is behavior-preserving."""
    parsed_output = MockParsedOutput(
        compiler_error_code="E_FILE_CONTENT_REQUIRES_ACTION",
        invalid_kind="file_content_must_follow_action",
    )
    payload = {"mode": "activate"}

    outcome = harness._reject_compiler_invalid_atomic_bundle_before_transition(
        ctx=None, payload=payload, parsed_output=parsed_output, response=""
    )

    assert isinstance(outcome, ResponsePipelineOutcome)
    assert outcome.reason == "atomic_bundle_file_content_invalid"
    assert outcome.atomic_bundle_plan.bundle_reason == "file_content_must_follow_action"
    harness.prompt_builder.build_atomic_bundle_rejected_prompt.assert_called_once()
    call_kwargs = harness.prompt_builder.build_atomic_bundle_rejected_prompt.call_args.kwargs
    assert call_kwargs["invalid_part"] == "file_content"
    assert "write_file_block requires a complete" in call_kwargs["reason"]


def test_reject_compiler_invalid_bundle_passes_through_for_mismatch_error(harness):
    """Tests that E_FILE_CONTENT_ACTION_MISMATCH passes through, preserving legacy behavior."""
    parsed_output = MockParsedOutput(
        compiler_error_code="E_FILE_CONTENT_ACTION_MISMATCH",
        invalid_kind="file_content_must_follow_action",
    )
    payload = {"mode": "activate"}

    outcome = harness._reject_compiler_invalid_atomic_bundle_before_transition(
        ctx=None, payload=payload, parsed_output=parsed_output, response=""
    )

    assert outcome is None


def test_reject_compiler_invalid_bundle_passes_through_for_other_errors(harness):
    """Tests that other compiler errors pass through, preserving legacy behavior."""
    parsed_output = MockParsedOutput(
        compiler_error_code="SOME_OTHER_ERROR",
        invalid_kind="some_other_kind",
    )
    payload = {"mode": "activate"}

    outcome = harness._reject_compiler_invalid_atomic_bundle_before_transition(
        ctx=None, payload=payload, parsed_output=parsed_output, response=""
    )

    assert outcome is None


def test_reject_compiler_invalid_bundle_passes_through_if_not_bundle_kind(harness):
    """Tests that non-bundle validation kinds pass through."""
    # The compiler_code is in this consumer's legacy gate.
    # But the invalid_kind is not one of the approved bundle invalid kinds,
    # so the BundleSemanticValidator returns UNKNOWN.
    # This test asserts that the method preserves the legacy pass-through behavior.
    parsed_output = MockParsedOutput(
        compiler_error_code="E_ATOMIC_BUNDLE_REQUIRES_EXACTLY_ONE_ACTION",
        invalid_kind="some_other_kind",  # This makes the validator return UNKNOWN
    )
    payload = {"mode": "activate"}

    outcome = harness._reject_compiler_invalid_atomic_bundle_before_transition(
        ctx=None, payload=payload, parsed_output=parsed_output, response=""
    )

    assert outcome is None
