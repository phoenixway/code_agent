from types import SimpleNamespace
from unittest.mock import MagicMock

from modules.agent.orchestration.responses.response_pipeline_stages import ResponsePipelineStagesMixin
from modules.agent.orchestration.prompts.recovery_prompt_builder import RecoveryPromptBuilderMixin


class BlockedActionVisibilityHarness(ResponsePipelineStagesMixin, RecoveryPromptBuilderMixin):
    def __init__(self):
        self.state = SimpleNamespace(
            active_intent=SimpleNamespace(intent_id="intent-1"),
            plan_review_required_after_state_change=True,
            plan_review_required_reason="state_changing_action_committed",
            plan_review_required_action_type="edit_file",
            plan_review_required_target="src/example.py",
            plan_review_required_action_effects=["edit_file:src/example.py"],
            pending_loop_stop_info=None,
        )
        self.prompt_builder = self
        self.stage_logger = SimpleNamespace(log=MagicMock())
        self.semantics = SimpleNamespace(
            has_any_action_proposal=MagicMock(return_value=True),
        )
        self.parsed_output = SimpleNamespace(
            runtime_protocol_semantics=SimpleNamespace(
                has_plan_review_checkpoint=False,
                has_plan_review_checkpoint_before_action=False,
            )
        )


def test_p40_plan_review_gate_blocked_action_sets_next_turn_current_intent_recovery_metadata():
    harness = BlockedActionVisibilityHarness()

    assert harness._plan_review_gate_should_block(harness.parsed_output, parsed_action_count=1) is True

    recovery = harness._plan_review_gate_recovery_prompt()
    active_intent_id = harness.state.active_intent.intent_id
    recovery_visibility = {
        "mode": "next_turn",
        "intent_scope": "current_intent",
        "intent_id": active_intent_id,
        "reason": "missing_plan_review_after_state_change",
    }
    status_text = (
        "Action was not executed.\n"
        "Reason: plan_review_required_after_state_change.\n"
        "Next required step: review plan/subgoals and emit <plan_review_done /> before any action."
    )
    harness.state.pending_loop_stop_info = {
        "reason": "missing_plan_review_after_state_change",
        "recoverable": True,
        "action_proposed_but_not_executed": True,
        "tool_execution_attempted": False,
        "status_text": status_text,
        "recovery_instruction": recovery,
        "recovery_visibility": recovery_visibility,
    }

    assert "Action was not executed" in status_text
    assert "plan_review_required_after_state_change" in status_text
    assert "Do not emit any <action>" in recovery
    assert "Review current plan and sub-goals" in recovery
    assert "<plan_review_done />" in recovery
    assert "[EXIT_CONDITION]" in recovery
    assert harness.state.pending_loop_stop_info["action_proposed_but_not_executed"] is True
    assert harness.state.pending_loop_stop_info["tool_execution_attempted"] is False
    assert harness.state.pending_loop_stop_info["recovery_visibility"] == {
        "mode": "next_turn",
        "intent_scope": "current_intent",
        "intent_id": "intent-1",
        "reason": "missing_plan_review_after_state_change",
    }


def test_p40_plan_review_done_then_action_still_allowed_by_existing_gate_invariant():
    harness = BlockedActionVisibilityHarness()
    harness.parsed_output.runtime_protocol_semantics.has_plan_review_checkpoint = True
    harness.parsed_output.runtime_protocol_semantics.has_plan_review_checkpoint_before_action = True

    assert harness._plan_review_gate_should_block(harness.parsed_output, parsed_action_count=1) is False
