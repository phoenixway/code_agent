"""Structured export helpers for orchestration trace diagnostics."""

from __future__ import annotations

from .shared.decision_models import OrchestrationTraceEntry


class OrchestrationTraceExporter:
    def snapshot(self, state) -> list[dict]:
        trace = list(getattr(state, "orchestration_trace", []) or [])
        snapshot: list[dict] = []
        for entry in trace:
            if isinstance(entry, OrchestrationTraceEntry):
                snapshot.append(
                    {
                        "sequence": entry.sequence,
                        "stage": entry.stage,
                        "decision": entry.decision,
                        "fields": dict(entry.fields),
                    }
                )
            elif isinstance(entry, dict):
                snapshot.append(dict(entry))
        return snapshot

    def render_text(self, state) -> str:
        snapshot = self.snapshot(state)
        if not snapshot:
            return "No orchestration trace entries.\n"

        lines = []
        for entry in snapshot:
            sequence = entry.get("sequence", "?")
            stage = entry.get("stage", "")
            decision = entry.get("decision", "")
            fields = entry.get("fields", {}) or {}
            header = f"[{sequence}] stage={stage} decision={decision}"
            lines.append(header)
            for key, value in fields.items():
                lines.append(f"    {key}: {value}")
        return "\n".join(lines) + "\n"
