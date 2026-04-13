"""Runtime contract for model-declared intents.

This module intentionally stays simple:
- model may declare a formal intent contract
- runtime validates allowed_actions and numeric limits
- runtime tracks steps/retries and exposes light pre/post checks
"""

from __future__ import annotations

import re

from dataclasses import dataclass

KNOWN_TOOL_ACTIONS = {
    "read_file",
    "read_file_skeleton",
    "search_content",
    "search_files",
    "list_directory",
    "find_files",
    "git_diff",
    "run_shell",
    "create_file",
    "write_file",
    "edit_file",
    "replace",
    "delete_file",
    "git_add",
    "git_commit",
    "git_checkout",
}


@dataclass
class IntentContract:
    intent_id: str
    intent_type: str
    goal: str
    allowed_actions: list[str]
    safe_steps_limit: int
    retry_limit: int
    mode: str = "activate"
    step_count: int = 0
    retry_count: int = 0


class IntentRuntime:
    SUPPORTED_TYPES = {"INVESTIGATE", "VERIFY", "MODIFY", "CLEANUP", "SUMMARIZE"}
    SUPPORTED_MODES = {"activate", "retry", "replace"}

    def __init__(self, config):
        self.config = config
        self.active_intent: IntentContract | None = None
        self.intent_required_until_activated = False
        self.intent_required_reason = ""
        self.last_apply_warning = ""

    def reset(self):
        self.active_intent = None
        self.intent_required_until_activated = False
        self.intent_required_reason = ""

    def require_intent(self, reason: str):
        self.intent_required_until_activated = True
        self.intent_required_reason = str(reason or "").strip()

    def clear_requirement(self):
        self.intent_required_until_activated = False
        self.intent_required_reason = ""

    def _normalize_goal(self, goal: str) -> str:
        goal = str(goal or "").lower().strip()
        goal = re.sub(r"[^a-zа-яіїє0-9]+", " ", goal)
        return re.sub(r"\s+", " ", goal).strip()

    def _goal_similarity(self, a: str, b: str) -> float:
        na = set(self._normalize_goal(a).split())
        nb = set(self._normalize_goal(b).split())
        if not na or not nb:
            return 0.0
        return len(na & nb) / max(1, len(na | nb))

    def _reuse_retry_on_same_subtask(self, contract: IntentContract) -> bool:
        if self.active_intent is None:
            return False
        if contract.intent_id == self.active_intent.intent_id:
            return True
        sim = self._goal_similarity(contract.goal, self.active_intent.goal)
        threshold = float(getattr(self.config, "INTENT_RETRY_GOAL_SIMILARITY_THRESHOLD", 0.45))
        return sim >= threshold

    def validate_payload(self, payload: dict) -> tuple[IntentContract | None, str | None]:
        if not isinstance(payload, dict):
            return None, "intent_payload_must_be_object"
        intent_id = str(payload.get("intent_id") or "").strip()
        intent_type = str(payload.get("intent_type") or "").strip().upper()
        goal = str(payload.get("goal") or "").strip()
        mode = str(payload.get("mode") or "activate").strip().lower()
        if not intent_id:
            return None, "intent_id_required"
        if intent_type not in self.SUPPORTED_TYPES:
            return None, "unsupported_intent_type"
        if not goal:
            return None, "intent_goal_required"
        if mode not in self.SUPPORTED_MODES:
            return None, "unsupported_intent_mode"

        raw_allowed = payload.get("allowed_actions")
        if not isinstance(raw_allowed, list) or not raw_allowed:
            return None, "intent_allowed_actions_required"
        allowed_actions = []
        for item in raw_allowed:
            action = str(item or "").strip()
            if action in KNOWN_TOOL_ACTIONS and action not in allowed_actions:
                allowed_actions.append(action)
        if not allowed_actions:
            return None, "intent_allowed_actions_empty"

        try:
            safe_steps_limit = int(payload.get("safe_steps_limit", getattr(self.config, "INTENT_DEFAULT_SAFE_STEPS", 4)))
            retry_limit = int(payload.get("retry_limit", getattr(self.config, "INTENT_DEFAULT_RETRY_LIMIT", 2)))
        except Exception:
            return None, "intent_limits_invalid"

        safe_steps_limit = max(1, min(safe_steps_limit, int(getattr(self.config, "INTENT_MAX_SAFE_STEPS", 8))))
        retry_limit = max(1, min(retry_limit, int(getattr(self.config, "INTENT_MAX_RETRY_LIMIT", 4))))

        return IntentContract(
            intent_id=intent_id,
            intent_type=intent_type,
            goal=goal[:240],
            allowed_actions=allowed_actions,
            safe_steps_limit=safe_steps_limit,
            retry_limit=retry_limit,
            mode=mode,
        ), None

    def apply_payload(self, payload: dict) -> tuple[bool, str]:
        contract, error = self.validate_payload(payload)
        if error:
            return False, error

        self.last_apply_warning = ""

        if contract.mode == "retry":
            if self.active_intent is None:
                return False, "intent_retry_without_active_intent"

            if not self._reuse_retry_on_same_subtask(contract):
                # Pragmatic degradation: convert retry to replace instead of failing
                # on cosmetic id mismatch. Keep this visible in logs.
                self.last_apply_warning = "intent_retry_degraded_to_replace"
                contract.mode = "replace"
            else:
                self.active_intent.retry_count += 1
                self.active_intent.intent_type = contract.intent_type
                self.active_intent.goal = contract.goal
                self.active_intent.allowed_actions = contract.allowed_actions
                self.active_intent.safe_steps_limit = contract.safe_steps_limit
                self.active_intent.retry_limit = contract.retry_limit
                self.active_intent.step_count = 0
                self.clear_requirement()
                if self.active_intent.retry_count > self.active_intent.retry_limit:
                    return False, "intent_retry_limit_exceeded"
                return True, "intent_retried"

        if contract.mode == "replace" or self.active_intent is None or contract.intent_id != self.active_intent.intent_id:
            if self.active_intent is not None and self._goal_similarity(contract.goal, self.active_intent.goal) >= float(getattr(self.config, "INTENT_RETRY_GOAL_SIMILARITY_THRESHOLD", 0.45)):
                contract.retry_count = min(self.active_intent.retry_count, contract.retry_limit)
            self.active_intent = contract
            self.clear_requirement()
            return True, "intent_activated"

        contract.retry_count = self.active_intent.retry_count
        self.active_intent = contract
        self.clear_requirement()
        return True, "intent_refreshed"

    def can_continue_current_intent_after_failure(self) -> bool:
        if self.active_intent is None:
            return False
        return self.active_intent.step_count < self.active_intent.safe_steps_limit

    def pre_action_check(self, command: dict) -> dict | None:
        if self.active_intent is None:
            return None
        cmd_type = command.get("type") or command.get("action") or "unknown"
        if cmd_type not in self.active_intent.allowed_actions:
            return {
                "reason": "intent_action_not_allowed",
                "recoverable": True,
                "error_code": "INTENT_ACTION_NOT_ALLOWED",
                "next_actions": self.active_intent.allowed_actions[:],
                "command": command.copy(),
            }
        return None

    def note_action(self, command: dict) -> dict | None:
        if self.active_intent is None:
            return None
        self.active_intent.step_count += 1
        if self.active_intent.step_count > self.active_intent.safe_steps_limit:
            return {
                "reason": "intent_step_limit_exceeded",
                "recoverable": True,
                "error_code": "INTENT_STEP_LIMIT_EXCEEDED",
                "next_actions": self.active_intent.allowed_actions[:],
                "command": command.copy(),
            }
        return None

    def summary(self) -> str:
        if self.active_intent is None:
            return ""
        i = self.active_intent
        return (
            f"intent_id={i.intent_id}, type={i.intent_type}, "
            f"steps={i.step_count}/{i.safe_steps_limit}, retries={i.retry_count}/{i.retry_limit}, "
            f"allowed={','.join(i.allowed_actions)}"
        )