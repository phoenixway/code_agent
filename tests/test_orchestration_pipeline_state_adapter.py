from types import SimpleNamespace

from modules.agent.orchestration.runtime.pipeline_state import OrchestrationPipelineStateAdapter


def test_pipeline_state_adapter_tracks_terminal_plaintext_buffer_and_reset():
    state = SimpleNamespace(
        terminal_plaintext_completion_pending=True,
        terminal_plaintext_completion_text="buffer",
        readonly_steps_this_turn=2,
    )
    adapter = OrchestrationPipelineStateAdapter(state)

    assert adapter.terminal_plaintext_completion_pending() is True
    assert adapter.terminal_plaintext_completion_text() == "buffer"

    adapter.set_terminal_plaintext_completion_text("done")
    adapter.reset_readonly_steps_this_turn()

    assert state.terminal_plaintext_completion_text == "done"
    assert state.readonly_steps_this_turn == 0


def test_pipeline_state_adapter_reads_and_clears_model_stop_reason():
    state = SimpleNamespace(last_model_response_stop_reason="smart_stop")
    adapter = OrchestrationPipelineStateAdapter(state)

    assert adapter.model_stop_reason() == "smart_stop"

    adapter.clear_model_stop_reason()

    assert state.last_model_response_stop_reason == ""


def test_pipeline_state_adapter_closes_active_intent_after_interruption():
    calls = []

    def close_active_intent_as_resumable(reason):
        calls.append(reason)

    state = SimpleNamespace(close_active_intent_as_resumable=close_active_intent_as_resumable)
    adapter = OrchestrationPipelineStateAdapter(state)

    assert adapter.close_active_intent_as_resumable("technical_interruption") is True
    assert calls == ["technical_interruption"]
