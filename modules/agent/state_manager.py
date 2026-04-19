"""Управління станом сесії агента."""

from __future__ import annotations

import json

from .defect_detector import DefectDetector
from .intent_runtime import IntentRuntime

READ_ONLY_RECOVERY_ACTIONS = {
    "read_file",
    "read_chunk",
    "read_file_skeleton",
    "extract_kotlin_function",
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
        self._pending_loop_stop_info = None

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
        self.intent_step_batch_mode = ""
        self.intent_step_batch_consumed = False
        self.stop_reason_counts = {}

        self.recoverable_retry_budget_remaining = 2
        self.critical_retry_budget_remaining = 1

        self.current_task = None
        self.is_awaiting_model_selection = False

        self.intent_runtime = IntentRuntime(config) if config is not None else None
        self.defect_detector = DefectDetector(config) if config is not None else None
        self.last_defect_info = None
        self._pending_loop_stop_info = None
        self.readonly_steps_this_turn = 0
        self.last_turn_had_failure = False
        self.intent_only_response_count = 0
        self.recent_problem_actions = []
        self.pending_suspect_intent_payload = None
        self.pending_goal_drift_payload = None
        self.allow_suspect_intent_once = False
        self.memory_board_store = None
        self.memory_board_engine = None

        # Critical: this must advance across real user turns.
        # Working-material protection/degradation depends on it.
        self.current_turn_id = 0
        self.orchestration_trace = []
        self.orchestration_trace_sequence = 0
        self.stop_reason_counts = {}

    @property
    def pending_loop_stop_info(self):
        return self._pending_loop_stop_info

    @pending_loop_stop_info.setter
    def pending_loop_stop_info(self, value):
        self._pending_loop_stop_info = value
        if not isinstance(value, dict):
            return
        reason = str(value.get("reason") or "").strip()
        if reason:
            self.stop_reason_counts[reason] = int(self.stop_reason_counts.get(reason, 0) or 0) + 1
        updates = value.get("intent_constraint_updates")
        if isinstance(updates, dict):
            self.apply_intent_constraint_updates(updates)

    def get_stop_reason_count(self, reason: str) -> int:
        key = str(reason or "").strip()
        if not key:
            return 0
        return int(self.stop_reason_counts.get(key, 0) or 0)

    def apply_intent_constraint_updates(self, updates: dict) -> bool:
        if not isinstance(updates, dict):
            return False
        self.attach_config(self._config)
        if not self.intent_runtime:
            return False
        applier = getattr(self.intent_runtime, "apply_constraint_updates", None)
        if not callable(applier):
            return False
        try:
            return bool(applier(updates))
        except Exception:
            return False

    def start_turn_runtime(self):
        self.readonly_steps_this_turn = 0
        self.last_turn_had_failure = False
        self.intent_only_response_count = 0
        self.pending_suspect_intent_payload = None
        self.pending_goal_drift_payload = None
        self.allow_suspect_intent_once = False
        self.orchestration_trace = []
        self.orchestration_trace_sequence = 0

        # FIX:
        # Do not reset to 0. Each new user turn must get a new turn id so that
        # previous turn_working_material can degrade normally.
        self.current_turn_id = int(self.current_turn_id or 0) + 1

        if self.defect_detector:
            self.defect_detector.reset()

    def note_intent_only_response(self):
        self.intent_only_response_count += 1

    def _trim_recent_problem_actions(self):
        window = int(getattr(self._config, "INTENT_RELABEL_PROBLEM_WINDOW", 5) if self._config is not None else 5)
        if window < 1:
            window = 5
        if len(self.recent_problem_actions) > window:
            self.recent_problem_actions = self.recent_problem_actions[-window:]


    def _normalize_goal_text(self, text: str) -> str:
        text = str(text or "").lower().strip()
        cleaned = []
        for ch in text:
            if ch.isalnum() or ch in {" ", "_"}:
                cleaned.append(ch)
            else:
                cleaned.append(" ")
        return " ".join("".join(cleaned).split())

    def _goal_token_set(self, text: str) -> set[str]:
        return {tok for tok in self._normalize_goal_text(text).split() if tok}

    def _goal_core_loss_suspected(self, old_goal: str, new_goal: str) -> bool:
        old_tokens = self._goal_token_set(old_goal)
        new_tokens = self._goal_token_set(new_goal)
        if not old_tokens or not new_tokens:
            return False
        overlap = len(old_tokens & new_tokens) / max(1, len(old_tokens))
        return overlap < float(getattr(self._config, "INTENT_RELABEL_GOAL_CORE_OVERLAP_THRESHOLD", 0.45) if self._config is not None else 0.45)

    def note_problem_action(self, command: dict, result: dict, *, reason: str = ""):
        entry = {
            "fingerprint": self.get_action_fingerprint(command),
            "command": command.copy(),
            "reason": str(reason or "").strip(),
            "status": str((result or {}).get("status") or ""),
            "error_code": str((result or {}).get("error_code") or ""),
            "output_preview": str(
                (result or {}).get("output")
                or (result or {}).get("raw_output")
                or (result or {}).get("stdout_full")
                or ""
            )[:280],
        }
        self.recent_problem_actions.append(entry)
        self._trim_recent_problem_actions()

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
    def active_intent_id(self) -> str | None:
        active = self.active_intent
        if active is None:
            return None
        value = getattr(active, "intent_id", None)
        return str(value).strip() if value else None

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

    def apply_intent_contract(self, payload: dict, config, *, bypass_suspicion: bool = False) -> tuple[bool, str]:
        self.attach_config(config)
        if not self.intent_runtime:
            return False, "intent_runtime_unavailable"

        contract, transition_info, error = self.intent_runtime.inspect_transition(payload)
        if error:
            return False, error

        should_skip_suspicion = bool(
            bypass_suspicion
            or contract is None
            or transition_info is None
            or not bool(getattr(config, "INTENT_RELABEL_SUSPICION_ENABLED", True))
            or (self.intent_runtime is not None and hasattr(self.intent_runtime, "should_bypass_relabel_suspicion") and self.intent_runtime.should_bypass_relabel_suspicion(contract, transition_info))
        )

        suspicious = False
        if (
            not should_skip_suspicion
            and transition_info.get("same_lineage")
            and transition_info.get("old_goal")
            and contract.mode in {"activate", "replace"}
        ):
            recent = self.recent_problem_actions[-1] if self.recent_problem_actions else {}
            same_allowed = transition_info.get("actions_overlap", 0.0) >= float(getattr(config, "INTENT_RELABEL_ACTION_OVERLAP_THRESHOLD", 0.6))
            goal_core_loss = self._goal_core_loss_suspected(
                transition_info.get("old_goal", ""),
                transition_info.get("new_goal", ""),
            )
            goal_changed = self._normalize_goal_text(transition_info.get("old_goal", "")) != self._normalize_goal_text(transition_info.get("new_goal", ""))
            suspicious = bool(goal_core_loss or (same_allowed and goal_changed))
            if suspicious:
                self.pending_suspect_intent_payload = payload
                self.pending_goal_drift_payload = payload if goal_core_loss else None
                self.last_defect_info = {
                    "reason": "suspect_intent_goal_drift" if goal_core_loss else "suspect_intent_relabel_repeat",
                    "recoverable": True,
                    "error_code": "SUSPECT_INTENT_GOAL_DRIFT" if goal_core_loss else "SUSPECT_INTENT_RELABEL_REPEAT",
                    "next_actions": list(contract.allowed_actions),
                    "command": recent.get("command", {}).copy() if isinstance(recent.get("command"), dict) else {},
                    "message": (
                        "Модель підозріло змінила поточну ціль у межах тієї самої лінії роботи."
                        if goal_core_loss else
                        "Є підозра на cosmetic intent relabel without a legitimate transition trigger."
                    ),
                    "suspicion": {
                        "old_intent_id": transition_info.get("old_intent_id", ""),
                        "old_goal": transition_info.get("old_goal", ""),
                        "old_allowed_actions": transition_info.get("old_allowed_actions", []),
                        "new_intent_id": transition_info.get("new_intent_id", ""),
                        "new_goal": transition_info.get("new_goal", ""),
                        "new_allowed_actions": transition_info.get("new_allowed_actions", []),
                        "goal_similarity": transition_info.get("goal_similarity", 0.0),
                        "actions_overlap": transition_info.get("actions_overlap", 0.0),
                        "goal_core_loss": goal_core_loss,
                        "recent_problem_reason": recent.get("reason", ""),
                        "recent_problem_action": recent.get("fingerprint", ""),
                        "recent_problem_output": recent.get("output_preview", ""),
                    },
                }
                return False, "suspect_intent_goal_drift" if goal_core_loss else "suspect_intent_relabel_repeat"

        ok, msg = self.intent_runtime.apply_payload(payload)
        if ok:
            self.pending_suspect_intent_payload = None
            self.pending_goal_drift_payload = None
        return ok, msg

    def allow_pending_suspect_intent_once(self, config) -> tuple[bool, str]:
        if not self.pending_suspect_intent_payload:
            return False, "no_pending_suspect_intent"
        payload = self.pending_suspect_intent_payload
        self.allow_suspect_intent_once = True
        ok, msg = self.apply_intent_contract(payload, config, bypass_suspicion=True)
        self.allow_suspect_intent_once = False
        return ok, msg

    def allow_pending_goal_drift_once(self, config) -> tuple[bool, str]:
        if not self.pending_goal_drift_payload:
            return False, "no_pending_goal_drift"
        payload = self.pending_goal_drift_payload
        self.allow_suspect_intent_once = True
        ok, msg = self.apply_intent_contract(payload, config, bypass_suspicion=True)
        self.allow_suspect_intent_once = False
        return ok, msg

    def active_intent_summary(self) -> str:
        return self.intent_runtime.summary() if self.intent_runtime else ""

    def check_intent_pre_action(self, command: dict) -> dict | None:
        if not self.intent_runtime:
            return None
        return self.intent_runtime.pre_action_check(command)

    def block_action_for_current_intent(self, command: dict, reason: str) -> bool:
        if not self.intent_runtime:
            return False
        blocker = getattr(self.intent_runtime, "block_action_for_current_intent", None)
        if not callable(blocker):
            return False
        try:
            return bool(blocker(command, reason))
        except Exception:
            return False

    def is_action_blocked_for_current_intent(self, command: dict) -> bool:
        if not self.intent_runtime:
            return False
        checker = getattr(self.intent_runtime, "is_action_blocked_for_current_intent", None)
        if not callable(checker):
            return False
        try:
            return bool(checker(command))
        except Exception:
            return False

    def get_blocked_action_reason(self, command: dict) -> str:
        if not self.intent_runtime:
            return ""
        getter = getattr(self.intent_runtime, "get_blocked_action_reason", None)
        if not callable(getter):
            return ""
        try:
            return str(getter(command) or "")
        except Exception:
            return ""

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
            should_count_intent_step = True
            batch_mode = str(getattr(self, "intent_step_batch_mode", "") or "").strip()
            if batch_mode == "single_readonly_batch" and is_readonly:
                if bool(getattr(self, "intent_step_batch_consumed", False)):
                    should_count_intent_step = False
                else:
                    self.intent_step_batch_consumed = True
            intent_defect = self.intent_runtime.note_action(command) if should_count_intent_step else None
            if intent_defect:
                defect_info = intent_defect
        if defect_info is None and self.defect_detector:
            evt = self.defect_detector.evaluate(self, command, result)
            if evt is not None:
                policy_actions = list(evt.next_actions or [])
                defect_info = {
                    "reason": evt.reason,
                    "recoverable": evt.recoverable,
                    "error_code": evt.error_code or evt.reason.upper(),
                    "next_actions": policy_actions,
                    "command": command.copy(),
                    "message": evt.message,
                    "policy_allowed_actions": policy_actions,
                    "policy_recommended_actions": [],
                    "policy_blocked_actions": [],
                    "policy_intent_actions": policy_actions,
                    "policy_authoritative_source": "intent" if policy_actions else "",
                    "policy_keep_current_intent": True if policy_actions else False,
                }

        if status in {"failed", "error"}:
            self.note_problem_action(command, result, reason=error_code or status)
        elif defect_info is not None:
            self.note_problem_action(command, result, reason=str(defect_info.get("reason") or "defect"))

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
