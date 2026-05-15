from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest

from modules.agent.action_dispatcher import ActionDispatcher


class _DummyState:
    def __init__(self):
        self.pending_loop_stop_info = None
        self.state_machine = None
        self.note_recovery_visibility_success = MagicMock()
        self.record_action_result = MagicMock(return_value={"same_action_repeats": 0, "defect_info": None})
        self.reset_retry_budgets = MagicMock()
        self.consume_forbidden_action_if_matches = MagicMock(return_value=False)
        self.current_turn_id = 3

    def note_fresh_edit_evidence_if_applicable(self, command, result):
        return None

    def consume_authorized_fresh_evidence_retry_exemption(self, command, defect_reason):
        return False


class _DummyDispatcher(ActionDispatcher):
    def _capture_turn_working_material(self, command, result, state):
        return None

    def _refresh_current_file_state_after_success(self, command, result):
        return None

    def _format_model_facing_tool_result(self, cmd_type, command, result):
        return str(result.get("output") or "")


@pytest.mark.asyncio
async def test_dispatcher_records_recovery_visibility_success_after_successful_action():
    state = _DummyState()
    agent = SimpleNamespace(
        ui=SimpleNamespace(),
        processor=SimpleNamespace(),
        config=SimpleNamespace(
            STATE_CHANGING_OPS=set(),
            RECOVERABLE_ERROR_RETRY_BUDGET=2,
            CRITICAL_ERROR_RETRY_BUDGET=1,
            READ_ONLY_REPEAT_THRESHOLD=3,
        ),
        log=None,
        history=None,
    )
    dispatcher = _DummyDispatcher(agent)
    dispatcher._handlers["read_file"] = AsyncMock(return_value={"status": "success", "output": "ok"})

    await dispatcher._execute_action({"type": "read_file", "path": "a.py"}, state)

    state.note_recovery_visibility_success.assert_called_once_with(
        {"type": "read_file", "path": "a.py"},
        {"status": "success", "output": "ok"},
    )


@pytest.mark.asyncio
async def test_dispatcher_does_not_record_recovery_visibility_success_after_failed_action():
    state = _DummyState()
    agent = SimpleNamespace(
        ui=SimpleNamespace(),
        processor=SimpleNamespace(),
        config=SimpleNamespace(
            STATE_CHANGING_OPS=set(),
            RECOVERABLE_ERROR_RETRY_BUDGET=2,
            CRITICAL_ERROR_RETRY_BUDGET=1,
            READ_ONLY_REPEAT_THRESHOLD=3,
        ),
        log=None,
        history=None,
    )
    dispatcher = _DummyDispatcher(agent)
    dispatcher._handlers["read_file"] = AsyncMock(return_value={"status": "error", "output": "bad"})

    await dispatcher._execute_action({"type": "read_file", "path": "a.py"}, state)

    state.note_recovery_visibility_success.assert_not_called()
