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


def test_p43_execution_commit_characterizes_batch_as_commit_count_plus_plan_effects_not_per_action_telemetry():
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

    # Characterization: ExecutionCommit has aggregate counts/effects, not
    # per-action telemetry records. Per-action result detail currently lives only
    # in sys_results text.
    assert not hasattr(commit, "per_action_telemetry")
    assert not hasattr(commit, "system_results")


def test_p43_execution_commit_partial_failure_records_aggregate_stop_not_per_action_failure_shape():
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

    # Characterization: partial failure is aggregate stop metadata, not a
    # structured per-action failure vector.
    assert not hasattr(commit, "per_action_telemetry")
    assert not hasattr(commit, "failed_action_index")
