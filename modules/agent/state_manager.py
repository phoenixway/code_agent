"""Управління станом сесії агента."""

from __future__ import annotations

import json
import re
from dataclasses import asdict, is_dataclass

from .defect_detector import DefectDetector
from .intent_runtime import IntentRuntime
from .technical_interruptions import TechnicalInterruption, detect_technical_interruption

READ_ONLY_RECOVERY_ACTIONS = {
    "read_file",
    "read_chunk",
    "read_file_skeleton",
    "extract_kotlin_function",
    "extract_symbol",
    "search_content",
    "search_files",
    "list_directory",
    "find_files",
    "git_diff",
}

INTENTLESS_STATE_CHANGING_FILE_ACTIONS = {
    "write_file",
    "write_file_block",
    "append_file_block",
    "create_file",
    "edit_file",
    "delete_file",
    "replace",
}

BUILD_FAILURE_RE = re.compile(
    r"(?im)(?:^> Task .* FAILED$|compile(?:Debug|Release)?Kotlin FAILED|ksp\w*Kotlin|"
    r"Unresolved reference:|Compilation error|^e:\s+file://|FAILURE: Build failed)"
)
COMPILER_FILE_RE = re.compile(r"(?im)(?:file://)?(?P<path>[\w./-]+\.(?:kt|kts|java|groovy|xml))(?::\d+(?::\d+)?)?")
BUILD_STATUS_RE = re.compile(
    r"(?is)\b(build (?:was|is)?\s*(?:run|not run|passed|failed|green|red)|"
    r"ran\s+\.?/gradlew|assembledebug|compiledebugkotlin|build\s+(?:passed|failed|did not pass))\b"
)


class AgentState:
    """Зберігає динамічний стан агента: токени, циклічність, задачі."""

    ORCHESTRATION_TURN_LOCAL_FIELDS = (
        "readonly_steps_this_turn",
        "intent_only_response_count",
        "pending_suspect_intent_payload",
        "pending_goal_drift_payload",
        "allow_suspect_intent_once",
        "orchestration_trace",
        "orchestration_trace_sequence",
        "last_execution_plan",
        "last_execution_commit",
        "last_memory_board_parsed_count",
        "last_memory_board_accepted_count",
        "last_memory_board_rejected_count",
        "last_memory_update_done",
        "memory_tag_expected_next_step",
        "memory_tag_reason",
        "memory_tag_expected_intent_id",
        "current_turn_state_change_count",
        "current_turn_state_change_tools",
        "intentless_state_changing_file_write_count",
        "last_plan_subgoal_create_count",
        "reuse_only_intent_required",
        "reuse_only_blocked_action",
        "transition_only_intent_required",
        "transition_only_blocked_action",
        "intent_transition_defect_reason",
        "intent_transition_defect_universe",
        "intent_transition_defect_count",
        "think_reflection_repair_kind",
        "build_fix_last_build_ran",
        "build_fix_last_build_passed",
        "build_fix_last_build_command",
    )

    ORCHESTRATION_CROSS_TURN_FIELDS = (
        "pending_loop_stop_info",
        "terminal_plaintext_completion_pending",
        "terminal_plaintext_completion_text",
        "pending_finalize_after_terminal_plaintext_completion",
        "pending_finalize_completion_reason",
        "pending_finalize_completion_source",
        "last_resumable_intent_id",
        "last_resumable_intent_type",
        "last_resumable_intent_goal",
        "last_resumable_intent_allowed_actions",
        "last_resumable_intent_lineage_id",
        "last_resumable_intent_safe_steps_limit",
        "last_resumable_intent_retry_limit",
        "last_resumable_intent_completion_reason",
        "last_technical_interruption",
        "pending_resume_query",
        "build_fix_mode_active",
        "build_fix_mode_reason",
        "build_fix_error_summary",
        "build_fix_compiler_mentioned_files",
        "current_turn_id",
    )

    RESUMABLE_INTENT_FIELDS = (
        "last_resumable_intent_id",
        "last_resumable_intent_type",
        "last_resumable_intent_goal",
        "last_resumable_intent_allowed_actions",
        "last_resumable_intent_lineage_id",
        "last_resumable_intent_safe_steps_limit",
        "last_resumable_intent_retry_limit",
        "last_resumable_intent_completion_reason",
    )

    TECHNICAL_INTERRUPTION_FIELDS = (
        "last_technical_interruption",
        "pending_resume_query",
    )

    @classmethod
    def orchestration_state_field_groups(cls) -> dict[str, tuple[str, ...]]:
        return {
            "turn_local": cls.ORCHESTRATION_TURN_LOCAL_FIELDS,
            "cross_turn": cls.ORCHESTRATION_CROSS_TURN_FIELDS,
            "resumable": cls.RESUMABLE_INTENT_FIELDS,
            "technical_interruption": cls.TECHNICAL_INTERRUPTION_FIELDS,
        }

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
        self.last_schema_preflight_failure_fingerprint = ""
        self.consecutive_schema_preflight_failures = 0
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

        self.intent_runtime = IntentRuntime(config, state=self) if config is not None else None
        self.defect_detector = DefectDetector(config) if config is not None else None
        self.last_defect_info = None
        self._pending_loop_stop_info = None
        self.readonly_steps_this_turn = 0
        self.last_turn_had_failure = False
        self.intent_only_response_count = 0
        self.recent_problem_actions = []
        self.last_failed_edit_retry_turn_id = 0
        self.last_failed_edit_retry_command = None
        self.last_failed_edit_retry_fingerprint = ""
        self.last_failed_edit_retry_path = ""
        self.last_failed_edit_retry_search_text = ""
        self.last_fresh_edit_evidence_turn_id = 0
        self.last_fresh_edit_evidence_path = ""
        self.last_fresh_edit_evidence_action_type = ""
        self.last_fresh_edit_evidence_fingerprint = ""
        self.last_fresh_edit_evidence_excerpt = ""
        self.authorized_fresh_evidence_retry_consumed_key = ""
        self.pending_suspect_intent_payload = None
        self.pending_goal_drift_payload = None
        self.allow_suspect_intent_once = False
        self.memory_board_store = None
        self.memory_board_engine = None
        self.task_board = None
        self.task_board_enabled = False
        self.last_memory_board_parsed_count = 0
        self.last_memory_board_accepted_count = 0
        self.last_memory_board_rejected_count = 0
        self.last_memory_update_done = False
        self.memory_tag_expected_next_step = False
        self.memory_tag_reason = ""
        self.memory_tag_expected_intent_id = ""
        self.current_turn_state_change_count = 0
        self.current_turn_state_change_tools = []
        self.intentless_state_changing_file_write_count = 0
        self.last_plan_subgoal_create_count = 0
        self.reuse_only_intent_required = False
        self.reuse_only_blocked_action = ""
        self.transition_only_intent_required = False
        self.transition_only_blocked_action = ""
        self.intent_transition_defect_reason = ""
        self.intent_transition_defect_universe = ""
        self.intent_transition_defect_count = 0
        self.consecutive_nonproductive_thinking_count = 0
        self.last_nonproductive_thinking_reason = ""
        self.missing_think_reflection_warning_count = 0
        self.missing_think_reflection_warning_intent_id = ""
        self.malformed_think_count = 0
        self.malformed_think_intent_id = ""
        self.recovery_loop_handoff_count = 0
        self.recovery_loop_handoff_intent_id = ""
        self.recovery_loop_handoff_defect_kind = ""
        self.large_malformed_response_count = 0
        self.large_malformed_response_intent_id = ""
        self.large_malformed_response_kind = ""
        self.think_reflection_repair_kind = ""
        self.reread_blocked_path = ""
        self.reread_blocked_intent_id = ""
        self.reread_blocked_count = 0
        self.pending_edit_mismatch_path = ""
        self.pending_edit_mismatch_intent_id = ""
        self.pending_edit_mismatch_count = 0
        self.disallowed_action_repeat_type = ""
        self.disallowed_action_repeat_intent_id = ""
        self.disallowed_action_repeat_count = 0
        self.last_blocked_action_type = ""
        self.last_blocked_action_path = ""
        # FIXME:
        # This is a secondary/fallback signal only. When an active accepted
        # intent exists, downstream policy must prefer the active contract type
        # over last_completed_intent_type.
        self.last_completed_intent_type = ""
        self.terminal_plaintext_completion_pending = False
        self.terminal_plaintext_completion_text = ""
        self.pending_finalize_after_terminal_plaintext_completion = False
        self.pending_finalize_completion_reason = ""
        self.pending_finalize_completion_source = ""
        self.last_resumable_intent_id = ""
        self.last_resumable_intent_type = ""
        self.last_resumable_intent_goal = ""
        self.last_resumable_intent_allowed_actions = []
        self.last_resumable_intent_lineage_id = ""
        self.last_resumable_intent_safe_steps_limit = 0
        self.last_resumable_intent_retry_limit = 0
        self.last_resumable_intent_completion_reason = ""
        self.last_technical_interruption = None
        self.pending_resume_query = ""
        self.consecutive_nonproductive_thinking_count = 0
        self.last_nonproductive_thinking_reason = ""
        self.build_fix_mode_active = False
        self.build_fix_mode_reason = ""
        self.build_fix_error_summary = ""
        self.build_fix_compiler_mentioned_files = []
        self.build_fix_last_build_ran = False
        self.build_fix_last_build_passed = False
        self.build_fix_last_build_command = ""

        # Critical: this must advance across real user turns.
        # Working-material protection/degradation depends on it.
        self.current_turn_id = 0
        self.orchestration_trace = []
        self.orchestration_trace_sequence = 0
        self.last_execution_plan = None
        self.last_execution_commit = None
        self.operational_journal = []
        self.operational_journal_sequence = 0
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
        command = value.get("command") if isinstance(value.get("command"), dict) else {}
        path = str(command.get("path") or "").strip()
        active_intent = self.active_intent
        intent_id = str(getattr(active_intent, "intent_id", "") or "").strip()
        if reason in {"reread_already_in_history", "reread_already_in_history_use_existing_content"} and path:
            if self.reread_blocked_path != path or self.reread_blocked_intent_id != intent_id:
                self.reread_blocked_count = 0
            self.reread_blocked_path = path
            self.reread_blocked_intent_id = intent_id
            self.reread_blocked_count = int(self.reread_blocked_count or 0) + 1
        elif reason:
            self.reread_blocked_path = ""
            self.reread_blocked_intent_id = ""
            self.reread_blocked_count = 0
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
        self.last_execution_plan = None
        self.last_execution_commit = None
        self.last_memory_board_parsed_count = 0
        self.last_memory_board_accepted_count = 0
        self.last_memory_board_rejected_count = 0
        self.last_memory_update_done = False
        self.memory_tag_expected_next_step = False
        self.memory_tag_reason = ""
        self.memory_tag_expected_intent_id = ""
        self.current_turn_state_change_count = 0
        self.current_turn_state_change_tools = []
        self.intentless_state_changing_file_write_count = 0
        self.last_plan_subgoal_create_count = 0
        self.reuse_only_intent_required = False
        self.reuse_only_blocked_action = ""
        self.transition_only_intent_required = False
        self.transition_only_blocked_action = ""
        self.intent_transition_defect_reason = ""
        self.intent_transition_defect_universe = ""
        self.intent_transition_defect_count = 0
        self.think_reflection_repair_kind = ""
        # FIXME:
        # This is a secondary/fallback signal only. When an active accepted
        # intent exists, downstream policy must prefer the active contract type
        # over last_completed_intent_type.
        self.last_completed_intent_type = ""
        self.build_fix_last_build_ran = False
        self.build_fix_last_build_passed = False
        self.build_fix_last_build_command = ""

        # Forced plain-text completion is a recovery latch for the previous
        # turn. A fresh user turn must not inherit an exhausted contract that
        # should already have been closed by the canonical forced-completion path.
        self.finalize_pending_forced_plaintext_completion_if_needed()
        if self.intent_runtime is not None and self.intent_runtime.active_intent is not None:
            self.intent_runtime.active_intent.force_plaintext_completion = False
            # Hard-limit overrun escalation is also turn-local. A fresh user
            # turn may continue the same contract, but it should not start in a
            # pre-escalated "repeated overrun" state.
            self.intent_runtime.active_intent.hard_limit_hit_count = 0

        # FIX:
        # Do not reset to 0. Each new user turn must get a new turn id so that
        # previous turn_working_material can degrade normally.
        self.current_turn_id = int(self.current_turn_id or 0) + 1

        if self.defect_detector:
            self.defect_detector.reset()

    def append_operational_journal_entry(self, entry: dict) -> dict:
        payload = dict(entry or {})
        sequence = int(getattr(self, "operational_journal_sequence", 0) or 0) + 1
        self.operational_journal_sequence = sequence
        payload.setdefault("sequence", sequence)
        payload.setdefault("turn_id", int(getattr(self, "current_turn_id", 0) or 0))
        journal = list(getattr(self, "operational_journal", []) or [])
        journal.append(payload)
        max_entries = 25
        if len(journal) > max_entries:
            journal = journal[-max_entries:]
        self.operational_journal = journal
        return payload

    def operational_journal_snapshot(self) -> list[dict]:
        snapshot: list[dict] = []
        for entry in list(getattr(self, "operational_journal", []) or []):
            if isinstance(entry, dict):
                snapshot.append(dict(entry))
            elif is_dataclass(entry):
                snapshot.append(asdict(entry))
            elif hasattr(entry, "__dict__"):
                snapshot.append(dict(vars(entry)))
            else:
                snapshot.append({"value": str(entry)})
        return snapshot

    def mark_pending_forced_plaintext_completion_close(self, reason: str = "forced_plaintext_completion", source: str = "") -> None:
        self.pending_finalize_after_terminal_plaintext_completion = True
        self.pending_finalize_completion_reason = str(reason or "forced_plaintext_completion").strip()
        self.pending_finalize_completion_source = str(source or "").strip()

    def clear_pending_forced_plaintext_completion_close(self) -> None:
        self.pending_finalize_after_terminal_plaintext_completion = False
        self.pending_finalize_completion_reason = ""
        self.pending_finalize_completion_source = ""

    def clear_task_board(self) -> None:
        self.task_board = None
        self.task_board_enabled = False

    def _reconcile_task_board_after_intent_transition(self) -> None:
        board = getattr(self, "task_board", None)
        if not isinstance(board, dict):
            return
        active_intent = self.active_intent
        if active_intent is None:
            self.clear_task_board()
            return
        runtime = self.intent_runtime
        info = getattr(runtime, "last_transition_info", {}) if runtime is not None else {}
        same_lineage = bool(info.get("same_lineage")) if isinstance(info, dict) else False
        if not same_lineage:
            self.clear_task_board()
            return
        intent_id = str(getattr(active_intent, "intent_id", "") or "").strip()
        lineage_id = str(getattr(active_intent, "lineage_id", "") or intent_id or "").strip()
        board["intent_id"] = intent_id
        board["lineage_id"] = lineage_id
        self.task_board = board
        self.task_board_enabled = bool(board.get("steps"))

    def _capture_recent_resumable_intent_from_active(self, active_intent, completion_reason: str = "forced_plaintext_completion") -> None:
        if active_intent is None:
            return
        self.last_resumable_intent_id = str(getattr(active_intent, "intent_id", "") or "")
        self.last_resumable_intent_type = str(getattr(active_intent, "intent_type", "") or "")
        self.last_resumable_intent_goal = str(getattr(active_intent, "goal", "") or "")
        self.last_resumable_intent_allowed_actions = list(getattr(active_intent, "allowed_actions", []) or [])
        self.last_resumable_intent_lineage_id = str(getattr(active_intent, "lineage_id", "") or getattr(active_intent, "intent_id", "") or "")
        self.last_resumable_intent_safe_steps_limit = int(getattr(active_intent, "safe_steps_limit", 0) or 0)
        self.last_resumable_intent_retry_limit = int(getattr(active_intent, "retry_limit", 0) or 0)
        self.last_resumable_intent_completion_reason = str(completion_reason or "forced_plaintext_completion")
        self.last_completed_intent_type = str(getattr(active_intent, "intent_type", "") or "").strip().upper()

    def close_active_intent_as_resumable(
        self,
        completion_reason: str = "interrupted_resumable",
        *,
        clear_pending_stop: bool = True,
    ) -> bool:
        active_intent = self.active_intent
        if active_intent is None:
            if clear_pending_stop:
                self.pending_loop_stop_info = None
            return False

        self._capture_recent_resumable_intent_from_active(active_intent, completion_reason)

        finalized = False
        runtime = self.intent_runtime
        if runtime is not None:
            finalizer = getattr(runtime, "finalize_current_intent_completion", None)
            if callable(finalizer):
                try:
                    finalized = bool(finalizer())
                except Exception:
                    finalized = False
            if not finalized:
                try:
                    runtime.active_intent = None
                    runtime.clear_requirement()
                    finalized = True
                except Exception:
                    finalized = False

        if finalized:
            self.clear_task_board()
        if clear_pending_stop:
            self.pending_loop_stop_info = None
        return finalized

    def finalize_pending_forced_plaintext_completion_if_needed(self) -> bool:
        if not bool(getattr(self, "pending_finalize_after_terminal_plaintext_completion", False)):
            return False

        completion_reason = str(getattr(self, "pending_finalize_completion_reason", "forced_plaintext_completion") or "forced_plaintext_completion")
        finalized = self.close_active_intent_as_resumable(
            completion_reason,
            clear_pending_stop=True,
        )

        self.clear_pending_forced_plaintext_completion_close()
        return finalized

    def note_intent_only_response(self):
        self.intent_only_response_count += 1

    def _extract_build_failure_files(self, text: str) -> list[str]:
        files: list[str] = []
        for match in BUILD_FAILURE_RE.finditer(str(text or "")):
            _ = match
        for match in COMPILER_FILE_RE.finditer(str(text or "")):
            path = str(match.group("path") or "").strip()
            if not path:
                continue
            if path.startswith("/"):
                marker = "/app/"
                if marker in path:
                    path = path[path.index(marker) + 1 :]
            if path not in files:
                files.append(path)
        return files

    def note_build_failure_from_text(self, text: str, *, reason: str = "build_failure_requires_formal_intent") -> bool:
        raw = str(text or "")
        if not raw or not BUILD_FAILURE_RE.search(raw):
            return False
        files = self._extract_build_failure_files(raw)
        self.build_fix_mode_active = True
        self.build_fix_mode_reason = str(reason or "build_failure_requires_formal_intent").strip()
        self.build_fix_error_summary = "Fix current Android compile errors."
        self.build_fix_compiler_mentioned_files = files
        self.build_fix_last_build_ran = True
        self.build_fix_last_build_passed = False
        self.build_fix_last_build_command = "./gradlew :app:assembleDebug"
        return True

    def clear_build_fix_mode(self) -> None:
        self.build_fix_mode_active = False
        self.build_fix_mode_reason = ""
        self.build_fix_error_summary = ""
        self.build_fix_compiler_mentioned_files = []
        self.build_fix_last_build_ran = False
        self.build_fix_last_build_passed = False
        self.build_fix_last_build_command = ""

    def build_fix_mode_requires_intent(self) -> bool:
        return bool(self.build_fix_mode_active and self.active_intent is None)

    def is_build_fix_intent_active(self) -> bool:
        active = self.active_intent
        if active is None:
            return False
        if not self.build_fix_mode_active:
            return False
        goal = str(getattr(active, "goal", "") or "").lower()
        intent_type = str(getattr(active, "intent_type", "") or "").strip().upper()
        return intent_type == "MODIFY" and ("build" in goal or "compile" in goal or "ksp" in goal)

    def compiler_mentioned_file_allowed(self, path: str) -> bool:
        normalized = str(path or "").strip()
        if not normalized:
            return False
        files = [str(item or "").strip() for item in (self.build_fix_compiler_mentioned_files or []) if str(item or "").strip()]
        return normalized in files

    def build_fix_final_answer_has_build_status(self, text: str) -> bool:
        return bool(BUILD_STATUS_RE.search(str(text or "")))

    def note_technical_interruption(self, interruption: TechnicalInterruption | dict | str | None, current_query: str = "") -> None:
        detected = detect_technical_interruption(interruption)
        raw = interruption
        if detected is None and isinstance(raw, dict):
            payload = dict(raw)
            detected = TechnicalInterruption(
                kind=str(payload.get("kind") or "technical_interruption"),
                provider=str(payload.get("provider") or "").strip() or None,
                status_code=payload.get("status_code"),
                message=str(payload.get("message") or "Technical interruption").strip(),
                recoverable=bool(payload.get("recoverable", True)),
                retryable=bool(payload.get("retryable", True)),
                retry_after_seconds=payload.get("retry_after_seconds"),
                details=payload.get("details"),
            )
        if detected is None:
            text = str(interruption or "").strip()
            if not text:
                self.last_technical_interruption = None
                self.pending_resume_query = str(current_query or "")
                return
            detected = TechnicalInterruption(
                kind="technical_interruption",
                message=text,
            )

        active_intent = self.active_intent
        last_resumable_intent_id = str(getattr(self, "last_resumable_intent_id", "") or "").strip() or None
        active_intent_id = str(getattr(active_intent, "intent_id", "") or "").strip() or None
        detected.active_intent_id = active_intent_id
        detected.resumable_intent_id = active_intent_id or last_resumable_intent_id
        detected.resumable = bool(detected.resumable_intent_id)

        self.last_technical_interruption = detected
        self.pending_resume_query = str(current_query or "")

    def clear_technical_interruption(self) -> None:
        self.last_technical_interruption = None
        self.pending_resume_query = ""

    def technical_interruption_snapshot(self) -> dict:
        interruption = getattr(self, "last_technical_interruption", None)
        if interruption is None:
            return {}
        if is_dataclass(interruption):
            return asdict(interruption)
        if isinstance(interruption, dict):
            return dict(interruption)
        return {"message": str(interruption)}

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

    def _action_type(self, command: dict) -> str:
        return str((command or {}).get("type") or (command or {}).get("action") or "").strip().lower()

    def _action_path(self, command: dict) -> str:
        return str((command or {}).get("path") or (command or {}).get("file") or "").strip()

    def _result_excerpt(self, result: dict) -> str:
        return str(
            (result or {}).get("file_content")
            or (result or {}).get("output")
            or (result or {}).get("raw_output")
            or (result or {}).get("stdout_full")
            or ""
        )[:8000]

    def _same_retry_target(self, left: str, right: str) -> bool:
        left = str(left or "").strip()
        right = str(right or "").strip()
        if not left or not right:
            return False
        return left == right or left.endswith("/" + right) or right.endswith("/" + left)

    def note_failed_edit_retry_candidate(self, command: dict) -> None:
        cmd_type = self._action_type(command)
        if cmd_type not in {"edit_file", "write_file", "write_file_block", "append_file_block", "replace"}:
            return
        self.last_failed_edit_retry_turn_id = int(getattr(self, "current_turn_id", 0) or 0)
        self.last_failed_edit_retry_command = command.copy()
        self.last_failed_edit_retry_fingerprint = self.get_action_fingerprint(command)
        self.last_failed_edit_retry_path = self._action_path(command)
        self.last_failed_edit_retry_search_text = str((command or {}).get("search_text") or "")
        self.last_fresh_edit_evidence_turn_id = 0
        self.last_fresh_edit_evidence_path = ""
        self.last_fresh_edit_evidence_action_type = ""
        self.last_fresh_edit_evidence_fingerprint = ""
        self.last_fresh_edit_evidence_excerpt = ""
        self.authorized_fresh_evidence_retry_consumed_key = ""

    def note_fresh_edit_evidence_if_applicable(self, command: dict, result: dict) -> None:
        if str((result or {}).get("status") or "").strip().lower() != "success":
            return
        cmd_type = self._action_type(command)
        if cmd_type not in {"read_file", "read_chunk", "extract_symbol", "extract_kotlin_function", "search_content"}:
            return
        path = self._action_path(command)
        failed_path = str(getattr(self, "last_failed_edit_retry_path", "") or "").strip()
        failed_turn = int(getattr(self, "last_failed_edit_retry_turn_id", 0) or 0)
        current_turn = int(getattr(self, "current_turn_id", 0) or 0)
        if not failed_turn or current_turn <= failed_turn:
            return
        if not self._same_retry_target(path, failed_path):
            output = self._result_excerpt(result)
            if not failed_path or failed_path not in output:
                return
        self.last_fresh_edit_evidence_turn_id = current_turn
        self.last_fresh_edit_evidence_path = path or failed_path
        self.last_fresh_edit_evidence_action_type = cmd_type
        self.last_fresh_edit_evidence_fingerprint = self.get_action_fingerprint(command)
        self.last_fresh_edit_evidence_excerpt = self._result_excerpt(result)

    def _retry_payload_materially_changed(self, command: dict) -> bool:
        current_fingerprint = self.get_action_fingerprint(command)
        failed_fingerprint = str(getattr(self, "last_failed_edit_retry_fingerprint", "") or "")
        if current_fingerprint and failed_fingerprint and current_fingerprint != failed_fingerprint:
            return True

        search_text = str((command or {}).get("search_text") or "")
        failed_search_text = str(getattr(self, "last_failed_edit_retry_search_text", "") or "")
        evidence = str(getattr(self, "last_fresh_edit_evidence_excerpt", "") or "")
        return bool(search_text and search_text != failed_search_text and search_text in evidence)

    def consume_authorized_fresh_evidence_retry_exemption(self, command: dict, defect_reason: str) -> bool:
        if str(defect_reason or "") not in {"defect_same_action_repeat", "defect_repeated_action_cycle"}:
            return False
        cmd_type = self._action_type(command)
        if cmd_type not in {"edit_file", "write_file", "write_file_block", "append_file_block", "replace"}:
            return False

        failed_turn = int(getattr(self, "last_failed_edit_retry_turn_id", 0) or 0)
        fresh_turn = int(getattr(self, "last_fresh_edit_evidence_turn_id", 0) or 0)
        current_turn = int(getattr(self, "current_turn_id", 0) or 0)
        if not failed_turn or current_turn <= failed_turn:
            return False
        if fresh_turn != current_turn or fresh_turn <= failed_turn:
            return False
        if not self._same_retry_target(self._action_path(command), getattr(self, "last_failed_edit_retry_path", "")):
            return False
        if not self._retry_payload_materially_changed(command):
            return False

        key = "|".join(
            [
                str(failed_turn),
                str(fresh_turn),
                str(getattr(self, "last_fresh_edit_evidence_fingerprint", "") or ""),
                self.get_action_fingerprint(command),
            ]
        )
        if key and key == str(getattr(self, "authorized_fresh_evidence_retry_consumed_key", "") or ""):
            return False
        self.authorized_fresh_evidence_retry_consumed_key = key
        self.consecutive_same_action_count = 0
        self.last_completed_fingerprint = None
        return True

    def _latest_operational_journal_action_command(self) -> dict:
        snapshotter = getattr(self, "operational_journal_snapshot", None)
        if callable(snapshotter):
            try:
                snapshot = snapshotter() or []
                for entry in reversed(snapshot):
                    if not isinstance(entry, dict):
                        continue
                    if str(entry.get("kind") or "").strip() != "tool_execution_commit":
                        continue
                    action_type = str(entry.get("action_type") or "").strip()
                    target = str(entry.get("target") or "").strip()
                    if action_type:
                        command = {"type": action_type}
                        if target:
                            command["path"] = target
                        return command
            except Exception:
                pass
        for entry in reversed(list(getattr(self, "operational_journal", []) or [])):
            if hasattr(entry, "__dict__"):
                try:
                    entry = dict(vars(entry))
                except Exception:
                    continue
            if not isinstance(entry, dict):
                continue
            if str(entry.get("kind") or "").strip() != "tool_execution_commit":
                continue
            action_type = str(entry.get("action_type") or "").strip()
            target = str(entry.get("target") or "").strip()
            if action_type:
                command = {"type": action_type}
                if target:
                    command["path"] = target
                return command
        return {}

    def _suspicion_context_command(self) -> dict:
        command = getattr(self, "last_failed_action_command", None)
        if isinstance(command, dict) and command:
            return command.copy()
        command = self._latest_operational_journal_action_command()
        if isinstance(command, dict) and command:
            return command.copy()
        recent = self.recent_problem_actions[-1] if self.recent_problem_actions else {}
        if isinstance(recent, dict):
            command = recent.get("command")
            if isinstance(command, dict) and command:
                return command.copy()
        return {}

    def attach_config(self, config):
        self._config = config
        if self.intent_runtime is None:
            self.intent_runtime = IntentRuntime(config, state=self)
        else:
            self.intent_runtime.config = config
            self.intent_runtime.state = self
        
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

    def has_exhausted_active_intent(self) -> bool:
        return self.has_hard_exhausted_active_intent()

    def active_intent_hard_steps_remaining(self) -> int:
        runtime = self.intent_runtime
        active = runtime.active_intent if runtime is not None else None
        if active is None or runtime is None:
            return 0
        getter = getattr(runtime, "_effective_hard_limit", None)
        if callable(getter):
            try:
                return max(0, int(getter()) - int(getattr(active, "step_count", 0) or 0))
            except Exception:
                return 0
        return 0

    def has_hard_exhausted_active_intent(self) -> bool:
        runtime = self.intent_runtime
        active = runtime.active_intent if runtime is not None else None
        if active is None or runtime is None:
            return False
        checker = getattr(runtime, "can_soft_continue_after_step_limit", None)
        if callable(checker):
            try:
                return not bool(checker()) and self.active_intent_hard_steps_remaining() <= 0
            except Exception:
                return False
        return False

    def apply_intent_contract(self, payload: dict, config, *, bypass_suspicion: bool = False) -> tuple[bool, str]:
        self.attach_config(config)
        if not self.intent_runtime:
            return False, "intent_runtime_unavailable"
        try:
            self.intent_runtime.last_apply_warning = ""
            self.intent_runtime.last_transition_info = {}
        except Exception:
            pass

        contract, transition_info, error = self.intent_runtime.inspect_transition(payload)
        if error:
            try:
                self.intent_runtime.last_transition_info = {
                    "transition": "rejected",
                    "transition_applied": False,
                    "reason": error,
                }
            except Exception:
                pass
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
                    "command": self._suspicion_context_command(),
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
                try:
                    self.intent_runtime.last_transition_info = {
                        "transition": "rejected",
                        "transition_applied": False,
                        "reason": "suspect_intent_goal_drift" if goal_core_loss else "suspect_intent_relabel_repeat",
                        "same_lineage": bool(transition_info.get("same_lineage")),
                    }
                except Exception:
                    pass
                return False, "suspect_intent_goal_drift" if goal_core_loss else "suspect_intent_relabel_repeat"

        ok, msg = self.intent_runtime.apply_payload(payload)
        if ok:
            self.pending_suspect_intent_payload = None
            self.pending_goal_drift_payload = None
            self._reconcile_task_board_after_intent_transition()
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

    def record_schema_preflight_failure(self, command: dict, schema_stop: dict) -> int:
        """Record malformed action preflight failures that stop before tool dispatch."""
        command = command if isinstance(command, dict) else {}
        schema_stop = schema_stop if isinstance(schema_stop, dict) else {}
        snapshot = schema_stop.get("validation_snapshot") if isinstance(schema_stop.get("validation_snapshot"), dict) else {}
        command_type = str(command.get("type") or command.get("action") or snapshot.get("action_type") or "").strip()
        path = str(command.get("path") or "").strip()
        missing = tuple(str(item) for item in snapshot.get("missing_fields", []) or [])
        forbidden = tuple(str(item) for item in snapshot.get("forbidden_fields", []) or [])
        fingerprint = json.dumps(
            {
                "type": command_type,
                "path": path,
                "reason": str(schema_stop.get("reason") or ""),
                "error_code": str(schema_stop.get("error_code") or ""),
                "missing_fields": missing,
                "forbidden_fields": forbidden,
            },
            sort_keys=True,
        )

        if fingerprint == self.last_schema_preflight_failure_fingerprint:
            self.consecutive_schema_preflight_failures += 1
        else:
            self.consecutive_schema_preflight_failures = 1
        self.last_schema_preflight_failure_fingerprint = fingerprint

        result = {
            "status": "error",
            "error_code": schema_stop.get("error_code"),
            "recoverable": True,
            "output": schema_stop.get("message", ""),
            "next_actions": list(schema_stop.get("next_actions") or []),
            "error_details": {
                "reason": schema_stop.get("reason"),
                "action_type": command_type,
                "path": path,
                "missing_fields": list(missing),
                "forbidden_fields": list(forbidden),
                "schema_preflight": True,
            },
        }

        self.last_error_code = schema_stop.get("error_code")
        self.last_error_message = schema_stop.get("message", "")
        self.last_error_recoverable = True
        self.last_error_next_actions = list(schema_stop.get("next_actions") or [])
        self.last_failed_action_command = command.copy()
        self.last_failed_action_result = result
        self.consecutive_same_error_count = self.consecutive_schema_preflight_failures
        return self.consecutive_schema_preflight_failures

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

    def reset_turn_scoped_repeat_guards(self):
        """Clear repeat-action tripwires at a real user turn boundary without clearing session context."""
        self.consecutive_same_action_count = 0
        self.last_completed_fingerprint = None
        self.forbidden_next_action_fingerprint = None

    def _result_confirms_state_change(self, command: dict, result: dict) -> bool:
        cmd_type = str(command.get("type") or command.get("action") or "").strip().lower()
        status = str(result.get("status") or "").strip().lower()
        if status != "success":
            return False

        if cmd_type in {"create_file", "write_file", "write_file_block", "append_file_block", "edit_file", "replace"}:
            return True

        if cmd_type != "run_shell":
            return False

        evidence = " ".join(
            str(result.get(key) or "")
            for key in ("output", "stdout", "stdout_full")
        ).lower()
        if not evidence.strip():
            return False
        positive_markers = (
            "changes applied",
            "changed ",
            "updated ",
            "modified ",
            "created ",
            "deleted ",
            "renamed ",
            "wrote ",
            "patched ",
            "applied ",
        )
        return any(marker in evidence for marker in positive_markers)

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
        state_change_confirmed = self._result_confirms_state_change(command, result)
        is_readonly = cmd_type in READ_ONLY_RECOVERY_ACTIONS or (cmd_type == "run_shell" and "command" in command)
        if is_readonly:
            self.readonly_steps_this_turn += 1
        if state_change_confirmed:
            self.current_turn_state_change_count += 1
            self.current_turn_state_change_tools.append(cmd_type)
            if self.active_intent is None and cmd_type in INTENTLESS_STATE_CHANGING_FILE_ACTIONS:
                self.intentless_state_changing_file_write_count += 1

        if cmd_type == "run_shell":
            command_text = str(command.get("command") or "").strip()
            output_text = " ".join(
                str(result.get(key) or "")
                for key in ("output", "stdout", "stdout_full", "raw_output")
            )
            if BUILD_FAILURE_RE.search(output_text):
                self.note_build_failure_from_text(output_text)
                self.build_fix_last_build_command = command_text or "./gradlew :app:assembleDebug"
            elif "gradlew" in command_text and "assembleDebug" in command_text and str(status or "").strip().lower() == "success":
                self.build_fix_last_build_ran = True
                self.build_fix_last_build_passed = True
                self.build_fix_last_build_command = command_text

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
            self.note_failed_edit_retry_candidate(command)
            if cmd_type == "edit_file" and error_code == "VALIDATION_ERROR":
                details = result.get("error_details") or {}
                mismatch_type = str(details.get("mismatch_type") or "").strip()
                if mismatch_type in {"no_similar_block_found", "search_text_stale_or_block_modified", "whitespace_mismatch"}:
                    active_intent = self.active_intent
                    self.pending_edit_mismatch_path = str(command.get("path") or "").strip()
                    self.pending_edit_mismatch_intent_id = str(getattr(active_intent, "intent_id", "") or "").strip()
                    self.pending_edit_mismatch_count = int(self.pending_edit_mismatch_count or 0) + 1
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
            self.note_fresh_edit_evidence_if_applicable(command, result)
            if cmd_type in {"read_file", "read_chunk"}:
                path = str(command.get("path") or "").strip()
                if path and path == str(self.pending_edit_mismatch_path or "").strip():
                    self.pending_edit_mismatch_path = ""
                    self.pending_edit_mismatch_intent_id = ""
                    self.pending_edit_mismatch_count = 0

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

        if defect_info is not None and self.consume_authorized_fresh_evidence_retry_exemption(
            command,
            str(defect_info.get("reason") or ""),
        ):
            defect_info = None

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
