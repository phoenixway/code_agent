from types import SimpleNamespace

from modules.agent.orchestration.runtime.core_state import OrchestratorCoreStateAdapter


def test_terminal_plaintext_completion_text_is_normalized_and_cleared():
    state = SimpleNamespace(
        terminal_plaintext_completion_pending=True,
        terminal_plaintext_completion_text="  done  ",
    )
    adapter = OrchestratorCoreStateAdapter(state)

    assert adapter.terminal_plaintext_completion_text() == "done"

    adapter.clear_terminal_plaintext_completion()

    assert state.terminal_plaintext_completion_pending is False
    assert state.terminal_plaintext_completion_text == ""


def test_pending_finalize_completion_reason_defaults_and_clears():
    state = SimpleNamespace(
        pending_finalize_after_terminal_plaintext_completion=True,
        pending_finalize_completion_reason="",
        pending_finalize_completion_source="runtime",
    )
    adapter = OrchestratorCoreStateAdapter(state)

    assert adapter.pending_finalize_after_terminal_plaintext_completion() is True
    assert adapter.pending_finalize_completion_reason() == "forced_plaintext_completion"

    adapter.clear_pending_finalize_after_terminal_plaintext_completion()

    assert state.pending_finalize_after_terminal_plaintext_completion is False
    assert state.pending_finalize_completion_reason == ""
    assert state.pending_finalize_completion_source == ""


def test_close_active_intent_as_resumable_passes_reason_and_flag():
    calls = []

    def close_active_intent_as_resumable(reason, clear_pending_stop=False):
        calls.append((reason, clear_pending_stop))

    state = SimpleNamespace(close_active_intent_as_resumable=close_active_intent_as_resumable)
    adapter = OrchestratorCoreStateAdapter(state)

    assert adapter.close_active_intent_as_resumable("user_requested_stop", clear_pending_stop=True) is True
    assert calls == [("user_requested_stop", True)]
