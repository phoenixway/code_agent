from types import SimpleNamespace

import pytest

from modules.agent.orchestration.runtime.recovery_visibility import recovery_message_is_visible


def _state(intent_id="intent-1", intent_type="MODIFY", current_turn_id=10, successes=None):
    return SimpleNamespace(
        active_intent=SimpleNamespace(intent_id=intent_id, intent_type=intent_type) if intent_id else None,
        current_turn_id=current_turn_id,
        recovery_visibility_successes=list(successes or []),
    )


def _message(visibility=None):
    msg = {
        "role": "system",
        "type": "recovery_instruction",
        "content": "SYSTEM: temporary recovery instruction",
    }
    if visibility is not None:
        msg["recovery_visibility"] = visibility
    return msg


def test_message_without_visibility_metadata_is_legacy_visible():
    assert recovery_message_is_visible(_message(), state=_state()) is True


def test_legacy_mode_is_visible_even_with_metadata():
    msg = _message({"mode": "legacy", "intent_scope": "current_intent", "intent_id": "old-intent"})

    assert recovery_message_is_visible(msg, state=_state(intent_id="new-intent")) is True


def test_current_intent_scope_is_visible_when_active_intent_matches():
    msg = _message(
        {
            "mode": "next_turn",
            "intent_scope": "current_intent",
            "intent_id": "intent-1",
            "intent_type": "MODIFY",
            "created_turn_id": 10,
        }
    )

    assert recovery_message_is_visible(msg, state=_state(intent_id="intent-1", current_turn_id=10)) is True


def test_current_intent_scope_hides_when_active_intent_changed():
    msg = _message(
        {
            "mode": "next_turn",
            "intent_scope": "current_intent",
            "intent_id": "intent-1",
            "intent_type": "MODIFY",
            "created_turn_id": 10,
        }
    )

    assert recovery_message_is_visible(msg, state=_state(intent_id="intent-2", current_turn_id=10)) is False


def test_current_intent_scope_hides_when_no_active_intent():
    msg = _message(
        {
            "mode": "next_turn",
            "intent_scope": "current_intent",
            "intent_id": "intent-1",
            "intent_type": "MODIFY",
            "created_turn_id": 10,
        }
    )

    assert recovery_message_is_visible(msg, state=_state(intent_id=None, current_turn_id=10)) is False


def test_next_turn_mode_is_visible_on_creation_turn_and_next_turn_only():
    msg = _message(
        {
            "mode": "next_turn",
            "intent_scope": "current_intent",
            "intent_id": "intent-1",
            "created_turn_id": 10,
        }
    )

    assert recovery_message_is_visible(msg, state=_state(current_turn_id=10)) is True
    assert recovery_message_is_visible(msg, state=_state(current_turn_id=11)) is True
    assert recovery_message_is_visible(msg, state=_state(current_turn_id=12)) is False


def test_until_any_success_hides_after_any_recorded_success_after_creation():
    msg = _message(
        {
            "mode": "until_any_success",
            "intent_scope": "current_intent",
            "intent_id": "intent-1",
            "created_turn_id": 10,
        }
    )

    assert recovery_message_is_visible(msg, state=_state(current_turn_id=11, successes=[])) is True
    assert recovery_message_is_visible(
        msg,
        state=_state(
            current_turn_id=11,
            successes=[{"turn_id": 11, "action_type": "read_file", "target": "a.py"}],
        ),
    ) is False


def test_until_same_action_success_hides_only_after_matching_action_and_target_success():
    msg = _message(
        {
            "mode": "until_same_action_success",
            "intent_scope": "current_intent",
            "intent_id": "intent-1",
            "action_type": "create_file",
            "target": "app/build.gradle.kts",
            "created_turn_id": 10,
        }
    )

    assert recovery_message_is_visible(
        msg,
        state=_state(
            current_turn_id=11,
            successes=[{"turn_id": 11, "action_type": "read_file", "target": "app/build.gradle.kts"}],
        ),
    ) is True
    assert recovery_message_is_visible(
        msg,
        state=_state(
            current_turn_id=11,
            successes=[{"turn_id": 11, "action_type": "create_file", "target": "other.txt"}],
        ),
    ) is True
    assert recovery_message_is_visible(
        msg,
        state=_state(
            current_turn_id=11,
            successes=[{"turn_id": 11, "action_type": "create_file", "target": "app/build.gradle.kts"}],
        ),
    ) is False


def test_until_target_success_hides_after_matching_target_success_from_any_action():
    msg = _message(
        {
            "mode": "until_target_success",
            "intent_scope": "current_intent",
            "intent_id": "intent-1",
            "target": "modules/history.py",
            "created_turn_id": 10,
        }
    )

    assert recovery_message_is_visible(
        msg,
        state=_state(
            current_turn_id=11,
            successes=[{"turn_id": 11, "action_type": "read_file", "target": "other.py"}],
        ),
    ) is True
    assert recovery_message_is_visible(
        msg,
        state=_state(
            current_turn_id=11,
            successes=[{"turn_id": 11, "action_type": "search_content", "target": "modules/history.py"}],
        ),
    ) is False


def test_unknown_mode_fails_open_as_legacy_visible():
    msg = _message({"mode": "future_mode", "intent_scope": "current_intent", "intent_id": "intent-1"})

    assert recovery_message_is_visible(msg, state=_state()) is True
