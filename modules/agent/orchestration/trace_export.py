"""Structured export helpers for orchestration trace diagnostics."""

from __future__ import annotations

from .shared.trace import render_trace_text, snapshot_trace


class OrchestrationTraceExporter:
    def snapshot(self, state) -> list[dict]:
        return snapshot_trace(state)

    def render_text(self, state) -> str:
        return render_trace_text(state)
