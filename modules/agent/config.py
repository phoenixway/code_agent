"""Конфігурація та налаштування агента.

Updated for formal intent completion and intent-switch validation.
The goal is to keep transition rules compact and configurable, without
introducing new orchestration entities.
"""

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
        self.INTENTLESS_SHORT_MODE_MAX_STEPS = self._get_positive_int("intentless_short_mode_max_steps", 2)
        self.INTENT_DEFAULT_SAFE_STEPS = self._get_positive_int("intent_default_safe_steps", 4)
        self.INTENT_DEFAULT_RETRY_LIMIT = self._get_positive_int("intent_default_retry_limit", 2)
        self.INTENT_MAX_SAFE_STEPS = self._get_positive_int("intent_max_safe_steps", 8)
        self.INTENT_MAX_RETRY_LIMIT = self._get_positive_int("intent_max_retry_limit", 4)
        self.INTENT_COMPLETION_ALLOWANCE = self._get_positive_int("intent_completion_allowance", 1)
        self.INTENT_USER_EXTENSION_STEPS = self._get_positive_int("intent_user_extension_steps", 4)
        self.INTENT_USER_ONE_SHOT_STEPS = self._get_positive_int("intent_user_one_shot_steps", 2)
        self.INTENT_ALLOW_UNLIMITED_OVERRIDE = bool(self.settings.get("intent_allow_unlimited_override", True))

        # Intent transition / relabel heuristics
        self.INTENT_RETRY_GOAL_SIMILARITY_THRESHOLD = self._get_float(
            "intent_retry_goal_similarity_threshold", 0.45
        )
        self.INTENT_RELABEL_GOAL_SIMILARITY_THRESHOLD = self._get_float(
            "intent_relabel_goal_similarity_threshold", 0.60
        )
        self.INTENT_RELABEL_ACTION_OVERLAP_THRESHOLD = self._get_float(
            "intent_relabel_action_overlap_threshold", 0.60
        )
        self.INTENT_RELABEL_SUSPICION_ENABLED = bool(
            self.settings.get("intent_relabel_suspicion_enabled", True)
        )
        self.INTENT_RELABEL_PROBLEM_WINDOW = self._get_positive_int(
            "intent_relabel_problem_window", 5
        )

        # Formal transition reasons.
        # Keep the set small and explicit to avoid policy bloat.
        self.INTENT_SWITCH_REASON_REQUIRED = bool(
            self.settings.get("intent_switch_reason_required", True)
        )
        self.INTENT_COMPLETION_REASON_REQUIRED = bool(
            self.settings.get("intent_completion_reason_required", True)
        )
        self.INTENT_SWITCH_EXPLANATION_REQUIRED = bool(
            self.settings.get("intent_switch_explanation_required", False)
        )
        self.INTENT_COMPLETION_EXPLANATION_REQUIRED = bool(
            self.settings.get("intent_completion_explanation_required", False)
        )

        self.INTENT_ALLOWED_SWITCH_REASONS = self._get_csv_set(
            "intent_allowed_switch_reasons",
            {
                "user_requested_new_task",
                "current_intent_completed",
                "current_intent_exhausted",
                "work_type_changed",
                "current_intent_no_longer_fits",
            },
        )
        self.INTENT_ALLOWED_COMPLETION_REASONS = self._get_csv_set(
            "intent_allowed_completion_reasons",
            {
                "goal_completed",
                "user_requested_stop",
                "user_requested_switch",
                "no_further_action_needed",
                "handoff_to_user",
            },
        )

        # Policy knobs for accepting legitimate transitions.
        self.INTENT_ALLOW_SWITCH_ON_USER_REQUEST = bool(
            self.settings.get("intent_allow_switch_on_user_request", True)
        )
        self.INTENT_ALLOW_SWITCH_ON_COMPLETION = bool(
            self.settings.get("intent_allow_switch_on_completion", True)
        )
        self.INTENT_ALLOW_SWITCH_ON_EXHAUSTION = bool(
            self.settings.get("intent_allow_switch_on_exhaustion", True)
        )
        self.INTENT_ALLOW_SWITCH_ON_WORK_TYPE_CHANGE = bool(
            self.settings.get("intent_allow_switch_on_work_type_change", True)
        )
        self.INTENT_ALLOW_SWITCH_ON_NO_LONGER_FITS = bool(
            self.settings.get("intent_allow_switch_on_no_longer_fits", True)
        )

        # If True, an exhausted current intent should no longer behave like a
        # prison that blocks all new intents merely because it once set
        # forbid_new_intent.
        self.INTENT_EXHAUSTION_OVERRIDES_FORBID_NEW = bool(
            self.settings.get("intent_exhaustion_overrides_forbid_new", True)
        )

        # Defect detector thresholds
        self.DEFECT_SAME_ACTION_REPEAT_THRESHOLD = self._get_positive_int(
            "defect_same_action_repeat_threshold", 3
        )
        self.DEFECT_ACTION_CYCLE_WINDOW = self._get_positive_int(
            "defect_action_cycle_window", 3
        )
        self.DEFECT_ACTION_HISTORY_WINDOW = self._get_positive_int(
            "defect_action_history_window", 12
        )
        self.DEFECT_LOW_VALUE_BROAD_SEARCH_REPEAT_THRESHOLD = self._get_positive_int(
            "defect_low_value_broad_search_repeat_threshold", 2
        )
        self.DEFECT_TOO_BROAD_SEARCH_THRESHOLD = self._get_positive_int(
            "defect_too_broad_search_threshold", 1
        )
        self.DEFECT_STRATEGY_EXHAUSTED_THRESHOLD = self._get_positive_int(
            "defect_strategy_exhausted_threshold", 3
        )

        # Existing phase/budget controls
        self.OBSERVE_PHASE_BUDGET = self._get_positive_int("observe_phase_budget", 8)
        self.MAX_ROOT_LISTINGS_PER_TURN = self._get_positive_int("max_root_listings_per_turn", 1)
        self.MAX_LIST_DIRECTORY_ACTIONS_PER_TURN = self._get_positive_int(
            "max_list_directory_actions_per_turn", 4
        )
        self.MAX_DIRECTORY_DESCENT_CHAIN = self._get_positive_int(
            "max_directory_descent_chain", 3
        )
        self.MAX_BROAD_RECON_BATCHES = self._get_positive_int("max_broad_recon_batches", 2)
        self.MULTI_FILE_PER_FILE_READ_ONLY_LIMIT = self._get_positive_int(
            "multi_file_per_file_read_only_limit", 3
        )

        # Task contract
        self.TASK_CONTRACT_FORCE_IMPLEMENT_FOR_HYBRID = bool(
            self.settings.get("task_contract_force_implement_for_hybrid", True)
        )

        # Compatibility / misc values expected by the rest of the codebase.
        self.default_model = self.settings.get("default_model", "gpt-5")
        self.max_history_tokens = self._get_positive_int("max_history_tokens", 16384)
        self.history_size = str(self.settings.get("history_size", "medium") or "medium").strip()
        self.autosummarize_requires_confirmation = bool(
            self.settings.get("autosummarize_requires_confirmation", False)
        )
        self.permission_policy = self.settings.get("permission_policy", "ask")
        self.PLANNER_ENABLED = bool(self.settings.get("planner_enabled", False))
        self.PLANNER_MODE = str(self.settings.get("planner_mode", "auto") or "auto")

        # Provider / networking settings
        self.ollama_base_url = str(
            self.settings.get("ollama_base_url", "http://127.0.0.1:11434")
        ).strip()

        # Operations that mutate repository / workspace state.
        # Required by action_dispatcher/state_machine compatibility layer.
        self.STATE_CHANGING_OPS = {
            "run_shell",
            "create_file",
            "replace",
            "edit_file",
            "write_file",
            "git_add",
            "git_commit",
            "git_checkout",
            "delete_file",
        }

    def _get_positive_int(self, key: str, default: int) -> int:
        value = self.settings.get(key, default)
        try:
            parsed = int(value)
            return parsed if parsed > 0 else int(default)
        except Exception:
            return int(default)

    def _get_float(self, key: str, default: float) -> float:
        value = self.settings.get(key, default)
        try:
            parsed = float(value)
            if parsed < 0:
                return float(default)
            return parsed
        except Exception:
            return float(default)

    def _get_csv_set(self, key: str, default: set[str]) -> set[str]:
        raw = self.settings.get(key)
        if raw is None:
            return set(default)
        if isinstance(raw, (list, tuple, set)):
            return {str(x).strip() for x in raw if str(x).strip()} or set(default)
        text = str(raw).strip()
        if not text:
            return set(default)
        parts = [p.strip() for p in text.split(",")]
        cleaned = {p for p in parts if p}
        return cleaned or set(default)