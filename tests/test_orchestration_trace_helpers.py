from types import SimpleNamespace

from modules.agent.orchestration.shared.decision_models import OrchestrationTraceEntry
from modules.agent.orchestration.shared.decision_models import ExecutionCommit, ExecutionPlan
from modules.agent.orchestration.protocol.models import CompilerAnalysis, ResponseShape
from modules.agent.orchestration.shared.trace import (
    TRACE_SCHEMA_DEFAULTS,
    append_trace_entry,
    compact_compiler_replay,
    compact_execution_commit,
    compact_execution_plan,
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
    assert normalized["compiler_shape"] == ""
    assert normalized["compiler_replay"] is None
    assert normalized["execution_plan"] is None
    assert normalized["execution_commit"] is None


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


def test_compact_execution_plan_and_commit_use_stable_trace_shape():
    plan = ExecutionPlan(
        shape="intent_action_bundle",
        transaction_kind="atomic_intent_action_bundle",
        action_effects=["read_chunk:x.py"],
        bundle_validated=True,
        transition_applied=True,
        action_dispatched=False,
        before_active_intent_id="intent_before",
        after_active_intent_id="intent_after",
    )
    commit = ExecutionCommit(
        shape="intent_action_bundle",
        transaction_kind="atomic_intent_action_bundle",
        action_effects=["read_chunk:x.py"],
        bundle_validated=True,
        transition_applied=True,
        action_dispatched=True,
        before_active_intent_id="intent_before",
        after_active_intent_id="intent_after",
        committed_action_count=1,
        committed_system_result_count=2,
        dispatch_stop_requested=True,
    )

    assert compact_execution_plan(plan) == {
        "shape": "intent_action_bundle",
        "transaction_kind": "atomic_intent_action_bundle",
        "bundle_validated": True,
        "transition_applied": True,
        "action_dispatched": False,
        "before_active_intent_id": "intent_before",
        "after_active_intent_id": "intent_after",
        "action_effects": ["read_chunk:x.py"],
    }
    assert compact_execution_commit(commit) == {
        "shape": "intent_action_bundle",
        "transaction_kind": "atomic_intent_action_bundle",
        "bundle_validated": True,
        "transition_applied": True,
        "action_dispatched": True,
        "before_active_intent_id": "intent_before",
        "after_active_intent_id": "intent_after",
        "committed_action_count": 1,
        "committed_system_result_count": 2,
        "dispatch_stop_requested": True,
        "action_effects": ["read_chunk:x.py"],
    }


def test_compact_compiler_replay_uses_stable_trace_shape():
    class StartTagToken:
        pass

    class PayloadToken:
        pass

    class ActionNode:
        pass

    analysis = CompilerAnalysis(
        shape=ResponseShape.ACTION_ONLY,
        tokens=[StartTagToken(), PayloadToken()],
        ast=SimpleNamespace(nodes=[ActionNode()]),
        ir=SimpleNamespace(
            shape=ResponseShape.ACTION_ONLY,
            intent_ops=[],
            action_ops=[object()],
            board_ops=[],
            annotations=[],
            visible_answer=None,
            file_content=None,
            effects_preview=[SimpleNamespace(summary="read_file")],
        ),
        error=None,
    )

    assert compact_compiler_replay(analysis) == {
        "shape": "ACTION_ONLY",
        "error_code": "",
        "recovery_id": "",
        "tokens": ["StartTagToken", "PayloadToken"],
        "ast_nodes": ["ActionNode"],
        "ir": {
            "shape": "ACTION_ONLY",
            "intent_ops": 0,
            "action_ops": 1,
            "board_ops": 0,
            "annotations": 0,
            "visible_answer": False,
            "file_content": False,
            "effects_preview": ["read_file"],
        },
        "span_excerpt": "",
    }
