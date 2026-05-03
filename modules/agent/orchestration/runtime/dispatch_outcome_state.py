"""State adapter for dispatch outcome handling."""

from __future__ import annotations


class DispatchOutcomeStateAdapter:
    def __init__(self, state):
        self.state = state

    def clear_terminal_plaintext_completion(self) -> None:
        self._safe_set("terminal_plaintext_completion_pending", False)
        self._safe_set("terminal_plaintext_completion_text", "")

    def close_active_intent_as_resumable(self, completion_reason: str) -> bool:
        closer = getattr(self.state, "close_active_intent_as_resumable", None)
        if not callable(closer):
            return False
        try:
            return bool(closer(completion_reason))
        except Exception:
            return False

    def active_intent(self):
        return getattr(self.state, "active_intent", None)

    def pending_loop_stop_info(self) -> dict | None:
        value = getattr(self.state, "pending_loop_stop_info", None)
        return value if isinstance(value, dict) else value

    def clear_pending_loop_stop_info(self) -> None:
        self._safe_set("pending_loop_stop_info", None)

    def force_plaintext_completion_reason(self, fallback_reason: str = "") -> str:
        return str(getattr(self.state, "pending_finalize_completion_reason", "") or "").strip() or str(
            fallback_reason or ""
        ).strip() or "forced_plaintext_completion"

    def has_exhausted_active_intent(self) -> bool:
        checker = getattr(self.state, "has_exhausted_active_intent", None)
        if not callable(checker):
            return False
        try:
            return bool(checker())
        except Exception:
            return False

    def note_technical_interruption(self, interruption, *, current_query: str) -> None:
        note = getattr(self.state, "note_technical_interruption", None)
        if callable(note):
            note(interruption, current_query=current_query)

    def technical_interruption_snapshot(self, fallback):
        return getattr(self.state, "last_technical_interruption", None) or fallback

    def set_memory_tag_followup(self, *, expected: bool, reason: str = "", intent_id: str = "") -> None:
        self._safe_set("memory_tag_expected_next_step", bool(expected))
        self._safe_set("memory_tag_reason", str(reason or ""))
        self._safe_set("memory_tag_expected_intent_id", str(intent_id or ""))

    def last_memory_board_counts_indicate_tag(self) -> bool:
        try:
            if int(getattr(self.state, "last_memory_board_accepted_count", 0) or 0) > 0:
                return True
            if int(getattr(self.state, "last_memory_board_parsed_count", 0) or 0) > 0:
                return True
        except Exception:
            return False
        return False

    def _safe_set(self, name: str, value) -> None:
        try:
            setattr(self.state, name, value)
        except Exception:
            pass
