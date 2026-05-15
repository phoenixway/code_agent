"""History adapter for dispatch outcome handling."""

from __future__ import annotations


class DispatchOutcomeHistoryAdapter:
    def __init__(self, history):
        self.history = history

    def add_assistant_message(self, text: str) -> None:
        self.history.add_message("assistant", text)

    def add_system_message(self, text: str) -> None:
        self.history.add_message("system", text)

    def add_recovery_instruction(self, text: str, *, recovery_visibility: dict | None = None) -> None:
        if not isinstance(text, str) or not text.strip():
            return
        metadata = {}
        if isinstance(recovery_visibility, dict):
            metadata["recovery_visibility"] = dict(recovery_visibility)
        self.history.add_message(
            "system",
            text.strip(),
            msg_type="recovery_instruction",
            **metadata,
        )
