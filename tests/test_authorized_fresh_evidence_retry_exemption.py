from types import SimpleNamespace

from modules.agent.defect_detector import DefectDetector
from modules.agent.state_manager import AgentState


def _state() -> AgentState:
    state = AgentState(None)
    state.defect_detector = DefectDetector(
        SimpleNamespace(
            DEFECT_SAME_ACTION_REPEAT_THRESHOLD=2,
            DEFECT_ACTION_CYCLE_WINDOW=3,
        )
    )
    state.intent_runtime = None
    return state


def _failed_edit(search_text="old wrong"):
    return {
        "type": "edit_file",
        "path": "src/example.py",
        "search_text": search_text,
        "replace_text": "replacement",
    }


def _fixed_edit(search_text="old correct"):
    return {
        "type": "edit_file",
        "path": "src/example.py",
        "search_text": search_text,
        "replace_text": "replacement",
    }


def _failed_result():
    return {
        "status": "error",
        "error_code": "VALIDATION_ERROR",
        "recoverable": True,
        "output": "Search block not found",
    }


def _read_result():
    return {
        "status": "success",
        "output": "def f():\n    old correct\n",
    }


def _success_result():
    return {
        "status": "success",
        "output": "Changes applied",
    }


def _prime_repeat_guard(state: AgentState, command: dict) -> None:
    state.last_completed_fingerprint = state.get_action_fingerprint(command)
    state.consecutive_same_action_count = 1


def test_blocks_repeat_without_user_intervention_even_after_read():
    state = _state()
    failed = _failed_edit()
    fixed = _fixed_edit()

    state.current_turn_id = 1
    state.record_action_result(failed, _failed_result())
    state.record_action_result({"type": "read_chunk", "path": "src/example.py"}, _read_result())
    _prime_repeat_guard(state, fixed)

    metrics = state.record_action_result(fixed, _success_result())

    assert metrics["defect_info"] is not None
    assert metrics["defect_info"]["reason"] == "defect_same_action_repeat"


def test_blocks_user_intervention_without_fresh_same_target_read():
    state = _state()
    failed = _failed_edit()
    fixed = _fixed_edit()

    state.current_turn_id = 1
    state.record_action_result(failed, _failed_result())
    state.current_turn_id = 2
    _prime_repeat_guard(state, fixed)

    metrics = state.record_action_result(fixed, _success_result())

    assert metrics["defect_info"] is not None
    assert metrics["defect_info"]["reason"] == "defect_same_action_repeat"


def test_blocks_user_intervention_and_read_but_same_payload():
    state = _state()
    failed = _failed_edit()

    state.current_turn_id = 1
    state.record_action_result(failed, _failed_result())
    state.current_turn_id = 2
    state.record_action_result({"type": "read_chunk", "path": "src/example.py"}, _read_result())
    _prime_repeat_guard(state, failed)

    metrics = state.record_action_result(failed, _success_result())

    assert metrics["defect_info"] is not None
    assert metrics["defect_info"]["reason"] == "defect_same_action_repeat"


def test_allows_one_user_authorized_fresh_read_materially_changed_retry():
    state = _state()
    failed = _failed_edit()
    fixed = _fixed_edit()

    state.current_turn_id = 1
    state.record_action_result(failed, _failed_result())
    state.current_turn_id = 2
    state.record_action_result({"type": "read_chunk", "path": "src/example.py"}, _read_result())
    _prime_repeat_guard(state, fixed)

    metrics = state.record_action_result(fixed, _success_result())

    assert metrics["defect_info"] is None
    assert metrics["same_action_repeats"] == 0


def test_second_retry_requires_new_user_message_or_new_fresh_read():
    state = _state()
    failed = _failed_edit()
    fixed = _fixed_edit()

    state.current_turn_id = 1
    state.record_action_result(failed, _failed_result())
    state.current_turn_id = 2
    state.record_action_result({"type": "read_chunk", "path": "src/example.py"}, _read_result())
    _prime_repeat_guard(state, fixed)
    first = state.record_action_result(fixed, _success_result())
    assert first["defect_info"] is None

    _prime_repeat_guard(state, fixed)
    second = state.record_action_result(fixed, _success_result())

    assert second["defect_info"] is not None
    assert second["defect_info"]["reason"] == "defect_same_action_repeat"
