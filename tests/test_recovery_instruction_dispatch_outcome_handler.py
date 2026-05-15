from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest

from modules.agent.orchestration.runtime.dispatch_outcome import DispatchOutcomeHandler


class _Parser:
    def reconstruct(self, processed_segs):
        return ""


class _Recovery:
    def __init__(self):
        self.handle_dispatch_stop = AsyncMock(
            return_value=SimpleNamespace(
                handled=True,
                clear_pending_stop=True,
                next_query="retry now",
                stop_loop=False,
                reason="recoverable_failure",
                source="dispatch_recovery",
            )
        )


class _State:
    def __init__(self, stop_info):
        self.pending_loop_stop_info = stop_info
        self.terminal_plaintext_completion_pending = False
        self.terminal_plaintext_completion_text = ""
        self.orchestration_trace_sequence = 0
        self.orchestration_trace = []


@pytest.mark.asyncio
async def test_dispatch_outcome_handler_records_scoped_recovery_instruction_when_stop_info_has_visibility():
    visibility = {
        "mode": "until_same_action_success",
        "intent_scope": "current_intent",
        "intent_id": "intent-1",
        "intent_type": "MODIFY",
        "action_type": "create_file",
        "target": "a.txt",
        "created_turn_id": 7,
    }
    stop_info = {
        "reason": "retry_or_continuation_after_failure",
        "recoverable": True,
        "message": "create_file requires file body. Retry with real content.",
        "recovery_visibility": visibility,
    }
    state = _State(stop_info)
    history = MagicMock()
    agent = SimpleNamespace(
        state=state,
        history=history,
        ui=SimpleNamespace(),
        log=None,
    )
    recovery = _Recovery()
    handler = DispatchOutcomeHandler(agent, _Parser(), recovery)
    ctx = SimpleNamespace(current_query="fix", state_machine=None, active_loop=True)

    decision = await handler.handle(
        ctx,
        processed_segs=[],
        sys_results=["SYSTEM RESULT for `create_file`: failed"],
        should_stop=True,
    )

    assert decision.handled is True
    history.add_message.assert_any_call("system", "SYSTEM RESULT for `create_file`: failed")
    history.add_message.assert_any_call(
        "system",
        "create_file requires file body. Retry with real content.",
        msg_type="recovery_instruction",
        recovery_visibility=visibility,
    )
    recovery.handle_dispatch_stop.assert_awaited_once_with(stop_info, None)


@pytest.mark.asyncio
async def test_dispatch_outcome_handler_does_not_record_recovery_instruction_without_visibility_metadata():
    stop_info = {
        "reason": "retry_or_continuation_after_failure",
        "recoverable": True,
        "message": "legacy recovery message",
    }
    state = _State(stop_info)
    history = MagicMock()
    agent = SimpleNamespace(
        state=state,
        history=history,
        ui=SimpleNamespace(),
        log=None,
    )
    recovery = _Recovery()
    handler = DispatchOutcomeHandler(agent, _Parser(), recovery)
    ctx = SimpleNamespace(current_query="fix", state_machine=None, active_loop=True)

    await handler.handle(
        ctx,
        processed_segs=[],
        sys_results=["SYSTEM RESULT for `read_file`: failed"],
        should_stop=True,
    )

    calls = history.add_message.call_args_list
    assert (("system", "SYSTEM RESULT for `read_file`: failed"), {}) in [
        (call.args, call.kwargs) for call in calls
    ]
    assert not any(call.kwargs.get("msg_type") == "recovery_instruction" for call in calls)
