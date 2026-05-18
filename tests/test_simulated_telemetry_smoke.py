from types import SimpleNamespace

from modules.agent.orchestration.runtime.dispatch_pipeline import DispatchPipeline
from modules.agent.orchestration.runtime.execution_commit_observer import ExecutionCommitObserverAdapter
from modules.agent.orchestration.shared.decision_models import ExecutionCommit, ExecutionPlan
from modules.agent.orchestration.trace_export import OrchestrationTraceExporter


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
                action_ops=[
                    SimpleNamespace(
                        action_type=action_type,
                        payload={"type": action_type, "path": path},
                    )
                ]
            ),
        )
    )


def _observe(state, plan, commit, *, sys_results=None):
    ExecutionCommitObserverAdapter(state).observe_execution_commit(
        plan,
        commit,
        sys_results=sys_results or [],
    )
    return state.operational_journal[-1]


def test_p3_fallback_action_success_telemetry_reaches_journal_and_runtime_exports():
    harness = Harness()
    commit = harness._build_execution_commit(
        None,
        [_action_segment("write_file_block", "test_file.txt")],
        ["SYSTEM RESULT for `write_file_block`: Changes applied to test_file.txt"],
        False,
        iteration=_iteration("write_file_block", "test_file.txt"),
    )

    entry = _observe(
        harness.state,
        None,
        commit,
        sys_results=["SYSTEM RESULT for `write_file_block`: Changes applied to test_file.txt"],
    )

    assert entry["transaction_kind"] == "fallback_single_action"
    assert entry["fallback_dispatch_used"] is True
    assert entry["execution_plan_dispatched"] is False
    assert entry["atomic_bundle_validated"] is False
    assert entry["tool_execution_attempted"] is True
    assert entry["tool_execution_succeeded"] is True
    assert entry["system_result_recorded"] is True
    assert entry["state_change_effect_recorded"] is True
    assert entry["state_change_applied"] is True
    assert entry["dispatch_stop_requested"] is False

    artifacts = OrchestrationTraceExporter().runtime_artifacts(harness.state)
    assert artifacts["last_execution_commit"]["fallback_dispatch_used"] is True
    assert artifacts["last_execution_commit"]["tool_execution_attempted"] is True
    assert artifacts["last_execution_commit"]["system_result_recorded"] is True
    assert artifacts["operational_journal"][-1]["fallback_dispatch_used"] is True
    assert artifacts["operational_journal"][-1]["state_change_applied"] is True


def test_p3_atomic_bundle_action_success_telemetry_reaches_journal_and_runtime_exports():
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
        harness.state,
        plan,
        commit,
        sys_results=["SYSTEM RESULT for `list_directory`: Directory listing for app"],
    )

    assert entry["transaction_kind"] == "atomic_intent_action_bundle"
    assert entry["execution_plan_dispatched"] is True
    assert entry["atomic_bundle_validated"] is True
    assert entry["fallback_dispatch_used"] is False
    assert entry["tool_execution_attempted"] is True
    assert entry["system_result_recorded"] is True
    assert entry["state_change_effect_recorded"] is False
    assert entry["state_change_applied"] is False

    artifacts = OrchestrationTraceExporter().runtime_artifacts(harness.state)
    assert artifacts["last_execution_plan"]["transaction_kind"] == "atomic_intent_action_bundle"
    assert artifacts["last_execution_commit"]["execution_plan_dispatched"] is True
    assert artifacts["last_execution_commit"]["atomic_bundle_validated"] is True
    assert artifacts["last_execution_commit"]["tool_execution_attempted"] is True
    assert artifacts["operational_journal"][-1]["atomic_bundle_validated"] is True


def test_p3_blocked_preflight_telemetry_records_no_tool_execution_attempt():
    state = SimpleNamespace(active_intent=None)
    commit = ExecutionCommit(
        shape="ACTION_ONLY",
        transaction_kind="fallback_single_action",
        action_effects=["read_file:too_large.py"],
        action_dispatched=False,
        committed_action_count=0,
        committed_system_result_count=0,
        dispatch_stop_requested=True,
    )

    entry = _observe(state, None, commit, sys_results=[])

    assert entry["model_action_present"] is True
    assert entry["action_validated"] is True
    assert entry["fallback_dispatch_used"] is True
    assert entry["execution_plan_dispatched"] is False
    assert entry["tool_execution_attempted"] is False
    assert entry["tool_execution_succeeded"] is None
    assert entry["system_result_recorded"] is False
    assert entry["state_change_effect_recorded"] is False
    assert entry["state_change_applied"] is False
    assert entry["dispatch_stop_requested"] is True

    diagnostics = OrchestrationTraceExporter().runtime_diagnostics_snapshot(state)
    assert diagnostics["last_execution_commit"]["tool_execution_attempted"] is False
    assert diagnostics["last_execution_commit"]["system_result_recorded"] is False
    assert diagnostics["last_execution_commit"]["dispatch_stop_requested"] is True
    assert diagnostics["operational_journal"][-1]["tool_execution_attempted"] is False


def test_p3_state_changing_failed_result_records_effect_but_not_applied():
    harness = Harness()
    commit = harness._build_execution_commit(
        None,
        [_action_segment("edit_file", "src/Screen.kt")],
        ["SYSTEM RESULT for `edit_file`: VALIDATION_ERROR Search block not found"],
        True,
        iteration=_iteration("edit_file", "src/Screen.kt"),
    )

    entry = _observe(
        harness.state,
        None,
        commit,
        sys_results=["SYSTEM RESULT for `edit_file`: VALIDATION_ERROR Search block not found"],
    )

    assert entry["tool_execution_attempted"] is True
    assert entry["tool_execution_succeeded"] is False
    assert entry["system_result_recorded"] is True
    assert entry["state_change_effect_recorded"] is True
    assert entry["state_change_applied"] is False
    assert entry["dispatch_stop_requested"] is True

    artifacts = OrchestrationTraceExporter().runtime_artifacts(harness.state)
    assert artifacts["operational_journal"][-1]["state_change_effect_recorded"] is True
    assert artifacts["operational_journal"][-1]["state_change_applied"] is False


def test_p3_read_only_success_does_not_claim_state_change_applied():
    harness = Harness()
    commit = harness._build_execution_commit(
        None,
        [_action_segment("read_file", "README.md")],
        ["SYSTEM RESULT for `read_file`: File content for README.md"],
        False,
        iteration=_iteration("read_file", "README.md"),
    )

    entry = _observe(
        harness.state,
        None,
        commit,
        sys_results=["SYSTEM RESULT for `read_file`: File content for README.md"],
    )

    assert entry["tool_execution_attempted"] is True
    assert entry["system_result_recorded"] is True
    assert entry["state_change_effect_recorded"] is False
    assert entry["state_change_applied"] is False

    diagnostics = OrchestrationTraceExporter().runtime_diagnostics_snapshot(harness.state)
    assert diagnostics["last_execution_commit"]["tool_execution_attempted"] is True
    assert diagnostics["operational_journal"][-1]["state_change_effect_recorded"] is False
    assert diagnostics["operational_journal"][-1]["state_change_applied"] is False


def test_p41_read_file_added_to_history_counts_as_success():
    harness = Harness()
    result = "SYSTEM RESULT for `read_file`: Read file 'app/build.gradle.kts' and added to history as v1."
    commit = harness._build_execution_commit(
        None,
        [_action_segment("read_file", "app/build.gradle.kts")],
        [result],
        False,
        iteration=_iteration("read_file", "app/build.gradle.kts"),
    )

    entry = _observe(harness.state, None, commit, sys_results=[result])

    assert entry["tool_execution_attempted"] is True
    assert entry["tool_execution_succeeded"] is True
    assert entry["system_result_recorded"] is True
    assert entry["state_change_effect_recorded"] is False
    assert entry["state_change_applied"] is False

    diagnostics = OrchestrationTraceExporter().runtime_diagnostics_snapshot(harness.state)
    assert diagnostics["last_execution_commit"]["tool_execution_succeeded"] is True

    artifacts = OrchestrationTraceExporter().runtime_artifacts(harness.state)
    assert artifacts["last_execution_commit"]["tool_execution_succeeded"] is True


def test_p41_read_file_unchanged_already_in_history_counts_as_success():
    harness = Harness()
    result = "SYSTEM RESULT for `read_file`: Read file 'app/build.gradle.kts' (unchanged, already in history as v1)."
    commit = harness._build_execution_commit(
        None,
        [_action_segment("read_file", "app/build.gradle.kts")],
        [result],
        False,
        iteration=_iteration("read_file", "app/build.gradle.kts"),
    )

    entry = _observe(harness.state, None, commit, sys_results=[result])

    assert entry["tool_execution_attempted"] is True
    assert entry["tool_execution_succeeded"] is True
    assert entry["system_result_recorded"] is True
    assert entry["state_change_effect_recorded"] is False
    assert entry["state_change_applied"] is False


def test_p41_read_file_already_available_stop_is_non_failure_guard():
    harness = Harness()
    result = (
        "SYSTEM RESULT for `read_file`: SYSTEM: File content is already available as history version v1. "
        "Use that content now. Do not call read_file again."
    )
    commit = harness._build_execution_commit(
        None,
        [_action_segment("read_file", "app/build.gradle.kts")],
        [result],
        True,
        iteration=_iteration("read_file", "app/build.gradle.kts"),
    )

    entry = _observe(harness.state, None, commit, sys_results=[result])

    assert entry["tool_execution_attempted"] is True
    assert entry["tool_execution_succeeded"] is True
    assert entry["system_result_recorded"] is True
    assert entry["dispatch_stop_requested"] is True
    assert entry["state_change_effect_recorded"] is False
    assert entry["state_change_applied"] is False


def test_p41_run_shell_command_executed_successfully_counts_as_success():
    harness = Harness()
    result = "SYSTEM RESULT for `run_shell`: Command executed successfully (no output)."
    commit = harness._build_execution_commit(
        None,
        [_action_segment("run_shell", "")],
        [result],
        False,
        iteration=_iteration("run_shell", ""),
    )

    entry = _observe(harness.state, None, commit, sys_results=[result])

    assert entry["tool_execution_attempted"] is True
    assert entry["tool_execution_succeeded"] is True
    assert entry["system_result_recorded"] is True
    assert entry["state_change_effect_recorded"] is False
    assert entry["state_change_applied"] is False


def test_p41_run_shell_command_blocked_remains_failure():
    harness = Harness()
    result = "SYSTEM RESULT for `run_shell`: Command blocked: length exceeds 1000 characters."
    commit = harness._build_execution_commit(
        None,
        [_action_segment("run_shell", "")],
        [result],
        True,
        iteration=_iteration("run_shell", ""),
    )

    entry = _observe(harness.state, None, commit, sys_results=[result])

    assert entry["tool_execution_attempted"] is True
    assert entry["tool_execution_succeeded"] is False
    assert entry["system_result_recorded"] is True
    assert entry["dispatch_stop_requested"] is True
