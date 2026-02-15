"""Конфігурація та налаштування агента."""

from modules.config_loader import load_settings


class AgentConfig:
    """Клас для зберігання незмінної конфігурації агента."""
    
    def __init__(self):
        self.settings = load_settings()
        
        # Константи поведінки
        self.MAX_CONSECUTIVE_CALLS = self._get_positive_int("max_consecutive_calls", 12)
        self.MAX_STEP_SECONDS = self._get_positive_int("max_step_seconds", 120)
        self.MAX_SESSION_SECONDS = self._get_positive_int("max_session_seconds", 900)
        self.LOOP_ERROR_REPEAT_THRESHOLD = self._get_positive_int("loop_error_repeat_threshold", 2)
        self.MALFORMED_ACTION_GRACE_STEPS = self._get_positive_int("malformed_action_grace_steps", 2)
        self.RECOVERABLE_ERROR_RETRY_BUDGET = self._get_positive_int("recoverable_error_retry_budget", 2)
        self.CRITICAL_ERROR_RETRY_BUDGET = self._get_positive_int("critical_error_retry_budget", 1)
        self.READ_ONLY_REPEAT_THRESHOLD = self._get_positive_int("read_only_repeat_threshold", 3)
        self.IMPLEMENT_STAGNATION_LIMIT = self._get_positive_int("implement_stagnation_limit", 3)
        self.RESEARCH_STAGNATION_LIMIT = self._get_positive_int("research_stagnation_limit", 6)
        self.STAGNATION_MAX_DIAGNOSTICS = self._get_positive_int("stagnation_max_diagnostics", 1)
        self.INVARIANT_VIOLATION_LIMIT = self._get_positive_int("invariant_violation_limit", 1)
        self.PLANNER_ENABLED = bool(self.settings.get("planner_enabled", False))
        self.PLANNER_MODE = str(self.settings.get("planner_mode", "auto") or "auto").lower()
        self.PLANNER_MAX_STEPS = self._get_positive_int("planner_max_steps", 12)
        self.PLANNER_MAX_VISIBLE_STEPS = self._get_positive_int("planner_max_visible_steps", 4)
        self.PLANNER_MAX_GOAL_CHARS = self._get_positive_int("planner_max_goal_chars", 240)
        self.PLANNER_MAX_STEP_TITLE_CHARS = self._get_positive_int("planner_max_step_title_chars", 160)
        self.PLANNER_MAX_STEP_NOTES_CHARS = self._get_positive_int("planner_max_step_notes_chars", 240)
        
        # Операції, що змінюють стан (викликають зупинку циклу для підтвердження або роздумів)
        self.STATE_CHANGING_OPS = {
            "run_shell", "create_file", "replace", 
            "edit_file", "git_add", "git_commit", 
            "git_checkout", "delete_file"
        }

    def _get_positive_int(self, key: str, default: int) -> int:
        value = self.settings.get(key, default)
        if isinstance(value, int) and value > 0:
            return value
        return default
        
    @property
    def default_model(self) -> str:
        return self.settings.get("default_model", "ollama/qwen2.5-coder:7b")
    
    @property
    def max_history_tokens(self) -> int:
        return self.settings.get("max_history_tokens", 4000)
    
    @property
    def permission_policy(self) -> str:
        return self.settings.get("permission_policy", "ask")
    
    @property
    def history_size(self) -> str:
        return self.settings.get("history_size", "small")

    @property
    def autosummarize_requires_confirmation(self) -> bool:
        return bool(self.settings.get("autosummarize_requires_confirmation", False))
