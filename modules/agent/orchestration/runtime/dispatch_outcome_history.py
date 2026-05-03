"""History adapter for dispatch outcome handling."""

from __future__ import annotations


class DispatchOutcomeHistoryAdapter:
    def __init__(self, history):
        self.history = history

    def add_assistant_message(self, text: str) -> None:
        self.history.add_message("assistant", text)

    def add_system_message(self, text: str) -> None:
        self.history.add_message("system", text)
