from types import SimpleNamespace
from unittest.mock import MagicMock

from modules.agent.orchestration.responses.response_pipeline_stages import ResponsePipelineStagesMixin
from modules.agent.orchestration.runtime.execution_commit_observer import ExecutionCommitObserverAdapter
from modules.agent.orchestration.shared.decision_models import ExecutionCommit


class Harness(ResponsePipelineStagesMixin):
    def __init__(self, *, has_plan_review_checkpoint: bool, invalid_kind: str = "", checkpoint_before_action: bool | None = None):
        self.state = SimpleNamespace()
        self.stage_logger = SimpleNamespace(log=MagicMock())
        self.parser = SimpleNamespace(parse=MagicMock(return_value=[]))
        self._normalize_response_stage = MagicMock(
            side_effect=lambda response, **_kwargs: SimpleNamespace(normalized_response=response)
        )
        if checkpoint_before_action is None:
            checkpoint_before_action = has_plan_review_checkpoint
        self._classify_intent_output = MagicMock(
            return_value=SimpleNamespace(
                invalid_kind=invalid_kind,
                has_action_segment=False,
                auto_closed_think=False,
                auto_closed_think_reason="",
                auto_closed_think_tag="",
                runtime_protocol_semantics=SimpleNamespace(
                    has_plan_review_checkpoint=has_plan_review_checkpoint,
                    has_plan_review_checkpoint_before_action=checkpoint_before_action,
                ),
            )
        )
        self._merge_normalization_metadata = MagicMock()
        self._apply_compiler_diagnosis = MagicMock(
            return_value=SimpleNamespace(
                shape=SimpleNamespace(name="CHECKPOINT_ONLY"),
                error=None,
            )
        )
        self.semantics = SimpleNamespace(
            has_complete_think_before_action=MagicMock(return_value=False),
            has_memory_update_done_before_action=MagicMock(return_value=False),
            has_checkpoint_before_action=MagicMock(return_value=False),
        )
        self._log_semantic_shadow_disagreements = MagicMock()


def _state_changing_commit():
    return ExecutionCommit(
        shape="action_only",
        transaction_kind="single_action",
        action_effects=["edit_file:src/example.py"],
        action_dispatched=True,
        committed_action_count=1,
        committed_system_result_count=1,
    )


def test_plan_review_checkpoint_clears_required_state_in_classification_stage():
    harness = Harness(has_plan_review_checkpoint=True)
    ExecutionCommitObserverAdapter(harness.state).observe_execution_commit(
        None,
        _state_changing_commit(),
        sys_results=["ok"],
    )
    assert harness.state.plan_review_required_after_state_change is True

    classified = harness._run_classification_stage(
        SimpleNamespace(model_stop_reason=""),
        "<plan_review_done />",
        SimpleNamespace(response="<plan_review_done />", memory_checkpoint_and_action=False, plan_checkpoint_and_action=False),
    )

    assert harness.state.plan_review_required_after_state_change is False
    assert harness.state.plan_review_required_reason == ""
    assert harness.state.plan_review_required_action_type == ""
    assert harness.state.plan_review_required_target == ""
    assert harness.state.plan_review_required_action_effects == []
    assert classified.parsed_output.runtime_protocol_semantics.has_plan_review_checkpoint is True
    harness.stage_logger.log.assert_any_call(
        "response_pipeline",
        "pass",
        reason="plan_review_checkpoint_cleared",
        source="plan_review_checkpoint",
        plan_review_required_after_state_change=False,
        plan_review_required_reason="state_changing_action_committed",
        plan_review_required_action_type="edit_file",
        plan_review_required_target="src/example.py",
        plan_review_required_action_effects=["edit_file:src/example.py"],
    )


def test_invalid_response_with_plan_review_checkpoint_does_not_clear_required_state():
    harness = Harness(
        has_plan_review_checkpoint=True,
        invalid_kind="mixed_visible_text_and_control_protocol",
    )
    ExecutionCommitObserverAdapter(harness.state).observe_execution_commit(
        None,
        _state_changing_commit(),
        sys_results=["ok"],
    )

    harness._run_classification_stage(
        SimpleNamespace(model_stop_reason=""),
        '<plan_review_done />\nvisible text\n<action>{"type":"read_file","path":"x.py"}</action>',
        SimpleNamespace(response='<plan_review_done />\nvisible text\n<action>{"type":"read_file","path":"x.py"}</action>', memory_checkpoint_and_action=False, plan_checkpoint_and_action=True),
    )

    assert harness.state.plan_review_required_after_state_change is True
    assert harness.state.plan_review_required_action_type == "edit_file"
    assert harness.state.plan_review_required_target == "src/example.py"


def test_plan_review_checkpoint_after_action_does_not_clear_required_state():
    harness = Harness(has_plan_review_checkpoint=True, checkpoint_before_action=False)
    ExecutionCommitObserverAdapter(harness.state).observe_execution_commit(
        None,
        _state_changing_commit(),
        sys_results=["ok"],
    )

    harness._run_classification_stage(
        SimpleNamespace(model_stop_reason=""),
        '<action>{"type":"read_file","path":"x.py"}</action>\n<plan_review_done />',
        SimpleNamespace(response='<action>{"type":"read_file","path":"x.py"}</action>\n<plan_review_done />', memory_checkpoint_and_action=False, plan_checkpoint_and_action=True),
    )

    assert harness.state.plan_review_required_after_state_change is True
    assert harness.state.plan_review_required_action_type == "edit_file"
    assert harness.state.plan_review_required_target == "src/example.py"


def test_response_without_plan_review_checkpoint_does_not_clear_required_state():
    harness = Harness(has_plan_review_checkpoint=False)
    ExecutionCommitObserverAdapter(harness.state).observe_execution_commit(
        None,
        _state_changing_commit(),
        sys_results=["ok"],
    )

    harness._run_classification_stage(
        SimpleNamespace(model_stop_reason=""),
        "plain response",
        SimpleNamespace(response="plain response", memory_checkpoint_and_action=False, plan_checkpoint_and_action=False),
    )

    assert harness.state.plan_review_required_after_state_change is True
    assert harness.state.plan_review_required_action_type == "edit_file"
    assert harness.state.plan_review_required_target == "src/example.py"


def test_action_without_plan_review_checkpoint_is_not_blocked_by_clear_hook():
    harness = Harness(has_plan_review_checkpoint=False)
    harness.parser.parse.return_value = [SimpleNamespace(type="action", content={"type": "read_file", "path": "x.py"})]
    harness._classify_intent_output.return_value.has_action_segment = True

    classified = harness._run_classification_stage(
        SimpleNamespace(model_stop_reason=""),
        '<action>{"type":"read_file","path":"x.py"}</action>',
        SimpleNamespace(
            response='<action>{"type":"read_file","path":"x.py"}</action>',
            memory_checkpoint_and_action=False,
            plan_checkpoint_and_action=False,
        ),
    )

    assert classified.parsed_action_count == 1
    assert classified.parsed_output.has_action_segment is True
