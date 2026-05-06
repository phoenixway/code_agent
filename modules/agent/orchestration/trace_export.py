"""Structured export helpers for orchestration trace diagnostics."""

from __future__ import annotations

from dataclasses import asdict, is_dataclass

from .shared.trace import render_trace_text, snapshot_trace


class OrchestrationTraceExporter:
    def snapshot(self, state) -> list[dict]:
        return snapshot_trace(state)

    def runtime_diagnostics_snapshot(self, state) -> dict:
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
            "last_execution_commit": self.serialize_runtime_artifact(getattr(state, "last_execution_commit", None)),
            "operational_journal": self.operational_journal_snapshot(state),
            "orchestration_trace_text": self.render_text(state),
        }

    def runtime_artifacts(self, state) -> dict:
        return {
            "last_execution_plan": self.serialize_runtime_artifact(getattr(state, "last_execution_plan", None)),
            "last_execution_commit": self.serialize_runtime_artifact(getattr(state, "last_execution_commit", None)),
            "operational_journal": self.operational_journal_snapshot(state),
            "orchestration_trace": snapshot_trace(state),
        }

    def render_text(self, state) -> str:
        return render_trace_text(state)

    @staticmethod
    def serialize_runtime_artifact(value):
        if value is None:
            return None
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
