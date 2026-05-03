from types import SimpleNamespace

from modules.agent.orchestration.runtime.action_policy_state import ActionPolicyStateAdapter


def test_disallowed_action_repeat_resets_when_intent_changes():
    state = SimpleNamespace(
        active_intent=SimpleNamespace(intent_id="intent_a"),
        disallowed_action_repeat_type="write_file_block",
        disallowed_action_repeat_intent_id="intent_b",
        disallowed_action_repeat_count=2,
    )
    adapter = ActionPolicyStateAdapter(state)

    count = adapter.note_disallowed_action_repeat("write_file_block")

    assert count == 1
    assert state.disallowed_action_repeat_intent_id == "intent_a"
    assert state.disallowed_action_repeat_count == 1


def test_pending_edit_mismatch_matches_only_current_intent_and_path():
    state = SimpleNamespace(
        active_intent=SimpleNamespace(intent_id="intent_a"),
        pending_edit_mismatch_path="a.py",
        pending_edit_mismatch_intent_id="intent_a",
    )
    adapter = ActionPolicyStateAdapter(state)

    assert adapter.has_pending_edit_mismatch_for_path("a.py")
    assert not adapter.has_pending_edit_mismatch_for_path("b.py")


def test_mark_terminal_plaintext_handoff_updates_state_and_calls_marker():
    called = {}

    def marker(reason, source):
        called["reason"] = reason
        called["source"] = source

    state = SimpleNamespace(mark_pending_forced_plaintext_completion_close=marker)
    adapter = ActionPolicyStateAdapter(state)

    adapter.mark_terminal_plaintext_handoff("done", "terminal_reason")

    assert state.terminal_plaintext_completion_pending is True
    assert state.terminal_plaintext_completion_text == "done"
    assert called == {"reason": "terminal_reason", "source": "action_policy"}
