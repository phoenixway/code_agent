from types import SimpleNamespace

import pytest

from modules.agent.action_dispatcher import ActionDispatcher
from modules.agent.orchestration.runtime.dispatch_pipeline import DispatchPipeline
from modules.agent.orchestration.shared.decision_models import ExecutionPlan


class RecordingUi:
    async def print_thought(self, _text):
        return None


class RecordingReadOnlyDispatcher(ActionDispatcher):
    def __init__(self):
        self.config = SimpleNamespace(MAX_READONLY_BATCH_ACTIONS=6)
        self.agent = SimpleNamespace(log=None, config=self.config)
        self.ui = RecordingUi()
        self.executed_commands = []

    def _preflight_turn_working_material_budget(self, action_commands, execute_indices, state):
        return None

    async def _execute_action(self, command, state):
        self.executed_commands.append(dict(command))
        action_type = command.get("type", "unknown")
        path = command.get("path", "")
        return (
            dict(command),
            f"SYSTEM RESULT for `{action_type}`: simulated success for {path}",
            False,
        )


class RecordingPartialFailureDispatcher(RecordingReadOnlyDispatcher):
    async def _execute_action(self, command, state):
        self.executed_commands.append(dict(command))
        action_type = command.get("type", "unknown")
        path = command.get("path", "")
        if len(self.executed_commands) == 2:
            return (
                dict(command),
                f"SYSTEM RESULT for `{action_type}`: NOT_FOUND {path}",
                True,
            )
        return (
            dict(command),
            f"SYSTEM RESULT for `{action_type}`: simulated success for {path}",
            False,
        )


def _action(command):
    return SimpleNamespace(type="action", content=dict(command))


def _state():
    return SimpleNamespace(
        state_machine=None,
        pending_loop_stop_info=None,
    )


def _read_only_actions():
    return [
        {"type": "read_file", "path": "app/src/main/AndroidManifest.xml"},
        {"type": "read_file", "path": "app/src/main/java/MainActivity.kt"},
        {"type": "search_content", "path": ".", "pattern": "ShareReceiverActivity"},
    ]


@pytest.mark.asyncio
async def test_p43_action_dispatcher_executes_all_bounded_readonly_batch_actions():
    dispatcher = RecordingReadOnlyDispatcher()
    state = _state()
    segments = [_action(command) for command in _read_only_actions()]

    processed, system_results, should_stop = await dispatcher.dispatch_segments(segments, state)

    assert should_stop is False
    assert len(dispatcher.executed_commands) == 3
    assert dispatcher.executed_commands == _read_only_actions()
    # Characterization: dispatch executes action segments but does not return
    # them in processed_segments. Processed action detail is represented by
    # system_results and batch counters instead.
    assert len([segment for segment in processed if segment.type == "action"]) == 0

    assert state.last_batch_actions_total == 3
    assert state.last_batch_actions_executed == 3
    # Characterization: transient batch mode flags are reset before return.
    assert state.intent_step_batch_mode == ""
    assert state.intent_step_batch_consumed is False

    assert len(system_results) == 3
    assert system_results[0].startswith("[BATCH 1/3] SYSTEM RESULT for `read_file`")
    assert system_results[1].startswith("[BATCH 2/3] SYSTEM RESULT for `read_file`")
    assert system_results[2].startswith("[BATCH 3/3] SYSTEM RESULT for `search_content`")


@pytest.mark.asyncio
async def test_p43_action_dispatcher_stops_readonly_batch_after_partial_failure():
    dispatcher = RecordingPartialFailureDispatcher()
    state = _state()
    segments = [_action(command) for command in _read_only_actions()]

    processed, system_results, should_stop = await dispatcher.dispatch_segments(segments, state)

    assert should_stop is True
    assert len(dispatcher.executed_commands) == 2
    assert dispatcher.executed_commands == _read_only_actions()[:2]
    # Characterization: even executed action segments are not returned in
    # processed_segments after dispatch.
    assert len([segment for segment in processed if segment.type == "action"]) == 0

    assert state.last_batch_actions_total == 3
    assert state.last_batch_actions_executed == 2
    # Characterization: transient batch mode flags are reset before return.
    assert state.intent_step_batch_mode == ""
    assert state.intent_step_batch_consumed is False

    # Characterization: partial failure appends a synthetic batch-aborted
    # system result after the failed action result.
    assert len(system_results) == 3
    assert system_results[0].startswith("[BATCH 1/3] SYSTEM RESULT for `read_file`")
    assert system_results[1].startswith("[BATCH 2/3] SYSTEM RESULT for `read_file`: NOT_FOUND")
    assert system_results[2] == (
        "SYSTEM RESULT for `read_file`: Batch aborted after action 2/3 due to stop condition."
    )


def test_p46_execution_commit_exports_successful_readonly_batch_per_action_telemetry():
    pipeline = DispatchPipeline(
        agent=SimpleNamespace(ui=SimpleNamespace(), state=SimpleNamespace(), log=None),
        dispatch_outcome=SimpleNamespace(),
    )
    execution_plan = ExecutionPlan(
        shape="READ_ONLY_BATCH_CANDIDATE",
        transaction_kind="atomic_intent_action_bundle",
        action_effects=[
            "read_file:app/src/main/AndroidManifest.xml",
            "read_file:app/src/main/java/MainActivity.kt",
            "search_content:.",
        ],
        bundle_validated=True,
        transition_applied=True,
        action_dispatched=False,
        before_active_intent_id="intent_before",
        after_active_intent_id="intent_after",
    )
    processed = [_action(command) for command in _read_only_actions()]
    sys_results = [
        "[BATCH 1/3] SYSTEM RESULT for `read_file`: simulated success for app/src/main/AndroidManifest.xml",
        "[BATCH 2/3] SYSTEM RESULT for `read_file`: simulated success for app/src/main/java/MainActivity.kt",
        "[BATCH 3/3] SYSTEM RESULT for `search_content`: simulated success for .",
    ]

    commit = pipeline._build_execution_commit(
        execution_plan,
        processed,
        sys_results,
        False,
        iteration=SimpleNamespace(),
    )

    assert commit.shape == "READ_ONLY_BATCH_CANDIDATE"
    assert commit.action_dispatched is True
    assert commit.committed_action_count == 3
    assert commit.committed_system_result_count == 3
    assert commit.dispatch_stop_requested is False
    assert commit.action_effects == execution_plan.action_effects

    assert commit.per_action_telemetry
    assert commit.batch_telemetry_source == "compiler_ir"
    assert commit.failed_action_index is None
    assert commit.batch_aborted is False


def test_p46_execution_commit_exports_partial_failure_readonly_batch_per_action_telemetry():
    pipeline = DispatchPipeline(
        agent=SimpleNamespace(ui=SimpleNamespace(), state=SimpleNamespace(), log=None),
        dispatch_outcome=SimpleNamespace(),
    )
    execution_plan = ExecutionPlan(
        shape="READ_ONLY_BATCH_CANDIDATE",
        transaction_kind="atomic_intent_action_bundle",
        action_effects=[
            "read_file:app/src/main/AndroidManifest.xml",
            "read_file:app/src/main/java/MainActivity.kt",
            "search_content:.",
        ],
        bundle_validated=True,
        transition_applied=True,
        action_dispatched=False,
        before_active_intent_id="intent_before",
        after_active_intent_id="intent_after",
    )
    processed = [_action(command) for command in _read_only_actions()[:2]]
    sys_results = [
        "[BATCH 1/3] SYSTEM RESULT for `read_file`: simulated success for app/src/main/AndroidManifest.xml",
        "[BATCH 2/3] SYSTEM RESULT for `read_file`: NOT_FOUND app/src/main/java/MainActivity.kt",
    ]

    commit = pipeline._build_execution_commit(
        execution_plan,
        processed,
        sys_results,
        True,
        iteration=SimpleNamespace(),
    )

    assert commit.shape == "READ_ONLY_BATCH_CANDIDATE"
    assert commit.action_dispatched is True
    assert commit.committed_action_count == 2
    assert commit.committed_system_result_count == 2
    assert commit.dispatch_stop_requested is True
    assert commit.action_effects == execution_plan.action_effects

    assert commit.per_action_telemetry
    assert commit.batch_telemetry_source == "compiler_ir"
    assert commit.failed_action_index == 2
    assert commit.batch_aborted is False


def _pipeline_state():
    return SimpleNamespace(
        operational_journal=[],
        operational_journal_sequence=0,
        orchestration_trace=[],
        orchestration_trace_sequence=0,
    )


def _batch_execution_plan():
    return ExecutionPlan(
        shape="READ_ONLY_BATCH_CANDIDATE",
        transaction_kind="atomic_intent_action_bundle",
        action_effects=[
            "read_file:app/src/main/AndroidManifest.xml",
            "read_file:app/src/main/java/MainActivity.kt",
            "search_content:.",
        ],
        bundle_validated=True,
        transition_applied=True,
        action_dispatched=False,
        before_active_intent_id="intent_before",
        after_active_intent_id="intent_after",
    )


def _pipeline_with_state(state):
    return DispatchPipeline(
        agent=SimpleNamespace(ui=SimpleNamespace(), state=state, log=None),
        dispatch_outcome=SimpleNamespace(),
    )


def _observe_commit(state, execution_plan, processed, sys_results, should_stop):
    from modules.agent.orchestration.runtime.execution_commit_observer import ExecutionCommitObserverAdapter

    pipeline = _pipeline_with_state(state)
    commit = pipeline._build_execution_commit(
        execution_plan,
        processed,
        sys_results,
        should_stop,
        iteration=SimpleNamespace(),
    )
    ExecutionCommitObserverAdapter(state).observe_execution_commit(
        execution_plan,
        commit,
        sys_results=sys_results,
    )
    return commit, state.operational_journal[-1]


def test_p46_successful_readonly_batch_telemetry_is_per_action_and_exported():
    from modules.agent.orchestration.trace_export import OrchestrationTraceExporter

    state = _pipeline_state()
    execution_plan = _batch_execution_plan()
    processed = [_action(command) for command in _read_only_actions()]
    sys_results = [
        "[BATCH 1/3] SYSTEM RESULT for `read_file`: simulated success for app/src/main/AndroidManifest.xml",
        "[BATCH 2/3] SYSTEM RESULT for `read_file`: simulated success for app/src/main/java/MainActivity.kt",
        "[BATCH 3/3] SYSTEM RESULT for `search_content`: simulated success for .",
    ]

    commit, journal = _observe_commit(state, execution_plan, processed, sys_results, False)

    assert commit.committed_action_count == 3
    assert commit.committed_system_result_count == 3
    assert commit.dispatch_stop_requested is False

    assert journal["kind"] == "tool_execution_commit"
    assert journal["tool_execution_attempted"] is True
    assert journal["tool_execution_succeeded"] is True
    assert journal["system_result_recorded"] is True
    assert journal["state_change_effect_recorded"] is False
    assert journal["state_change_applied"] is False
    assert journal["committed_action_count"] == 3
    assert journal["committed_system_result_count"] == 3
    assert journal["action_effects"] == execution_plan.action_effects

    # Current export surface: top-level system_result_excerpt still shows only the first batch result.
    assert journal["system_result_excerpt"].startswith("[BATCH 1/3] SYSTEM RESULT for `read_file`")
    assert "[BATCH 2/3]" not in journal["system_result_excerpt"]

    diagnostics = OrchestrationTraceExporter().runtime_diagnostics_snapshot(state)
    artifacts = OrchestrationTraceExporter().runtime_artifacts(state)

    assert diagnostics["last_execution_commit"]["tool_execution_succeeded"] is True
    assert diagnostics["last_execution_commit"]["committed_action_count"] == 3
    assert diagnostics["last_execution_commit"]["committed_system_result_count"] == 3
    assert diagnostics["operational_journal"][-1]["tool_execution_succeeded"] is True

    assert artifacts["last_execution_commit"]["tool_execution_succeeded"] is True
    assert artifacts["last_execution_commit"]["committed_action_count"] == 3
    assert artifacts["last_execution_commit"]["committed_system_result_count"] == 3
    assert artifacts["operational_journal"][-1]["tool_execution_succeeded"] is True

    assert len(diagnostics["last_execution_commit"]["per_action_telemetry"]) == 3
    assert diagnostics["last_execution_commit"]["batch_telemetry_source"] == "compiler_ir"
    assert len(artifacts["last_execution_commit"]["per_action_telemetry"]) == 3
    assert artifacts["last_execution_commit"]["batch_telemetry_source"] == "compiler_ir"


def test_p46_partial_failure_readonly_batch_telemetry_is_per_action_and_exported():
    from modules.agent.orchestration.trace_export import OrchestrationTraceExporter

    state = _pipeline_state()
    execution_plan = _batch_execution_plan()
    processed = [_action(command) for command in _read_only_actions()[:2]]
    sys_results = [
        "[BATCH 1/3] SYSTEM RESULT for `read_file`: simulated success for app/src/main/AndroidManifest.xml",
        "[BATCH 2/3] SYSTEM RESULT for `read_file`: NOT_FOUND app/src/main/java/MainActivity.kt",
        "SYSTEM RESULT for `read_file`: Batch aborted after action 2/3 due to stop condition.",
    ]

    commit, journal = _observe_commit(state, execution_plan, processed, sys_results, True)

    assert commit.committed_action_count == 2
    assert commit.committed_system_result_count == 3
    assert commit.dispatch_stop_requested is True

    assert journal["kind"] == "tool_execution_commit"
    assert journal["tool_execution_attempted"] is True
    assert journal["tool_execution_succeeded"] is False
    assert journal["system_result_recorded"] is True
    assert journal["dispatch_stop_requested"] is True
    assert journal["committed_action_count"] == 2
    assert journal["committed_system_result_count"] == 3
    assert journal["action_effects"] == execution_plan.action_effects

    # Current export surface: top-level system_result_excerpt still shows only first result,
    # while per_action_telemetry carries the structured failure detail.
    assert journal["system_result_excerpt"].startswith("[BATCH 1/3] SYSTEM RESULT for `read_file`")
    assert "NOT_FOUND" not in journal["system_result_excerpt"]
    assert "Batch aborted" not in journal["system_result_excerpt"]

    diagnostics = OrchestrationTraceExporter().runtime_diagnostics_snapshot(state)
    artifacts = OrchestrationTraceExporter().runtime_artifacts(state)

    assert diagnostics["last_execution_commit"]["tool_execution_succeeded"] is False
    assert diagnostics["last_execution_commit"]["committed_action_count"] == 2
    assert diagnostics["last_execution_commit"]["committed_system_result_count"] == 3
    assert diagnostics["last_execution_commit"]["dispatch_stop_requested"] is True
    assert diagnostics["operational_journal"][-1]["tool_execution_succeeded"] is False

    assert artifacts["last_execution_commit"]["tool_execution_succeeded"] is False
    assert artifacts["last_execution_commit"]["committed_action_count"] == 2
    assert artifacts["last_execution_commit"]["committed_system_result_count"] == 3
    assert artifacts["last_execution_commit"]["dispatch_stop_requested"] is True
    assert artifacts["operational_journal"][-1]["tool_execution_succeeded"] is False

    assert len(diagnostics["last_execution_commit"]["per_action_telemetry"]) == 3
    assert diagnostics["last_execution_commit"]["failed_action_index"] == 2
    assert diagnostics["last_execution_commit"]["batch_aborted"] is True
    assert diagnostics["last_execution_commit"]["batch_telemetry_source"] == "compiler_ir"
    assert len(artifacts["last_execution_commit"]["per_action_telemetry"]) == 3
    assert artifacts["last_execution_commit"]["failed_action_index"] == 2
    assert artifacts["last_execution_commit"]["batch_aborted"] is True
    assert artifacts["last_execution_commit"]["batch_telemetry_source"] == "compiler_ir"


def test_p45_successful_readonly_batch_exports_per_action_telemetry_from_ir():
    from modules.agent.orchestration.trace_export import OrchestrationTraceExporter

    state = _pipeline_state()
    execution_plan = _batch_execution_plan()
    processed = [_action(command) for command in _read_only_actions()]
    sys_results = [
        "[BATCH 1/3] SYSTEM RESULT for `read_file`: simulated success for app/src/main/AndroidManifest.xml",
        "[BATCH 2/3] SYSTEM RESULT for `read_file`: simulated success for app/src/main/java/MainActivity.kt",
        "[BATCH 3/3] SYSTEM RESULT for `search_content`: simulated success for .",
    ]

    _commit, _journal = _observe_commit(state, execution_plan, processed, sys_results, False)

    diagnostics = OrchestrationTraceExporter().runtime_diagnostics_snapshot(state)
    last_commit = diagnostics["last_execution_commit"]

    per_action = last_commit["per_action_telemetry"]

    assert len(per_action) == 3
    assert [
        {
            "index": item["index"],
            "action_type": item["action_type"],
            "target": item["target"],
            "attempted": item["attempted"],
            "succeeded": item["succeeded"],
            "stop_requested": item["stop_requested"],
        }
        for item in per_action
    ] == [
        {
            "index": 1,
            "action_type": "read_file",
            "target": "app/src/main/AndroidManifest.xml",
            "attempted": True,
            "succeeded": True,
            "stop_requested": False,
        },
        {
            "index": 2,
            "action_type": "read_file",
            "target": "app/src/main/java/MainActivity.kt",
            "attempted": True,
            "succeeded": True,
            "stop_requested": False,
        },
        {
            "index": 3,
            "action_type": "search_content",
            "target": ".",
            "attempted": True,
            "succeeded": True,
            "stop_requested": False,
        },
    ]
    assert all("system_result_excerpt" in item for item in per_action)
    assert last_commit["tool_execution_succeeded"] is True
    assert last_commit["batch_telemetry_source"] == "compiler_ir"


def test_p45_partial_failure_readonly_batch_exports_failed_action_and_false_aggregate_success():
    from modules.agent.orchestration.trace_export import OrchestrationTraceExporter

    state = _pipeline_state()
    execution_plan = _batch_execution_plan()
    processed = [_action(command) for command in _read_only_actions()[:2]]
    sys_results = [
        "[BATCH 1/3] SYSTEM RESULT for `read_file`: simulated success for app/src/main/AndroidManifest.xml",
        "[BATCH 2/3] SYSTEM RESULT for `read_file`: NOT_FOUND app/src/main/java/MainActivity.kt",
        "SYSTEM RESULT for `read_file`: Batch aborted after action 2/3 due to stop condition.",
    ]

    _commit, _journal = _observe_commit(state, execution_plan, processed, sys_results, True)

    diagnostics = OrchestrationTraceExporter().runtime_diagnostics_snapshot(state)
    last_commit = diagnostics["last_execution_commit"]

    per_action = last_commit["per_action_telemetry"]

    assert last_commit["tool_execution_succeeded"] is False
    assert last_commit["dispatch_stop_requested"] is True
    assert last_commit["failed_action_index"] == 2
    assert last_commit["batch_aborted"] is True
    assert last_commit["batch_telemetry_source"] == "compiler_ir"

    assert len(per_action) == 3
    assert per_action[0]["attempted"] is True
    assert per_action[0]["succeeded"] is True
    assert per_action[0]["stop_requested"] is False

    assert per_action[1]["attempted"] is True
    assert per_action[1]["succeeded"] is False
    assert per_action[1]["stop_requested"] is True
    assert per_action[1]["failure_kind"] == "NOT_FOUND"

    # The third planned action exists in compiler/IR but was not executed
    # because the batch stopped after action 2/3.
    assert per_action[2]["action_type"] == "search_content"
    assert per_action[2]["attempted"] is False
    assert per_action[2]["succeeded"] is None
    assert per_action[2]["stop_requested"] is False
