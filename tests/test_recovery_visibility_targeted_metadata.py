from types import SimpleNamespace

from modules.agent.action_dispatcher import ActionDispatcher


class _DummyDispatcher(ActionDispatcher):
    pass


def _dispatcher():
    agent = SimpleNamespace(
        ui=SimpleNamespace(),
        processor=SimpleNamespace(),
        config=SimpleNamespace(),
        log=None,
        history=None,
    )
    return _DummyDispatcher(agent)


def _state():
    return SimpleNamespace(
        current_turn_id=17,
        active_intent=SimpleNamespace(intent_id="intent-1", intent_type="MODIFY"),
    )


def test_create_file_missing_body_recovery_visibility_is_until_same_action_success_current_intent():
    dispatcher = _dispatcher()
    command = {"type": "create_file", "path": "app/build.gradle.kts"}
    result = {
        "status": "failed",
        "error_code": "VALIDATION_ERROR",
        "recoverable": True,
        "output": "create_file requires file body. Either put content as JSON string or use file_content block.",
    }

    visibility = dispatcher._targeted_recovery_visibility_metadata(command, result, _state())

    assert visibility == {
        "mode": "until_same_action_success",
        "intent_scope": "current_intent",
        "intent_id": "intent-1",
        "intent_type": "MODIFY",
        "action_type": "create_file",
        "target": "app/build.gradle.kts",
        "created_turn_id": 17,
    }


def test_search_content_regex_parse_recovery_visibility_is_next_turn_current_intent():
    dispatcher = _dispatcher()
    command = {"type": "search_content", "path": "modules", "pattern": "("}
    result = {
        "status": "failed",
        "error_code": "SEARCH_REGEX_PARSE_ERROR",
        "recoverable": True,
        "output": "regex parse error: missing closing parenthesis",
    }

    visibility = dispatcher._targeted_recovery_visibility_metadata(command, result, _state())

    assert visibility == {
        "mode": "next_turn",
        "intent_scope": "current_intent",
        "intent_id": "intent-1",
        "intent_type": "MODIFY",
        "action_type": "search_content",
        "target": "modules:(",
        "created_turn_id": 17,
    }


def test_read_file_not_found_recovery_visibility_is_next_turn_current_intent():
    dispatcher = _dispatcher()
    command = {"type": "read_file", "path": "missing.py"}
    result = {
        "status": "failed",
        "error_code": "NOT_FOUND",
        "recoverable": True,
        "output": "File not found",
    }

    visibility = dispatcher._targeted_recovery_visibility_metadata(command, result, _state())

    assert visibility == {
        "mode": "next_turn",
        "intent_scope": "current_intent",
        "intent_id": "intent-1",
        "intent_type": "MODIFY",
        "action_type": "read_file",
        "target": "missing.py",
        "created_turn_id": 17,
    }


def test_list_directory_not_found_recovery_visibility_is_next_turn_current_intent():
    dispatcher = _dispatcher()
    command = {"type": "list_directory", "path": "missing_dir"}
    result = {
        "status": "failed",
        "error_code": "NOT_FOUND",
        "recoverable": True,
        "output": "Directory not found",
    }

    visibility = dispatcher._targeted_recovery_visibility_metadata(command, result, _state())

    assert visibility == {
        "mode": "next_turn",
        "intent_scope": "current_intent",
        "intent_id": "intent-1",
        "intent_type": "MODIFY",
        "action_type": "list_directory",
        "target": "missing_dir",
        "created_turn_id": 17,
    }


def test_run_shell_transient_io_recovery_visibility_is_next_turn_current_intent():
    dispatcher = _dispatcher()
    command = {"type": "run_shell", "command": "pytest -q tests"}
    result = {
        "status": "failed",
        "error_code": "TRANSIENT_IO",
        "recoverable": True,
        "output": "transient I/O failure",
    }

    visibility = dispatcher._targeted_recovery_visibility_metadata(command, result, _state())

    assert visibility == {
        "mode": "next_turn",
        "intent_scope": "current_intent",
        "intent_id": "intent-1",
        "intent_type": "MODIFY",
        "action_type": "run_shell",
        "target": "pytest -q tests",
        "created_turn_id": 17,
    }


def test_run_shell_timeout_recovery_visibility_is_next_turn_current_intent():
    dispatcher = _dispatcher()
    command = {"type": "run_shell", "command": "./gradlew test"}
    result = {
        "status": "failed",
        "error_code": "COMMAND_TIMEOUT",
        "recoverable": True,
        "output": "Command timed out",
    }

    visibility = dispatcher._targeted_recovery_visibility_metadata(command, result, _state())

    assert visibility == {
        "mode": "next_turn",
        "intent_scope": "current_intent",
        "intent_id": "intent-1",
        "intent_type": "MODIFY",
        "action_type": "run_shell",
        "target": "./gradlew test",
        "created_turn_id": 17,
    }


def test_action_denied_recovery_visibility_is_next_turn_current_intent():
    dispatcher = _dispatcher()
    command = {"type": "run_shell", "command": "rm -rf build"}
    result = {
        "status": "denied",
        "error_code": "USER_DENIED",
        "recoverable": True,
        "output": "Action denied by user",
    }

    visibility = dispatcher._targeted_recovery_visibility_metadata(command, result, _state())

    assert visibility == {
        "mode": "next_turn",
        "intent_scope": "current_intent",
        "intent_id": "intent-1",
        "intent_type": "MODIFY",
        "action_type": "run_shell",
        "target": "rm -rf build",
        "created_turn_id": 17,
    }


def test_run_shell_missing_executable_recovery_visibility_is_next_turn_current_intent():
    dispatcher = _dispatcher()
    command = {"type": "run_shell", "command": "./gradlew test"}
    result = {
        "status": "failed",
        "error_code": "MISSING_EXECUTABLE",
        "recoverable": True,
        "output": "Required executable is unavailable",
    }

    visibility = dispatcher._targeted_recovery_visibility_metadata(command, result, _state())

    assert visibility == {
        "mode": "next_turn",
        "intent_scope": "current_intent",
        "intent_id": "intent-1",
        "intent_type": "MODIFY",
        "action_type": "run_shell",
        "target": "./gradlew test",
        "created_turn_id": 17,
    }


def test_unmigrated_recovery_visibility_metadata_stays_legacy_none():
    dispatcher = _dispatcher()
    command = {"type": "read_file", "path": "weird.py"}
    result = {
        "status": "failed",
        "error_code": "SOME_UNMIGRATED_ERROR",
        "recoverable": True,
        "output": "Some unmigrated failure",
    }

    assert dispatcher._targeted_recovery_visibility_metadata(command, result, _state()) is None


def test_targeted_recovery_visibility_handles_missing_active_intent_as_any_scope():
    dispatcher = _dispatcher()
    command = {"type": "create_file", "path": "a.txt"}
    result = {
        "status": "failed",
        "error_code": "VALIDATION_ERROR",
        "recoverable": True,
        "output": "create_file requires file body.",
    }
    state = SimpleNamespace(current_turn_id=5, active_intent=None)

    visibility = dispatcher._targeted_recovery_visibility_metadata(command, result, state)

    assert visibility == {
        "mode": "until_same_action_success",
        "intent_scope": "any",
        "intent_id": "",
        "intent_type": "",
        "action_type": "create_file",
        "target": "a.txt",
        "created_turn_id": 5,
    }
