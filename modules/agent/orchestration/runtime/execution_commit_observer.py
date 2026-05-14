"""State-side observer for execution plan/commit artifacts."""

from __future__ import annotations

from ..shared.trace import append_trace_entry


STATE_CHANGING_FILE_ACTIONS = {
    "write_file",
    "write_file_block",
    "append_file_block",
    "create_file",
    "edit_file",
    "delete_file",
    "replace",
}


class ExecutionCommitObserverAdapter:
    def __init__(self, state):
        self.state = state

    def observe_execution_commit(self, execution_plan, execution_commit, *, sys_results=None) -> None:
        self.remember_execution_artifacts(execution_plan, execution_commit)
        self.mark_plan_review_required_if_state_changing_commit(execution_commit, sys_results=sys_results)
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

    def _primary_action_effect_parts(self, execution_commit) -> tuple[str, str, list[str]]:
        action_effects = list(getattr(execution_commit, "action_effects", []) or [])
        primary_effect = str(action_effects[0] or "").strip() if action_effects else ""
        action_type = primary_effect.split(":", 1)[0] if ":" in primary_effect else primary_effect
        target = primary_effect.split(":", 1)[1] if ":" in primary_effect else ""
        return action_type.strip(), target.strip(), action_effects

    def commit_has_successful_system_result(self, execution_commit, *, sys_results=None) -> bool:
        if execution_commit is None:
            return False
        if int(getattr(execution_commit, "committed_system_result_count", 0) or 0) <= 0:
            return False

        action_type, target, _action_effects = self._primary_action_effect_parts(execution_commit)
        action_type = action_type.strip()
        target = target.strip()
        result_lines = [str(item or "") for item in (sys_results or []) if str(item or "").strip()]
        if not result_lines:
            return True

        current_action_lines = [line for line in result_lines if action_type and f"`{action_type}`" in line]
        if not current_action_lines:
            current_action_lines = [line for line in result_lines if action_type and f'"tool": "{action_type}"' in line]
        if target:
            targeted_lines = [line for line in current_action_lines if target in line]
            if targeted_lines:
                current_action_lines = targeted_lines
        if not current_action_lines:
            return False

        current_text = "\n".join(current_action_lines)
        failure_markers = (
            "Action failed",
            "VALIDATION_ERROR",
            "RECOVERABLE",
            "status=failed",
            "'status': 'failed'",
            "\"status\": \"failed\"",
            "execution failed",
            "requires both 'search_text' and 'replace_text'",
        )
        if any(marker in current_text for marker in failure_markers):
            return False
        success_markers = (
            "Changes applied",
            "status=success",
            "'status': 'success'",
            "\"status\": \"success\"",
        )
        return any(marker in current_text for marker in success_markers)

    def commit_requires_plan_review(self, execution_commit, *, sys_results=None) -> bool:
        if execution_commit is None:
            return False
        legacy_dispatched_success = bool(getattr(execution_commit, "action_dispatched", False)) and int(
            getattr(execution_commit, "committed_action_count", 0) or 0
        ) > 0
        system_result_success = self.commit_has_successful_system_result(execution_commit, sys_results=sys_results)
        if not legacy_dispatched_success and not system_result_success:
            return False
        action_type, _target, _action_effects = self._primary_action_effect_parts(execution_commit)
        return action_type.strip().lower() in STATE_CHANGING_FILE_ACTIONS

    def mark_plan_review_required_if_state_changing_commit(self, execution_commit, *, sys_results=None) -> bool:
        if not self.commit_requires_plan_review(execution_commit, sys_results=sys_results):
            return False
        action_type, target, action_effects = self._primary_action_effect_parts(execution_commit)
        reason = "state_changing_action_committed"
        self._safe_set("plan_review_required_after_state_change", True)
        self._safe_set("plan_review_required_reason", reason)
        self._safe_set("plan_review_required_action_type", action_type)
        self._safe_set("plan_review_required_target", target)
        self._safe_set("plan_review_required_action_effects", action_effects)
        self.append_plan_review_required_trace_entry(
            execution_commit,
            action_type=action_type,
            target=target,
            action_effects=action_effects,
            reason=reason,
        )
        return True

    def append_plan_review_required_trace_entry(
        self,
        execution_commit,
        *,
        action_type: str,
        target: str,
        action_effects: list[str],
        reason: str,
    ) -> None:
        transaction_kind = str(getattr(execution_commit, "transaction_kind", "") or "")
        fallback_commit_used = transaction_kind == "fallback_single_action"
        append_trace_entry(
            self.state,
            stage="plan_review_gate",
            decision="required_set",
            fields={
                "reason": reason,
                "source": "execution_commit_observer",
                "plan_review_required_after_state_change": True,
                "plan_review_required_reason": reason,
                "plan_review_required_action_type": str(action_type or ""),
                "plan_review_required_target": str(target or ""),
                "plan_review_required_action_effects": list(action_effects or []),
                "fallback_commit_used": fallback_commit_used,
                "fallback_commit_reason": "no_execution_plan" if fallback_commit_used else "",
                "execution_commit": {
                    "shape": str(getattr(execution_commit, "shape", "") or ""),
                    "transaction_kind": transaction_kind,
                    "committed_action_count": int(getattr(execution_commit, "committed_action_count", 0) or 0),
                    "committed_system_result_count": int(
                        getattr(execution_commit, "committed_system_result_count", 0) or 0
                    ),
                    "action_effects": list(action_effects or []),
                },
            },
        )

    def clear_plan_review_required_after_checkpoint(self) -> None:
        self._safe_set("plan_review_required_after_state_change", False)
        self._safe_set("plan_review_required_reason", "")
        self._safe_set("plan_review_required_action_type", "")
        self._safe_set("plan_review_required_target", "")
        self._safe_set("plan_review_required_action_effects", [])

    def build_operational_journal_entry(self, execution_commit, *, sys_results=None) -> dict | None:
        if execution_commit is None:
            return None
        action_type, target, action_effects = self._primary_action_effect_parts(execution_commit)
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
