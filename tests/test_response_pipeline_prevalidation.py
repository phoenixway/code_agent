"""Unit tests for ResponsePipelinePrevalidationMixin to prove behavior preservation."""

from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest

from modules.agent.orchestration.responses.response_pipeline_prevalidation import ResponsePipelinePrevalidationMixin
from modules.agent.orchestration.runtime.action_policy_models import AtomicBundlePolicyResultKind
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
        # Add mocks for the legacy bundle validation path
        self.action_policy = SimpleNamespace(validate_atomic_bundle_action=MagicMock())
        self.semantics = SimpleNamespace(has_any_action_proposal=MagicMock(return_value=True))

    def _has_any_action_proposal(self, parsed_output, *, parsed_action_count: int = 0) -> bool:
        """Mocked version of _has_any_action_proposal."""
        return self.semantics.has_any_action_proposal(parsed_output, parsed_action_count=parsed_action_count)

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
    h = PrevalidationTestHarness()
    # Reset mocks before each test
    h.intent_transitions.preview_payload_decision.reset_mock()
    h.stage_logger.log.reset_mock()
    h.prompt_builder.build_atomic_bundle_rejected_prompt.reset_mock()
    h.action_policy.validate_atomic_bundle_action.reset_mock()
    h.semantics.has_any_action_proposal.reset_mock()
    h.semantics.has_any_action_proposal.return_value = True
    return h


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


# --- Characterization tests for _reject_invalid_atomic_bundle_before_transition ---


def test_reject_invalid_atomic_bundle_passes_through_for_non_bundle_mode(harness):
    """_reject_invalid_atomic_bundle_before_transition passes through if payload mode is not a bundle mode."""
    payload = {"mode": "complete"}  # Not activate, reuse, or replace
    outcome = harness._reject_invalid_atomic_bundle_before_transition(
        ctx=None, payload=payload, parsed_output=MockParsedOutput(), segments=[], response=""
    )
    assert outcome is None
    harness.action_policy.validate_atomic_bundle_action.assert_not_called()


def test_reject_invalid_atomic_bundle_passes_through_if_no_action(harness):
    """_reject_invalid_atomic_bundle_before_transition passes through if there is no action proposal."""
    harness.semantics.has_any_action_proposal.return_value = False
    payload = {"mode": "activate"}
    outcome = harness._reject_invalid_atomic_bundle_before_transition(
        ctx=None, payload=payload, parsed_output=MockParsedOutput(), segments=[], response=""
    )
    assert outcome is None
    harness.action_policy.validate_atomic_bundle_action.assert_not_called()


def test_reject_invalid_atomic_bundle_rejects_on_invalid_intent_preview(harness):
    """_reject_invalid_atomic_bundle_before_transition rejects if the intent transition preview is invalid."""
    harness.intent_transitions.preview_payload_decision.return_value = SimpleNamespace(
        applied=False, message="invalid_intent_transition"
    )
    payload = {"mode": "activate", "goal": "test goal"}
    outcome = harness._reject_invalid_atomic_bundle_before_transition(
        ctx=None, payload=payload, parsed_output=MockParsedOutput(), segments=[], response=""
    )
    assert isinstance(outcome, ResponsePipelineOutcome)
    assert outcome.reason == "atomic_bundle_intent_invalid"
    assert outcome.source == "intent_atomic_bundle_guard"
    assert outcome.atomic_bundle_plan.invalid_part == "intent"
    assert outcome.atomic_bundle_plan.bundle_reason == "invalid_intent_transition"
    harness.prompt_builder.build_atomic_bundle_rejected_prompt.assert_called_once_with(
        invalid_part="intent", reason="invalid_intent_transition", goal="test goal"
    )


def test_reject_invalid_atomic_bundle_rejects_on_action_policy_fail(harness):
    """_reject_invalid_atomic_bundle_before_transition rejects if action_policy validation fails."""
    harness.action_policy.validate_atomic_bundle_action.return_value = SimpleNamespace(
        ok=False,
        kind=AtomicBundlePolicyResultKind.REJECTED_MISSING_FILE_CONTENT,
        reason="missing_file_content_block",
        details={
            "message": "write_file_block requires a complete <file_content>...</file_content> block",
            "blocked_action": "write_file_block",
            "allowed_actions": [],
        },
    )
    payload = {"mode": "activate", "goal": "test goal"}
    outcome = harness._reject_invalid_atomic_bundle_before_transition(
        ctx=None, payload=payload, parsed_output=MockParsedOutput(), segments=[], response=""
    )
    assert isinstance(outcome, ResponsePipelineOutcome)
    assert outcome.reason == "atomic_bundle_file_content_invalid"
    assert outcome.source == "intent_atomic_bundle_guard"
    assert outcome.atomic_bundle_plan.invalid_part == "file_content"
    assert outcome.atomic_bundle_plan.bundle_reason == "missing_file_content_block"
    assert outcome.atomic_bundle_plan.blocked_action == "write_file_block"
    harness.prompt_builder.build_atomic_bundle_rejected_prompt.assert_called_once_with(
        invalid_part="file_content",
        reason="write_file_block requires a complete <file_content>...</file_content> block",
        blocked_action="write_file_block",
        proposed_allowed_actions=[],
        goal="test goal",
    )


def test_reject_invalid_atomic_bundle_passes_through_on_action_policy_ok(harness):
    """_reject_invalid_atomic_bundle_before_transition passes through if action_policy validation is ok."""
    harness.action_policy.validate_atomic_bundle_action.return_value = SimpleNamespace(ok=True)
    harness.intent_transitions.preview_payload_decision.return_value.active_intent.intent_id = "test_intent_id"
    payload = {"mode": "activate"}
    outcome = harness._reject_invalid_atomic_bundle_before_transition(
        ctx=None, payload=payload, parsed_output=MockParsedOutput(), segments=[], response=""
    )
    assert outcome is None
    harness.stage_logger.log.assert_called_with(
        "response_pipeline",
        "pass",
        reason="atomic_bundle_validated",
        source="intent_atomic_bundle_guard",
        bundle_validated=True,
        invalid_part="",
        bundle_reason="validated",
        transition_applied=True,
        action_dispatched=True,
        active_intent_unchanged=False,
        before_active_intent_id="",
        after_active_intent_id="test_intent_id",
    )
