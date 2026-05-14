from types import SimpleNamespace

from modules.agent.state_manager import AgentState


def test_turn_scoped_repeat_guard_reset_clears_only_repeat_tripwires():
    state = AgentState()
    active_intent = SimpleNamespace(intent_id="keep-me")
    state.intent_runtime = SimpleNamespace(active_intent=active_intent)
    state.last_failed_action_command = {"type": "edit_file", "path": "a.kt"}
    state.last_failed_action_result = {"status": "error", "error_code": "VALIDATION_ERROR"}
    state.plan_review_required_after_state_change = True
    state.current_turn_id = 7
    state.operational_journal = [{"kind": "keep"}]

    repeated_command = {"type": "extract_symbol", "path": "a.kt", "symbol_name": "Screen"}
    state.last_completed_fingerprint = state.get_action_fingerprint(repeated_command)
    state.consecutive_same_action_count = 3
    state.forbidden_next_action_fingerprint = state.get_action_fingerprint(repeated_command)

    state.reset_turn_scoped_repeat_guards()

    assert state.consecutive_same_action_count == 0
    assert state.last_completed_fingerprint is None
    assert state.forbidden_next_action_fingerprint is None

    assert state.intent_runtime.active_intent is active_intent
    assert state.last_failed_action_command == {"type": "edit_file", "path": "a.kt"}
    assert state.last_failed_action_result == {"status": "error", "error_code": "VALIDATION_ERROR"}
    assert state.plan_review_required_after_state_change is True
    assert state.current_turn_id == 7
    assert state.operational_journal == [{"kind": "keep"}]


def test_turn_scoped_repeat_guard_reset_prevents_cross_turn_same_action_repeat():
    state = AgentState()
    command = {"type": "extract_symbol", "path": "a.kt", "symbol_name": "Screen"}

    state.update_action_repetition(command)
    state.update_action_repetition(command)
    assert state.consecutive_same_action_count == 2

    state.reset_turn_scoped_repeat_guards()
    state.update_action_repetition(command)

    assert state.consecutive_same_action_count == 1
    assert state.last_completed_fingerprint == state.get_action_fingerprint(command)
