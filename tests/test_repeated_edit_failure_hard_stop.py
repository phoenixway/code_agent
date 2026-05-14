from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

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


def _ui():
    return SimpleNamespace(
        print_edit_file_start=AsyncMock(return_value=object()),
        start_action=AsyncMock(),
        update_edit_file_result=AsyncMock(),
        print_tool_call=AsyncMock(return_value=object()),
        update_tool_call=AsyncMock(),
        print_plan=AsyncMock(),
        print_command_result=AsyncMock(),
        print_confirmation=AsyncMock(),
        print_shell_start=AsyncMock(return_value=object()),
        update_shell_result=AsyncMock(),
        print_read_file_start=AsyncMock(return_value=object()),
        update_read_file_result=AsyncMock(),
    )


def _config():
    return SimpleNamespace(
        STATE_CHANGING_OPS={"edit_file", "create_file", "run_shell", "write_file_block"},
        LOOP_ERROR_REPEAT_THRESHOLD=2,
        READ_ONLY_REPEAT_THRESHOLD=3,
        RECOVERABLE_ERROR_RETRY_BUDGET=2,
        CRITICAL_ERROR_RETRY_BUDGET=1,
    )


def _failed_edit_result():
    return {
        "status": "error",
        "error_code": "VALIDATION_ERROR",
        "recoverable": True,
        "output": "Search block not found in src/example.py",
        "next_actions": ["read_chunk", "read_file", "search_content", "edit_file", "write_file_block"],
        "error_details": {"mismatch_type": "search_text_stale_or_block_modified"},
    }


def _agent(*, processor_result=None):
    return SimpleNamespace(
        ui=_ui(),
        processor=SimpleNamespace(process_single_action=AsyncMock(return_value=processor_result or _failed_edit_result())),
        config=_config(),
        log=DummyLog(),
    )


@pytest.mark.asyncio
async def test_repeated_edit_validation_failure_hard_stop_includes_write_file_block_for_modify():
    agent = _agent()
    dispatcher = ActionDispatcher(agent)
    state = AgentState(agent.config)
    state.intent_runtime = _intent_runtime(
        intent_type="MODIFY",
        allowed_actions=["read_chunk", "read_file", "search_content", "edit_file"],
    )
    state.record_action_result = MagicMock(
        return_value={
            "status": "error",
            "error_code": "VALIDATION_ERROR",
            "recoverable": True,
            "next_actions": ["read_chunk", "read_file", "search_content", "edit_file", "write_file_block"],
            "same_error_repeats": 2,
            "same_action_repeats": 0,
            "defect_info": None,
        }
    )

    command = {
        "type": "edit_file",
        "path": "src/example.py",
        "search_text": "old",
        "replace_text": "new",
    }
    _cmd_copy, result_text, should_stop = await dispatcher._execute_action(command, state)

    assert should_stop is True
    assert "Repeated edit_file search mismatch detected" in result_text
    assert state.pending_loop_stop_info["reason"] == "repeated_edit_failure_hard_stop"
    assert state.pending_loop_stop_info["error_code"] == "VALIDATION_ERROR"
    assert state.pending_loop_stop_info["policy_allowed_actions"] == [
        "read_chunk",
        "extract_symbol",
        "replace_symbol",
        "write_file_block",
    ]
    assert state.pending_loop_stop_info["policy_recommended_actions"] == [
        "read_chunk",
        "extract_symbol",
        "replace_symbol",
        "write_file_block",
    ]
    assert "edit_file" not in state.pending_loop_stop_info["policy_allowed_actions"]
    # The stable recovery contract is the hard-stop reason plus policy actions.
    # Additional diagnostic metadata may be exported differently by RecoveryContext.


@pytest.mark.asyncio
async def test_repeated_edit_validation_failure_hard_stop_excludes_write_file_block_for_non_modify():
    agent = _agent()
    dispatcher = ActionDispatcher(agent)
    state = AgentState(agent.config)
    state.intent_runtime = _intent_runtime(
        intent_type="INVESTIGATE",
        allowed_actions=["read_chunk", "read_file", "search_content", "edit_file"],
    )
    state.record_action_result = MagicMock(
        return_value={
            "status": "error",
            "error_code": "VALIDATION_ERROR",
            "recoverable": True,
            "next_actions": ["read_chunk", "read_file", "search_content", "edit_file", "write_file_block"],
            "same_error_repeats": 2,
            "same_action_repeats": 0,
            "defect_info": None,
        }
    )

    command = {
        "type": "edit_file",
        "path": "src/example.py",
        "search_text": "old",
        "replace_text": "new",
    }
    _cmd_copy, _result_text, should_stop = await dispatcher._execute_action(command, state)

    assert should_stop is True
    assert state.pending_loop_stop_info["reason"] == "repeated_edit_failure_hard_stop"
    assert state.pending_loop_stop_info["policy_allowed_actions"] == [
        "read_chunk",
        "search_content",
        "read_file",
    ]
    assert "edit_file" not in state.pending_loop_stop_info["policy_allowed_actions"]
    assert "replace_symbol" not in state.pending_loop_stop_info["policy_allowed_actions"]
    assert "write_file_block" not in state.pending_loop_stop_info["policy_allowed_actions"]


@pytest.mark.asyncio
async def test_single_edit_validation_failure_does_not_hard_stop_before_threshold():
    agent = _agent()
    dispatcher = ActionDispatcher(agent)
    state = AgentState(agent.config)
    state.intent_runtime = _intent_runtime(
        intent_type="MODIFY",
        allowed_actions=["read_chunk", "read_file", "search_content", "edit_file"],
    )
    state.record_action_result = MagicMock(
        return_value={
            "status": "error",
            "error_code": "VALIDATION_ERROR",
            "recoverable": True,
            "next_actions": ["read_chunk", "read_file", "search_content", "edit_file", "write_file_block"],
            "same_error_repeats": 1,
            "same_action_repeats": 0,
            "defect_info": None,
        }
    )

    command = {
        "type": "edit_file",
        "path": "src/example.py",
        "search_text": "old",
        "replace_text": "new",
    }
    _cmd_copy, result_text, should_stop = await dispatcher._execute_action(command, state)

    assert should_stop is False
    assert "Repeated edit_file" not in result_text
    assert state.pending_loop_stop_info is None
