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


def test_not_dispatched_commit_without_system_result_does_not_set_plan_review_required():
    state = SimpleNamespace()
    observer = ExecutionCommitObserverAdapter(state)

    observer.observe_execution_commit(
        None,
        _commit(action_dispatched=False, committed_action_count=0, committed_system_result_count=0),
        sys_results=[],
    )

    assert getattr(state, "plan_review_required_after_state_change", False) is False


def test_system_result_only_state_changing_commit_sets_plan_review_required():
    state = SimpleNamespace()
    observer = ExecutionCommitObserverAdapter(state)

    observer.observe_execution_commit(
        None,
        _commit(
            action_effects=["create_file:smoke_test.txt"],
            action_dispatched=False,
            committed_action_count=0,
            committed_system_result_count=1,
        ),
        sys_results=["SYSTEM RESULT for `create_file`: Changes applied to smoke_test.txt"],
    )

    assert state.plan_review_required_after_state_change is True
    assert state.plan_review_required_reason == "state_changing_action_committed"
    assert state.plan_review_required_action_type == "create_file"
    assert state.plan_review_required_target == "smoke_test.txt"
    assert state.plan_review_required_action_effects == ["create_file:smoke_test.txt"]
    trace_entry = state.orchestration_trace[-1]
    assert trace_entry.stage == "plan_review_gate"
    assert trace_entry.decision == "required_set"
    assert trace_entry.fields["source"] == "execution_commit_observer"
    assert trace_entry.fields["plan_review_required_after_state_change"] is True
    assert trace_entry.fields["plan_review_required_action_type"] == "create_file"
    assert trace_entry.fields["plan_review_required_target"] == "smoke_test.txt"
    assert trace_entry.fields["fallback_commit_used"] is False


def test_failed_system_result_does_not_set_plan_review_required():
    state = SimpleNamespace()
    observer = ExecutionCommitObserverAdapter(state)

    observer.observe_execution_commit(
        None,
        _commit(
            action_effects=["edit_file:smoke_test.txt"],
            action_dispatched=False,
            committed_action_count=0,
            committed_system_result_count=1,
        ),
        sys_results=[
            "SYSTEM RESULT for `edit_file`: edit_file requires both 'search_text' and 'replace_text' as strings.\n"
            "[SYSTEM: Action failed. Use the runtime recovery payload below.]\n"
            "last_tool_error_code=VALIDATION_ERROR"
        ],
    )

    assert getattr(state, "plan_review_required_after_state_change", False) is False


def test_prior_failure_does_not_poison_current_successful_write_file_block_result():
    state = SimpleNamespace()
    observer = ExecutionCommitObserverAdapter(state)

    observer.observe_execution_commit(
        None,
        _commit(
            action_effects=["write_file_block:test_file.txt"],
            action_dispatched=False,
            committed_action_count=0,
            committed_system_result_count=1,
        ),
        sys_results=[
            "SYSTEM RESULT for `create_file`: Tool `create_file` execution failed: unexpected keyword argument 'file_content'\n"
            "[SYSTEM: Action failed. Use the runtime recovery payload below.]\n"
            "last_tool_error_code=INTERNAL",
            "SYSTEM RESULT for `write_file_block`: Changes applied to test_file.txt",
        ],
    )

    assert state.plan_review_required_after_state_change is True
    assert state.plan_review_required_action_type == "write_file_block"
    assert state.plan_review_required_target == "test_file.txt"
    assert state.plan_review_required_action_effects == ["write_file_block:test_file.txt"]


def test_unrelated_success_result_does_not_set_plan_review_required_for_failed_current_action():
    state = SimpleNamespace()
    observer = ExecutionCommitObserverAdapter(state)

    observer.observe_execution_commit(
        None,
        _commit(
            action_effects=["edit_file:test_file.txt"],
            action_dispatched=False,
            committed_action_count=0,
            committed_system_result_count=1,
        ),
        sys_results=[
            "SYSTEM RESULT for `write_file_block`: Changes applied to test_file.txt",
            "SYSTEM RESULT for `edit_file`: edit_file requires both 'search_text' and 'replace_text' as strings.\n"
            "[SYSTEM: Action failed. Use the runtime recovery payload below.]\n"
            "last_tool_error_code=VALIDATION_ERROR",
        ],
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
