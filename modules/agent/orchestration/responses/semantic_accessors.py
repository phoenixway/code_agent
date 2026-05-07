"""
Semantic accessors for behavior-preserving reads of response semantics.

This module provides a single, testable access point for selected semantic
reads. It acts as a translation layer between the raw `ParsedModelOutput` (with
its mix of legacy and compiler fields) and the rest of the runtime for
specific, approved use cases.

Core Principles:
- Compiler-First, Legacy-Aware: Accessors prioritize data from
  `RuntimeProtocolSemantics` but maintain careful, explicit fallbacks to legacy
  fields to ensure backward compatibility.
- Strict Authority Boundaries: Accessors provide STRUCTURAL FACTS, not
  POLICY DECISIONS. For example, an accessor can state `has_action`, but it
  cannot state `is_dispatch_allowed`.
"""

from __future__ import annotations

from typing import Any

from ..shared.decision_models import ParsedModelOutput
from .runtime_protocol_semantics import runtime_semantics_from_output_or_none


def _safe_getattr(obj: Any, name: str, default: Any) -> Any:
    """Safely get an attribute from an object that might not have it."""
    try:
        return getattr(obj, name, default)
    except Exception:
        return default


def get_compiler_metadata(parsed_output: ParsedModelOutput | None) -> dict[str, str]:
    """
    Provides a stable, centralized way to access compiler-derived metadata
    (error_code, recovery_id, invalid_kind) for recovery and diagnostic purposes.

    This accessor formalizes the logic from the now-deprecated
    `output_recovery_compiler_metadata` helper.

    Authority Boundary: Structural Fact. This is NOT dispatch authority.
    """
    if parsed_output is None:
        return {"source": "missing", "error_code": "", "recovery_id": "", "invalid_kind": ""}

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


def has_any_action_proposal_compat(parsed_output: ParsedModelOutput | None, parsed_action_count: int = 0) -> bool:
    """
    Behavior-preserving, backward-compatible check for any "action-like" content
    for recovery and guardrail purposes only.

    This accessor replaces `ResponseSemantics.has_any_action_proposal`.

    Authority Boundary: Compatibility Shim / Recovery Evidence.
    A `True` result is NOT dispatch permission.
    """
    if parsed_output is None:
        return False

    # 1. Check legacy parsed action count.
    if int(parsed_action_count or 0) > 0:
        return True

    # 2. Check for compiler-derived action ops (critical compatibility shim).
    ir = _safe_getattr(parsed_output, "compiler_ir", None)
    if ir is not None and len(list(_safe_getattr(ir, "action_ops", ()) or ())) > 0:
        return True

    # 3. Check for legacy action segment flag.
    return bool(_safe_getattr(parsed_output, "has_action_segment", False))


def is_compiler_invalid(parsed_output: ParsedModelOutput | None) -> bool:
    """
    Provides a single, unambiguous signal of whether the protocol compiler
    found the response to be structurally invalid.

    Authority Boundary: Supreme Structural Fact.
    A `True` result means the response is structurally invalid and, per the
    constitution, MUST NOT be dispatched.
    """
    if parsed_output is None:
        return False

    snapshot = runtime_semantics_from_output_or_none(parsed_output)
    if snapshot is not None:
        # Source of truth is the snapshot's validity flag.
        return not snapshot.is_valid

    # Fallback to legacy fields if snapshot is not available.
    if str(_safe_getattr(parsed_output, "compiler_shape", "") or "") == "INVALID":
        return True

    if str(_safe_getattr(parsed_output, "compiler_error_code", "") or ""):
        return True

    # If no compiler information is present, it cannot be compiler-invalid.
    return False


def is_compiler_invalid_with_legacy_action(
    parsed_output: ParsedModelOutput | None, parsed_action_count: int = 0
) -> bool:
    """
    Detects the high-risk condition where the compiler deems a response
    structurally invalid, but a broad compatibility check detects action-like
    content.

    This is the primary scenario the "Compiler `INVALID` Is Final" invariant
    is designed to protect against.

    Authority Boundary: Safety Check / Recovery Trigger.
    A `True` result indicates that a dispatch would violate the constitution.
    The action-like content should be treated as RECOVERY EVIDENCE ONLY.
    """
    # This is a pure composition of the other two accessors.
    # It is True only if the compiler found an issue AND there is some
    # form of action-like content (legacy or compiler-derived).
    return is_compiler_invalid(parsed_output) and has_any_action_proposal_compat(
        parsed_output, parsed_action_count
    )
