from types import SimpleNamespace
from unittest.mock import MagicMock

from modules.agent.orchestration.responses.response_pipeline_stages import ResponsePipelineStagesMixin
from modules.agent.orchestration.prompts.recovery_prompt_builder import RecoveryPromptBuilderMixin
from modules.agent.orchestration.runtime.execution_commit_observer import ExecutionCommitObserverAdapter
from modules.agent.orchestration.shared.decision_models import ExecutionCommit


class PlanReviewClassificationHarness(ResponsePipelineStagesMixin):
    def __init__(
        self,
        *,
        has_plan_review_checkpoint: bool,
        checkpoint_before_action: bool | None = None,
        invalid_kind: str = "",
    ):
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


class PlanReviewGateHarness(ResponsePipelineStagesMixin, RecoveryPromptBuilderMixin):
    def __init__(
        self,
        *,
        pending: bool,
        has_action: bool,
        has_checkpoint: bool,
        checkpoint_before_action: bool = False,
    ):
        self.state = SimpleNamespace(
            plan_review_required_after_state_change=pending,
            plan_review_required_reason="state_changing_action_committed" if pending else "",
            plan_review_required_action_type="edit_file" if pending else "",
            plan_review_required_target="src/example.py" if pending else "",
            plan_review_required_action_effects=["edit_file:src/example.py"] if pending else [],
        )
        self.stage_logger = SimpleNamespace(log=MagicMock())
        self.semantics = SimpleNamespace(
            has_any_action_proposal=MagicMock(return_value=has_action),
        )
        self.parsed_output = SimpleNamespace(
            runtime_protocol_semantics=SimpleNamespace(
                has_plan_review_checkpoint=has_checkpoint,
                has_plan_review_checkpoint_before_action=checkpoint_before_action,
            ),
            has_action_segment=has_action,
        )


def _state_changing_commit(action_type: str = "edit_file", path: str = "src/example.py") -> ExecutionCommit:
    return ExecutionCommit(
        shape="action_only",
        transaction_kind="single_action",
        action_effects=[f"{action_type}:{path}"],
        action_dispatched=True,
        committed_action_count=1,
        committed_system_result_count=1,
    )


def test_p36_state_changing_action_sets_plan_review_required_metadata():
    state = SimpleNamespace()

    ExecutionCommitObserverAdapter(state).observe_execution_commit(
        None,
        _state_changing_commit("edit_file", "src/example.py"),
        sys_results=["SYSTEM RESULT for `edit_file`: Changes applied to src/example.py"],
    )

    assert state.plan_review_required_after_state_change is True
    assert state.plan_review_required_reason == "state_changing_action_committed"
    assert state.plan_review_required_action_type == "edit_file"
    assert state.plan_review_required_target == "src/example.py"
    assert state.plan_review_required_action_effects == ["edit_file:src/example.py"]


def test_p36_file_action_plan_review_metadata_current_classification_is_characterized():
    # Characterization: this smoke test documents the current observer
    # classification for mutating-looking file actions without expanding
    # production behavior from this tests-only slice.
    cases = [
        ("write_file_block", "src/generated.py"),
        ("replace_line_range", "src/range_target.py"),
        ("create_file", "src/new_file.py"),
    ]

    observed = {}

    for action_type, path in cases:
        state = SimpleNamespace()

        ExecutionCommitObserverAdapter(state).observe_execution_commit(
            None,
            _state_changing_commit(action_type, path),
            sys_results=[f"SYSTEM RESULT for `{action_type}`: Changes applied to {path}"],
        )

        observed[action_type] = bool(getattr(state, "plan_review_required_after_state_change", False))

        if observed[action_type]:
            assert state.plan_review_required_reason == "state_changing_action_committed"
            assert state.plan_review_required_action_type == action_type
            assert state.plan_review_required_target == path
            assert state.plan_review_required_action_effects == [f"{action_type}:{path}"]

    assert observed["write_file_block"] is True
    assert observed["create_file"] is True
    assert observed["replace_line_range"] is True


def test_p36_action_then_plan_review_done_does_not_allow_next_action_past_gate():
    harness = PlanReviewGateHarness(
        pending=True,
        has_action=True,
        has_checkpoint=True,
        checkpoint_before_action=False,
    )

    assert harness._plan_review_gate_should_block(harness.parsed_output, parsed_action_count=1) is True

    prompt = harness.build_missing_plan_review_after_state_change_prompt(
        action_type="edit_file",
        target="src/example.py",
        reason="state_changing_action_committed",
        action_effects=["edit_file:src/example.py"],
    )
    assert "previous state-changing action succeeded" in prompt
    assert "<plan_review_done />" in prompt
    assert "mark_done" in prompt


def test_p36_plan_review_done_before_action_allows_action_past_gate():
    harness = PlanReviewGateHarness(
        pending=True,
        has_action=True,
        has_checkpoint=True,
        checkpoint_before_action=True,
    )

    assert harness._plan_review_gate_should_block(harness.parsed_output, parsed_action_count=1) is False


def test_p36_plain_response_without_plan_review_done_does_not_clear_required_state():
    harness = PlanReviewClassificationHarness(has_plan_review_checkpoint=False)
    ExecutionCommitObserverAdapter(harness.state).observe_execution_commit(
        None,
        _state_changing_commit(),
        sys_results=["SYSTEM RESULT for `edit_file`: Changes applied to src/example.py"],
    )

    harness._run_classification_stage(
        SimpleNamespace(model_stop_reason=""),
        "plain response without checkpoint",
        SimpleNamespace(
            response="plain response without checkpoint",
            memory_checkpoint_and_action=False,
            plan_checkpoint_and_action=False,
        ),
    )

    assert harness.state.plan_review_required_after_state_change is True
    assert harness.state.plan_review_required_action_type == "edit_file"
    assert harness.state.plan_review_required_target == "src/example.py"


def test_p36_plan_review_done_after_action_does_not_clear_required_state_in_classification():
    harness = PlanReviewClassificationHarness(
        has_plan_review_checkpoint=True,
        checkpoint_before_action=False,
    )
    ExecutionCommitObserverAdapter(harness.state).observe_execution_commit(
        None,
        _state_changing_commit(),
        sys_results=["SYSTEM RESULT for `edit_file`: Changes applied to src/example.py"],
    )

    harness._run_classification_stage(
        SimpleNamespace(model_stop_reason=""),
        '<action>{"type":"read_file","path":"x.py"}</action>\n<plan_review_done />',
        SimpleNamespace(
            response='<action>{"type":"read_file","path":"x.py"}</action>\n<plan_review_done />',
            memory_checkpoint_and_action=False,
            plan_checkpoint_and_action=True,
        ),
    )

    assert harness.state.plan_review_required_after_state_change is True
    assert harness.state.plan_review_required_action_type == "edit_file"
    assert harness.state.plan_review_required_target == "src/example.py"


def test_p36_plan_review_done_before_action_clears_required_state_in_classification():
    harness = PlanReviewClassificationHarness(
        has_plan_review_checkpoint=True,
        checkpoint_before_action=True,
    )
    ExecutionCommitObserverAdapter(harness.state).observe_execution_commit(
        None,
        _state_changing_commit(),
        sys_results=["SYSTEM RESULT for `edit_file`: Changes applied to src/example.py"],
    )

    harness._run_classification_stage(
        SimpleNamespace(model_stop_reason=""),
        '<plan_review_done />\n<action>{"type":"read_file","path":"x.py"}</action>',
        SimpleNamespace(
            response='<plan_review_done />\n<action>{"type":"read_file","path":"x.py"}</action>',
            memory_checkpoint_and_action=False,
            plan_checkpoint_and_action=True,
        ),
    )

    assert harness.state.plan_review_required_after_state_change is False
    assert harness.state.plan_review_required_reason == ""
    assert harness.state.plan_review_required_action_type == ""
    assert harness.state.plan_review_required_target == ""
    assert harness.state.plan_review_required_action_effects == []
