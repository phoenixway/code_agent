from types import SimpleNamespace

from modules.agent.orchestration.runtime.execution_commit_observer import ExecutionCommitObserverAdapter
from modules.agent.orchestration.shared.decision_models import ExecutionCommit


def _commit(**overrides):
    data = {
        "shape": "action_only",
        "transaction_kind": "single_action",
        "action_effects": ["edit_file:src/example.py"],
        "action_dispatched": True,
        "committed_action_count": 1,
        "committed_system_result_count": 1,
    }
    data.update(overrides)
    return ExecutionCommit(**data)


def test_state_changing_file_commit_sets_plan_review_required_fields():
    state = SimpleNamespace()
    observer = ExecutionCommitObserverAdapter(state)

    observer.observe_execution_commit(None, _commit(), sys_results=["ok"])

    assert state.last_execution_commit.action_effects == ["edit_file:src/example.py"]
    assert state.plan_review_required_after_state_change is True
    assert state.plan_review_required_reason == "state_changing_action_committed"
    assert state.plan_review_required_action_type == "edit_file"
    assert state.plan_review_required_target == "src/example.py"
    assert state.plan_review_required_action_effects == ["edit_file:src/example.py"]


def test_read_only_commit_does_not_set_plan_review_required():
    state = SimpleNamespace()
    observer = ExecutionCommitObserverAdapter(state)

    observer.observe_execution_commit(
        None,
        _commit(action_effects=["read_file:src/example.py"]),
        sys_results=["ok"],
    )

    assert getattr(state, "plan_review_required_after_state_change", False) is False
    assert state.last_execution_commit.action_effects == ["read_file:src/example.py"]


def test_not_dispatched_commit_does_not_set_plan_review_required():
    state = SimpleNamespace()
    observer = ExecutionCommitObserverAdapter(state)

    observer.observe_execution_commit(
        None,
        _commit(action_dispatched=False, committed_action_count=0),
        sys_results=[],
    )

    assert getattr(state, "plan_review_required_after_state_change", False) is False


def test_plan_review_required_fields_can_be_cleared_after_checkpoint():
    state = SimpleNamespace()
    observer = ExecutionCommitObserverAdapter(state)
    observer.observe_execution_commit(None, _commit(), sys_results=["ok"])

    observer.clear_plan_review_required_after_checkpoint()

    assert state.plan_review_required_after_state_change is False
    assert state.plan_review_required_reason == ""
    assert state.plan_review_required_action_type == ""
    assert state.plan_review_required_target == ""
    assert state.plan_review_required_action_effects == []


def test_state_changing_classification_is_pure_and_reusable():
    observer = ExecutionCommitObserverAdapter(SimpleNamespace())

    assert observer.commit_requires_plan_review(_commit(action_effects=["create_file:new.py"])) is True
    assert observer.commit_requires_plan_review(_commit(action_effects=["append_file_block:notes.md"])) is True
    assert observer.commit_requires_plan_review(_commit(action_effects=["run_shell:pytest -q"])) is False
    assert observer.commit_requires_plan_review(None) is False
