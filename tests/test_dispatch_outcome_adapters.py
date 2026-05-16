from types import SimpleNamespace

from modules.agent.orchestration.runtime.execution_commit_observer import ExecutionCommitObserverAdapter
from modules.agent.orchestration.runtime.dispatch_outcome_history import DispatchOutcomeHistoryAdapter
from modules.agent.orchestration.runtime.dispatch_outcome_state import DispatchOutcomeStateAdapter
from modules.agent.orchestration.shared.decision_models import ExecutionCommit, ExecutionPlan


def test_dispatch_outcome_state_adapter_clears_terminal_plaintext_and_stop_info():
    state = SimpleNamespace(
        terminal_plaintext_completion_pending=True,
        terminal_plaintext_completion_text="done",
        pending_loop_stop_info={"reason": "x"},
    )
    adapter = DispatchOutcomeStateAdapter(state)

    adapter.clear_terminal_plaintext_completion()
    adapter.clear_pending_loop_stop_info()

    assert state.terminal_plaintext_completion_pending is False
    assert state.terminal_plaintext_completion_text == ""
    assert state.pending_loop_stop_info is None


def test_dispatch_outcome_state_adapter_sets_memory_followup():
    state = SimpleNamespace()
    adapter = DispatchOutcomeStateAdapter(state)

    adapter.set_memory_tag_followup(expected=True, reason="meaningful_evidence_gain", intent_id="intent_1")

    assert state.memory_tag_expected_next_step is True
    assert state.memory_tag_reason == "meaningful_evidence_gain"
    assert state.memory_tag_expected_intent_id == "intent_1"


def test_dispatch_outcome_history_adapter_writes_assistant_and_system_messages():
    calls = []

    class History:
        def add_message(self, role, text):
            calls.append((role, text))

    adapter = DispatchOutcomeHistoryAdapter(History())
    adapter.add_assistant_message("assistant text")
    adapter.add_system_message("system text")

    assert calls == [("assistant", "assistant text"), ("system", "system text")]


def test_execution_commit_observer_adapter_records_plan_commit_and_journal_via_state_appender():
    captured = []
    state = SimpleNamespace(
        last_execution_plan=None,
        last_execution_commit=None,
        append_operational_journal_entry=lambda entry: captured.append(dict(entry)),
    )
    adapter = ExecutionCommitObserverAdapter(state)
    plan = ExecutionPlan(
        shape="intent_action_bundle",
        transaction_kind="atomic_intent_action_bundle",
        action_effects=["read_chunk:x.py"],
        bundle_validated=True,
        transition_applied=True,
        before_active_intent_id="intent_before",
        after_active_intent_id="intent_after",
    )
    commit = ExecutionCommit(
        shape="intent_action_bundle",
        transaction_kind="atomic_intent_action_bundle",
        action_effects=["read_chunk:x.py"],
        bundle_validated=True,
        transition_applied=True,
        action_dispatched=True,
        before_active_intent_id="intent_before",
        after_active_intent_id="intent_after",
        committed_action_count=1,
        committed_system_result_count=1,
    )

    adapter.observe_execution_commit(plan, commit, sys_results=["ok"])

    assert state.last_execution_plan is plan
    assert state.last_execution_commit is commit
    assert len(captured) == 1
    entry = captured[0]
    assert entry["kind"] == "tool_execution_commit"
    assert entry["transaction_kind"] == "atomic_intent_action_bundle"
    assert entry["shape"] == "intent_action_bundle"
    assert entry["bundle_validated"] is True
    assert entry["transition_applied"] is True
    assert entry["action_dispatched"] is True
    assert entry["model_action_present"] is True
    assert entry["action_validated"] is True
    assert entry["execution_plan_dispatched"] is True
    assert entry["atomic_bundle_validated"] is True
    assert entry["fallback_dispatch_used"] is False
    assert entry["tool_execution_attempted"] is True
    assert entry["system_result_recorded"] is True
    assert entry["state_change_effect_recorded"] is False
    assert entry["state_change_applied"] is False
    assert entry["action_type"] == "read_chunk"
    assert entry["target"] == "x.py"
    assert entry["action_effects"] == ["read_chunk:x.py"]
    assert entry["committed_action_count"] == 1
    assert entry["committed_system_result_count"] == 1
    assert entry["dispatch_stop_requested"] is False
    assert entry["before_active_intent_id"] == "intent_before"
    assert entry["after_active_intent_id"] == "intent_after"
    assert entry["system_result_excerpt"] == "ok"


def test_execution_commit_observer_adapter_falls_back_to_local_journal_storage():
    state = SimpleNamespace(
        operational_journal=[],
        operational_journal_sequence=0,
    )
    adapter = ExecutionCommitObserverAdapter(state)
    commit = ExecutionCommit(
        shape="action_only",
        transaction_kind="read_only_batch",
        action_effects=["search_files:src"],
        action_dispatched=True,
        committed_action_count=1,
    )

    adapter.append_operational_journal_entry(commit, sys_results=["result line"])

    assert state.operational_journal_sequence == 1
    assert len(state.operational_journal) == 1
    entry = state.operational_journal[0]
    assert entry["kind"] == "tool_execution_commit"
    assert entry["transaction_kind"] == "read_only_batch"
    assert entry["shape"] == "action_only"
    assert entry["bundle_validated"] is False
    assert entry["transition_applied"] is False
    assert entry["action_dispatched"] is True
    assert entry["model_action_present"] is True
    assert entry["action_validated"] is True
    assert entry["execution_plan_dispatched"] is False
    assert entry["atomic_bundle_validated"] is False
    assert entry["fallback_dispatch_used"] is False
    assert entry["tool_execution_attempted"] is True
    assert entry["system_result_recorded"] is True
    assert entry["state_change_effect_recorded"] is False
    assert entry["state_change_applied"] is False
    assert entry["action_type"] == "search_files"
    assert entry["target"] == "src"
    assert entry["action_effects"] == ["search_files:src"]
    assert entry["committed_action_count"] == 1
    assert entry["committed_system_result_count"] == 0
    assert entry["dispatch_stop_requested"] is False
    assert entry["before_active_intent_id"] == ""
    assert entry["after_active_intent_id"] == ""
    assert entry["system_result_excerpt"] == "result line"
    assert entry["sequence"] == 1
