"""Intent requirement policy for orchestrator actions."""

from __future__ import annotations


class IntentGuard:
    READ_ONLY_TOOLS = {
        "read_file",
        "read_chunk",
        "read_file_skeleton",
        "search_content",
        "search_files",
        "list_directory",
        "find_files",
        "git_diff",
        "run_shell",
    }

    SOFT_RECOVERABLE_ERROR_CODES = {
        "MALFORMED_READ_CHUNK_PAYLOAD",
        "MALFORMED_READ_FILE_PAYLOAD",
        "MALFORMED_READ_FILE_SKELETON_PAYLOAD",
        "TOOL_ARGUMENT_ERROR",
        "VALIDATION_ERROR",
    }

    def _is_rootish_path(self, path: object) -> bool:
        return isinstance(path, str) and path.strip() in {"", ".", "./", "/"}

    def _is_read_only_shell(self, command: str) -> bool:
        if not isinstance(command, str):
            return False
        lowered = command.strip().lower()
        if not lowered:
            return False
        if any(
            tok in lowered
            for tok in (
                ">",
                "| tee",
                ">>",
                "sed -i",
                "perl -i",
                "mkdir ",
                "rm ",
                "mv ",
                "cp ",
                "touch ",
            )
        ):
            return False
        bins = ("find ", "rg ", "grep ", "ls ", "cat ", "head ", "tail ", "wc ", "stat ", "file ")
        return lowered.startswith(bins)

    def _user_task_requires_intent(self, user_input: str) -> bool:
        text = (user_input or "").lower()
        keywords = (
            "знайти",
            "з’ясувати",
            "з'ясувати",
            "встановити",
            "порівняти",
            "перевірити",
            "класифікувати",
            "дослідити",
            "структур",
            "залежност",
            "точк",
            "entrypoint",
            "використання файлів",
            "file usage",
            "dependencies",
            "structure",
            "verify",
            "classify",
            "investigate",
            "find",
            "determine",
            "establish",
            "compare",
        )
        cleanup = ("cleanup", "stale", "obsolete", "delete", "remove", "застар", "видалити", "прибрати")
        return any(k in text for k in keywords) or any(k in text for k in cleanup)

    def _current_intent_allows_action(self, command: dict, state) -> bool:
        cmd_type = command.get("type") or command.get("action") or "unknown"
        active_intent = getattr(state, "active_intent", None)
        if active_intent is None:
            return False
        allowed = set(getattr(active_intent, "allowed_actions", []) or [])
        return cmd_type in allowed

    def _is_soft_recoverable_retry_context(self, state) -> bool:
        code = str(getattr(state, "last_error_code", "") or "").strip().upper()
        if code not in self.SOFT_RECOVERABLE_ERROR_CODES:
            return False
        if code == "VALIDATION_ERROR":
            return bool(getattr(state, "last_error_recoverable", False))
        return True

    def _should_require_new_intent_after_failure(self, command: dict, state) -> bool:
        """
        Failure-aware gate:
        - no retry context -> no new intent required
        - if current intent still covers this action and failure is a soft
          recoverable payload/argument/validation issue, allow continuation
        - if runtime explicitly says current intent can continue, allow continuation
        - otherwise require formal retry/continuation intent
        """
        has_retry_context = getattr(state, "has_retry_context", None)
        if not callable(has_retry_context) or not has_retry_context():
            return False

        if self._current_intent_allows_action(command, state) and self._is_soft_recoverable_retry_context(state):
            return False

        can_continue = getattr(state, "can_continue_current_intent_after_failure", None)
        if callable(can_continue) and can_continue():
            return False

        return True

    def action_requires_intent(
        self,
        command: dict,
        state,
        *,
        batch_size: int,
        current_user_input: str,
    ) -> tuple[bool, str]:
        cmd_type = command.get("type") or command.get("action") or "unknown"
        path = command.get("path")
        current_intent_allows = self._current_intent_allows_action(command, state)

        if getattr(state, "intent_required_until_activated", False):
            return True, getattr(state, "intent_required_reason", "intent_required")

        if current_intent_allows:
            if self._should_require_new_intent_after_failure(command, state):
                return True, "retry_or_continuation_after_failure"
            return False, ""

        if cmd_type in self.READ_ONLY_TOOLS and self._user_task_requires_intent(current_user_input):
            return True, "investigation_task_requires_formal_intent"

        if cmd_type in self.READ_ONLY_TOOLS:
            if batch_size > 2:
                return True, "read_only_multi_step_requires_intent"
            if batch_size > 1:
                return True, "read_only_batch_requires_intent"
            if getattr(state, "readonly_steps_this_turn", 0) > 0 and not current_intent_allows:
                return True, "not_first_read_only_step_requires_intent"

        if cmd_type == "list_directory" and self._is_rootish_path(path):
            return True, "broad_root_listing_requires_intent"
        if cmd_type == "search_content" and self._is_rootish_path(path):
            return True, "broad_search_content_requires_intent"
        if cmd_type == "search_files" and self._is_rootish_path(path):
            return True, "broad_search_files_requires_intent"
        if cmd_type == "run_shell" and self._is_read_only_shell(command.get("command", "")):
            cmd = str(command.get("command") or "").lower()
            if any(tok in cmd for tok in ("find .", "rg ", "grep -r", "grep -rn", "grep -r ", "grep -R")):
                return True, "broad_shell_search_requires_intent"

        if self._should_require_new_intent_after_failure(command, state):
            return True, "retry_or_continuation_after_failure"

        return False, ""