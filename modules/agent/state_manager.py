"""Управління станом сесії агента."""

import json

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
    
    def __init__(self):
        # Відстеження токенів
        self.session_tokens = 0
        self.confirmation_count = 0
        self.suppress_step_limit_warning = False
        self.consecutive_same_action_count = 0
        self.last_completed_fingerprint = None
        self.pending_loop_stop_info = None
        
        # Виявлення нескінченних циклів
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
        self.task_board = None
        self.task_board_enabled = False

        # Retry budgets
        self.recoverable_retry_budget_remaining = 2
        self.critical_retry_budget_remaining = 1
        
        # Асинхронні задачі
        self.current_task = None
        
        # Стан інтерфейсу
        self.is_awaiting_model_selection = False
    
    def get_action_fingerprint(self, command: dict) -> str:
        """Створює стабільний відбиток дії для перевірки циклів."""
        cmd_type = command.get("type") or command.get("action") or "unknown"
        
        # Ігноруємо службові поля, які змінюються при виконанні
        ignored_fields = {
            "before_execution", "during_execution", "after_execution", 
            "return_control", "id"
        }
        
        args = {k: v for k, v in command.items() if k not in ignored_fields}
        
        # sort_keys=True гарантує, що {a:1, b:2} == {b:2, a:1}
        return f"{cmd_type}:{json.dumps(args, sort_keys=True)}"
    
    def update_loop_tracker(self, command: dict, status: str):
        """Оновлює лічильники повторюваних помилок."""
        fingerprint = self.get_action_fingerprint(command)
        
        # Якщо дія та сама, і вона знову впала -> збільшуємо лічильник
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
        """Track repeated actions regardless of status to spot potential loops."""
        fingerprint = self.get_action_fingerprint(command)
        if fingerprint == self.last_completed_fingerprint:
            self.consecutive_same_action_count += 1
        else:
            self.consecutive_same_action_count = 1
        self.last_completed_fingerprint = fingerprint

    def record_action_result(self, command: dict, result: dict):
        """Record result details for loop/no-progress detection and recovery hints."""
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

        if status in {"failed", "error"}:
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
            self.last_failed_action_result = {
                k: v for k, v in result.items() if k != "output"
            }
            self.last_failed_action_result["output"] = str(error_message)[:4000]
        else:
            # Keep error-repeat counters across read-only reconnaissance steps:
            # this catches loops like edit_file(error)->read_file(success)->same edit_file(error).
            if cmd_type not in READ_ONLY_RECOVERY_ACTIONS:
                self.consecutive_same_error_count = 0
                self.last_error_fingerprint = None
                self.last_error_code = None
                self.last_error_message = None
                self.last_error_recoverable = False
                self.last_error_next_actions = []
                self.last_failed_action_command = None
                self.last_failed_action_result = None

        return {
            "status": status,
            "error_code": error_code,
            "recoverable": recoverable,
            "next_actions": next_actions,
            "same_error_repeats": self.consecutive_same_error_count,
            "same_action_repeats": self.consecutive_same_action_count,
        }

    def consume_retry_budget(self, recoverable: bool) -> bool:
        """Returns True when retry is still allowed after decrement."""
        if recoverable:
            if self.recoverable_retry_budget_remaining <= 0:
                return False
            self.recoverable_retry_budget_remaining -= 1
            return True
        if self.critical_retry_budget_remaining <= 0:
            return False
        self.critical_retry_budget_remaining -= 1
        return True
