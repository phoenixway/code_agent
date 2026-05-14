from types import SimpleNamespace

import pytest

from modules.agent.action_dispatcher import ActionDispatcher
from modules.agent.state_manager import AgentState


class DummyLog:
    def debug(self, *_args, **_kwargs):
        pass


class DummyIntent:
    def __init__(self, *, intent_type="MODIFY", allowed_actions=None):
        self.intent_type = intent_type
        self.allowed_actions = list(allowed_actions or [])


def _intent_runtime(*, intent_type="MODIFY", allowed_actions=None):
    return SimpleNamespace(
        active_intent=DummyIntent(
            intent_type=intent_type,
            allowed_actions=list(allowed_actions or []),
        ),
        pre_action_check=lambda _command: None,
    )


def _agent():
    return SimpleNamespace(
        ui=None,
        processor=SimpleNamespace(process_single_action=None),
        config=SimpleNamespace(LOOP_ERROR_REPEAT_THRESHOLD=2),
        log=DummyLog(),
    )


@pytest.mark.asyncio
async def test_repeated_malformed_edit_file_schema_preflight_hard_stops_without_dispatch():
    agent = _agent()
    dispatcher = ActionDispatcher(agent)
    state = AgentState(agent.config)
    state.intent_runtime = _intent_runtime(
        intent_type="MODIFY",
        allowed_actions=[
            "read_chunk",
            "read_file_skeleton",
            "extract_symbol",
            "replace_symbol",
            "edit_file",
            "write_file_block",
        ],
    )

    command = {
        "type": "edit_file",
        "path": "src/ChecklistViewModel.kt",
        "search_text": "old",
    }

    _cmd_copy, first_result, first_stop = await dispatcher._execute_action(command, state)
    assert first_stop is True
    assert "Invalid edit_file payload" in first_result
    assert state.pending_loop_stop_info["reason"] == "malformed_edit_file_payload"
    assert state.consecutive_schema_preflight_failures == 1
    assert state.last_error_code == "MALFORMED_EDIT_FILE_PAYLOAD"
    assert state.last_failed_action_command == command
    assert state.last_failed_action_result["error_details"]["schema_preflight"] is True

    _cmd_copy, second_result, second_stop = await dispatcher._execute_action(command, state)
    assert second_stop is True
    assert "Repeated malformed action payload detected before dispatch" in second_result
    assert state.pending_loop_stop_info["reason"] == "repeated_schema_preflight_failure_hard_stop"
    assert state.pending_loop_stop_info["error_code"] == "MALFORMED_EDIT_FILE_PAYLOAD"
    assert state.consecutive_schema_preflight_failures == 2
    assert "edit_file" not in state.pending_loop_stop_info["policy_allowed_actions"]
    assert state.pending_loop_stop_info["policy_allowed_actions"] == [
        "read_chunk",
        "read_file_skeleton",
        "extract_symbol",
        "replace_symbol",
        "write_file_block",
    ]


@pytest.mark.asyncio
async def test_schema_preflight_failure_fingerprint_resets_for_different_schema_shape():
    agent = _agent()
    dispatcher = ActionDispatcher(agent)
    state = AgentState(agent.config)
    state.intent_runtime = _intent_runtime(
        intent_type="MODIFY",
        allowed_actions=["read_chunk", "extract_symbol", "replace_symbol", "edit_file", "write_file_block"],
    )

    missing_replace_text = {
        "type": "edit_file",
        "path": "src/ChecklistViewModel.kt",
        "search_text": "old",
    }
    line_range_payload = {
        "type": "edit_file",
        "path": "src/ChecklistViewModel.kt",
        "start_line": 10,
        "end_line": 12,
        "replace_text": "new",
    }

    await dispatcher._execute_action(missing_replace_text, state)
    assert state.consecutive_schema_preflight_failures == 1

    await dispatcher._execute_action(line_range_payload, state)
    assert state.consecutive_schema_preflight_failures == 1
    assert state.pending_loop_stop_info["reason"] == "malformed_edit_file_payload"
