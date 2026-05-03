from types import SimpleNamespace

from modules.agent.orchestration.runtime.recovery_state import RecoveryStateAdapter


def test_universe_label_tracks_active_intent_presence():
    active = RecoveryStateAdapter(SimpleNamespace(active_intent=SimpleNamespace(intent_id="x")))
    inactive = RecoveryStateAdapter(SimpleNamespace(active_intent=None))

    assert active.universe_label() == "active_contract"
    assert inactive.universe_label() == "no_active_contract"


def test_mark_pending_finalize_after_terminal_plaintext_completion_sets_state_fields():
    state = SimpleNamespace()
    adapter = RecoveryStateAdapter(state)

    adapter.mark_pending_finalize_after_terminal_plaintext_completion("done_reason", "done_source")

    assert state.pending_finalize_after_terminal_plaintext_completion is True
    assert state.pending_finalize_completion_reason == "done_reason"
    assert state.pending_finalize_completion_source == "done_source"


def test_note_repeated_disallowed_action_increments_for_same_fingerprint():
    state = SimpleNamespace(
        last_disallowed_action_fingerprint="intent_a|write_file|x.md",
        last_disallowed_action_repeat_count=2,
        active_intent=SimpleNamespace(intent_id="intent_a"),
    )
    adapter = RecoveryStateAdapter(state)

    count, blocked_action, fingerprint = adapter.note_repeated_disallowed_action(
        {"command": {"type": "write_file", "path": "x.md"}},
        state.active_intent,
    )

    assert count == 3
    assert blocked_action == "write_file"
    assert fingerprint == "intent_a|write_file|x.md"
