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

    async def _handle_shell(self, command):
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
    assert "Return only a corrected compact recovery step" not in _result_text
    assert "[RECOVERY_SCOPE]" in _result_text
    assert "This instruction applies only to the next corrective step" in _result_text
    assert "[EXIT_CONDITION]" in _result_text
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
async def test_read_file_not_found_stop_info_gets_next_turn_recovery_visibility():
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

    assert should_stop is True
    assert "Use the runtime recovery payload below" in _result_text
    assert "Return only a corrected compact recovery step" not in _result_text
    assert "[RECOVERY_SCOPE]" in _result_text
    assert "[WHAT_FAILED]" in _result_text
    assert "The requested path was not found." in _result_text
    assert "Do not repeatedly probe the same missing path." in _result_text
    assert "[NEXT_STEP_RULE]" in _result_text
    assert "[EXIT_CONDITION]" in _result_text
    assert state.pending_loop_stop_info["recovery_visibility"] == {
        "mode": "next_turn",
        "intent_scope": "current_intent",
        "intent_id": "intent-1",
        "intent_type": "MODIFY",
        "action_type": "read_file",
        "target": "missing.py",
        "created_turn_id": 8,
    }


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
    assert "Return only a corrected compact recovery step" not in _result_text
    assert "[RECOVERY_SCOPE]" in _result_text
    assert "This instruction applies only to the next corrective step" in _result_text
    assert "[EXIT_CONDITION]" in _result_text
    assert state.pending_loop_stop_info["recovery_visibility"] == {
        "mode": "next_turn",
        "intent_scope": "current_intent",
        "intent_id": "intent-2",
        "intent_type": "INVESTIGATE",
        "action_type": "search_content",
        "target": "modules:(",
        "created_turn_id": 9,
    }


@pytest.mark.asyncio
async def test_action_denied_stop_info_gets_next_turn_recovery_visibility():
    result = {
        "status": "denied",
        "error_code": "USER_DENIED",
        "recoverable": True,
        "output": "Action denied by user",
        "next_actions": ["read_file", "search_content"],
    }
    dispatcher = _DummyDispatcher(_agent_with_processor_result(result))
    state = AgentState()
    state.current_turn_id = 10
    state.intent_runtime = SimpleNamespace(
        active_intent=SimpleNamespace(
            intent_id="intent-denied",
            intent_type="MODIFY",
            goal="",
            retry_count=0,
            retry_limit=3,
        ),
        pre_action_check=lambda _command: None,
        note_action=lambda _command: None,
    )

    _cmd_copy, _result_text, should_stop = await dispatcher._execute_action(
        {"type": "run_shell", "command": "rm -rf build"},
        state,
    )

    assert should_stop is True
    assert "Action denied by user" in _result_text
    assert state.pending_loop_stop_info["recovery_visibility"] == {
        "mode": "next_turn",
        "intent_scope": "current_intent",
        "intent_id": "intent-denied",
        "intent_type": "MODIFY",
        "action_type": "run_shell",
        "target": "rm -rf build",
        "created_turn_id": 10,
    }


@pytest.mark.asyncio
async def test_run_shell_timeout_stop_info_uses_shell_specific_scoped_recovery_text():
    result = {
        "status": "failed",
        "error_code": "COMMAND_TIMEOUT",
        "recoverable": True,
        "output": "Command timed out",
        "next_actions": ["run_shell", "read_file"],
    }
    dispatcher = _DummyDispatcher(_agent_with_processor_result(result))
    state = AgentState()
    state.current_turn_id = 11
    state.intent_runtime = SimpleNamespace(
        active_intent=SimpleNamespace(
            intent_id="intent-shell",
            intent_type="INVESTIGATE",
            goal="",
            retry_count=0,
            retry_limit=3,
        ),
        pre_action_check=lambda _command: None,
        note_action=lambda _command: None,
    )

    _cmd_copy, _result_text, should_stop = await dispatcher._execute_action(
        {"type": "run_shell", "command": "./gradlew test"},
        state,
    )

    assert should_stop is True
    assert "[RECOVERY_SCOPE]" in _result_text
    assert "[WHAT_FAILED]" in _result_text
    assert "The previous shell command failed, timed out, or hit transient I/O." in _result_text
    assert "Do not repeat the same long command blindly." in _result_text
    assert "If a command fails because an external tool/wrapper is missing" in _result_text
    assert "do not manually reconstruct vendor wrapper files" in _result_text
    assert "[NEXT_STEP_RULE]" in _result_text
    assert "[EXIT_CONDITION]" in _result_text
    assert state.pending_loop_stop_info["recovery_visibility"] == {
        "mode": "next_turn",
        "intent_scope": "current_intent",
        "intent_id": "intent-shell",
        "intent_type": "INVESTIGATE",
        "action_type": "run_shell",
        "target": "./gradlew test",
        "created_turn_id": 11,
    }


@pytest.mark.asyncio
async def test_run_shell_missing_executable_uses_shell_specific_scoped_recovery_text():
    result = {
        "status": "failed",
        "error_code": "MISSING_EXECUTABLE",
        "recoverable": True,
        "output": "Required executable is unavailable",
        "missing_executable": "gradle",
        "error_details": {"missing_executable": "gradle"},
        "next_actions": ["run_shell", "read_file"],
    }
    dispatcher = _DummyDispatcher(_agent_with_processor_result(result))
    state = AgentState()
    state.current_turn_id = 12
    state.intent_runtime = SimpleNamespace(
        active_intent=SimpleNamespace(
            intent_id="intent-gradle",
            intent_type="INVESTIGATE",
            goal="",
            retry_count=0,
            retry_limit=3,
        ),
        pre_action_check=lambda _command: None,
        note_action=lambda _command: None,
    )

    _cmd_copy, _result_text, should_stop = await dispatcher._execute_action(
        {"type": "run_shell", "command": "./gradlew test"},
        state,
    )

    assert should_stop is True
    assert "Required executable is unavailable" in _result_text
    assert "If a command fails because an external tool/wrapper is missing" in _result_text
    assert "do not manually reconstruct vendor wrapper files" in _result_text
    assert "Prefer a small diagnostic such as `gradle --version`" in _result_text
    assert state.pending_loop_stop_info["recovery_visibility"] == {
        "mode": "next_turn",
        "intent_scope": "current_intent",
        "intent_id": "intent-gradle",
        "intent_type": "INVESTIGATE",
        "action_type": "run_shell",
        "target": "./gradlew test",
        "created_turn_id": 12,
    }
