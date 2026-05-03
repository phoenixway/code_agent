"""State adapter for action-policy runtime decisions."""

from __future__ import annotations


class ActionPolicyStateAdapter:
    def __init__(self, state):
        self.state = state

    def active_intent(self):
        return getattr(self.state, "active_intent", None)

    def current_active_intent_id(self) -> str:
        active_intent = self.active_intent()
        return str(getattr(active_intent, "intent_id", "") or "").strip()

    def require_intent(self, reason: str) -> None:
        require_intent = getattr(self.state, "require_intent", None)
        if callable(require_intent):
            require_intent(reason)

    def build_fix_mode_requires_intent(self) -> bool:
        checker = getattr(self.state, "build_fix_mode_requires_intent", None)
        return bool(checker()) if callable(checker) else False

    def is_build_fix_intent_active(self) -> bool:
        checker = getattr(self.state, "is_build_fix_intent_active", None)
        return bool(checker()) if callable(checker) else False

    def build_fix_error_summary(self) -> str:
        return str(getattr(self.state, "build_fix_error_summary", "") or "")

    def build_fix_compiler_mentioned_files(self) -> list[str]:
        return list(getattr(self.state, "build_fix_compiler_mentioned_files", []) or [])

    def compiler_mentioned_file_allowed(self, path: str) -> bool:
        checker = getattr(self.state, "compiler_mentioned_file_allowed", None)
        if not callable(checker):
            return False
        try:
            return bool(checker(str(path or "").strip()))
        except Exception:
            return False

    def note_disallowed_action_repeat(self, action_type: str) -> int:
        normalized = str(action_type or "").strip().lower()
        intent_id = self.current_active_intent_id()
        current_type = str(getattr(self.state, "disallowed_action_repeat_type", "") or "").strip().lower()
        current_intent = str(getattr(self.state, "disallowed_action_repeat_intent_id", "") or "").strip()
        count = int(getattr(self.state, "disallowed_action_repeat_count", 0) or 0)
        if normalized != current_type or intent_id != current_intent:
            count = 0
        count += 1
        self._safe_set("disallowed_action_repeat_type", normalized)
        self._safe_set("disallowed_action_repeat_intent_id", intent_id)
        self._safe_set("disallowed_action_repeat_count", count)
        return count

    def clear_disallowed_action_repeat(self) -> None:
        self._safe_set("disallowed_action_repeat_type", "")
        self._safe_set("disallowed_action_repeat_intent_id", "")
        self._safe_set("disallowed_action_repeat_count", 0)
        self._safe_set("last_blocked_action_type", "")
        self._safe_set("last_blocked_action_path", "")

    def record_blocked_action(self, action_type: str, path: str = "") -> None:
        self._safe_set("last_blocked_action_type", str(action_type or "").strip())
        self._safe_set("last_blocked_action_path", str(path or "").strip())

    def set_reuse_only_intent_required(self, value: bool, blocked_action: str = "") -> None:
        self._safe_set("reuse_only_intent_required", bool(value))
        self._safe_set("reuse_only_blocked_action", str(blocked_action or "").strip() if value else "")

    def set_transition_only_intent_required(self, value: bool, blocked_action: str = "") -> None:
        self._safe_set("transition_only_intent_required", bool(value))
        self._safe_set("transition_only_blocked_action", str(blocked_action or "").strip() if value else "")

    def mark_terminal_plaintext_handoff(self, text: str, reason: str) -> None:
        normalized_text = str(text or "").strip()
        if not normalized_text:
            return
        self._safe_set("terminal_plaintext_completion_pending", True)
        self._safe_set("terminal_plaintext_completion_text", normalized_text)
        marker = getattr(self.state, "mark_pending_forced_plaintext_completion_close", None)
        if callable(marker):
            try:
                marker(str(reason or "terminal_plaintext_completion").strip(), "action_policy")
            except Exception:
                pass

    def has_pending_edit_mismatch_for_path(self, path: str) -> bool:
        normalized_path = str(path or "").strip()
        if not normalized_path:
            return False
        pending_path = str(getattr(self.state, "pending_edit_mismatch_path", "") or "").strip()
        pending_intent = str(getattr(self.state, "pending_edit_mismatch_intent_id", "") or "").strip()
        return bool(
            pending_path
            and normalized_path == pending_path
            and pending_intent == self.current_active_intent_id()
        )

    def has_hard_exhausted_active_intent(self) -> bool:
        checker = getattr(self.state, "has_hard_exhausted_active_intent", None)
        if not callable(checker):
            return False
        try:
            return bool(checker())
        except Exception:
            return False

    def intentless_state_changing_write_count(self) -> int:
        return int(getattr(self.state, "intentless_state_changing_file_write_count", 0) or 0)

    def last_plan_subgoal_create_count(self) -> int:
        return int(getattr(self.state, "last_plan_subgoal_create_count", 0) or 0)

    def task_board(self):
        board = getattr(self.state, "task_board", None)
        if not isinstance(board, dict):
            return board
        active_intent = self.active_intent()
        if active_intent is None:
            return None
        board_intent_id = str(board.get("intent_id", "") or "").strip()
        board_lineage_id = str(board.get("lineage_id", "") or "").strip()
        active_intent_id = str(getattr(active_intent, "intent_id", "") or "").strip()
        active_lineage_id = str(getattr(active_intent, "lineage_id", "") or active_intent_id or "").strip()
        if board_lineage_id and board_lineage_id == active_lineage_id:
            return board
        if board_intent_id and board_intent_id == active_intent_id:
            return board
        return None

    def _safe_set(self, name: str, value) -> None:
        try:
            setattr(self.state, name, value)
        except Exception:
            pass
