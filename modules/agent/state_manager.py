"""Управління станом сесії агента."""

from __future__ import annotations

import json

from .defect_detector import DefectDetector
from .intent_runtime import IntentRuntime

READ_ONLY_RECOVERY_ACTIONS = {
    "read_file",
    "read_file_skeleton",
    "search_content",
    "search_files",
    "list_directory",
    "find_files",
    "git_diff",
}


class AgentState:
    """Зберігає динамічний стан агента: токени, циклічність, задачі."""

    def __init__(self, config=None):
        self._config = config
        self.session_tokens = 0
        self.confirmation_count = 0
        self.suppress_step_limit_warning = False
        self.consecutive_same_action_count = 0
        self.last_completed_fingerprint = None
        self.pending_loop_stop_info = None

        self.last_action_fingerprint = None
        self.last_action_status = None
        self.consecutive_failed_repeats = 0
        self.last_error_fingerprint = None
        self.consecutive_same_error_count = 0
        self.last_error_code = None
        self.last_error_message = None
        self.last_error_recoverable = False
        self.last_error_next_actions = []
        self.last_failed_action_command = None
        self.last_failed_action_result = None
        self.malformed_recovery_grace_remaining = 0
        self.forbidden_next_action_fingerprint = None
        self.state_machine = None
        self.last_batch_actions_executed = 0
        self.last_batch_actions_total = 0

        self.recoverable_retry_budget_remaining = 2
        self.critical_retry_budget_remaining = 1

        self.current_task = None
        self.is_awaiting_model_selection = False

        self.intent_runtime = IntentRuntime(config) if config is not None else None
        self.defect_detector = DefectDetector(config) if config is not None else None
        self.last_defect_info = None
        self.readonly_steps_this_turn = 0
        self.last_turn_had_failure = False
        self.intent_only_response_count = 0

    def start_turn_runtime(self):
        self.readonly_steps_this_turn = 0
        self.last_turn_had_failure = False
        self.intent_only_response_count = 0
        if self.defect_detector:
            self.defect_detector.reset()

    def note_intent_only_response(self):
        self.intent_only_response_count += 1

    def attach_config(self, config):
        self._config = config
        if self.intent_runtime is None:
            self.intent_runtime = IntentRuntime(config)
        if self.defect_detector is None:
            self.defect_detector = DefectDetector(config)

    @property
    def active_intent(self):
        return self.intent_runtime.active_intent if self.intent_runtime else None

    @property
    def intent_required_until_activated(self):
        return self.intent_runtime.intent_required_until_activated if self.intent_runtime else False

    @property
    def intent_required_reason(self):
        return self.intent_runtime.intent_required_reason if self.intent_runtime else ""

    def require_intent(self, reason: str):
        if self.intent_runtime:
            self.intent_runtime.require_intent(reason)

    def clear_intent_requirement(self):
        if self.intent_runtime:
            self.intent_runtime.clear_requirement()

    def has_retry_context(self) -> bool:
        if self.last_turn_had_failure:
            return True
        if self.consecutive_same_error_count > 0:
            return True
        if self.intent_runtime and self.intent_runtime.active_intent is not None and self.intent_runtime.active_intent.retry_count > 0:
            return True
        return False

    def can_continue_current_intent_after_failure(self) -> bool:
        if not self.intent_runtime:
            return False
        checker = getattr(self.intent_runtime, "can_continue_current_intent_after_failure", None)
        if callable(checker):
            return bool(checker())
        return False

    def apply_intent_contract(self, payload: dict, config) -> tuple[bool, str]:
        self.attach_config(config)
        return self.intent_runtime.apply_payload(payload)

    def active_intent_summary(self) -> str:
        return self.intent_runtime.summary() if self.intent_runtime else ""

    def check_intent_pre_action(self, command: dict) -> dict | None:
        if not self.intent_runtime:
            return None
        return self.intent_runtime.pre_action_check(command)

    def get_action_fingerprint(self, command: dict) -> str:
        cmd_type = command.get("type") or command.get("action") or "unknown"
        ignored_fields = {"before_execution", "during_execution", "after_execution", "return_control", "id"}
        args = {k: v for k, v in command.items() if k not in ignored_fields}
        return f"{cmd_type}:{json.dumps(args, sort_keys=True)}"

    def update_loop_tracker(self, command: dict, status: str):
        fingerprint = self.get_action_fingerprint(command)
        if fingerprint == self.last_action_fingerprint and self.last_action_status in ["failed", "error"]:
            self.consecutive_failed_repeats += 1
        else:
            self.consecutive_failed_repeats = 0
        self.last_action_fingerprint = fingerprint
        self.last_action_status = status

    def set_retry_budgets(self, recoverable_budget: int, critical_budget: int):
        self.recoverable_retry_budget_remaining = max(0, int(recoverable_budget))
        self.critical_retry_budget_remaining = max(0, int(critical_budget))

    def reset_retry_budgets(self, recoverable_budget: int, critical_budget: int):
        self.set_retry_budgets(recoverable_budget, critical_budget)

    def set_malformed_grace(self, steps: int):
        self.malformed_recovery_grace_remaining = max(0, int(steps))

    def consume_malformed_grace(self) -> bool:
        if self.malformed_recovery_grace_remaining > 0:
            self.malformed_recovery_grace_remaining -= 1
            return True
        return False

    def forbid_next_action_fingerprint(self, fingerprint: str | None):
        self.forbidden_next_action_fingerprint = fingerprint

    def consume_forbidden_action_if_matches(self, command: dict) -> bool:
        forbidden = self.forbidden_next_action_fingerprint
        if not forbidden:
            return False
        current = self.get_action_fingerprint(command)
        self.forbidden_next_action_fingerprint = None
        return current == forbidden

    def add_tokens(self, prompt: int, completion: int):
        self.session_tokens += (prompt + completion)

    def add_confirmation(self, count: int = 1):
        self.confirmation_count += count

    def update_action_repetition(self, command: dict):
        fingerprint = self.get_action_fingerprint(command)
        if fingerprint == self.last_completed_fingerprint:
            self.consecutive_same_action_count += 1
        else:
            self.consecutive_same_action_count = 1
        self.last_completed_fingerprint = fingerprint

    def record_action_result(self, command: dict, result: dict, config=None):
        if config is not None:
            self.attach_config(config)

        cmd_type = command.get("type") or command.get("action") or "unknown"
        status = result.get("status")
        error_code = result.get("error_code")
        error_message = result.get("output", "")
        recoverable = bool(result.get("recoverable", False))
        next_actions = result.get("next_actions") or []
        if not isinstance(next_actions, list):
            next_actions = []

        self.update_loop_tracker(command, status)
        self.update_action_repetition(command)
        is_readonly = cmd_type in READ_ONLY_RECOVERY_ACTIONS or (cmd_type == "run_shell" and "command" in command)
        if is_readonly:
            self.readonly_steps_this_turn += 1

        if status in {"failed", "error"}:
            self.last_turn_had_failure = True
            fingerprint = self.get_action_fingerprint(command)
            error_fp = f"{fingerprint}|{error_code or 'UNSPECIFIED'}"
            if error_fp == self.last_error_fingerprint:
                self.consecutive_same_error_count += 1
            else:
                self.consecutive_same_error_count = 1
            self.last_error_fingerprint = error_fp
            self.last_error_code = error_code
            self.last_error_message = str(error_message)[:1000]
            self.last_error_recoverable = recoverable
            self.last_error_next_actions = next_actions
            self.last_failed_action_command = command.copy()
            self.last_failed_action_result = {k: v for k, v in result.items() if k != "output"}
            self.last_failed_action_result["output"] = str(error_message)[:4000]
        else:
            if cmd_type not in READ_ONLY_RECOVERY_ACTIONS:
                self.consecutive_same_error_count = 0
                self.last_error_fingerprint = None
                self.last_error_code = None
                self.last_error_message = None
                self.last_error_recoverable = False
                self.last_error_next_actions = []
                self.last_failed_action_command = None
                self.last_failed_action_result = None

        defect_info = None
        if self.intent_runtime:
            intent_defect = self.intent_runtime.note_action(command)
            if intent_defect:
                defect_info = intent_defect
        if defect_info is None and self.defect_detector:
            evt = self.defect_detector.evaluate(self, command, result)
            if evt is not None:
                defect_info = {
                    "reason": evt.reason,
                    "recoverable": evt.recoverable,
                    "error_code": evt.error_code or evt.reason.upper(),
                    "next_actions": evt.next_actions or [],
                    "command": command.copy(),
                    "message": evt.message,
                }

        self.last_defect_info = defect_info

        return {
            "status": status,
            "error_code": error_code,
            "recoverable": recoverable,
            "next_actions": next_actions,
            "same_error_repeats": self.consecutive_same_error_count,
            "same_action_repeats": self.consecutive_same_action_count,
            "defect_info": defect_info,
        }

    def consume_retry_budget(self, recoverable: bool) -> bool:
        if recoverable:
            if self.recoverable_retry_budget_remaining <= 0:
                return False
            self.recoverable_retry_budget_remaining -= 1
            return True
        if self.critical_retry_budget_remaining <= 0:
            return False
        self.critical_retry_budget_remaining -= 1
        return True