"""Defect detector for repeated low-value agent behavior.

Updated to stay in its lane:
- it detects repeated/low-value action behavior
- it does NOT become the main judge of legitimate intent transitions
- it tolerates the post-completion / intent-switch protocol instead of fighting it
"""

from __future__ import annotations

from collections import deque
from dataclasses import dataclass


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
        self._fingerprints = deque(
            maxlen=max(12, int(getattr(config, "DEFECT_ACTION_HISTORY_WINDOW", 12)))
        )
        self._strategy_history: dict[str, deque[str]] = {}
        self._strategy_failures: dict[str, set[str]] = {}
        self._rules = [
            self._history_self_reference_hit,
            self._too_broad_search,
            self._same_action_repeat,
            self._repeated_cycle,
            self._low_value_broad_search_repeat,
            self._strategy_exhausted,
        ]

    def reset(self):
        self._fingerprints.clear()
        self._strategy_history.clear()
        self._strategy_failures.clear()

    def note_fingerprint(self, fingerprint: str):
        self._fingerprints.append(fingerprint)

    def evaluate(self, state, command: dict, result: dict) -> DefectEvent | None:
        # The defect detector judges *actions*, not formal intent transitions.
        # Intent acceptance/rejection belongs to apply_intent_contract.
        fp = state.get_action_fingerprint(command)
        self.note_fingerprint(fp)
        self._note_strategy(state, command, result)

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

    def _active_next_actions(self, state):
        if getattr(state, "intent_runtime", None) and state.intent_runtime.active_intent is not None:
            return state.intent_runtime.active_intent.allowed_actions[:]
        return None

    def _same_action_repeat(self, state, command: dict, result: dict) -> DefectEvent | None:
        threshold = max(2, int(getattr(self.config, "DEFECT_SAME_ACTION_REPEAT_THRESHOLD", 3)))
        if getattr(state, "consecutive_same_action_count", 0) >= threshold:
            return DefectEvent(
                reason="defect_same_action_repeat",
                error_code="DEFECT_SAME_ACTION_REPEAT",
                next_actions=self._active_next_actions(state),
                message="Model repeats the same action several times.",
            )
        return None

    def _repeated_cycle(self, state, command: dict, result: dict) -> DefectEvent | None:
        cycle_window = max(2, int(getattr(self.config, "DEFECT_ACTION_CYCLE_WINDOW", 3)))
        recent = list(self._fingerprints)
        if len(recent) < cycle_window * 2:
            return None

        if recent[-cycle_window:] == recent[-2 * cycle_window:-cycle_window]:
            return DefectEvent(
                reason="defect_repeated_action_cycle",
                error_code="DEFECT_REPEATED_ACTION_CYCLE",
                next_actions=self._active_next_actions(state),
                message="Model appears to repeat a short action cycle.",
            )
        return None

    def _history_self_reference_hit(self, state, command: dict, result: dict) -> DefectEvent | None:
        cmd_type = command.get("type") or command.get("action") or "unknown"
        if cmd_type != "search_content":
            return None

        if bool((result or {}).get("history_self_reference_only", False)):
            return DefectEvent(
                reason="history_self_reference_hit",
                error_code="HISTORY_SELF_REFERENCE_HIT",
                next_actions=self._active_next_actions(state) or [
                    "search_content",
                    "search_files",
                    "read_file",
                ],
                message=(
                    "Search hit only self-referential history entries (for example modules/history.py). "
                    "This is not real usage evidence. Change the search strategy or narrow scope."
                ),
            )
        return None

    def _too_broad_search(self, state, command: dict, result: dict) -> DefectEvent | None:
        cmd_type = command.get("type") or command.get("action") or "unknown"
        if cmd_type not in {"search_content", "search_files", "list_directory"}:
            return None

        path = str(command.get("path") or "")
        broad = path in {"", ".", "./", "/"} or path.endswith("/.")
        recursive = bool(command.get("recursive", True))
        code_only = bool(command.get("code_only", False))
        pattern = str(command.get("pattern") or command.get("query") or "")
        output = str((result or {}).get("output") or "")

        too_many = (
            ("Showing first" in output and ("matches" in output or "files" in output))
            or ("Found 451 matches" in output)
        )
        generic_pattern = pattern in {r"\.py", "*.py", ""} or len(pattern) <= 8
        threshold = max(1, int(getattr(self.config, "DEFECT_TOO_BROAD_SEARCH_THRESHOLD", 1)))

        if broad and recursive and not code_only and generic_pattern and too_many and threshold <= 1:
            return DefectEvent(
                reason="too_broad_search",
                error_code="TOO_BROAD_SEARCH",
                next_actions=self._active_next_actions(state),
                message="Search is too broad for the current goal. Narrow the scope before continuing.",
            )
        return None

    def _low_value_broad_search_repeat(self, state, command: dict, result: dict) -> DefectEvent | None:
        cmd_type = command.get("type") or command.get("action") or "unknown"
        if cmd_type not in {"search_content", "search_files", "list_directory", "run_shell"}:
            return None

        threshold = max(
            2,
            int(getattr(self.config, "DEFECT_LOW_VALUE_BROAD_SEARCH_REPEAT_THRESHOLD", 2)),
        )
        tail = list(self._fingerprints)[-threshold:]
        if len(tail) < threshold:
            return None

        if all(fp.split(":", 1)[0] == cmd_type for fp in tail) and self._is_low_value_result(result):
            return DefectEvent(
                reason="low_value_broad_search_repeat",
                error_code="LOW_VALUE_BROAD_SEARCH_REPEAT",
                next_actions=self._active_next_actions(state),
                message="Model keeps repeating broad low-value search probes.",
            )
        return None

    def _strategy_signature(self, command: dict) -> str:
        cmd_type = command.get("type") or command.get("action") or "unknown"
        path = str(command.get("path") or "")
        pattern = str(command.get("pattern") or command.get("query") or "")
        recursive = bool(command.get("recursive", True))
        code_only = bool(command.get("code_only", False))
        scope = "project_wide" if path in {"", ".", "./", "/"} else ("specific_path" if path else "unknown")
        domain = "code_only" if code_only else "mixed_domain"
        depth = "recursive" if recursive else "root_only"
        specificity = "generic" if pattern in {r"\.py", "*.py", ""} or len(pattern) <= 8 else "specific"
        return f"{cmd_type}|{scope}|{depth}|{domain}|{specificity}"

    def _is_low_value_result(self, result: dict) -> bool:
        status = str((result or {}).get("status") or "")
        output = str((result or {}).get("output") or "")
        if status in {"failed", "error"}:
            return True
        if "No matches found." in output:
            return True
        if "Only self-referential history hits were found" in output:
            return True
        if bool((result or {}).get("history_self_reference_only", False)):
            return True
        if "Showing first" in output and ("matches" in output or "files" in output):
            return True
        return False

    def _lineage_key(self, state) -> str | None:
        intent = getattr(getattr(state, "intent_runtime", None), "active_intent", None)
        if intent is None:
            return None
        return f"{intent.intent_type}:{intent.intent_id}:{intent.goal[:120]}"

    def _note_strategy(self, state, command: dict, result: dict):
        lineage_key = self._lineage_key(state)
        if not lineage_key:
            return
        sig = self._strategy_signature(command)
        history = self._strategy_history.setdefault(lineage_key, deque(maxlen=8))
        if not history or history[-1] != sig:
            history.append(sig)
        if self._is_low_value_result(result):
            failures = self._strategy_failures.setdefault(lineage_key, set())
            failures.add(sig)

    def _strategy_exhausted(self, state, command: dict, result: dict) -> DefectEvent | None:
        lineage_key = self._lineage_key(state)
        if not lineage_key:
            return None
        failures = self._strategy_failures.get(lineage_key, set())
        threshold = max(2, int(getattr(self.config, "DEFECT_STRATEGY_EXHAUSTED_THRESHOLD", 3)))
        if len(failures) >= threshold:
            return DefectEvent(
                reason="strategy_exhausted",
                error_code="STRATEGY_EXHAUSTED",
                next_actions=self._active_next_actions(state),
                message="Several materially different strategies have already failed for the current goal.",
            )
        return None