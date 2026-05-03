from types import SimpleNamespace

from modules.agent.orchestration.shared.decision_models import OrchestrationTraceEntry
from modules.agent.orchestration.shared.trace import (
    TRACE_SCHEMA_DEFAULTS,
    append_trace_entry,
    normalize_trace_fields,
    render_trace_text,
    snapshot_trace,
)


def test_normalize_trace_fields_applies_canonical_defaults():
    normalized = normalize_trace_fields({"reason": "x", "repeat_count": 2})

    assert normalized["reason"] == "x"
    assert normalized["repeat_count"] == 2
    assert normalized["source"] == TRACE_SCHEMA_DEFAULTS["source"]
    assert normalized["transition_applied"] is None
    assert normalized["think_repair_applied"] is False


def test_append_trace_entry_updates_sequence_and_normalizes_fields():
    state = SimpleNamespace(orchestration_trace=[], orchestration_trace_sequence=0)

    entry = append_trace_entry(
        state,
        stage="response_pipeline",
        decision="pass",
        fields={"reason": "ok"},
    )

    assert isinstance(entry, OrchestrationTraceEntry)
    assert entry.sequence == 1
    assert state.orchestration_trace_sequence == 1
    assert state.orchestration_trace[-1].fields["reason"] == "ok"
    assert state.orchestration_trace[-1].fields["source"] == ""


def test_snapshot_and_render_trace_use_canonical_entry_shape():
    state = SimpleNamespace(
        orchestration_trace=[
            OrchestrationTraceEntry(
                sequence=1,
                stage="intent_transition",
                decision="continue",
                fields={"reason": "intent_accepted", "source": "intent_runtime"},
            )
        ]
    )

    snapshot = snapshot_trace(state)
    rendered = render_trace_text(state)

    assert snapshot == [
        {
            "sequence": 1,
            "stage": "intent_transition",
            "decision": "continue",
            "fields": {"reason": "intent_accepted", "source": "intent_runtime"},
        }
    ]
    assert "[1] stage=intent_transition decision=continue" in rendered
    assert "reason: intent_accepted" in rendered
