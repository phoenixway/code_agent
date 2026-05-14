from types import SimpleNamespace

from modules.agent.orchestration.runtime.dispatch_pipeline import DispatchPipeline
from modules.agent.orchestration.shared.decision_models import ExecutionCommit


class Harness(DispatchPipeline):
    def __init__(self):
        self.state = SimpleNamespace(active_intent=None)


def _action_segment(action_type="write_file_block", path="test_file.txt"):
    return SimpleNamespace(type="action", content={"type": action_type, "path": path})


def _iteration(action_type="write_file_block", path="test_file.txt"):
    return SimpleNamespace(
        parsed_output=SimpleNamespace(
            compiler_shape="ACTION_ONLY",
            compiler_ir=SimpleNamespace(
                action_ops=[SimpleNamespace(action_type=action_type, payload={"type": action_type, "path": path})]
            ),
        )
    )


def test_fallback_execution_commit_is_built_without_execution_plan():
    harness = Harness()

    commit = harness._build_execution_commit(
        None,
        [_action_segment()],
        ["SYSTEM RESULT for `write_file_block`: Changes applied to test_file.txt"],
        False,
        iteration=_iteration(),
    )

    assert isinstance(commit, ExecutionCommit)
    assert commit.shape == "ACTION_ONLY"
    assert commit.transaction_kind == "fallback_single_action"
    assert commit.action_effects == ["write_file_block:test_file.txt"]
    assert commit.action_dispatched is True
    assert commit.committed_action_count == 1
    assert commit.committed_system_result_count == 1


def test_fallback_execution_commit_returns_none_without_action_effects():
    harness = Harness()
    iteration = SimpleNamespace(parsed_output=SimpleNamespace(compiler_shape="ACTION_ONLY", compiler_ir=None))

    commit = harness._build_execution_commit(
        None,
        [_action_segment()],
        ["SYSTEM RESULT for `write_file_block`: Changes applied to test_file.txt"],
        False,
        iteration=iteration,
    )

    assert commit is None


def test_fallback_execution_commit_feeds_plan_review_observer_for_write_file_block():
    from modules.agent.orchestration.runtime.execution_commit_observer import ExecutionCommitObserverAdapter

    harness = Harness()
    commit = harness._build_execution_commit(
        None,
        [_action_segment()],
        ["SYSTEM RESULT for `write_file_block`: Changes applied to test_file.txt"],
        False,
        iteration=_iteration(),
    )

    ExecutionCommitObserverAdapter(harness.state).observe_execution_commit(
        None,
        commit,
        sys_results=["SYSTEM RESULT for `write_file_block`: Changes applied to test_file.txt"],
    )

    assert harness.state.plan_review_required_after_state_change is True
    assert harness.state.plan_review_required_action_type == "write_file_block"
    assert harness.state.plan_review_required_target == "test_file.txt"
    assert harness.state.plan_review_required_action_effects == ["write_file_block:test_file.txt"]
