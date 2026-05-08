"""
Read-only adapter for providing a stable view of compiler-derived protocol semantics.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any


def _safe_getattr(obj: Any, name: str, default: Any) -> Any:
    try:
        return getattr(obj, name, default)
    except Exception:
        return default


@dataclass(frozen=True)
class RuntimeProtocolSemantics:
    """A stable, read-only snapshot of protocol semantics derived from the compiler."""

    source: str
    shape: str
    is_valid: bool
    error_code: str
    recovery_id: str
    invalid_kind: str
    action_count: int
    has_action: bool
    action_ops: tuple[object, ...]
    intent_ops: tuple[object, ...]
    visible_text: str
    has_visible_answer: bool
    pre_action_text: str
    has_pre_action_text: bool
    visible_text_source: str
    has_memory_tags: bool
    has_subgoal_tags: bool
    has_memory_checkpoint: bool
    memory_ops: tuple[object, ...]
    subgoal_ops: tuple[object, ...]
    has_file_content: bool
    file_content: str
    effects_preview: tuple[object, ...]


def runtime_semantics_from_compiler_analysis(compiler_analysis: Any, *, invalid_kind: str = "") -> RuntimeProtocolSemantics:
    """Creates a semantic snapshot from a CompilerAnalysis object."""
    if compiler_analysis is None:
        return RuntimeProtocolSemantics(
            source="missing_compiler_analysis",
            shape="",
            is_valid=False,
            error_code="",
            recovery_id="",
            invalid_kind=invalid_kind,
            action_count=0,
            has_action=False,
            action_ops=(),
            intent_ops=(),
            visible_text="",
            has_visible_answer=False,
            pre_action_text="",
            has_pre_action_text=False,
            visible_text_source="UNKNOWN",
            has_memory_tags=False,
            has_subgoal_tags=False,
            has_memory_checkpoint=False,
            memory_ops=(),
            subgoal_ops=(),
            has_file_content=False,
            file_content="",
            effects_preview=(),
        )

    ir = _safe_getattr(compiler_analysis, "ir", None)
    error = _safe_getattr(compiler_analysis, "error", None)
    shape_obj = _safe_getattr(compiler_analysis, "shape", None)
    shape_name = str(_safe_getattr(shape_obj, "name", "") or str(shape_obj or "")).strip()

    board_ops = _safe_getattr(ir, "board_ops", ()) or ()
    memory_ops = tuple(op for op in board_ops if _safe_getattr(op, "kind", "") != "subgoal")
    subgoal_ops = tuple(op for op in board_ops if _safe_getattr(op, "kind", "") == "subgoal")

    return RuntimeProtocolSemantics(
        source="compiler",
        shape=shape_name,
        is_valid=bool(shape_name != "INVALID" and error is None),
        error_code=str(_safe_getattr(error, "code", "") or ""),
        recovery_id=str(_safe_getattr(error, "recovery_id", "") or ""),
        invalid_kind=str(invalid_kind or ""),
        action_count=int(_safe_getattr(ir, "action_count", 0) or 0),
        has_action=bool(_safe_getattr(ir, "has_action", False)),
        action_ops=tuple(_safe_getattr(ir, "action_ops", ()) or ()),
        intent_ops=tuple(_safe_getattr(ir, "intent_ops", ()) or ()),
        visible_text=str(_safe_getattr(ir, "visible_text", "") or ""),
        has_visible_answer=bool(_safe_getattr(ir, "has_visible_answer", False)),
        pre_action_text=str(_safe_getattr(ir, "pre_action_text", "") or ""),
        has_pre_action_text=bool(_safe_getattr(ir, "has_pre_action_text", False)),
        visible_text_source=str(_safe_getattr(ir, "visible_text_source", "UNKNOWN") or "UNKNOWN"),
        has_memory_tags=bool(_safe_getattr(ir, "has_memory_tags", False)),
        has_subgoal_tags=bool(_safe_getattr(ir, "has_subgoal_tags", False)),
        has_memory_checkpoint=bool(_safe_getattr(ir, "has_memory_checkpoint", False)),
        memory_ops=memory_ops,
        subgoal_ops=subgoal_ops,
        has_file_content=bool(_safe_getattr(ir, "has_file_content", False)),
        file_content=str(_safe_getattr(ir, "file_content_text", "") or ""),
        effects_preview=tuple(_safe_getattr(ir, "effects_preview", ()) or ()),
    )


def runtime_semantics_from_parsed_output(parsed_output: Any) -> RuntimeProtocolSemantics:
    """Creates a semantic snapshot from a ParsedModelOutput object."""
    compiler_ir = _safe_getattr(parsed_output, "compiler_ir", None)
    if compiler_ir is not None:
        shape_name = str(_safe_getattr(parsed_output, "compiler_shape", "") or "")
        error_code = str(_safe_getattr(parsed_output, "compiler_error_code", "") or "")

        board_ops = _safe_getattr(compiler_ir, "board_ops", ()) or ()
        memory_ops = tuple(op for op in board_ops if _safe_getattr(op, "kind", "") != "subgoal")
        subgoal_ops = tuple(op for op in board_ops if _safe_getattr(op, "kind", "") == "subgoal")

        return RuntimeProtocolSemantics(
            source="compiler",
            shape=shape_name,
            is_valid=bool(shape_name != "INVALID" and not error_code),
            error_code=error_code,
            recovery_id=str(_safe_getattr(parsed_output, "compiler_recovery_id", "") or ""),
            invalid_kind=str(_safe_getattr(parsed_output, "invalid_kind", "") or ""),
            action_count=int(_safe_getattr(compiler_ir, "action_count", 0) or 0),
            has_action=bool(_safe_getattr(compiler_ir, "has_action", False)),
            action_ops=tuple(_safe_getattr(compiler_ir, "action_ops", ()) or ()),
            intent_ops=tuple(_safe_getattr(compiler_ir, "intent_ops", ()) or ()),
            visible_text=str(_safe_getattr(compiler_ir, "visible_text", "") or ""),
            has_visible_answer=bool(_safe_getattr(compiler_ir, "has_visible_answer", False)),
            pre_action_text=str(_safe_getattr(compiler_ir, "pre_action_text", "") or ""),
            has_pre_action_text=bool(_safe_getattr(compiler_ir, "has_pre_action_text", False)),
            visible_text_source=str(_safe_getattr(compiler_ir, "visible_text_source", "UNKNOWN") or "UNKNOWN"),
            has_memory_tags=bool(_safe_getattr(compiler_ir, "has_memory_tags", False)),
            has_subgoal_tags=bool(_safe_getattr(compiler_ir, "has_subgoal_tags", False)),
            has_memory_checkpoint=bool(_safe_getattr(compiler_ir, "has_memory_checkpoint", False)),
            memory_ops=memory_ops,
            subgoal_ops=subgoal_ops,
            has_file_content=bool(_safe_getattr(compiler_ir, "has_file_content", False)),
            file_content=str(_safe_getattr(compiler_ir, "file_content_text", "") or ""),
            effects_preview=tuple(_safe_getattr(compiler_ir, "effects_preview", ()) or ()),
        )

    # Fallback for legacy or missing compiler data
    return RuntimeProtocolSemantics(
        source="legacy_fallback",
        shape=str(_safe_getattr(parsed_output, "compiler_shape", "") or ""),
        is_valid=False,
        error_code=str(_safe_getattr(parsed_output, "compiler_error_code", "") or ""),
        recovery_id=str(_safe_getattr(parsed_output, "compiler_recovery_id", "") or ""),
        invalid_kind=str(_safe_getattr(parsed_output, "invalid_kind", "") or ""),
        action_count=0,
        has_action=False,
        action_ops=(),
        intent_ops=(),
        visible_text="",
        has_visible_answer=False,
        pre_action_text="",
        has_pre_action_text=False,
        visible_text_source="UNKNOWN",
        has_memory_tags=False,
        has_subgoal_tags=False,
        has_memory_checkpoint=False,
        memory_ops=(),
        subgoal_ops=(),
        has_file_content=False,
        file_content="",
        effects_preview=(),
    )


def compact_runtime_protocol_semantics(snapshot: RuntimeProtocolSemantics | None) -> dict[str, Any]:
    """Creates a compact, log-friendly dictionary from a semantic snapshot."""
    if not isinstance(snapshot, RuntimeProtocolSemantics):
        return {"source": "not_a_snapshot"}

    return {
        "source": snapshot.source,
        "shape": snapshot.shape,
        "is_valid": snapshot.is_valid,
        "error_code": snapshot.error_code,
        "recovery_id": snapshot.recovery_id,
        "invalid_kind": snapshot.invalid_kind,
        "action_count": snapshot.action_count,
        "has_action": snapshot.has_action,
        "intent_count": len(snapshot.intent_ops),
        "has_visible_answer": snapshot.has_visible_answer,
        "has_pre_action_text": snapshot.has_pre_action_text,
        "has_file_content": snapshot.has_file_content,
        "effects_preview_count": len(snapshot.effects_preview),
    }


def runtime_semantics_from_output_or_none(parsed_output: Any) -> RuntimeProtocolSemantics | None:
    """Returns an existing semantic snapshot or creates one from compiler fields."""
    if isinstance(getattr(parsed_output, "runtime_protocol_semantics", None), RuntimeProtocolSemantics):
        return parsed_output.runtime_protocol_semantics
    if _safe_getattr(parsed_output, "compiler_ir", None) is not None:
        try:
            return runtime_semantics_from_parsed_output(parsed_output)
        except Exception:
            return None
    return None


def output_recovery_compiler_metadata(parsed_output: Any) -> dict[str, str]:
    """Extracts compiler metadata for output recovery routing, with fallback."""
    snapshot = runtime_semantics_from_output_or_none(parsed_output)
    legacy_invalid_kind = str(_safe_getattr(parsed_output, "invalid_kind", "") or "")

    if snapshot is not None:
        snapshot_invalid_kind = str(_safe_getattr(snapshot, "invalid_kind", "") or "")
        return {
            "source": "runtime_protocol_semantics",
            "error_code": snapshot.error_code,
            "recovery_id": snapshot.recovery_id,
            "invalid_kind": snapshot_invalid_kind or legacy_invalid_kind,
        }

    error_code = str(_safe_getattr(parsed_output, "compiler_error_code", "") or "")
    if error_code:
        return {
            "source": "parsed_output_compiler_fields",
            "error_code": error_code,
            "recovery_id": str(_safe_getattr(parsed_output, "compiler_recovery_id", "") or ""),
            "invalid_kind": legacy_invalid_kind,
        }

    return {
        "source": "missing",
        "error_code": "",
        "recovery_id": "",
        "invalid_kind": legacy_invalid_kind,
    }


def output_recovery_structural_parity(parsed_output: Any, *, parsed_action_count: int = 0) -> dict[str, Any]:
    """Creates a compact parity-check dictionary for output recovery diagnostics."""
    snapshot = runtime_semantics_from_output_or_none(parsed_output)
    if snapshot is None:
        return {"has_snapshot": False}

    parsed_invalid_kind = str(_safe_getattr(parsed_output, "invalid_kind", "") or "")
    snapshot_invalid_kind = str(_safe_getattr(snapshot, "invalid_kind", "") or "")

    action_count_matches = None
    if parsed_action_count > 0 or snapshot.action_count > 0:
        action_count_matches = snapshot.action_count == parsed_action_count

    has_action_matches = None
    parsed_has_action = bool(_safe_getattr(parsed_output, "has_action_segment", False))
    if parsed_has_action or snapshot.has_action:
        has_action_matches = snapshot.has_action == parsed_has_action

    mismatch_kind = ""
    expected_mismatch = False
    if snapshot.shape == "INVALID" and snapshot.error_code:
        if (parsed_action_count > 0 and snapshot.action_count == 0) or (
            parsed_has_action and not snapshot.has_action
        ):
            mismatch_kind = "legacy_action_in_compiler_invalid_response"
            expected_mismatch = True

    return {
        "has_snapshot": True,
        "snapshot_shape": snapshot.shape,
        "snapshot_error_code": snapshot.error_code,
        "snapshot_recovery_id": snapshot.recovery_id,
        "snapshot_invalid_kind": snapshot_invalid_kind,
        "parsed_invalid_kind": parsed_invalid_kind,
        "invalid_kind_matches": snapshot_invalid_kind == parsed_invalid_kind,
        "snapshot_action_count": snapshot.action_count,
        "parsed_action_count": parsed_action_count,
        "action_count_matches": action_count_matches,
        "snapshot_has_action": snapshot.has_action,
        "parsed_has_action_segment": parsed_has_action,
        "has_action_matches": has_action_matches,
        "mismatch_kind": mismatch_kind,
        "expected_mismatch": expected_mismatch,
    }
