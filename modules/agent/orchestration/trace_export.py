"""Structured export helpers for orchestration trace diagnostics."""

from __future__ import annotations

from dataclasses import asdict, is_dataclass

from .shared.decision_models import ExecutionCommit
from .shared.trace import compact_execution_commit, render_trace_text, snapshot_trace


class OrchestrationTraceExporter:
    def snapshot(self, state) -> list[dict]:
        return snapshot_trace(state)

    def runtime_diagnostics_snapshot(self, state) -> dict:
        operational_journal = self.operational_journal_snapshot(state)
        return {
            "last_error_code": getattr(state, "last_error_code", None),
            "last_error_recoverable": getattr(state, "last_error_recoverable", None),
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
