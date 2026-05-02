"""Structured stage-level logging for orchestration pipeline diagnostics."""

from __future__ import annotations

from ..decision_models import OrchestrationTraceEntry


class OrchestrationStageLogger:
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

    def __init__(self, logger, state=None):
        self.logger = logger
        self.state = state

    def _normalized_trace_fields(self, fields: dict) -> dict:
        normalized = dict(self.TRACE_SCHEMA_DEFAULTS)
        for key, value in (fields or {}).items():
            normalized[str(key)] = value
        return normalized

    def log_architecture_defect(self, defect_kind: str, decision: str, **fields) -> None:
        payload = dict(fields or {})
        payload["defect_kind"] = str(defect_kind or "").strip()
        payload.setdefault("trace_class", "architecture_defect")
        self.log("architecture_defect", decision, **payload)

    def log(self, stage: str, decision: str, **fields) -> None:
        payload = {
            "stage": str(stage or "").strip(),
            "decision": str(decision or "").strip(),
        }
        for key, value in fields.items():
            if value in (None, "", [], {}, ()):
                continue
            payload[str(key)] = value
        if self.state is not None:
            sequence = int(getattr(self.state, "orchestration_trace_sequence", 0) or 0) + 1
            self.state.orchestration_trace_sequence = sequence
            trace = list(getattr(self.state, "orchestration_trace", []) or [])
            trace_fields = self._normalized_trace_fields(
                {k: v for k, v in payload.items() if k not in {"stage", "decision"}}
            )
            trace.append(
                OrchestrationTraceEntry(
                    sequence=sequence,
                    stage=payload["stage"],
                    decision=payload["decision"],
                    fields=trace_fields,
                )
            )
            self.state.orchestration_trace = trace
        if self.logger is None:
            return
        rendered = " ".join(f"{key}={payload[key]}" for key in payload)
        self.logger.info("OrchStage %s", rendered)
