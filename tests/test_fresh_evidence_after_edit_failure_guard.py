from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from modules.agent.action_dispatcher import ActionDispatcher
from modules.agent.state_manager import AgentState


class DummyLog:
    def debug(self, *_args, **_kwargs):
        pass


def _ui():
    return SimpleNamespace(
        print_edit_file_start=AsyncMock(return_value=object()),
        start_action=AsyncMock(),
        update_edit_file_result=AsyncMock(),
        print_tool_call=AsyncMock(),
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
        STATE_CHANGING_OPS={"edit_file", "create_file", "replace_symbol", "run_shell"},
        LOOP_ERROR_REPEAT_THRESHOLD=2,
        READ_ONLY_REPEAT_THRESHOLD=3,
        RECOVERABLE_ERROR_RETRY_BUDGET=2,
        CRITICAL_ERROR_RETRY_BUDGET=1,
    )


def _agent(*, processor_result=None):
    return SimpleNamespace(
        ui=_ui(),
        processor=SimpleNamespace(
            process_single_action=AsyncMock(
                return_value=processor_result or {"status": "success", "output": "symbol body"}
            )
        ),
        config=_config(),
        log=DummyLog(),
    )


def _prime_failed_edit_mismatch(state: AgentState, *, path="a.kt"):
    state.last_failed_action_command = {
        "type": "edit_file",
        "path": path,
        "search_text": "old",
        "replace_text": "new",
    }
    state.last_failed_action_result = {
        "status": "error",
        "error_code": "VALIDATION_ERROR",
        "output": "Search block not found. Ensure whitespace and indentation match exactly.",
    }
    state.last_error_code = "VALIDATION_ERROR"


@pytest.mark.asyncio
async def test_allows_fresh_extract_symbol_after_edit_mismatch_even_if_fingerprint_was_forbidden():
    agent = _agent()
    dispatcher = ActionDispatcher(agent)
    state = AgentState(agent.config)
    _prime_failed_edit_mismatch(state, path="a.kt")

    command = {
        "type": "extract_symbol",
        "path": "a.kt",
        "symbol_name": "Screen",
        "symbol_kind": "composable",
    }
    state.forbid_next_action_fingerprint(state.get_action_fingerprint(command))

    _cmd_copy, result_text, should_stop = await dispatcher._execute_action(command, state)

    assert should_stop is False
    assert "symbol body" in result_text
    agent.processor.process_single_action.assert_called_once()


@pytest.mark.asyncio
async def test_blocks_forbidden_extract_symbol_when_failed_edit_was_for_different_path():
    agent = _agent()
    dispatcher = ActionDispatcher(agent)
    state = AgentState(agent.config)
    _prime_failed_edit_mismatch(state, path="other.kt")

    command = {
        "type": "extract_symbol",
        "path": "a.kt",
        "symbol_name": "Screen",
        "symbol_kind": "composable",
    }
    state.forbid_next_action_fingerprint(state.get_action_fingerprint(command))

    _cmd_copy, result_text, should_stop = await dispatcher._execute_action(command, state)

    assert should_stop is True
    assert "repeating the previous action immediately after malformed-action recovery" in result_text
    agent.processor.process_single_action.assert_not_called()


@pytest.mark.asyncio
async def test_blocks_forbidden_search_content_when_search_is_broad_root_scope():
    agent = _agent()
    dispatcher = ActionDispatcher(agent)
    state = AgentState(agent.config)
    _prime_failed_edit_mismatch(state, path=".")

    command = {
        "type": "search_content",
        "path": ".",
        "pattern": "Screen",
    }
    state.forbid_next_action_fingerprint(state.get_action_fingerprint(command))

    _cmd_copy, result_text, should_stop = await dispatcher._execute_action(command, state)

    assert should_stop is True
    assert "repeating the previous action immediately after malformed-action recovery" in result_text
    agent.processor.process_single_action.assert_not_called()
