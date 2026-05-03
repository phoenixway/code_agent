from types import SimpleNamespace

from modules.agent.orchestration.runtime.dispatch_outcome_history import DispatchOutcomeHistoryAdapter
from modules.agent.orchestration.runtime.dispatch_outcome_state import DispatchOutcomeStateAdapter


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
