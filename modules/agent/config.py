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
        self.MULTI_FILE_READ_ONLY_GLOBAL_LIMIT = self._get_positive_int("multi_file_read_only_global_limit", 10)
        self.MAX_REPEAT_READ_SAME_FILE = self._get_positive_int("max_repeat_read_same_file", 1)
        self.SUMMARY_DEFER_OBSERVE_STEPS = self._get_positive_int("summary_defer_observe_steps", 1)
        self.SUMMARY_MIN_READS_BEFORE_DEFER = self._get_positive_int("summary_min_reads_before_defer", 2)
        self.RECENT_SUMMARY_REREAD_WINDOW_SEC = self._get_positive_int("recent_summary_reread_window_sec", 90)

        # Adaptive observe budgets
        self.OBSERVE_BUDGET_INSPECTION = self._get_positive_int("observe_budget_inspection", 6)
        self.OBSERVE_BUDGET_HYBRID = self._get_positive_int("observe_budget_hybrid", 4)
        self.OBSERVE_BUDGET_MODIFICATION = self._get_positive_int("observe_budget_modification", 2)
        self.OBSERVE_BUDGET_LIGHT_CAP = self._get_positive_int("observe_budget_light_cap", 2)
        self.OBSERVE_BUDGET_DEEP_BONUS = self._get_positive_int("observe_budget_deep_bonus", 2)

        # Modification bootstrap
        self.MODIFICATION_BOOTSTRAP_LIMIT = self._get_positive_int("modification_bootstrap_limit", 2)

        # Narrow provenance after entrypoint discovery
        self.ENTRYPOINT_PROVENANCE_LIMIT = self._get_positive_int("entrypoint_provenance_limit", 1)


        # Intent contract + defect detector
        self.INTENT_CONTRACT_ENABLED = bool(self.settings.get("intent_contract_enabled", True))
        self.INTENT_REQUIRE_ON_DEFECT = bool(self.settings.get("intent_require_on_defect", True))
        self.INTENT_REQUIRE_FOR_INVESTIGATION = bool(self.settings.get("intent_require_for_investigation", True))
        self.INTENT_REQUIRE_FOR_READONLY_BATCH = bool(self.settings.get("intent_require_for_readonly_batch", True))
        self.INTENT_REQUIRE_FOR_BROAD_SEARCH = bool(self.settings.get("intent_require_for_broad_search", True))
        self.INTENT_REQUIRE_FOR_RETRY = bool(self.settings.get("intent_require_for_retry", True))
        self.INTENT_REQUIRE_FOR_CLEANUP = bool(self.settings.get("intent_require_for_cleanup", True))
        self.INTENT_DEFAULT_SAFE_STEPS = self._get_positive_int("intent_default_safe_steps", 4)
        self.INTENT_DEFAULT_RETRY_LIMIT = self._get_positive_int("intent_default_retry_limit", 2)
        self.INTENT_MAX_SAFE_STEPS = self._get_positive_int("intent_max_safe_steps", 8)
        self.INTENT_MAX_RETRY_LIMIT = self._get_positive_int("intent_max_retry_limit", 4)
        self.INTENT_COMPLETION_ALLOWANCE = self._get_positive_int("intent_completion_allowance", 1)
        self.INTENT_USER_EXTENSION_STEPS = self._get_positive_int("intent_user_extension_steps", 4)
        self.INTENT_USER_ONE_SHOT_STEPS = self._get_positive_int("intent_user_one_shot_steps", 2)
        self.INTENT_ALLOW_UNLIMITED_OVERRIDE = bool(self.settings.get("intent_allow_unlimited_override", True))
        self.DEFECT_SAME_ACTION_REPEAT_THRESHOLD = self._get_positive_int("defect_same_action_repeat_threshold", 3)
        self.DEFECT_ACTION_CYCLE_WINDOW = self._get_positive_int("defect_action_cycle_window", 3)
        self.DEFECT_ACTION_HISTORY_WINDOW = self._get_positive_int("defect_action_history_window", 12)
        self.DEFECT_LOW_VALUE_BROAD_SEARCH_REPEAT_THRESHOLD = self._get_positive_int("defect_low_value_broad_search_repeat_threshold", 2)
        self.DEFECT_TOO_BROAD_SEARCH_THRESHOLD = self._get_positive_int("defect_too_broad_search_threshold", 1)
        self.DEFECT_STRATEGY_EXHAUSTED_THRESHOLD = self._get_positive_int("defect_strategy_exhausted_threshold", 3)

        # Existing phase/budget controls
        self.OBSERVE_PHASE_BUDGET = self._get_positive_int("observe_phase_budget", 8)
        self.MAX_ROOT_LISTINGS_PER_TURN = self._get_positive_int("max_root_listings_per_turn", 1)
        self.MAX_LIST_DIRECTORY_ACTIONS_PER_TURN = self._get_positive_int("max_list_directory_actions_per_turn", 4)
        self.MAX_DIRECTORY_DESCENT_CHAIN = self._get_positive_int("max_directory_descent_chain", 3)
        self.MAX_BROAD_RECON_BATCHES = self._get_positive_int("max_broad_recon_batches", 2)
        self.MULTI_FILE_PER_FILE_READ_ONLY_LIMIT = self._get_positive_int("multi_file_per_file_read_only_limit", 3)

        # Task contract
        self.TASK_CONTRACT_FORCE_IMPLEMENT_FOR_HYBRID = bool(
            self.settings.get("task_contract_force_implement_for_hybrid", True)
        )

        # Planner
        self.PLANNER_ENABLED = bool(self.settings.get("planner_enabled", False))
        self.PLANNER_MODE = self.settings.get("planner_mode", "auto")
        self.PLANNER_MAX_GOAL_CHARS = self._get_positive_int("planner_max_goal_chars", 240)
        self.PLANNER_MAX_STEPS = self._get_positive_int("planner_max_steps", 12)
        self.PLANNER_MAX_STEP_TITLE_CHARS = self._get_positive_int("planner_max_step_title_chars", 160)
        self.PLANNER_MAX_STEP_NOTES_CHARS = self._get_positive_int("planner_max_step_notes_chars", 240)
        self.PLANNER_MAX_VISIBLE_STEPS = self._get_positive_int("planner_max_visible_steps", 4)

        # Операції, що змінюють стан
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