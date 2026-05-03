"""State adapter for orchestration pre-dispatch pipeline."""

from __future__ import annotations


class OrchestrationPipelineStateAdapter:
    def __init__(self, state):
        self.state = state

    def close_active_intent_as_resumable(self, completion_reason: str) -> bool:
        closer = getattr(self.state, "close_active_intent_as_resumable", None)
        if not callable(closer):
            return False
        try:
            closer(str(completion_reason or "technical_interruption"))
            return True
        except Exception:
            return False

    def note_technical_interruption(self, interruption, *, current_query: str) -> None:
        note = getattr(self.state, "note_technical_interruption", None)
        if callable(note):
            note(interruption, current_query=current_query)

    def technical_interruption_snapshot(self, fallback):
        return getattr(self.state, "last_technical_interruption", None) or fallback

    def clear_technical_interruption(self) -> None:
        clear = getattr(self.state, "clear_technical_interruption", None)
        if callable(clear):
            clear()

    def set_current_task(self, task) -> None:
        self._safe_set("current_task", task)

    def model_stop_reason(self) -> str:
        return str(getattr(self.state, "last_model_response_stop_reason", "") or "").strip()

    def clear_model_stop_reason(self) -> None:
        self._safe_set("last_model_response_stop_reason", "")

    def terminal_plaintext_completion_pending(self) -> bool:
        return bool(getattr(self.state, "terminal_plaintext_completion_pending", False))

    def terminal_plaintext_completion_text(self) -> str:
        return str(getattr(self.state, "terminal_plaintext_completion_text", "") or "")

    def set_terminal_plaintext_completion_text(self, text: str) -> None:
        self._safe_set("terminal_plaintext_completion_text", str(text or ""))

    def reset_readonly_steps_this_turn(self) -> None:
        if hasattr(self.state, "readonly_steps_this_turn"):
            self._safe_set("readonly_steps_this_turn", 0)

    def _safe_set(self, name: str, value) -> None:
        try:
            setattr(self.state, name, value)
        except Exception:
            pass
