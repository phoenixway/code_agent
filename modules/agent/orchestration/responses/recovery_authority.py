"""Observational authority diagnostics for recovery/invalid-output flows."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Tuple

from .terminal_answer_models import TerminalAnswerKind


@dataclass(frozen=True)
class RecoveryAuthorityDiagnostic:
    branch: str = ""
    switch_value: str = "legacy"
    authority_source: str = "legacy"
    effective_source: str = "legacy"
    selected_by_switch: bool = False
    legacy_kind: str = ""
    compiler_kind: str = ""
    typed_kind: str = ""
    parsed_invalid_kind: str = ""
    effective_invalid_kind: str = ""
    agreement: bool = False
    fallback_used: bool = False
    behavior_changed: bool = False
    branch_active: bool = False
    recovery_action: str = ""
    recovery_reason: str = ""
    recovery_prompt_kind: str = ""
    blocking_reasons: Tuple[str, ...] = ()
    compiler_error_code: str = ""
    terminal_answer_kind: str = ""
    parsed_action_count: int = 0
    has_action: bool = False
    has_checkpoint: bool = False
    has_visible_text: bool = False
    is_leaked_system_result: bool = False
    is_internal_summary: bool = False
    retry_count: int = 0
    guard_name: str = ""
    guard_triggered: bool = False
    guard_state: str = ""


@dataclass(frozen=True)
class RecoveryDecisionAuthorityResolution:
    effective_decision: object
    diagnostic: RecoveryAuthorityDiagnostic


def _typed_kind(parsed_output) -> tuple[object | None, str]:
    typed_result = getattr(parsed_output, "terminal_answer_semantic_result", None)
    typed_kind_enum = getattr(typed_result, "kind", None)
    typed_kind = str(getattr(typed_kind_enum, "name", "") or "")
    return typed_kind_enum, typed_kind


def _recovery_facts(parsed_output, *, parsed_action_count: int) -> dict[str, object]:
    typed_kind_enum, typed_kind = _typed_kind(parsed_output)
    compiler_ir = getattr(parsed_output, "compiler_ir", None)
    has_action = bool(
        parsed_action_count > 0
        or getattr(parsed_output, "has_action_segment", False)
        or getattr(compiler_ir, "has_action", False)
    )
    has_checkpoint = bool(
        getattr(compiler_ir, "has_checkpoint", False)
        or getattr(compiler_ir, "has_memory_tags", False)
        or getattr(compiler_ir, "has_subgoal_tags", False)
        or getattr(compiler_ir, "has_memory_checkpoint", False)
    )
    has_visible_text = bool(
        str(getattr(parsed_output, "visible_text", "") or "").strip()
        or getattr(compiler_ir, "has_visible_answer", False)
        or getattr(compiler_ir, "has_pre_action_text", False)
    )
    is_leaked_system_result = typed_kind_enum == TerminalAnswerKind.LEAKED_SYSTEM_RESULT
    is_internal_summary = typed_kind_enum == TerminalAnswerKind.INTERNAL_SUMMARY_LIKE_TEXT
    return {
        "typed_kind_enum": typed_kind_enum,
        "typed_kind": typed_kind,
        "has_action": has_action,
        "has_checkpoint": has_checkpoint,
        "has_visible_text": has_visible_text,
        "is_leaked_system_result": is_leaked_system_result,
        "is_internal_summary": is_internal_summary,
    }


def build_compiler_invalid_mapping_diagnostic(
    parsed_output,
    *,
    compiler_kind: str,
    legacy_kind: str,
    effective_invalid_kind: str,
    parsed_action_count: int = 0,
    has_plain_think_prefix: bool = False,
) -> RecoveryAuthorityDiagnostic:
    return resolve_compiler_invalid_kind_mapping_authority(
        parsed_output,
        compiler_kind=compiler_kind,
        legacy_kind=legacy_kind,
        switch_value="legacy",
        compiler_driven_invalid_kinds=(),
        parsed_action_count=parsed_action_count,
        has_plain_think_prefix=has_plain_think_prefix,
    )


def resolve_compiler_invalid_kind_mapping_authority(
    parsed_output,
    *,
    compiler_kind: str,
    legacy_kind: str,
    switch_value: str,
    compiler_driven_invalid_kinds: tuple[str, ...] | set[str],
    parsed_action_count: int = 0,
    has_plain_think_prefix: bool = False,
    apply_plain_think_prefix_exception: bool = True,
) -> RecoveryAuthorityDiagnostic:
    facts = _recovery_facts(parsed_output, parsed_action_count=parsed_action_count)
    normalized_switch = str(switch_value or "legacy").strip().lower()
    if normalized_switch not in {"legacy", "compiler", "shadow"}:
        normalized_switch = "legacy"
    compiler_error_code = str(getattr(parsed_output, "compiler_error_code", "") or "")
    normalized_compiler_kind = str(compiler_kind or "").strip()
    normalized_legacy_kind = str(legacy_kind or "").strip()
    driven_kinds = set(compiler_driven_invalid_kinds or ())

    effective_invalid_kind = normalized_legacy_kind
    blocking_reasons: list[str] = []
    if has_plain_think_prefix:
        blocking_reasons.append("plain_think_prefix_exception")
    compiler_eligible = bool(normalized_compiler_kind)
    plain_think_prefix_exception = False
    if compiler_eligible:
        plain_think_prefix_exception = bool(
            apply_plain_think_prefix_exception
            and normalized_compiler_kind == "mixed_visible_text_and_control_protocol"
            and has_plain_think_prefix
            and not normalized_legacy_kind
        )
        if plain_think_prefix_exception:
            effective_invalid_kind = normalized_legacy_kind
        elif not normalized_legacy_kind or normalized_legacy_kind in driven_kinds:
            effective_invalid_kind = normalized_compiler_kind
        elif normalized_legacy_kind != normalized_compiler_kind:
            blocking_reasons.append("legacy_kind_preserved")

    if normalized_compiler_kind and effective_invalid_kind and normalized_compiler_kind != effective_invalid_kind:
        blocking_reasons.append("effective_invalid_kind_differs_from_compiler_kind")
    if normalized_legacy_kind and normalized_compiler_kind and normalized_legacy_kind != normalized_compiler_kind:
        blocking_reasons.append("legacy_compiler_mismatch")

    branch_active = bool(
        compiler_error_code
        or normalized_compiler_kind
        or normalized_legacy_kind
        or effective_invalid_kind
    )
    agreement = bool(
        normalized_compiler_kind
        and (
            not normalized_legacy_kind
            or normalized_compiler_kind == normalized_legacy_kind
        )
    )
    compiler_safe_for_switch = bool(
        compiler_eligible
        and effective_invalid_kind == normalized_compiler_kind
        and not plain_think_prefix_exception
        and "legacy_kind_preserved" not in blocking_reasons
    )

    if normalized_compiler_kind and effective_invalid_kind == normalized_compiler_kind:
        effective_source = "compiler"
    elif effective_invalid_kind:
        effective_source = "legacy"
    else:
        effective_source = "none"

    if normalized_switch == "compiler":
        if compiler_safe_for_switch:
            authority_source = "compiler"
            fallback_used = False
            selected_by_switch = True
        else:
            authority_source = "legacy_fallback"
            fallback_used = True
            selected_by_switch = False
    else:
        if effective_invalid_kind:
            authority_source = "legacy"
            fallback_used = False
        else:
            authority_source = "legacy_fallback"
            fallback_used = True
        selected_by_switch = False

    return RecoveryAuthorityDiagnostic(
        branch="recovery.compiler_invalid_kind_mapping",
        switch_value=normalized_switch,
        authority_source=authority_source,
        effective_source=effective_source,
        selected_by_switch=selected_by_switch,
        legacy_kind=normalized_legacy_kind,
        compiler_kind=normalized_compiler_kind,
        typed_kind=str(facts["typed_kind"] or ""),
        parsed_invalid_kind=normalized_legacy_kind,
        effective_invalid_kind=str(effective_invalid_kind or ""),
        agreement=agreement,
        fallback_used=fallback_used,
        behavior_changed=False,
        branch_active=branch_active,
        recovery_action="",
        recovery_reason="",
        recovery_prompt_kind="",
        blocking_reasons=tuple(blocking_reasons),
        compiler_error_code=compiler_error_code,
        terminal_answer_kind=str(facts["typed_kind"] or ""),
        parsed_action_count=int(parsed_action_count or 0),
        has_action=bool(facts["has_action"]),
        has_checkpoint=bool(facts["has_checkpoint"]),
        has_visible_text=bool(facts["has_visible_text"]),
        is_leaked_system_result=bool(facts["is_leaked_system_result"]),
        is_internal_summary=bool(facts["is_internal_summary"]),
        retry_count=0,
        guard_name="",
        guard_triggered=False,
        guard_state="",
    )


def build_prevalidation_reject_invalid_output_diagnostic(
    parsed_output,
    *,
    recovery_action: str,
    recovery_reason: str = "",
    recovery_prompt_kind: str = "",
    parsed_action_count: int = 0,
    malformed_action_retries: int = 0,
    guard_name: str = "",
    guard_triggered: bool = False,
    guard_state: str = "",
) -> RecoveryAuthorityDiagnostic:
    return resolve_prevalidation_reject_invalid_output_authority(
        parsed_output,
        legacy_decision=None,
        switch_value="legacy",
        parsed_action_count=parsed_action_count,
        malformed_action_retries=malformed_action_retries,
        guard_name=guard_name,
        guard_triggered=guard_triggered,
        guard_state=guard_state,
        recovery_action=recovery_action,
        recovery_reason=recovery_reason,
        recovery_prompt_kind=recovery_prompt_kind,
    ).diagnostic


def resolve_prevalidation_reject_invalid_output_authority(
    parsed_output,
    *,
    legacy_decision,
    switch_value: str,
    parsed_action_count: int = 0,
    malformed_action_retries: int = 0,
    guard_name: str = "",
    guard_triggered: bool = False,
    guard_state: str = "",
    recovery_action: str = "",
    recovery_reason: str = "",
    recovery_prompt_kind: str = "",
) -> RecoveryDecisionAuthorityResolution:
    facts = _recovery_facts(parsed_output, parsed_action_count=parsed_action_count)
    normalized_switch = str(switch_value or "legacy").strip().lower()
    if normalized_switch not in {"legacy", "compiler", "shadow"}:
        normalized_switch = "legacy"
    legacy_kind = str(getattr(parsed_output, "invalid_kind", "") or "")
    compiler_kind = str(getattr(parsed_output, "compiler_error_code", "") or "")
    effective_invalid_kind = legacy_kind
    decision = legacy_decision
    decision_reason = str(recovery_reason or getattr(decision, "reason", "") or "")
    decision_prompt_kind = str(
        recovery_prompt_kind
        or ("output_recovery_query" if bool(getattr(decision, "next_query", "")) else "")
    )
    decision_action = str(recovery_action or decision_reason or "")
    blocking_reasons: list[str] = []
    if facts["has_action"]:
        blocking_reasons.append("action_present")
    if facts["has_checkpoint"]:
        blocking_reasons.append("checkpoint_present")
    if facts["is_leaked_system_result"]:
        blocking_reasons.append("leaked_system_result_present")

    typed_recovery_kind = facts["typed_kind"] in {
        TerminalAnswerKind.LEAKED_SYSTEM_RESULT.name,
        TerminalAnswerKind.INTERNAL_SUMMARY_LIKE_TEXT.name,
        TerminalAnswerKind.INVALID_OR_TRUNCATED_TERMINAL_TEXT.name,
    }

    if legacy_kind and compiler_kind:
        effective_source = "mixed" if legacy_kind != compiler_kind else "compiler"
    elif legacy_kind:
        effective_source = "legacy"
    elif typed_recovery_kind:
        effective_source = "typed"
    else:
        effective_source = "legacy"

    branch_active = bool(legacy_kind or compiler_kind or facts["typed_kind"] or getattr(decision, "handled", False))
    agreement = bool(not compiler_kind or compiler_kind == legacy_kind)
    behavior_changed = False

    if normalized_switch == "compiler":
        authority_source = "legacy_fallback"
        fallback_used = True
        selected_by_switch = False
        blocking_reasons.append("no_compiler_decision_path")
    else:
        if branch_active:
            authority_source = "legacy"
            fallback_used = False
        else:
            authority_source = "legacy_fallback"
            fallback_used = True
        selected_by_switch = False

    diagnostic = RecoveryAuthorityDiagnostic(
        branch="recovery.prevalidation_reject_invalid_output",
        switch_value=normalized_switch,
        authority_source=authority_source,
        effective_source=effective_source,
        selected_by_switch=selected_by_switch,
        legacy_kind=legacy_kind,
        compiler_kind=compiler_kind,
        typed_kind=str(facts["typed_kind"] or ""),
        parsed_invalid_kind=legacy_kind,
        effective_invalid_kind=effective_invalid_kind,
        agreement=agreement,
        fallback_used=fallback_used,
        behavior_changed=behavior_changed,
        branch_active=branch_active,
        recovery_action=decision_action,
        recovery_reason=decision_reason,
        recovery_prompt_kind=decision_prompt_kind,
        blocking_reasons=tuple(blocking_reasons),
        compiler_error_code=compiler_kind,
        terminal_answer_kind=str(facts["typed_kind"] or ""),
        parsed_action_count=int(parsed_action_count or 0),
        has_action=bool(facts["has_action"]),
        has_checkpoint=bool(facts["has_checkpoint"]),
        has_visible_text=bool(facts["has_visible_text"]),
        is_leaked_system_result=bool(facts["is_leaked_system_result"]),
        is_internal_summary=bool(facts["is_internal_summary"]),
        retry_count=int(malformed_action_retries or 0),
        guard_name=str(guard_name or ""),
        guard_triggered=bool(guard_triggered),
        guard_state=str(guard_state or ""),
    )
    return RecoveryDecisionAuthorityResolution(
        effective_decision=decision,
        diagnostic=diagnostic,
    )
