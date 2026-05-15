from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest

from modules.agent.action_dispatcher import ActionDispatcher
from modules.agent.state_manager import AgentState


class _DummyDispatcher(ActionDispatcher):
    async def _handle_create_file(self, command):
        return await self.processor.process_single_action(command)

    async def _handle_read_file(self, command):
        return await self.processor.process_single_action(command)

    async def _handle_default(self, command):
        return await self.processor.process_single_action(command)

    def _capture_turn_working_material(self, command, result, state):
        return None

    def _refresh_current_file_state_after_success(self, command, result):
        return None

    def _format_model_facing_tool_result(self, cmd_type, command, result):
        return str(result.get("output") or "")


def _agent_with_processor_result(result):
    return SimpleNamespace(
        ui=SimpleNamespace(),
        processor=SimpleNamespace(process_single_action=AsyncMock(return_value=result)),
        config=SimpleNamespace(
            STATE_CHANGING_OPS={"create_file", "edit_file", "write_file", "run_shell"},
            RECOVERABLE_ERROR_RETRY_BUDGET=2,
            CRITICAL_ERROR_RETRY_BUDGET=1,
            READ_ONLY_REPEAT_THRESHOLD=3,
            LOOP_ERROR_REPEAT_THRESHOLD=2,
        ),
        log=None,
        history=None,
    )


@pytest.mark.asyncio
async def test_create_file_missing_body_stop_info_gets_scoped_recovery_visibility():
    result = {
        "status": "failed",
        "error_code": "VALIDATION_ERROR",
        "recoverable": True,
        "output": "create_file requires file body. Either put content as JSON string or use file_content block.",
        "next_actions": ["read_file", "create_file", "write_file_block"],
    }
    dispatcher = _DummyDispatcher(_agent_with_processor_result(result))
    state = AgentState()
    state.current_turn_id = 7
    state.intent_runtime = SimpleNamespace(
        active_intent=SimpleNamespace(
            intent_id="intent-1",
            intent_type="MODIFY",
            goal="",
            retry_count=0,
            retry_limit=3,
        ),
        pre_action_check=lambda _command: None,
        note_action=lambda _command: None,
    )

    _cmd_copy, _result_text, should_stop = await dispatcher._execute_action(
        {"type": "create_file", "path": "app/build.gradle.kts"},
        state,
    )

    assert should_stop is True
    assert state.pending_loop_stop_info["recovery_visibility"] == {
        "mode": "until_same_action_success",
        "intent_scope": "current_intent",
        "intent_id": "intent-1",
        "intent_type": "MODIFY",
        "action_type": "create_file",
        "target": "app/build.gradle.kts",
        "created_turn_id": 7,
    }


@pytest.mark.asyncio
async def test_unrelated_failed_action_stop_info_does_not_get_recovery_visibility():
    result = {
        "status": "failed",
        "error_code": "NOT_FOUND",
        "recoverable": True,
        "output": "File not found",
        "next_actions": ["list_directory", "search_files"],
    }
    dispatcher = _DummyDispatcher(_agent_with_processor_result(result))
    state = AgentState()
    state.current_turn_id = 8
    state.intent_runtime = SimpleNamespace(
        active_intent=SimpleNamespace(
            intent_id="intent-1",
            intent_type="MODIFY",
            goal="",
            retry_count=0,
            retry_limit=3,
        ),
        pre_action_check=lambda _command: None,
        note_action=lambda _command: None,
    )

    _cmd_copy, _result_text, should_stop = await dispatcher._execute_action(
        {"type": "read_file", "path": "missing.py"},
        state,
    )

    assert should_stop is False
    assert state.pending_loop_stop_info is None or "recovery_visibility" not in state.pending_loop_stop_info


@pytest.mark.asyncio
async def test_search_content_regex_parse_stop_info_gets_next_turn_recovery_visibility():
    result = {
        "status": "failed",
        "error_code": "SEARCH_REGEX_PARSE_ERROR",
        "recoverable": True,
        "output": "regex parse error: missing closing parenthesis",
        "next_actions": ["search_content"],
    }
    dispatcher = _DummyDispatcher(_agent_with_processor_result(result))
    state = AgentState()
    state.current_turn_id = 9
    state.intent_runtime = SimpleNamespace(
        active_intent=SimpleNamespace(
            intent_id="intent-2",
            intent_type="INVESTIGATE",
            goal="",
            retry_count=0,
            retry_limit=3,
        ),
        pre_action_check=lambda _command: None,
        note_action=lambda _command: None,
    )

    _cmd_copy, _result_text, should_stop = await dispatcher._execute_action(
        {"type": "search_content", "path": "modules", "pattern": "("},
        state,
    )

    assert should_stop is True
    assert state.pending_loop_stop_info["recovery_visibility"] == {
        "mode": "next_turn",
        "intent_scope": "current_intent",
        "intent_id": "intent-2",
        "intent_type": "INVESTIGATE",
        "action_type": "search_content",
        "target": "modules:(",
        "created_turn_id": 9,
    }
