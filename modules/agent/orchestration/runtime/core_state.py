"""State adapter for orchestration core loop coordination."""

from __future__ import annotations


class OrchestratorCoreStateAdapter:
    def __init__(self, state):
        self.state = state

    def terminal_plaintext_completion_text(self) -> str:
        return str(getattr(self.state, "terminal_plaintext_completion_text", "") or "").strip()

    def clear_terminal_plaintext_completion(self) -> None:
        self._safe_set("terminal_plaintext_completion_pending", False)
        self._safe_set("terminal_plaintext_completion_text", "")

    def pending_finalize_after_terminal_plaintext_completion(self) -> bool:
        return bool(getattr(self.state, "pending_finalize_after_terminal_plaintext_completion", False))

    def pending_finalize_completion_reason(self) -> str:
        return str(
            getattr(self.state, "pending_finalize_completion_reason", "forced_plaintext_completion")
            or "forced_plaintext_completion"
        )

    def clear_pending_finalize_after_terminal_plaintext_completion(self) -> None:
        self._safe_set("pending_finalize_after_terminal_plaintext_completion", False)
        self._safe_set("pending_finalize_completion_reason", "")
        self._safe_set("pending_finalize_completion_source", "")

    def close_active_intent_as_resumable(self, reason: str, *, clear_pending_stop: bool = False) -> bool:
        closer = getattr(self.state, "close_active_intent_as_resumable", None)
        if not callable(closer):
            return False
        try:
            closer(str(reason or "forced_plaintext_completion"), clear_pending_stop=clear_pending_stop)
            return True
        except Exception:
            return False

    def _safe_set(self, name: str, value) -> None:
        try:
            setattr(self.state, name, value)
        except Exception:
            pass
