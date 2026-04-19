"""Resolve recovery stop_info into centralized intent message registry keys."""

from __future__ import annotations


REASON_TO_MESSAGE_KEY = {
    "intent_blocked_action_signature": "blocked_action_keep_current_intent",
    "unnecessary_intent_reactivation_or_replace": "unnecessary_intent_reactivation_or_replace",
    "suspect_intent_relabel_repeat": "suspect_intent_relabel_repeat",
    "suspect_intent_goal_drift": "suspect_intent_goal_drift",
    "retry_goal_change_forbidden": "retry_goal_change_forbidden",

    "malformed_read_file_payload": "malformed_read_file_payload",
    "malformed_read_file_skeleton_payload": "malformed_read_file_skeleton_payload",
    "malformed_read_chunk_payload": "malformed_read_chunk_payload",

    "intent_step_limit_soft_exceeded": "intent_step_limit_soft_exceeded",
    "intent_step_limit_exceeded": "intent_step_limit_exceeded",
    "intent_step_limit_exceeded_repeated": "intent_step_limit_exceeded_repeated",

    "planned_turn_working_material_too_large": "planned_turn_working_material_too_large",
    "planned_full_read_too_large": "planned_full_read_too_large",
    "turn_working_material_too_large": "turn_working_material_too_large",
}

ERROR_CODE_TO_MESSAGE_KEY = {
    "INTENT_BLOCKED_ACTION_SIGNATURE": "blocked_action_keep_current_intent",
    "UNNECESSARY_INTENT_REACTIVATION_OR_REPLACE": "unnecessary_intent_reactivation_or_replace",
    "SUSPECT_INTENT_RELABEL_REPEAT": "suspect_intent_relabel_repeat",
    "SUSPECT_INTENT_GOAL_DRIFT": "suspect_intent_goal_drift",
    "RETRY_GOAL_CHANGE_FORBIDDEN": "retry_goal_change_forbidden",

    "MALFORMED_READ_FILE_PAYLOAD": "malformed_read_file_payload",
    "MALFORMED_READ_FILE_SKELETON_PAYLOAD": "malformed_read_file_skeleton_payload",
    "MALFORMED_READ_CHUNK_PAYLOAD": "malformed_read_chunk_payload",

    "INTENT_STEP_LIMIT_SOFT_EXCEEDED": "intent_step_limit_soft_exceeded",
    "INTENT_STEP_LIMIT_EXCEEDED": "intent_step_limit_exceeded",
    "INTENT_STEP_LIMIT_EXCEEDED_REPEATED": "intent_step_limit_exceeded_repeated",

    "PLANNED_TURN_WORKING_MATERIAL_TOO_LARGE": "planned_turn_working_material_too_large",
    "PLANNED_FULL_READ_TOO_LARGE": "planned_full_read_too_large",
    "TURN_WORKING_MATERIAL_TOO_LARGE": "turn_working_material_too_large",
}


def resolve_intent_message_key(stop_info: dict | None) -> str:
    stop_info = stop_info or {}
    explicit = str(stop_info.get("message_key") or "").strip()
    if explicit:
        return explicit

    reason = str(stop_info.get("reason") or "").strip()
    if reason and reason in REASON_TO_MESSAGE_KEY:
        return REASON_TO_MESSAGE_KEY[reason]

    error_code = str(stop_info.get("error_code") or "").strip()
    if error_code and error_code in ERROR_CODE_TO_MESSAGE_KEY:
        return ERROR_CODE_TO_MESSAGE_KEY[error_code]

    return ""
