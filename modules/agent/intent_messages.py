"""Central registry for intent/policy-related recovery messages."""

from __future__ import annotations


INTENT_MESSAGES: dict[str, dict] = {
    "blocked_action_keep_current_intent": {
        "type": "action_block",
        "template": (
            "A specific action is blocked, but the current intent contract remains valid. "
            "Use the current intent contract's allowed actions for one corrective next step, or answer from current evidence if enough is already known."
        ),
    },
    "unnecessary_intent_reactivation_or_replace": {
        "type": "policy_reject",
        "template": (
            "The active intent contract is already shown in the system prompt and remains active by default. "
            "It will stay active until runtime explicitly completes, replaces, rejects, or closes it for a valid listed reason. "
            "There is no valid reason to reactivate or replace this same active intent contract now. "
            "Do not emit another activate/replace for the same contract. "
            "Continue with the next valid action under the current contract, or answer from current evidence if enough is already known."
        ),
    },
    "suspect_intent_relabel_repeat": {
        "type": "policy_reject",
        "template": (
            "The current intent contract is still valid. "
            "Do not treat intent as a new local intention or next micro-step. "
            "Intent here means the formal runtime contract for the current user-facing goal and allowed actions. "
            "Do not relabel or replace it unless there is a valid reason from the system prompt list. "
            "Do not restart the task from the beginning. "
            "Continue from already gathered evidence under the same intent contract."
        ),
    },
    "suspect_intent_goal_drift": {
        "type": "policy_reject",
        "template": (
            "The current intent contract is still valid. "
            "You changed the current goal in a suspicious way and may have lost part of the user's real question. "
            "Keep the original goal unless the user explicitly approves the changed goal. "
            "Continue under the same intent contract from already gathered evidence."
        ),
    },
    "retry_goal_change_forbidden": {
        "type": "policy_reject",
        "template": (
            "Retry must keep the same current goal and the same intent contract scope. "
            "Do not rewrite the goal during retry. "
            "Continue under the same intent contract."
        ),
    },
    "allow_activate": {
        "type": "allow",
        "template": "Intent contract activation is allowed.",
    },
    "allow_replace": {
        "type": "allow",
        "template": "Intent contract replacement is allowed.",
    },
    "allow_retry": {
        "type": "allow",
        "template": "Intent contract retry is allowed.",
    },
    "allow_complete": {
        "type": "allow",
        "template": "Intent contract completion is allowed.",
    },

    # Current-intent recovery registry entries
    "keep_current_intent_soft_limit": {
        "type": "current_intent_recovery",
        "template": (
            "Continue under the current intent contract. "
            "The current intent contract reached its nominal step limit, but it still remains valid. "
            "Do not relabel or restart the task. "
            "Prefer one final allowed action or conclude with current evidence."
        ),
    },
    "keep_current_intent_after_user_more_steps": {
        "type": "current_intent_recovery",
        "template": (
            "Continue under the current intent contract. "
            "The user explicitly approved a small additional step budget for this same intent contract. "
            "Do not relabel or restart the task."
        ),
    },
    "keep_current_intent_conflicting_phase_actions": {
        "type": "current_intent_recovery",
        "template": (
            "Continue under the current intent contract. "
            "The current intent contract remains valid, but a conflicting legacy recovery tried to push a different action family. "
            "Keep the current intent contract action family instead."
        ),
    },

    # Recovery / orchestration registry entries
    "malformed_read_file_payload": {
        "type": "malformed_action",
        "template": (
            "read_file requires a valid top-level payload with a path field."
        ),
    },
    "malformed_read_file_skeleton_payload": {
        "type": "malformed_action",
        "template": (
            "read_file_skeleton requires a valid top-level payload with a path field."
        ),
    },
    "malformed_read_chunk_payload": {
        "type": "malformed_action",
        "template": (
            "read_chunk requires a valid top-level payload. "
            "Preferred format uses line ranges: path, start_line, end_line. "
            "Byte offsets are optional only when explicitly needed."
        ),
    },
    "intent_step_limit_soft_exceeded": {
        "type": "limit",
        "template": (
            "The current intent contract reached its nominal step limit. "
            "Priority now is to finish quickly from current evidence, not to reopen exploration. "
            "Continue only from the strongest valid state already reached under this same intent. "
            "If the goal is already answerable, complete the intent and answer now."
        ),
    },
    "intent_step_limit_exceeded": {
        "type": "limit",
        "template": (
            "The current intent contract exceeded its hard step limit. "
            "Priority now is clean completion from current evidence, not more searching by default. "
            "Either answer now from the strongest evidence already gathered, or continue only from the last valid point if a concrete missing detail still blocks completion."
        ),
    },
    "intent_step_limit_exceeded_repeated": {
        "type": "limit",
        "template": (
            "The current intent contract exceeded its hard step limit repeatedly for the same lineage. "
            "Do not restart exploration. The default priority is to stop and finish from current evidence unless the user explicitly approves a small additional budget for this same work."
        ),
    },
    "planned_turn_working_material_too_large": {
        "type": "sizing",
        "template": (
            "The planned read/search output for this turn is too large. "
            "Do not resend the same heavy batch. "
            "Use a materially smaller step: one strongest candidate file, read_chunk, read_file_skeleton, narrower search, or rg/fd."
        ),
    },
    "planned_full_read_too_large": {
        "type": "sizing",
        "template": (
            "The planned full read_file action is too large for this path. "
            "Do not repeat the same full read_file action. "
            "Next step must be one of: read_chunk, read_file_skeleton, search_content, search_files, or run_shell with rg/fd."
        ),
    },
    "turn_working_material_too_large": {
        "type": "sizing",
        "template": (
            "Current turn working material is too large to preserve safely in context. "
            "Switch to chunked reading, read_file_skeleton, narrower search, or smaller shell output."
        ),
    },
}


def get_intent_message(message_key: str, default: str = "") -> str:
    if not message_key:
        return default
    data = INTENT_MESSAGES.get(str(message_key).strip())
    if not isinstance(data, dict):
        return default
    return str(data.get("template") or default)


def render_intent_message(message_key: str, *, next_hint: str = "", default: str = "") -> str:
    base = get_intent_message(message_key, default=default)
    if next_hint:
        return base + next_hint
    return base
