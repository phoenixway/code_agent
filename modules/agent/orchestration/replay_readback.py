from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class SemanticDecisionReadbackItem:
    sequence: int | None
    trace_stage: str
    trace_decision: str
    domain: str
    record_stage: str
    decision: str
    reason: str
    source: str
    diagnostic_only: bool
    authority_affecting: bool
    behavior_affecting: bool

    def to_dict(self) -> dict[str, Any]:
        return {
            "sequence": self.sequence,
            "trace_stage": self.trace_stage,
            "trace_decision": self.trace_decision,
            "domain": self.domain,
            "record_stage": self.record_stage,
            "decision": self.decision,
            "reason": self.reason,
            "source": self.source,
            "diagnostic_only": self.diagnostic_only,
            "authority_affecting": self.authority_affecting,
            "behavior_affecting": self.behavior_affecting,
        }


@dataclass(frozen=True)
class ReplayReadbackSummary:
    record_count: int
    trace_entry_count: int
    skipped_malformed_count: int
    domains: tuple[str, ...]
    stages: tuple[str, ...]
    decisions: tuple[str, ...]
    reasons: tuple[str, ...]
    sources: tuple[str, ...]
    diagnostic_only_count: int
    authority_affecting_count: int
    behavior_affecting_count: int
    items: tuple[SemanticDecisionReadbackItem, ...]

    def to_dict(self) -> dict[str, Any]:
        return {
            "record_count": self.record_count,
            "trace_entry_count": self.trace_entry_count,
            "skipped_malformed_count": self.skipped_malformed_count,
            "domains": list(self.domains),
            "stages": list(self.stages),
            "decisions": list(self.decisions),
            "reasons": list(self.reasons),
            "sources": list(self.sources),
            "diagnostic_only_count": self.diagnostic_only_count,
            "authority_affecting_count": self.authority_affecting_count,
            "behavior_affecting_count": self.behavior_affecting_count,
            "items": [item.to_dict() for item in self.items],
        }


def _trace_entries(trace_or_artifacts: Any) -> list[dict[str, Any]]:
    if isinstance(trace_or_artifacts, dict):
        value = trace_or_artifacts.get("orchestration_trace", [])
    else:
        value = trace_or_artifacts
    if not isinstance(value, list):
        return []
    return [entry for entry in value if isinstance(entry, dict)]


def _string(value: Any) -> str:
    return str(value or "")


def _bool(value: Any) -> bool:
    return bool(value)


def _optional_int(value: Any) -> int | None:
    if value is None:
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _sorted_nonempty(values: list[str]) -> tuple[str, ...]:
    return tuple(sorted({value for value in values if value}))


def summarize_semantic_decision_records(trace_or_artifacts: Any) -> ReplayReadbackSummary:
    """Summarize semantic decision records from trace-shaped data.

    This is passive readback only. It must not call the model pipeline,
    parser/compiler, recovery routing, dispatch, ActionPolicy, authority
    resolvers, switch registry, logging, or trace export code.
    """
    entries = _trace_entries(trace_or_artifacts)
    items: list[SemanticDecisionReadbackItem] = []
    skipped_malformed_count = 0

    for entry in entries:
        fields = entry.get("fields", {})
        if not isinstance(fields, dict):
            continue
        record = fields.get("semantic_decision_record")
        if record is None:
            continue
        if not isinstance(record, dict):
            skipped_malformed_count += 1
            continue

        items.append(
            SemanticDecisionReadbackItem(
                sequence=_optional_int(entry.get("sequence")),
                trace_stage=_string(entry.get("stage")),
                trace_decision=_string(entry.get("decision")),
                domain=_string(record.get("domain")),
                record_stage=_string(record.get("stage")),
                decision=_string(record.get("decision")),
                reason=_string(record.get("reason")),
                source=_string(record.get("source")),
                diagnostic_only=_bool(record.get("diagnostic_only")),
                authority_affecting=_bool(record.get("authority_affecting")),
                behavior_affecting=_bool(record.get("behavior_affecting")),
            )
        )

    return ReplayReadbackSummary(
        record_count=len(items),
        trace_entry_count=len(entries),
        skipped_malformed_count=skipped_malformed_count,
        domains=_sorted_nonempty([item.domain for item in items]),
        stages=_sorted_nonempty([item.record_stage for item in items]),
        decisions=_sorted_nonempty([item.decision for item in items]),
        reasons=_sorted_nonempty([item.reason for item in items]),
        sources=_sorted_nonempty([item.source for item in items]),
        diagnostic_only_count=sum(1 for item in items if item.diagnostic_only),
        authority_affecting_count=sum(1 for item in items if item.authority_affecting),
        behavior_affecting_count=sum(1 for item in items if item.behavior_affecting),
        items=tuple(items),
    )
