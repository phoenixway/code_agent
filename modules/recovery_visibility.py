"""Visibility policy for temporary recovery instructions.

This module is intentionally pure and passive. It decides whether an already
stored recovery instruction should be shown in the effective model-facing
context. It must not delete raw history, mutate runtime state, or change
recovery routing.
"""

from __future__ import annotations

from typing import Any


LEGACY_MODE = "legacy"
NEXT_TURN_MODE = "next_turn"
UNTIL_ANY_SUCCESS_MODE = "until_any_success"
UNTIL_SAME_ACTION_SUCCESS_MODE = "until_same_action_success"
UNTIL_TARGET_SUCCESS_MODE = "until_target_success"

ANY_INTENT_SCOPE = "any"
CURRENT_INTENT_SCOPE = "current_intent"

_KNOWN_MODES = {
    LEGACY_MODE,
    NEXT_TURN_MODE,
    UNTIL_ANY_SUCCESS_MODE,
    UNTIL_SAME_ACTION_SUCCESS_MODE,
    UNTIL_TARGET_SUCCESS_MODE,
}


def recovery_message_is_visible(message: dict[str, Any] | None, *, state: Any = None) -> bool:
    """Return whether a recovery-like message should be model-facing.

    Default behavior is intentionally fail-open/legacy-compatible:
    - messages without visibility metadata remain visible;
    - `mode=legacy` remains visible;
    - unknown future modes remain visible rather than silently hiding recovery.
    """

    if not isinstance(message, dict):
        return True

    visibility = message.get("recovery_visibility")
    if not isinstance(visibility, dict):
        return True

    mode = _clean(visibility.get("mode") or LEGACY_MODE)
    if not mode or mode == LEGACY_MODE:
        return True
    if mode not in _KNOWN_MODES:
        return True

    if not _intent_scope_matches(visibility, state=state):
        return False

    if mode == NEXT_TURN_MODE:
        return _is_next_turn_visible(visibility, state=state)
    if mode == UNTIL_ANY_SUCCESS_MODE:
        return not _has_any_success_after_creation(visibility, state=state)
    if mode == UNTIL_SAME_ACTION_SUCCESS_MODE:
        return not _has_same_action_success_after_creation(visibility, state=state)
    if mode == UNTIL_TARGET_SUCCESS_MODE:
        return not _has_target_success_after_creation(visibility, state=state)

    return True


def _intent_scope_matches(visibility: dict[str, Any], *, state: Any = None) -> bool:
    scope = _clean(visibility.get("intent_scope") or ANY_INTENT_SCOPE)
    if scope != CURRENT_INTENT_SCOPE:
        return True

    expected_intent_id = _clean(visibility.get("intent_id"))
    if not expected_intent_id:
        return True

    active_intent = getattr(state, "active_intent", None) if state is not None else None
    current_intent_id = _clean(getattr(active_intent, "intent_id", None))
    return bool(current_intent_id and current_intent_id == expected_intent_id)


def _is_next_turn_visible(visibility: dict[str, Any], *, state: Any = None) -> bool:
    created_turn = _int_or_none(visibility.get("created_turn_id"))
    current_turn = _int_or_none(getattr(state, "current_turn_id", None) if state is not None else None)
    if created_turn is None or current_turn is None:
        return True
    return current_turn <= created_turn + 1


def _has_any_success_after_creation(visibility: dict[str, Any], *, state: Any = None) -> bool:
    created_turn = _int_or_none(visibility.get("created_turn_id"))
    return any(
        _success_is_after_creation(success, created_turn=created_turn)
        for success in _successes(state)
    )


def _has_same_action_success_after_creation(visibility: dict[str, Any], *, state: Any = None) -> bool:
    expected_action = _clean(visibility.get("action_type"))
    expected_target = _clean(visibility.get("target"))
    created_turn = _int_or_none(visibility.get("created_turn_id"))
    if not expected_action and not expected_target:
        return False

    for success in _successes(state):
        if not _success_is_after_creation(success, created_turn=created_turn):
            continue
        if expected_action and _clean(success.get("action_type")) != expected_action:
            continue
        if expected_target and _clean(success.get("target")) != expected_target:
            continue
        return True
    return False


def _has_target_success_after_creation(visibility: dict[str, Any], *, state: Any = None) -> bool:
    expected_target = _clean(visibility.get("target"))
    created_turn = _int_or_none(visibility.get("created_turn_id"))
    if not expected_target:
        return False

    for success in _successes(state):
        if not _success_is_after_creation(success, created_turn=created_turn):
            continue
        if _clean(success.get("target")) == expected_target:
            return True
    return False


def _successes(state: Any = None) -> list[dict[str, Any]]:
    values = getattr(state, "recovery_visibility_successes", None) if state is not None else None
    if not isinstance(values, list):
        return []
    return [item for item in values if isinstance(item, dict)]


def _success_is_after_creation(success: dict[str, Any], *, created_turn: int | None) -> bool:
    if created_turn is None:
        return True
    success_turn = _int_or_none(success.get("turn_id"))
    if success_turn is None:
        return True
    return success_turn >= created_turn


def _clean(value: Any) -> str:
    return str(value or "").strip()


def _int_or_none(value: Any) -> int | None:
    try:
        if value is None or value == "":
            return None
        return int(value)
    except Exception:
        return None
