"""State adapter for orchestration recovery flows."""

from __future__ import annotations


class RecoveryStateAdapter:
    def __init__(self, state):
        self.state = state

    def active_intent(self):
        return getattr(self.state, "active_intent", None)

    def intent_runtime(self):
        return getattr(self.state, "intent_runtime", None)

    def universe_label(self) -> str:
        return "active_contract" if self.active_intent() is not None else "no_active_contract"

    def mark_pending_finalize_after_terminal_plaintext_completion(
        self,
        reason: str = "forced_plaintext_completion",
        source: str = "recovery",
    ) -> None:
        self._safe_set("pending_finalize_after_terminal_plaintext_completion", True)
        self._safe_set("pending_finalize_completion_reason", str(reason or "forced_plaintext_completion"))
        self._safe_set("pending_finalize_completion_source", str(source or "recovery"))

    def disallowed_action_fingerprint(self, stop_info: dict | None, active_intent) -> str:
        command = {}
        if isinstance(stop_info, dict):
            command = stop_info.get("command") or {}
        if not isinstance(command, dict):
            command = {}
        action_type = str(command.get("type") or command.get("action") or "").strip()
        path = str(command.get("path") or "").strip()
        intent_id = str(getattr(active_intent, "intent_id", "") or "").strip()
        return "|".join([intent_id, action_type, path])

    def note_repeated_disallowed_action(self, stop_info: dict | None, active_intent) -> tuple[int, str, str]:
        command = {}
        if isinstance(stop_info, dict):
            command = stop_info.get("command") or {}
        if not isinstance(command, dict):
            command = {}
        blocked_action = str(command.get("type") or command.get("action") or "").strip() or "action"
        fingerprint = self.disallowed_action_fingerprint(stop_info, active_intent)
        current_fingerprint = str(getattr(self.state, "last_disallowed_action_fingerprint", "") or "").strip()
        current_count = int(getattr(self.state, "last_disallowed_action_repeat_count", 0) or 0)
        current_count = current_count + 1 if fingerprint and fingerprint == current_fingerprint else 1
        self._safe_set("last_disallowed_action_fingerprint", fingerprint)
        self._safe_set("last_disallowed_action_repeat_count", current_count)
        self._safe_set("last_disallowed_action_type", blocked_action)
        return current_count, blocked_action, fingerprint

    def add_confirmation(self, count: int) -> None:
        adder = getattr(self.state, "add_confirmation", None)
        if callable(adder):
            adder(count)

    def set_retry_budgets(self, recoverable: int, critical: int) -> None:
        setter = getattr(self.state, "set_retry_budgets", None)
        if callable(setter):
            setter(recoverable, critical)

    def require_intent(self, reason: str) -> None:
        setter = getattr(self.state, "require_intent", None)
        if callable(setter):
            setter(reason)

    def get_stop_reason_count(self, reason: str) -> int:
        getter = getattr(self.state, "get_stop_reason_count", None)
        if not callable(getter):
            return 0
        try:
            return int(getter(reason) or 0)
        except Exception:
            return 0

    def allow_pending_goal_drift_once(self, config) -> tuple[bool, str]:
        method = getattr(self.state, "allow_pending_goal_drift_once", None)
        if not callable(method):
            return False, ""
        try:
            return method(config)
        except Exception:
            return False, ""

    def blocked_action_reason(self, command: dict) -> str:
        getter = getattr(self.state, "get_blocked_action_reason", None)
        if not callable(getter):
            return ""
        try:
            return str(getter(command) or "")
        except Exception:
            return ""

    def _safe_set(self, name: str, value) -> None:
        try:
            setattr(self.state, name, value)
        except Exception:
            pass
