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
        memory_ops=(),
        subgoal_ops=(),
        has_file_content=False,
        file_content="",
        effects_preview=(),
    )
