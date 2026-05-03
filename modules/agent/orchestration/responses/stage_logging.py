"""Structured stage-level logging for orchestration pipeline diagnostics."""

from __future__ import annotations

from ..shared.trace import append_trace_entry


class OrchestrationStageLogger:
    def __init__(self, logger, state=None):
        self.logger = logger
        self.state = state

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
            append_trace_entry(
                self.state,
                stage=payload["stage"],
                decision=payload["decision"],
                fields={k: v for k, v in payload.items() if k not in {"stage", "decision"}},
            )
        if self.logger is None:
            return
        rendered = " ".join(f"{key}={payload[key]}" for key in payload)
        self.logger.info("OrchStage %s", rendered)
