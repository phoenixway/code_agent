"""Runtime contract for model-declared intents.

This module intentionally stays simple:
- model may declare a formal intent contract
- runtime validates allowed_actions and numeric limits
- runtime tracks steps/retries and exposes light pre/post checks
"""

from __future__ import annotations

import re

from dataclasses import dataclass, field

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
    lineage_id: str = ""
    user_visible_note: str = ""
    hard_limit_hit_count: int = 0
    user_step_extension: int = 0
    user_one_shot_steps_remaining: int = 0
    user_unlimited_override: bool = False
    force_plaintext_completion: bool = False


class IntentRuntime:
    SUPPORTED_TYPES = {"INVESTIGATE", "VERIFY", "MODIFY", "CLEANUP", "SUMMARIZE"}
    SUPPORTED_MODES = {"activate", "retry", "replace"}

    def __init__(self, config):
        self.config = config
        self.active_intent: IntentContract | None = None
        self.intent_required_until_activated = False
        self.intent_required_reason = ""
        self.last_transition_info = {}
        self.last_apply_warning = ""
        self.last_transition_info: dict = {}

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

    def _normalized_goal_tokens(self, goal: str) -> set[str]:
        stop = {"the", "a", "an", "to", "and", "or", "of", "in", "on", "for", "is", "are", "be", "this", "that", "find", "check", "investigate", "verify", "search", "look", "знайти", "перевірити", "дослідити", "для", "та", "і", "це", "що", "як", "у", "в", "на"}
        return {t for t in self._normalize_goal(goal).split() if t and t not in stop}

    def _allowed_actions_overlap(self, a: list[str], b: list[str]) -> float:
        sa = set(a or [])
        sb = set(b or [])
        if not sa or not sb:
            return 0.0
        return len(sa & sb) / max(1, len(sa | sb))

    def _same_lineage(self, contract: IntentContract) -> bool:
        if self.active_intent is None:
            return False
        if contract.intent_id == self.active_intent.intent_id:
            return True
        if contract.intent_type != self.active_intent.intent_type:
            return False
        goal_sim = self._goal_similarity(contract.goal, self.active_intent.goal)
        actions_overlap = self._allowed_actions_overlap(contract.allowed_actions, self.active_intent.allowed_actions)
        return (
            goal_sim >= float(getattr(self.config, "INTENT_RELABEL_GOAL_SIMILARITY_THRESHOLD", 0.6))
            and actions_overlap >= float(getattr(self.config, "INTENT_RELABEL_ACTION_OVERLAP_THRESHOLD", 0.6))
        )

    def inspect_transition(self, payload: dict) -> tuple[IntentContract | None, dict | None, str | None]:
        contract, error = self.validate_payload(payload)
        if error:
            return None, None, error
        active = self.active_intent
        info = {
            "same_lineage": False,
            "goal_similarity": 0.0,
            "actions_overlap": 0.0,
            "old_intent_id": getattr(active, "intent_id", ""),
            "old_goal": getattr(active, "goal", ""),
            "old_allowed_actions": list(getattr(active, "allowed_actions", []) or []),
            "new_intent_id": contract.intent_id,
            "new_goal": contract.goal,
            "new_allowed_actions": contract.allowed_actions[:],
            "mode": contract.mode,
        }
        if active is not None:
            info["goal_similarity"] = self._goal_similarity(contract.goal, active.goal)
            info["actions_overlap"] = self._allowed_actions_overlap(contract.allowed_actions, active.allowed_actions)
            info["same_lineage"] = self._same_lineage(contract)
        return contract, info, None

    def validate_payload(self, payload: dict) -> tuple[IntentContract | None, str | None]:
        if not isinstance(payload, dict):
            return None, "intent_payload_must_be_object"
        intent_id = str(payload.get("intent_id") or "").strip()
        intent_type = str(payload.get("intent_type") or "").strip().upper()
        goal = str(payload.get("goal") or "").strip()
        mode = str(payload.get("mode") or "activate").strip().lower()
        user_visible_note = str(payload.get("user_visible_note") or payload.get("chat_note") or "").strip()
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
            lineage_id=intent_id,
            user_visible_note=user_visible_note[:240],
        ), None

    def apply_payload(self, payload: dict) -> tuple[bool, str]:
        contract, error = self.validate_payload(payload)
        if error:
            return False, error

        self.last_apply_warning = ""
        self.last_transition_info = {}
        active = self.active_intent
        same_lineage = self._same_lineage(contract)

        if contract.mode == "retry":
            if active is None:
                return False, "intent_retry_without_active_intent"

            if not self._reuse_retry_on_same_subtask(contract):
                self.last_apply_warning = "intent_retry_degraded_to_replace"
                contract.mode = "replace"
            else:
                active.retry_count += 1
                active.intent_type = contract.intent_type
                active.goal = contract.goal
                active.allowed_actions = contract.allowed_actions
                active.safe_steps_limit = contract.safe_steps_limit
                active.retry_limit = contract.retry_limit
                active.user_visible_note = contract.user_visible_note
                active.lineage_id = active.lineage_id or active.intent_id
                active.step_count = 0
                active.force_plaintext_completion = False
                self.clear_requirement()
                self.last_transition_info = {"transition": "intent_retried", "same_lineage": True}
                if active.retry_count > active.retry_limit:
                    return False, "intent_retry_limit_exceeded"
                return True, "intent_retried"

        if contract.mode == "replace" or active is None or contract.intent_id != active.intent_id:
            if active is not None and same_lineage:
                contract.lineage_id = active.lineage_id or active.intent_id
                contract.retry_count = min(active.retry_count, contract.retry_limit)
                contract.hard_limit_hit_count = active.hard_limit_hit_count
                contract.user_step_extension = active.user_step_extension
                contract.user_one_shot_steps_remaining = active.user_one_shot_steps_remaining
                contract.user_unlimited_override = active.user_unlimited_override
                contract.force_plaintext_completion = active.force_plaintext_completion
                if bool(getattr(self.config, "INTENT_RELABEL_PRESERVE_STEPS_ON_REFRESH", True)):
                    contract.step_count = min(active.step_count, contract.safe_steps_limit + max(0, contract.user_step_extension))
                self.last_transition_info = {"transition": "intent_replaced", "same_lineage": True}
            else:
                contract.lineage_id = contract.intent_id
                self.last_transition_info = {"transition": "intent_activated", "same_lineage": False}
            self.active_intent = contract
            self.clear_requirement()
            return True, self.last_transition_info["transition"]

        contract.retry_count = active.retry_count
        contract.lineage_id = active.lineage_id or active.intent_id
        contract.user_visible_note = contract.user_visible_note or active.user_visible_note
        if same_lineage:
            contract.hard_limit_hit_count = active.hard_limit_hit_count
            contract.user_step_extension = active.user_step_extension
            contract.user_one_shot_steps_remaining = active.user_one_shot_steps_remaining
            contract.user_unlimited_override = active.user_unlimited_override
            contract.force_plaintext_completion = active.force_plaintext_completion
        if bool(getattr(self.config, "INTENT_RELABEL_PRESERVE_STEPS_ON_REFRESH", True)) and same_lineage:
            contract.step_count = min(active.step_count, contract.safe_steps_limit + max(0, contract.user_step_extension))
        self.active_intent = contract
        self.clear_requirement()
        self.last_transition_info = {"transition": "intent_refreshed", "same_lineage": same_lineage}
        return True, "intent_refreshed"

    def _effective_nominal_limit(self) -> int:
        if self.active_intent is None:
            return 0
        return int(self.active_intent.safe_steps_limit) + max(0, int(self.active_intent.user_step_extension))

    def _effective_hard_limit(self) -> int:
        allowance = int(getattr(self.config, "INTENT_COMPLETION_ALLOWANCE", 1))
        return self._effective_nominal_limit() + max(0, allowance)

    def can_continue_current_intent_after_failure(self) -> bool:
        if self.active_intent is None:
            return False
        if self.active_intent.user_unlimited_override:
            return True
        return self.active_intent.step_count < self._effective_nominal_limit()

    def can_soft_continue_after_step_limit(self) -> bool:
        """Allow a small completion window past the nominal step limit.

        This avoids forcing refresh/relabel loops near the end of a coherent
        investigation when the current intent and strategy are still valid.
        """
        if self.active_intent is None:
            return False
        if self.active_intent.user_unlimited_override:
            return True
        return self.active_intent.step_count < self._effective_hard_limit()

    def grant_two_more_steps(self) -> bool:
        if self.active_intent is None:
            return False
        self.active_intent.user_one_shot_steps_remaining += max(1, int(getattr(self.config, "INTENT_USER_ONE_SHOT_STEPS", 2)))
        self.active_intent.force_plaintext_completion = False
        return True

    def extend_current_intent_limit(self, extra_steps: int | None = None) -> bool:
        if self.active_intent is None:
            return False
        if extra_steps is None:
            extra_steps = int(getattr(self.config, "INTENT_USER_EXTENSION_STEPS", 4))
        self.active_intent.user_step_extension += max(1, int(extra_steps))
        self.active_intent.force_plaintext_completion = False
        return True

    def enable_unlimited_for_current_intent(self) -> bool:
        if self.active_intent is None:
            return False
        if not bool(getattr(self.config, "INTENT_ALLOW_UNLIMITED_OVERRIDE", True)):
            return False
        self.active_intent.user_unlimited_override = True
        self.active_intent.force_plaintext_completion = False
        return True

    def force_current_intent_completion(self) -> bool:
        if self.active_intent is None:
            return False
        self.active_intent.force_plaintext_completion = True
        return True

    def pre_action_check(self, command: dict) -> dict | None:
        if self.active_intent is None:
            return None
        if self.active_intent.force_plaintext_completion:
            return {
                "reason": "intent_force_plaintext_completion",
                "recoverable": True,
                "error_code": "INTENT_FORCE_PLAINTEXT_COMPLETION",
                "next_actions": [],
                "command": command.copy(),
                "message": (
                    "User requested final answer from already gathered evidence. "
                    "Do not use more tools under this intent now."
                ),
            }
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

        if self.active_intent.user_unlimited_override:
            return None

        limit = self._effective_nominal_limit()
        hard_limit = self._effective_hard_limit()

        if self.active_intent.step_count > hard_limit:
            if self.active_intent.user_one_shot_steps_remaining > 0:
                self.active_intent.user_one_shot_steps_remaining -= 1
                return None

            self.active_intent.hard_limit_hit_count += 1
            repeated = self.active_intent.hard_limit_hit_count > 1
            return {
                "reason": "intent_step_limit_exceeded_repeated" if repeated else "intent_step_limit_exceeded",
                "recoverable": True,
                "error_code": "INTENT_STEP_LIMIT_EXCEEDED_REPEATED" if repeated else "INTENT_STEP_LIMIT_EXCEEDED",
                "next_actions": self.active_intent.allowed_actions[:],
                "message": (
                    "Current intent exceeded its hard step limit repeatedly for the same lineage. "
                    "Ask user what to do next."
                    if repeated else
                    "Current intent exceeded its hard step limit. "
                    "Do not refresh/relabel the same intent again. "
                    "Either conclude with current evidence or start a materially different retry/replace intent."
                ),
                "command": command.copy(),
            }

        if self.active_intent.step_count > limit:
            return {
                "reason": "intent_step_limit_soft_exceeded",
                "recoverable": True,
                "error_code": "INTENT_STEP_LIMIT_SOFT_EXCEEDED",
                "next_actions": self.active_intent.allowed_actions[:],
                "message": (
                    "Current intent reached its nominal step limit. "
                    "Prefer one final allowed action or a plain-text conclusion. "
                    "Do not refresh/relabel the same intent unless strategy materially changes."
                ),
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