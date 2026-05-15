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


def test_unrelated_recovery_visibility_metadata_stays_legacy_none():
    dispatcher = _dispatcher()
    command = {"type": "read_file", "path": "missing.py"}
    result = {
        "status": "failed",
        "error_code": "NOT_FOUND",
        "recoverable": True,
        "output": "File not found",
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
