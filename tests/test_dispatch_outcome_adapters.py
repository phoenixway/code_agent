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
    assert captured == [
        {
            "kind": "tool_execution_commit",
            "transaction_kind": "atomic_intent_action_bundle",
            "shape": "intent_action_bundle",
            "bundle_validated": True,
            "transition_applied": True,
            "action_dispatched": True,
            "action_type": "read_chunk",
            "target": "x.py",
            "action_effects": ["read_chunk:x.py"],
            "committed_action_count": 1,
            "committed_system_result_count": 1,
            "dispatch_stop_requested": False,
            "before_active_intent_id": "intent_before",
            "after_active_intent_id": "intent_after",
            "system_result_excerpt": "ok",
        }
    ]


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
    assert state.operational_journal == [
        {
            "kind": "tool_execution_commit",
            "transaction_kind": "read_only_batch",
            "shape": "action_only",
            "bundle_validated": False,
            "transition_applied": False,
            "action_dispatched": True,
            "action_type": "search_files",
            "target": "src",
            "action_effects": ["search_files:src"],
            "committed_action_count": 1,
            "committed_system_result_count": 0,
            "dispatch_stop_requested": False,
            "before_active_intent_id": "",
            "after_active_intent_id": "",
            "system_result_excerpt": "result line",
            "sequence": 1,
        }
    ]
