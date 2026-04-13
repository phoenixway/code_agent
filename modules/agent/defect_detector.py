"""Defect detector for repeated low-value agent behavior.

Keep extension simple:
- add a rule method
- register it in `self._rules`
"""

from __future__ import annotations

from dataclasses import dataclass
from collections import deque


@dataclass
class DefectEvent:
    reason: str
    recoverable: bool = True
    error_code: str = ""
    next_actions: list[str] | None = None
    message: str = ""


class DefectDetector:
    def __init__(self, config):
        self.config = config
        self._fingerprints = deque(maxlen=max(12, int(getattr(config, "DEFECT_ACTION_HISTORY_WINDOW", 12))))
        self._rules = [
            self._same_action_repeat,
            self._repeated_cycle,
            self._low_value_broad_search_repeat,
        ]

    def reset(self):
        self._fingerprints.clear()

    def note_fingerprint(self, fingerprint: str):
        self._fingerprints.append(fingerprint)

    def evaluate(self, state, command: dict, result: dict) -> DefectEvent | None:
        fp = state.get_action_fingerprint(command)
        self.note_fingerprint(fp)

        # intent-driven defects first
        if getattr(state, "intent_runtime", None) and state.intent_runtime.active_intent is not None:
            intent = state.intent_runtime.active_intent
            if intent.retry_count > intent.retry_limit:
                return DefectEvent(
                    reason="intent_retry_limit_exceeded",
                    error_code="INTENT_RETRY_LIMIT_EXCEEDED",
                    next_actions=intent.allowed_actions[:],
                    message="Agent exceeded retry_limit for the active intent.",
                )

        for rule in self._rules:
            defect = rule(state, command, result)
            if defect is not None:
                return defect
        return None

    def _same_action_repeat(self, state, command: dict, result: dict) -> DefectEvent | None:
        threshold = max(2, int(getattr(self.config, "DEFECT_SAME_ACTION_REPEAT_THRESHOLD", 3)))
        if getattr(state, "consecutive_same_action_count", 0) >= threshold:
            next_actions = None
            if getattr(state, "intent_runtime", None) and state.intent_runtime.active_intent is not None:
                next_actions = state.intent_runtime.active_intent.allowed_actions[:]
            return DefectEvent(
                reason="defect_same_action_repeat",
                error_code="DEFECT_SAME_ACTION_REPEAT",
                next_actions=next_actions,
                message="Model repeats the same action several times.",
            )
        return None

    def _repeated_cycle(self, state, command: dict, result: dict) -> DefectEvent | None:
        cycle_window = max(2, int(getattr(self.config, "DEFECT_ACTION_CYCLE_WINDOW", 3)))
        recent = list(self._fingerprints)
        if len(recent) >= cycle_window * 2 and recent[-cycle_window:] == recent[-2 * cycle_window:-cycle_window]:
            next_actions = None
            if getattr(state, "intent_runtime", None) and state.intent_runtime.active_intent is not None:
                next_actions = state.intent_runtime.active_intent.allowed_actions[:]
            return DefectEvent(
                reason="defect_repeated_action_cycle",
                error_code="DEFECT_REPEATED_ACTION_CYCLE",
                next_actions=next_actions,
                message="Model appears to repeat a short action cycle.",
            )
        return None

    def _low_value_broad_search_repeat(self, state, command: dict, result: dict) -> DefectEvent | None:
        cmd_type = command.get("type") or command.get("action") or "unknown"
        if cmd_type not in {"search_content", "search_files", "list_directory"}:
            return None

        path = str(command.get("path") or "")
        pattern = str(command.get("pattern") or command.get("query") or "")
        output = str((result or {}).get("output") or "")
        broad = path in {"", ".", "./", "/"} or path.endswith("/.")
        low_value = ("Found 0" in output) or ("No matches" in output) or (len(output) > 2000 and ("Found " in output or "matches" in output))
        generic_pattern = pattern in {r"\.py", "*.py", ""} or len(pattern) <= 6
        if not (broad and (low_value or generic_pattern)):
            return None

        threshold = max(2, int(getattr(self.config, "DEFECT_LOW_VALUE_BROAD_SEARCH_REPEAT_THRESHOLD", 2)))
        tail = list(self._fingerprints)[-threshold:]
        if len(tail) >= threshold and all(fp.split(":", 1)[0] == cmd_type for fp in tail):
            next_actions = None
            if getattr(state, "intent_runtime", None) and state.intent_runtime.active_intent is not None:
                next_actions = state.intent_runtime.active_intent.allowed_actions[:]
            return DefectEvent(
                reason="low_value_broad_search_repeat",
                error_code="LOW_VALUE_BROAD_SEARCH_REPEAT",
                next_actions=next_actions,
                message="Model keeps repeating broad low-value search probes.",
            )
        return None
