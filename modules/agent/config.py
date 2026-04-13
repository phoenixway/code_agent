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
        self.MAX_READONLY_BATCH_ACTIONS = self._get_positive_int("max_readonly_batch_actions", 6)
        self.IMPLEMENT_STAGNATION_LIMIT = self._get_positive_int("implement_stagnation_limit", 3)
        self.RESEARCH_STAGNATION_LIMIT = self._get_positive_int("research_stagnation_limit", 6)
        self.STAGNATION_MAX_DIAGNOSTICS = self._get_positive_int("stagnation_max_diagnostics", 1)
        self.INVARIANT_VIOLATION_LIMIT = self._get_positive_int("invariant_violation_limit", 1)
        self.MULTI_FILE_READ_ONLY_GLOBAL_LIMIT = self._get_positive_int(
            "multi_file_read_only_global_limit", 10
        )
        self.MAX_REPEAT_READ_SAME_FILE = self._get_positive_int("max_repeat_read_same_file", 1)
        self.SUMMARY_DEFER_OBSERVE_STEPS = self._get_positive_int("summary_defer_observe_steps", 1)
        self.SUMMARY_MIN_READS_BEFORE_DEFER = self._get_positive_int("summary_min_reads_before_defer", 2)
        self.RECENT_SUMMARY_REREAD_WINDOW_SEC = self._get_positive_int("recent_summary_reread_window_sec", 90)
        self.TASK_CONTRACT_FORCE_IMPLEMENT_FOR_HYBRID = bool(self.settings.get("task_contract_force_implement_for_hybrid", True))
        self.TASK_CONTRACT_BLOCK_WRITES_FOR_INSPECTION = bool(self.settings.get("task_contract_block_writes_for_inspection", False))
        self.OBSERVE_PHASE_BUDGET = self._get_positive_int("observe_phase_budget", 6)
        self.MAX_ROOT_LISTINGS_PER_TURN = self._get_positive_int("max_root_listings_per_turn", 1)
        self.MAX_DIRECTORY_DESCENT_CHAIN = self._get_positive_int("max_directory_descent_chain", 3)
        self.MAX_BROAD_RECON_BATCHES = self._get_positive_int("max_broad_recon_batches", 2)
        self.MAX_LIST_DIRECTORY_ACTIONS_PER_TURN = self._get_positive_int("max_list_directory_actions_per_turn", 4)
        self.PROJECT_INSPECTION_FORCE_ENTRYPOINTS_FIRST = bool(self.settings.get("project_inspection_force_entrypoints_first", True))
        self.PROJECT_INSPECTION_PREFER_SEARCH_OVER_LIST = bool(self.settings.get("project_inspection_prefer_search_over_list", True))
        
        # Операції, що змінюють стан (викликають зупинку циклу для підтвердження або роздумів)
        self.STATE_CHANGING_OPS = {
            "run_shell", "create_file", "replace", 
            "edit_file", "write_file", "git_add", "git_commit", 
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