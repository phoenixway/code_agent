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
    "compiler_shape": "",
    "compiler_code": "",
    "compiler_recovery_id": "",
    "compiler_replay": None,
    "execution_plan": None,
    "execution_commit": None,
    "bundle_validated": None,
    "invalid_part": "",
    "bundle_reason": "",
    "action_dispatched": None,
    "model_action_present": None,
    "action_validated": None,
    "execution_plan_dispatched": None,
    "atomic_bundle_validated": None,
    "fallback_dispatch_used": None,
    "tool_execution_attempted": None,
    "tool_execution_succeeded": None,
    "system_result_recorded": None,
    "state_change_effect_recorded": None,
    "state_change_applied": None,
    "active_intent_unchanged": None,
    "before_active_intent_id": "",
    "after_active_intent_id": "",
    "plan_review_required_after_state_change": None,
    "plan_review_required_reason": "",
    "plan_review_required_action_type": "",
    "plan_review_required_target": "",
    "plan_review_required_action_effects": None,
    "fallback_commit_used": None,
    "fallback_commit_reason": "",
}


def compact_execution_plan(execution_plan) -> dict | None:
    if execution_plan is None:
        return None
    return {
        "shape": getattr(execution_plan, "shape", ""),
        "transaction_kind": getattr(execution_plan, "transaction_kind", ""),
        "bundle_validated": getattr(execution_plan, "bundle_validated", False),
        "transition_applied": getattr(execution_plan, "transition_applied", False),
        "action_dispatched": getattr(execution_plan, "action_dispatched", False),
        "before_active_intent_id": getattr(execution_plan, "before_active_intent_id", ""),
        "after_active_intent_id": getattr(execution_plan, "after_active_intent_id", ""),
        "action_effects": list(getattr(execution_plan, "action_effects", []) or []),
    }


def compact_execution_commit(execution_commit) -> dict | None:
    if execution_commit is None:
        return None
    return {
        "shape": getattr(execution_commit, "shape", ""),
        "transaction_kind": getattr(execution_commit, "transaction_kind", ""),
        "bundle_validated": getattr(execution_commit, "bundle_validated", False),
        "transition_applied": getattr(execution_commit, "transition_applied", False),
        "action_dispatched": getattr(execution_commit, "action_dispatched", False),
        "before_active_intent_id": getattr(execution_commit, "before_active_intent_id", ""),
        "after_active_intent_id": getattr(execution_commit, "after_active_intent_id", ""),
        "committed_action_count": getattr(execution_commit, "committed_action_count", 0),
        "committed_system_result_count": getattr(execution_commit, "committed_system_result_count", 0),
        "dispatch_stop_requested": getattr(execution_commit, "dispatch_stop_requested", False),
        "action_effects": list(getattr(execution_commit, "action_effects", []) or []),
    }


def compact_compiler_replay(compiler_analysis) -> dict:
    snapshot = {
        "shape": getattr(getattr(compiler_analysis, "shape", None), "name", ""),
        "error_code": str(getattr(getattr(compiler_analysis, "error", None), "code", "") or ""),
        "recovery_id": str(getattr(getattr(compiler_analysis, "error", None), "recovery_id", "") or ""),
        "tokens": [],
        "ast_nodes": [],
        "ir": None,
        "span_excerpt": "",
    }
    error_span = getattr(getattr(compiler_analysis, "error", None), "span", None)
    if error_span is not None:
        snapshot["span_excerpt"] = str(getattr(error_span, "excerpt", "") or "")
    for token in list(getattr(compiler_analysis, "tokens", ()) or ())[:12]:
        snapshot["tokens"].append(token.__class__.__name__)
    ast = getattr(compiler_analysis, "ast", None)
    for node in list(getattr(ast, "nodes", ()) or ())[:12]:
        snapshot["ast_nodes"].append(node.__class__.__name__)
    ir = getattr(compiler_analysis, "ir", None)
    if ir is not None:
        snapshot["ir"] = {
            "shape": getattr(getattr(ir, "shape", None), "name", ""),
            "intent_ops": len(getattr(ir, "intent_ops", ()) or ()),
            "action_ops": len(getattr(ir, "action_ops", ()) or ()),
            "board_ops": len(getattr(ir, "board_ops", ()) or ()),
            "annotations": len(getattr(ir, "annotations", ()) or ()),
            "visible_answer": bool(getattr(ir, "visible_answer", None)),
            "file_content": bool(getattr(ir, "file_content", None)),
            "effects_preview": [
                str(getattr(effect, "summary", "") or "")
                for effect in list(getattr(ir, "effects_preview", ()) or ())[:6]
            ],
        }
    return snapshot


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
