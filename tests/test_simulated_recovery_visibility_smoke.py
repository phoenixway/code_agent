import tempfile
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest

from modules.history import HistoryManager
from modules.agent.action_dispatcher import ActionDispatcher
from modules.agent.orchestration.runtime.dispatch_outcome import DispatchOutcomeHandler


class _DummyChatProvider:
    async def get_streaming_response(self, query, history):
        if False:
            yield ""


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


def _state(intent_id="intent-1", intent_type="MODIFY", current_turn_id=10, successes=None):
    return SimpleNamespace(
        active_intent=SimpleNamespace(intent_id=intent_id, intent_type=intent_type) if intent_id else None,
        current_turn_id=current_turn_id,
        recovery_visibility_successes=list(successes or []),
    )


def _overlay_content(history, state):
    injected = history.build_recovery_instruction_injected_messages(state=state)
    if not injected:
        return ""
    assert len(injected) == 1
    assert injected[0]["role"] == "system"
    return injected[0]["content"]


def _add_recovery(history, message, visibility):
    history.add_message(
        "system",
        message,
        msg_type="recovery_instruction",
        recovery_visibility=visibility,
    )


def test_p3_create_file_missing_body_recovery_is_visible_until_same_action_success():
    dispatcher = _dispatcher()
    command = {"type": "create_file", "path": "app/build.gradle.kts"}
    result = {
        "status": "failed",
        "error_code": "VALIDATION_ERROR",
        "recoverable": True,
        "output": "create_file requires file body. Either put content as JSON string or use file_content block.",
    }
    visibility = dispatcher._targeted_recovery_visibility_metadata(command, result, _state(current_turn_id=17))

    assert visibility == {
        "mode": "until_same_action_success",
        "intent_scope": "current_intent",
        "intent_id": "intent-1",
        "intent_type": "MODIFY",
        "action_type": "create_file",
        "target": "app/build.gradle.kts",
        "created_turn_id": 17,
    }

    with tempfile.TemporaryDirectory() as tmpdir:
        history = HistoryManager(_DummyChatProvider(), storage_dir=tmpdir)
        _add_recovery(
            history,
            "[RECOVERY_SCOPE]\nThis recovery applies only to the failed create_file call.\n\n[WHAT_FAILED]\ncreate_file requires file body.\n\n[NEXT_STEP_RULE]\nRetry create_file with real file content.\n\n[EXIT_CONDITION]\nHide this instruction after the same create_file target succeeds.",
            visibility,
        )

        visible = _overlay_content(history, _state(current_turn_id=18))
        assert "## CURRENT RECOVERY INSTRUCTIONS" in visible
        assert "create_file requires file body" in visible

        hidden = _overlay_content(
            history,
            _state(
                current_turn_id=18,
                successes=[
                    {
                        "turn_id": 18,
                        "action_type": "create_file",
                        "target": "app/build.gradle.kts",
                    }
                ],
            ),
        )
        assert hidden == ""


def test_p3_search_content_regex_recovery_is_visible_next_turn_then_hidden():
    dispatcher = _dispatcher()
    command = {"type": "search_content", "path": "modules", "pattern": "("}
    result = {
        "status": "failed",
        "error_code": "SEARCH_REGEX_PARSE_ERROR",
        "recoverable": True,
        "output": "regex parse error: missing closing parenthesis",
    }
    visibility = dispatcher._targeted_recovery_visibility_metadata(command, result, _state(current_turn_id=20))

    assert visibility["mode"] == "next_turn"
    assert visibility["intent_scope"] == "current_intent"
    assert visibility["action_type"] == "search_content"
    assert visibility["created_turn_id"] == 20

    with tempfile.TemporaryDirectory() as tmpdir:
        history = HistoryManager(_DummyChatProvider(), storage_dir=tmpdir)
        _add_recovery(
            history,
            "[RECOVERY_SCOPE]\nTemporary regex parse recovery.\n\n[WHAT_FAILED]\nsearch_content pattern is invalid regex.\n\n[NEXT_STEP_RULE]\nRetry search_content with literal=true or escape the pattern.\n\n[EXIT_CONDITION]\nVisible only for the next turn.",
            visibility,
        )

        assert "Retry search_content with literal=true" in _overlay_content(history, _state(current_turn_id=20))
        assert "Retry search_content with literal=true" in _overlay_content(history, _state(current_turn_id=21))
        assert _overlay_content(history, _state(current_turn_id=22)) == ""


def test_p3_run_shell_missing_executable_recovery_is_scoped_and_next_turn_visible():
    dispatcher = _dispatcher()
    command = {"type": "run_shell", "command": "./gradlew test"}
    result = {
        "status": "failed",
        "error_code": "MISSING_EXECUTABLE",
        "recoverable": True,
        "output": "Required executable is unavailable",
    }
    visibility = dispatcher._targeted_recovery_visibility_metadata(command, result, _state(current_turn_id=30))

    assert visibility == {
        "mode": "next_turn",
        "intent_scope": "current_intent",
        "intent_id": "intent-1",
        "intent_type": "MODIFY",
        "action_type": "run_shell",
        "target": "./gradlew test",
        "created_turn_id": 30,
    }

    with tempfile.TemporaryDirectory() as tmpdir:
        history = HistoryManager(_DummyChatProvider(), storage_dir=tmpdir)
        _add_recovery(
            history,
            "[RECOVERY_SCOPE]\nTemporary shell recovery for the current intent.\n\n[WHAT_FAILED]\nThe required executable is unavailable.\n\n[NEXT_STEP_RULE]\nCheck whether a system Gradle executable is available or report manual setup requirement. Do not reconstruct vendor wrappers manually.\n\n[EXIT_CONDITION]\nVisible only for the next turn.",
            visibility,
        )

        overlay = _overlay_content(history, _state(current_turn_id=31))
        assert "[RECOVERY_SCOPE]" in overlay
        assert "[WHAT_FAILED]" in overlay
        assert "[NEXT_STEP_RULE]" in overlay
        assert "[EXIT_CONDITION]" in overlay
        assert "Return only a corrected compact recovery step" not in overlay
        assert "Return EXACTLY ONE" not in overlay

        assert _overlay_content(history, _state(current_turn_id=32)) == ""


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


class _OutcomeState:
    def __init__(self, stop_info):
        self.pending_loop_stop_info = stop_info
        self.terminal_plaintext_completion_pending = False
        self.terminal_plaintext_completion_text = ""
        self.orchestration_trace_sequence = 0
        self.orchestration_trace = []


@pytest.mark.asyncio
async def test_p3_action_denied_records_scoped_recovery_instruction_without_retry_pressure():
    visibility = {
        "mode": "next_turn",
        "intent_scope": "current_intent",
        "intent_id": "intent-1",
        "intent_type": "MODIFY",
        "action_type": "edit_file",
        "target": "modules/example.py",
        "created_turn_id": 40,
    }
    recovery_message = (
        "[RECOVERY_SCOPE]\n"
        "The user denied this action for the current intent.\n\n"
        "[WHAT_FAILED]\n"
        "The proposed edit_file action was denied by the user.\n\n"
        "[NEXT_STEP_RULE]\n"
        "Do not pressure-retry the denied action. Choose a safer alternative only if needed.\n\n"
        "[EXIT_CONDITION]\n"
        "Visible only for the next turn."
    )
    stop_info = {
        "reason": "action_denied_by_user",
        "recoverable": True,
        "message": recovery_message,
        "recovery_visibility": visibility,
    }
    state = _OutcomeState(stop_info)
    history = MagicMock()
    agent = SimpleNamespace(state=state, history=history, ui=SimpleNamespace(), log=None)
    recovery = _Recovery()
    handler = DispatchOutcomeHandler(agent, _Parser(), recovery)
    ctx = SimpleNamespace(current_query="fix", state_machine=None, active_loop=True)

    decision = await handler.handle(
        ctx,
        processed_segs=[],
        sys_results=["SYSTEM RESULT for `edit_file`: denied"],
        should_stop=True,
    )

    assert decision.handled is True
    history.add_message.assert_any_call("system", "SYSTEM RESULT for `edit_file`: denied")
    history.add_message.assert_any_call(
        "system",
        recovery_message,
        msg_type="recovery_instruction",
        recovery_visibility=visibility,
    )
    recovery.handle_dispatch_stop.assert_awaited_once_with(stop_info, None)
    assert "Return only a corrected compact recovery step" not in recovery_message
    assert "Return EXACTLY ONE" not in recovery_message


def test_p35_current_intent_recovery_hides_after_intent_change_but_raw_history_remains():
    visibility = {
        "mode": "next_turn",
        "intent_scope": "current_intent",
        "intent_id": "intent-1",
        "intent_type": "MODIFY",
        "action_type": "search_content",
        "target": "modules:(",
        "created_turn_id": 50,
    }

    with tempfile.TemporaryDirectory() as tmpdir:
        history = HistoryManager(_DummyChatProvider(), storage_dir=tmpdir)
        _add_recovery(history, "current-intent recovery text", visibility)

        assert "current-intent recovery text" in _overlay_content(
            history,
            _state(intent_id="intent-1", current_turn_id=51),
        )
        assert _overlay_content(
            history,
            _state(intent_id="intent-2", current_turn_id=51),
        ) == ""

        raw_recovery_messages = [
            msg for msg in history.messages
            if msg.get("type") == "recovery_instruction"
        ]
        assert len(raw_recovery_messages) == 1
        assert raw_recovery_messages[0]["content"] == "current-intent recovery text"
        assert raw_recovery_messages[0]["recovery_visibility"] == visibility


def test_p35_legacy_recovery_without_visibility_metadata_remains_visible_across_intents():
    with tempfile.TemporaryDirectory() as tmpdir:
        history = HistoryManager(_DummyChatProvider(), storage_dir=tmpdir)
        history.add_message(
            "system",
            "legacy recovery text",
            msg_type="recovery_instruction",
        )

        under_original_intent = _overlay_content(
            history,
            _state(intent_id="intent-1", current_turn_id=10),
        )
        under_changed_intent = _overlay_content(
            history,
            _state(intent_id="intent-2", current_turn_id=10),
        )

        assert "legacy recovery text" in under_original_intent
        assert "legacy recovery text" in under_changed_intent
        assert history.messages[0].get("recovery_visibility") is None


def test_p35_mixed_recovery_overlay_filters_only_visible_instructions():
    with tempfile.TemporaryDirectory() as tmpdir:
        history = HistoryManager(_DummyChatProvider(), storage_dir=tmpdir)

        _add_recovery(
            history,
            "A visible current-intent recovery",
            {
                "mode": "next_turn",
                "intent_scope": "current_intent",
                "intent_id": "intent-1",
                "intent_type": "MODIFY",
                "action_type": "search_content",
                "target": "modules:(",
                "created_turn_id": 70,
            },
        )
        _add_recovery(
            history,
            "B hidden other-intent recovery",
            {
                "mode": "next_turn",
                "intent_scope": "current_intent",
                "intent_id": "intent-2",
                "intent_type": "MODIFY",
                "action_type": "search_content",
                "target": "modules:(",
                "created_turn_id": 70,
            },
        )
        _add_recovery(
            history,
            "C expired next-turn recovery",
            {
                "mode": "next_turn",
                "intent_scope": "current_intent",
                "intent_id": "intent-1",
                "intent_type": "MODIFY",
                "action_type": "run_shell",
                "target": "pytest -q tests",
                "created_turn_id": 68,
            },
        )
        history.add_message(
            "system",
            "D legacy recovery without metadata",
            msg_type="recovery_instruction",
        )

        overlay = _overlay_content(
            history,
            _state(intent_id="intent-1", current_turn_id=70),
        )

        assert "## CURRENT RECOVERY INSTRUCTIONS" in overlay
        assert "A visible current-intent recovery" in overlay
        assert "D legacy recovery without metadata" in overlay
        assert "B hidden other-intent recovery" not in overlay
        assert "C expired next-turn recovery" not in overlay
        assert overlay.count("### Recovery instruction") == 2
        assert "### Recovery instruction 1" in overlay
        assert "### Recovery instruction 2" in overlay
        assert "### Recovery instruction 3" not in overlay


def test_p35_run_shell_transient_io_and_command_timeout_use_next_turn_current_intent_visibility():
    dispatcher = _dispatcher()

    cases = [
        (
            {"type": "run_shell", "command": "pytest -q tests"},
            {
                "status": "failed",
                "error_code": "TRANSIENT_IO",
                "recoverable": True,
                "output": "transient I/O failure",
            },
            "pytest -q tests",
        ),
        (
            {"type": "run_shell", "command": "./gradlew test"},
            {
                "status": "failed",
                "error_code": "COMMAND_TIMEOUT",
                "recoverable": True,
                "output": "Command timed out",
            },
            "./gradlew test",
        ),
    ]

    for command, result, target in cases:
        visibility = dispatcher._targeted_recovery_visibility_metadata(
            command,
            result,
            _state(current_turn_id=80),
        )

        assert visibility == {
            "mode": "next_turn",
            "intent_scope": "current_intent",
            "intent_id": "intent-1",
            "intent_type": "MODIFY",
            "action_type": "run_shell",
            "target": target,
            "created_turn_id": 80,
        }


def test_p35_denied_action_recovery_lifecycle_is_next_turn_and_current_intent_scoped():
    visibility = {
        "mode": "next_turn",
        "intent_scope": "current_intent",
        "intent_id": "intent-denied",
        "intent_type": "MODIFY",
        "action_type": "run_shell",
        "target": "rm -rf build",
        "created_turn_id": 90,
    }

    with tempfile.TemporaryDirectory() as tmpdir:
        history = HistoryManager(_DummyChatProvider(), storage_dir=tmpdir)
        _add_recovery(history, "denied action recovery text", visibility)

        assert "denied action recovery text" in _overlay_content(
            history,
            _state(intent_id="intent-denied", current_turn_id=91),
        )
        assert _overlay_content(
            history,
            _state(intent_id="intent-denied", current_turn_id=92),
        ) == ""
        assert _overlay_content(
            history,
            _state(intent_id="intent-other", current_turn_id=91),
        ) == ""
