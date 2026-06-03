"""Structured export helpers for orchestration trace diagnostics."""

from __future__ import annotations

import re
from dataclasses import asdict, is_dataclass

from .shared.decision_models import ExecutionCommit
from .shared.trace import compact_execution_commit, render_trace_text, snapshot_trace


class OrchestrationTraceExporter:
    def snapshot(self, state) -> list[dict]:
        return snapshot_trace(state)

    def runtime_diagnostics_snapshot(self, state) -> dict:
        operational_journal = self.operational_journal_snapshot(state)
        failure_resolution = self.failure_resolution_snapshot(state, operational_journal)
        return {
            "last_error_code": getattr(state, "last_error_code", None),
            "last_error_recoverable": getattr(state, "last_error_recoverable", None),
            "last_failed_action_error_code": failure_resolution["last_failed_action_error_code"],
            "last_failed_action_recoverable": failure_resolution["last_failed_action_recoverable"],
            "last_error_resolved": failure_resolution["last_error_resolved"],
            "resolved_by_sequence": failure_resolution["resolved_by_sequence"],
            "current_blocker": failure_resolution["current_blocker"],
            "last_unresolved_error_code": failure_resolution["last_unresolved_error_code"],
            "consecutive_same_error_count": getattr(state, "consecutive_same_error_count", None),
            "last_failed_action_command": self.serialize_runtime_artifact(
                getattr(state, "last_failed_action_command", None)
            ),
            "last_failed_action_result": self.serialize_runtime_artifact(
                getattr(state, "last_failed_action_result", None)
            ),
            "last_execution_plan": self.serialize_runtime_artifact(getattr(state, "last_execution_plan", None)),
            "last_execution_commit": self.last_execution_commit_snapshot(state, operational_journal=operational_journal),
            "operational_journal": operational_journal,
            "orchestration_trace_text": self.render_text(state),
        }

    def runtime_artifacts(self, state) -> dict:
        operational_journal = self.operational_journal_snapshot(state)
        return {
            "last_execution_plan": self.serialize_runtime_artifact(getattr(state, "last_execution_plan", None)),
            "last_execution_commit": self.last_execution_commit_snapshot(state, operational_journal=operational_journal),
            "operational_journal": operational_journal,
            "orchestration_trace": snapshot_trace(state),
        }

    def render_text(self, state) -> str:
        return render_trace_text(state)

    def failure_resolution_snapshot(self, state, operational_journal) -> dict:
        last_failed_result = self.serialize_runtime_artifact(
            getattr(state, "last_failed_action_result", None)
        )
        last_failed_command = self.serialize_runtime_artifact(
            getattr(state, "last_failed_action_command", None)
        )

        failed_entry = self.latest_failed_tool_execution_journal_entry(operational_journal)
        failed_sequence = self._entry_sequence(failed_entry)

        error_code = self._first_non_empty(
            self._dict_get(failed_entry, "error_code"),
            self._dict_get(failed_entry, "last_error_code"),
            self._dict_get(last_failed_result, "error_code"),
            getattr(state, "last_error_code", None),
        )
        recoverable = self._first_not_none(
            self._dict_get(failed_entry, "recoverable"),
            self._dict_get(last_failed_result, "recoverable"),
            getattr(state, "last_error_recoverable", None),
        )

        action_type = self._first_non_empty(
            self._dict_get(failed_entry, "action_type"),
            self._dict_get(last_failed_command, "type"),
        )
        target = self._first_non_empty(
            self._dict_get(failed_entry, "target"),
            self._dict_get(last_failed_command, "path"),
            self._dict_get(last_failed_command, "filename"),
        )

        has_failure = bool(error_code or failed_entry or last_failed_result)
        resolved_by = None
        if has_failure:
            resolved_by = self.find_resolving_success_entry(
                operational_journal,
                failed_entry=failed_entry,
                failed_sequence=failed_sequence,
                action_type=action_type,
                target=target,
                last_failed_command=last_failed_command,
            )

        resolved = bool(has_failure and resolved_by is not None)
        current_blocker = None
        if has_failure and not resolved:
            current_blocker = {
                "sequence": failed_sequence,
                "action_type": action_type or "",
                "target": target or "",
                "error_code": error_code,
                "recoverable": recoverable,
            }

        return {
            "last_failed_action_error_code": error_code,
            "last_failed_action_recoverable": recoverable,
            "last_error_resolved": resolved,
            "resolved_by_sequence": self._entry_sequence(resolved_by) if resolved_by else None,
            "current_blocker": current_blocker,
            "last_unresolved_error_code": None if resolved else (error_code if has_failure else None),
        }

    @staticmethod
    def _dict_get(value, key, default=None):
        return value.get(key, default) if isinstance(value, dict) else default

    @staticmethod
    def _first_non_empty(*values):
        for value in values:
            if value is None:
                continue
            text = str(value).strip()
            if text:
                return value
        return None

    @staticmethod
    def _first_not_none(*values):
        for value in values:
            if value is not None:
                return value
        return None

    @staticmethod
    def _entry_sequence(entry) -> int | None:
        if not isinstance(entry, dict):
            return None
        try:
            return int(entry.get("sequence"))
        except Exception:
            return None

    @classmethod
    def _same_failure_target(
        cls,
        success_entry,
        *,
        action_type: str | None,
        target: str | None,
        failed_entry=None,
        last_failed_command=None,
    ) -> bool:
        if not isinstance(success_entry, dict):
            return False
        if action_type and str(success_entry.get("action_type") or "") != str(action_type):
            return False
        if target:
            success_target = str(success_entry.get("target") or "")
            if success_target and success_target != str(target):
                return False

        # For symbol extraction, file-level target is not specific enough:
        # a later success for another symbol in the same file must not resolve
        # a previous NOT_FOUND for a different symbol/container.
        if str(action_type or "") in {"extract_symbol", "extract_kotlin_function"}:
            failed_symbol = cls._first_non_empty(
                cls._dict_get(failed_entry, "symbol_name"),
                cls._dict_get(last_failed_command, "symbol_name"),
            )
            failed_container = cls._first_non_empty(
                cls._dict_get(failed_entry, "container_name"),
                cls._dict_get(last_failed_command, "container_name"),
            )

            if failed_symbol:
                success_symbol = cls._first_non_empty(
                    cls._dict_get(success_entry, "symbol_name"),
                    cls._extract_symbol_name_from_excerpt(cls._dict_get(success_entry, "system_result_excerpt")),
                )
                if not success_symbol or str(success_symbol) != str(failed_symbol):
                    return False

            if failed_container:
                success_container = cls._first_non_empty(
                    cls._dict_get(success_entry, "container_name"),
                    cls._extract_container_name_from_excerpt(cls._dict_get(success_entry, "system_result_excerpt")),
                )
                if success_container and str(success_container) != str(failed_container):
                    return False

        return True

    @staticmethod
    def _extract_symbol_name_from_excerpt(excerpt) -> str | None:
        text = str(excerpt or "")
        match = re.search(r"['\"]([A-Za-z_][A-Za-z0-9_]*)['\"]", text)
        return match.group(1) if match else None

    @staticmethod
    def _extract_container_name_from_excerpt(excerpt) -> str | None:
        text = str(excerpt or "")
        match = re.search(r"container ['\"]([A-Za-z_][A-Za-z0-9_]*)['\"]", text)
        return match.group(1) if match else None

    @classmethod
    def find_resolving_success_entry(
        cls,
        operational_journal,
        *,
        failed_entry=None,
        failed_sequence: int | None = None,
        action_type: str | None = None,
        target: str | None = None,
        last_failed_command=None,
    ) -> dict | None:
        if failed_sequence is None and isinstance(failed_entry, dict):
            failed_sequence = cls._entry_sequence(failed_entry)

        for entry in list(operational_journal or []):
            if not isinstance(entry, dict) or entry.get("kind") != "tool_execution_commit":
                continue
            sequence = cls._entry_sequence(entry)
            if failed_sequence is not None and sequence is not None and sequence <= failed_sequence:
                continue
            if entry.get("tool_execution_succeeded") is not True:
                continue
            if cls._same_failure_target(
                entry,
                action_type=action_type,
                target=target,
                failed_entry=failed_entry,
                last_failed_command=last_failed_command,
            ):
                return dict(entry)
        return None

    @staticmethod
    def latest_failed_tool_execution_journal_entry(operational_journal) -> dict | None:
        for entry in reversed(list(operational_journal or [])):
            if not isinstance(entry, dict):
                continue
            if entry.get("kind") != "tool_execution_commit":
                continue
            if entry.get("tool_execution_succeeded") is False:
                return dict(entry)
        return None

    def last_execution_commit_snapshot(self, state, *, operational_journal=None) -> dict | None:
        snapshot = self.serialize_runtime_artifact(getattr(state, "last_execution_commit", None))
        if snapshot is None:
            return None
        latest_commit_entry = self.latest_tool_execution_journal_entry(
            operational_journal if operational_journal is not None else self.operational_journal_snapshot(state)
        )
        if latest_commit_entry:
            telemetry_keys = (
                "model_action_present",
                "action_validated",
                "execution_plan_dispatched",
                "atomic_bundle_validated",
                "fallback_dispatch_used",
                "tool_execution_attempted",
                "tool_execution_succeeded",
                "system_result_recorded",
                "state_change_effect_recorded",
                "state_change_applied",
                "per_action_telemetry",
                "failed_action_index",
                "batch_aborted",
                "batch_telemetry_source",
            )
            for key in telemetry_keys:
                if key in latest_commit_entry:
                    snapshot[key] = latest_commit_entry[key]
        return snapshot

    @staticmethod
    def latest_tool_execution_journal_entry(operational_journal) -> dict | None:
        for entry in reversed(list(operational_journal or [])):
            if isinstance(entry, dict) and entry.get("kind") == "tool_execution_commit":
                return dict(entry)
        return None

    @staticmethod
    def serialize_runtime_artifact(value):
        if value is None:
            return None
        if isinstance(value, ExecutionCommit) or (
            not is_dataclass(value)
            and hasattr(value, "transaction_kind")
            and hasattr(value, "action_dispatched")
        ):
            return compact_execution_commit(value)
        if is_dataclass(value):
            return asdict(value)
        if isinstance(value, dict):
            return dict(value)
        if isinstance(value, list):
            return [OrchestrationTraceExporter.serialize_runtime_artifact(item) for item in value]
        if hasattr(value, "__dict__"):
            return dict(vars(value))
        return str(value)

    @staticmethod
    def operational_journal_snapshot(state) -> list[dict]:
        journal_getter = getattr(state, "operational_journal_snapshot", None)
        if callable(journal_getter):
            try:
                return journal_getter() or []
            except Exception:
                return []
        return OrchestrationTraceExporter.serialize_runtime_artifact(
            getattr(state, "operational_journal", [])
        ) or []
