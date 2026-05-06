"""State-side observer for execution plan/commit artifacts."""

from __future__ import annotations


class ExecutionCommitObserverAdapter:
    def __init__(self, state):
        self.state = state

    def observe_execution_commit(self, execution_plan, execution_commit, *, sys_results=None) -> None:
        self.remember_execution_artifacts(execution_plan, execution_commit)
        self.append_operational_journal_entry(execution_commit, sys_results=sys_results)

    def remember_execution_artifacts(self, execution_plan, execution_commit) -> None:
        self._safe_set("last_execution_plan", execution_plan)
        self._safe_set("last_execution_commit", execution_commit)

    def append_operational_journal_entry(self, execution_commit, *, sys_results=None) -> None:
        entry = self.build_operational_journal_entry(execution_commit, sys_results=sys_results)
        if entry is None:
            return

        appender = getattr(self.state, "append_operational_journal_entry", None)
        if callable(appender):
            try:
                appender(entry)
                return
            except Exception:
                pass

        journal = list(getattr(self.state, "operational_journal", []) or [])
        sequence = int(getattr(self.state, "operational_journal_sequence", 0) or 0) + 1
        self._safe_set("operational_journal_sequence", sequence)
        entry["sequence"] = sequence
        journal.append(entry)
        self._safe_set("operational_journal", journal[-25:])

    def build_operational_journal_entry(self, execution_commit, *, sys_results=None) -> dict | None:
        if execution_commit is None:
            return None
        action_effects = list(getattr(execution_commit, "action_effects", []) or [])
        primary_effect = str(action_effects[0] or "").strip() if action_effects else ""
        action_type = primary_effect.split(":", 1)[0] if ":" in primary_effect else primary_effect
        target = primary_effect.split(":", 1)[1] if ":" in primary_effect else ""
        return {
            "kind": "tool_execution_commit",
            "transaction_kind": str(getattr(execution_commit, "transaction_kind", "") or ""),
            "shape": str(getattr(execution_commit, "shape", "") or ""),
            "bundle_validated": bool(getattr(execution_commit, "bundle_validated", False)),
            "transition_applied": bool(getattr(execution_commit, "transition_applied", False)),
            "action_dispatched": bool(getattr(execution_commit, "action_dispatched", False)),
            "action_type": str(action_type or ""),
            "target": str(target or ""),
            "action_effects": action_effects,
            "committed_action_count": int(getattr(execution_commit, "committed_action_count", 0) or 0),
            "committed_system_result_count": int(getattr(execution_commit, "committed_system_result_count", 0) or 0),
            "dispatch_stop_requested": bool(getattr(execution_commit, "dispatch_stop_requested", False)),
            "before_active_intent_id": str(getattr(execution_commit, "before_active_intent_id", "") or ""),
            "after_active_intent_id": str(getattr(execution_commit, "after_active_intent_id", "") or ""),
            "system_result_excerpt": str((sys_results or [""])[0] or "")[:240] if sys_results else "",
        }

    def _safe_set(self, name: str, value) -> None:
        try:
            setattr(self.state, name, value)
        except Exception:
            pass
