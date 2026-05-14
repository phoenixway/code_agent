from types import SimpleNamespace
from unittest.mock import MagicMock

from modules.agent.orchestration.responses.response_pipeline_stages import ResponsePipelineStagesMixin
from modules.agent.orchestration.prompts.recovery_prompt_builder import RecoveryPromptBuilderMixin


class GateHarness(ResponsePipelineStagesMixin):
    def __init__(self, *, pending: bool, has_action: bool, has_checkpoint: bool):
        self.state = SimpleNamespace(
            plan_review_required_after_state_change=pending,
            plan_review_required_reason="state_changing_action_committed",
            plan_review_required_action_type="edit_file",
            plan_review_required_target="src/example.py",
            plan_review_required_action_effects=["edit_file:src/example.py"],
        )
        self.semantics = SimpleNamespace(has_any_action_proposal=MagicMock(return_value=has_action))
        self.prompt_builder = SimpleNamespace(
            build_missing_plan_review_after_state_change_prompt=MagicMock(return_value="review prompt")
        )
        self.parsed_output = SimpleNamespace(
            runtime_protocol_semantics=SimpleNamespace(has_plan_review_checkpoint=has_checkpoint)
        )


def test_plan_review_gate_blocks_action_when_pending_and_checkpoint_missing():
    harness = GateHarness(pending=True, has_action=True, has_checkpoint=False)

    assert harness._plan_review_gate_should_block(harness.parsed_output, 1) is True
    assert harness._plan_review_gate_recovery_prompt() == "review prompt"
    harness.prompt_builder.build_missing_plan_review_after_state_change_prompt.assert_called_once_with(
        action_type="edit_file",
        target="src/example.py",
        reason="state_changing_action_committed",
        action_effects=["edit_file:src/example.py"],
    )


def test_plan_review_gate_allows_action_when_checkpoint_present():
    harness = GateHarness(pending=True, has_action=True, has_checkpoint=True)

    assert harness._plan_review_gate_should_block(harness.parsed_output, 1) is False


def test_plan_review_gate_allows_action_when_no_pending_review():
    harness = GateHarness(pending=False, has_action=True, has_checkpoint=False)

    assert harness._plan_review_gate_should_block(harness.parsed_output, 1) is False


def test_plan_review_gate_does_not_block_plain_text_without_action():
    harness = GateHarness(pending=True, has_action=False, has_checkpoint=False)

    assert harness._plan_review_gate_should_block(harness.parsed_output, 0) is False


def test_missing_plan_review_prompt_mentions_subgoal_review_and_checkpoint():
    class PromptHarness(RecoveryPromptBuilderMixin):
        pass

    prompt = PromptHarness().build_missing_plan_review_after_state_change_prompt(
        action_type="edit_file",
        target="src/example.py",
        reason="state_changing_action_committed",
        action_effects=["edit_file:src/example.py"],
    )

    assert "previous state-changing action succeeded" in prompt
    assert "edit_file on src/example.py" in prompt
    assert "<subgoal ... />" in prompt
    assert "mark_done" in prompt
    assert "<plan_review_done />" in prompt
    assert "Do not repeat the same edit" in prompt
    assert "Do not automatically complete the whole intent" in prompt
