"""Canonical trace schema and helpers for orchestration diagnostics."""

from __future__ import annotations

from .decision_models import OrchestrationTraceEntry


TRACE_SCHEMA_DEFAULTS = {
    "reason": "",
    "source": "",
    "universe": "",
    "invalid_kind": "",
    "transition": "",
    "transition_applied": None,
    "repeat_count": 0,
    "think_repair_applied": False,
    "think_repair_reason": "",
    "think_repair_confidence": "",
    "think_repair_tag": "",
}


def normalize_trace_fields(fields: dict | None) -> dict:
    normalized = dict(TRACE_SCHEMA_DEFAULTS)
    for key, value in (fields or {}).items():
        normalized[str(key)] = value
    return normalized


def append_trace_entry(state, *, stage: str, decision: str, fields: dict | None = None) -> OrchestrationTraceEntry | None:
    if state is None:
        return None
    sequence = int(getattr(state, "orchestration_trace_sequence", 0) or 0) + 1
    state.orchestration_trace_sequence = sequence
    trace = list(getattr(state, "orchestration_trace", []) or [])
    entry = OrchestrationTraceEntry(
        sequence=sequence,
        stage=str(stage or "").strip(),
        decision=str(decision or "").strip(),
        fields=normalize_trace_fields(fields),
    )
    trace.append(entry)
    state.orchestration_trace = trace
    return entry


def snapshot_trace(state) -> list[dict]:
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


def render_trace_text(state) -> str:
    snapshot = snapshot_trace(state)
    if not snapshot:
        return "No orchestration trace entries.\n"

    lines = []
    for entry in snapshot:
        sequence = entry.get("sequence", "?")
        stage = entry.get("stage", "")
        decision = entry.get("decision", "")
        fields = entry.get("fields", {}) or {}
        lines.append(f"[{sequence}] stage={stage} decision={decision}")
        for key, value in fields.items():
            lines.append(f"    {key}: {value}")
    return "\n".join(lines) + "\n"
