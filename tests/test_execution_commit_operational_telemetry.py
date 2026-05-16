from types import SimpleNamespace

from modules.agent.orchestration.runtime.dispatch_pipeline import DispatchPipeline
from modules.agent.orchestration.runtime.execution_commit_observer import ExecutionCommitObserverAdapter
from modules.agent.orchestration.shared.decision_models import ExecutionCommit, ExecutionPlan


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


def _observe(harness, commit, *, plan=None, sys_results=None):
    ExecutionCommitObserverAdapter(harness.state).observe_execution_commit(
        plan,
        commit,
        sys_results=sys_results or [],
    )
    return harness.state.operational_journal[-1]


def test_operational_journal_fallback_single_action_records_precise_execution_telemetry():
    harness = Harness()
    commit = harness._build_execution_commit(
        None,
        [_action_segment("write_file_block", "test_file.txt")],
        ["SYSTEM RESULT for `write_file_block`: Changes applied to test_file.txt"],
        False,
        iteration=_iteration("write_file_block", "test_file.txt"),
    )

    entry = _observe(
        harness,
        commit,
        sys_results=["SYSTEM RESULT for `write_file_block`: Changes applied to test_file.txt"],
    )

    assert entry["transaction_kind"] == "fallback_single_action"
    assert entry["action_dispatched"] is True
    assert entry["model_action_present"] is True
    assert entry["action_validated"] is True
    assert entry["fallback_dispatch_used"] is True
    assert entry["execution_plan_dispatched"] is False
    assert entry["atomic_bundle_validated"] is False
    assert entry["tool_execution_attempted"] is True
    assert entry["tool_execution_succeeded"] is True
    assert entry["system_result_recorded"] is True
    assert entry["state_change_effect_recorded"] is True
    assert entry["state_change_applied"] is True
    assert entry["dispatch_stop_requested"] is False


def test_operational_journal_atomic_bundle_action_records_plan_and_tool_telemetry():
    harness = Harness()
    plan = ExecutionPlan(
        shape="INTENT_ACTION_BUNDLE",
        transaction_kind="atomic_intent_action_bundle",
        state_effects=["activate_intent:intent-1"],
        action_effects=["list_directory:app"],
        output_effects=[],
        bundle_validated=True,
        transition_applied=True,
        action_dispatched=False,
        before_active_intent_id="",
        after_active_intent_id="intent-1",
    )
    commit = harness._build_execution_commit(
        plan,
        [_action_segment("list_directory", "app")],
        ["SYSTEM RESULT for `list_directory`: Directory listing for app"],
        False,
        iteration=None,
    )

    entry = _observe(
        harness,
        commit,
        plan=plan,
        sys_results=["SYSTEM RESULT for `list_directory`: Directory listing for app"],
    )

    assert entry["transaction_kind"] == "atomic_intent_action_bundle"
    assert entry["bundle_validated"] is True
    assert entry["transition_applied"] is True
    assert entry["atomic_bundle_validated"] is True
    assert entry["execution_plan_dispatched"] is True
    assert entry["fallback_dispatch_used"] is False
    assert entry["tool_execution_attempted"] is True
    assert entry["system_result_recorded"] is True
    assert entry["state_change_effect_recorded"] is False
    assert entry["state_change_applied"] is False


def test_operational_journal_preflight_block_records_no_tool_execution_attempt():
    harness = Harness()
    commit = ExecutionCommit(
        shape="ACTION_ONLY",
        transaction_kind="fallback_single_action",
        action_effects=["read_file:too_large.py"],
        action_dispatched=False,
        committed_action_count=0,
        committed_system_result_count=0,
        dispatch_stop_requested=True,
    )

    entry = _observe(harness, commit, sys_results=[])

    assert entry["model_action_present"] is True
    assert entry["action_validated"] is True
    assert entry["fallback_dispatch_used"] is True
    assert entry["tool_execution_attempted"] is False
    assert entry["tool_execution_succeeded"] is None
    assert entry["system_result_recorded"] is False
    assert entry["state_change_effect_recorded"] is False
    assert entry["state_change_applied"] is False
    assert entry["dispatch_stop_requested"] is True


def test_operational_journal_state_changing_failed_result_does_not_claim_applied():
    harness = Harness()
    commit = harness._build_execution_commit(
        None,
        [_action_segment("edit_file", "src/Screen.kt")],
        ["SYSTEM RESULT for `edit_file`: VALIDATION_ERROR Search block not found"],
        True,
        iteration=_iteration("edit_file", "src/Screen.kt"),
    )

    entry = _observe(
        harness,
        commit,
        sys_results=["SYSTEM RESULT for `edit_file`: VALIDATION_ERROR Search block not found"],
    )

    assert entry["tool_execution_attempted"] is True
    assert entry["tool_execution_succeeded"] is False
    assert entry["system_result_recorded"] is True
    assert entry["state_change_effect_recorded"] is True
    assert entry["state_change_applied"] is False
    assert entry["dispatch_stop_requested"] is True


def test_operational_journal_read_only_success_does_not_claim_state_change_applied():
    harness = Harness()
    commit = harness._build_execution_commit(
        None,
        [_action_segment("read_file", "README.md")],
        ["SYSTEM RESULT for `read_file`: File content for README.md"],
        False,
        iteration=_iteration("read_file", "README.md"),
    )

    entry = _observe(
        harness,
        commit,
        sys_results=["SYSTEM RESULT for `read_file`: File content for README.md"],
    )

    assert entry["tool_execution_attempted"] is True
    assert entry["system_result_recorded"] is True
    assert entry["state_change_effect_recorded"] is False
    assert entry["state_change_applied"] is False
