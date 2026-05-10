"""Observational authority diagnostics for terminal-answer branches."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Tuple

from .terminal_answer_models import TerminalAnswerKind


@dataclass(frozen=True)
class TerminalAnswerAuthorityDiagnostic:
    branch: str = ""
    switch_value: str = "legacy"
    authority_source: str = "legacy"
    legacy_active: bool = False
    typed_kind: str = "UNKNOWN"
    legacy_kind: str = "none"
    agreement: bool = False
    fallback_used: bool = False
    behavior_changed: bool = False
    branch_active: bool = False
    typed_eligible: bool = False
    typed_plaintext_eligible: bool = False
    effective_value: bool = False
    invalid_kind: str = ""
    compiler_shape: str = ""
    terminal_answer_kind: str = ""
    has_action: bool = False
    has_checkpoint: bool = False
    has_visible_text: bool = False
    is_leaked_system_result: bool = False
    invalid_or_truncated_terminal_text: bool = False
    checkpoint_with_visible_text_overlap: bool = False
    leaked_system_result_overlap: bool = False
    action_or_pre_action_overlap: bool = False
    clean_plaintext_candidate: bool = False
    clean_checkpoint_only_candidate: bool = False
    blocking_reasons: Tuple[str, ...] = ()
    mismatch_reason: str = ""


def resolve_plaintext_terminal_answer_authority(
    parsed_output,
    *,
    legacy_plaintext_answer_path: bool,
    switch_value: str,
) -> TerminalAnswerAuthorityDiagnostic:
    """
    Observational-only resolver for terminal plaintext authority.

    Step 28.2 intentionally does not transfer authority. The effective value
    always remains the current legacy plaintext-answer-path decision.
    """
    normalized_switch = str(switch_value or "legacy").strip().lower()
    if normalized_switch not in {"legacy", "compiler", "shadow"}:
        normalized_switch = "legacy"

    typed_result = getattr(parsed_output, "terminal_answer_semantic_result", None)
    typed_kind = str(getattr(getattr(typed_result, "kind", None), "name", "UNKNOWN") or "UNKNOWN")
    typed_kind_enum = getattr(typed_result, "kind", None)
    compiler_ir = getattr(parsed_output, "compiler_ir", None)
    has_action = bool(getattr(compiler_ir, "has_action", False))
    has_checkpoint = bool(
        getattr(compiler_ir, "has_checkpoint", False)
        or getattr(compiler_ir, "has_memory_tags", False)
        or getattr(compiler_ir, "has_subgoal_tags", False)
        or getattr(compiler_ir, "has_memory_checkpoint", False)
    )
    invalid_kind = str(getattr(parsed_output, "invalid_kind", "") or "")
    compiler_shape = str(getattr(parsed_output, "compiler_shape", "") or "")
    is_leaked_system_result = bool(
        typed_result is not None
        and typed_kind_enum == TerminalAnswerKind.LEAKED_SYSTEM_RESULT
    )
    invalid_or_truncated_terminal_text = bool(
        typed_result is not None
        and typed_kind_enum == TerminalAnswerKind.INVALID_OR_TRUNCATED_TERMINAL_TEXT
    )
    action_or_pre_action_overlap = bool(
        has_action
        or typed_kind_enum == TerminalAnswerKind.PRE_ACTION_VISIBLE_TEXT_WITH_ACTION
    )
    typed_plaintext_eligible = bool(
        typed_result is not None
        and typed_kind_enum == TerminalAnswerKind.PLAINTEXT_TERMINAL_ANSWER
        and not invalid_kind
        and not action_or_pre_action_overlap
        and not has_checkpoint
        and not is_leaked_system_result
        and compiler_shape == "PURE_PLAINTEXT"
    )
    typed_eligible = typed_plaintext_eligible
    legacy_kind = "plaintext_answer_path" if legacy_plaintext_answer_path else "none"
    legacy_active = bool(legacy_plaintext_answer_path)
    agreement = legacy_plaintext_answer_path == typed_eligible
    branch_active = bool(legacy_active or typed_eligible)
    checkpoint_with_visible_text_overlap = bool(
        legacy_active
        and (
            typed_kind == TerminalAnswerKind.CHECKPOINT_WITH_VISIBLE_TEXT.name
            or has_checkpoint
        )
    )
    leaked_system_result_overlap = bool(legacy_active and is_leaked_system_result)
    clean_plaintext_candidate = bool(legacy_active and typed_plaintext_eligible)
    blocking_reasons: list[str] = []
    if invalid_or_truncated_terminal_text:
        blocking_reasons.append("invalid_or_truncated_terminal_text")
    if checkpoint_with_visible_text_overlap:
        blocking_reasons.append("checkpoint_with_visible_text_overlap")
    if leaked_system_result_overlap:
        blocking_reasons.append("leaked_system_result_overlap")
    if action_or_pre_action_overlap:
        blocking_reasons.append("action_or_pre_action_overlap")
    if invalid_kind:
        blocking_reasons.append("invalid_kind")

    mismatch_reason = ""
    if branch_active and not agreement:
        if invalid_or_truncated_terminal_text:
            mismatch_reason = "invalid_or_truncated_plaintext_overlap"
        elif checkpoint_with_visible_text_overlap:
            mismatch_reason = "checkpoint_visible_text_overlap"
        elif leaked_system_result_overlap:
            mismatch_reason = "leaked_system_result_overlap"
        elif action_or_pre_action_overlap:
            mismatch_reason = "action_or_pre_action_overlap"
        else:
            mismatch_reason = "legacy_typed_disagreement"
    elif not branch_active:
        if action_or_pre_action_overlap:
            mismatch_reason = "action_or_pre_action_overlap"
        elif invalid_kind:
            mismatch_reason = "invalid_output"
        else:
            mismatch_reason = "branch_inactive"

    if normalized_switch == "compiler":
        if clean_plaintext_candidate and agreement and not blocking_reasons:
            authority_source = "compiler"
            fallback_used = False
        else:
            authority_source = "legacy_fallback"
            fallback_used = True
    else:
        if legacy_active:
            authority_source = "legacy"
            fallback_used = False
        else:
            authority_source = "legacy_fallback"
            fallback_used = True

    return TerminalAnswerAuthorityDiagnostic(
        branch="terminal_answer.plaintext_terminal_answer",
        switch_value=normalized_switch,
        authority_source=authority_source,
        legacy_active=legacy_active,
        typed_kind=typed_kind,
        legacy_kind=legacy_kind,
        agreement=agreement,
        fallback_used=fallback_used,
        behavior_changed=False,
        branch_active=branch_active,
        typed_eligible=typed_eligible,
        typed_plaintext_eligible=typed_plaintext_eligible,
        effective_value=legacy_plaintext_answer_path,
        invalid_kind=invalid_kind,
        compiler_shape=compiler_shape,
        terminal_answer_kind=typed_kind,
        has_action=has_action,
        has_checkpoint=has_checkpoint,
        is_leaked_system_result=is_leaked_system_result,
        invalid_or_truncated_terminal_text=invalid_or_truncated_terminal_text,
        checkpoint_with_visible_text_overlap=checkpoint_with_visible_text_overlap,
        leaked_system_result_overlap=leaked_system_result_overlap,
        action_or_pre_action_overlap=action_or_pre_action_overlap,
        clean_plaintext_candidate=clean_plaintext_candidate,
        blocking_reasons=tuple(blocking_reasons),
        mismatch_reason=mismatch_reason,
    )


def resolve_checkpoint_only_terminal_authority(
    parsed_output,
    *,
    legacy_checkpoint_only_active: bool,
    switch_value: str,
) -> TerminalAnswerAuthorityDiagnostic:
    normalized_switch = str(switch_value or "legacy").strip().lower()
    if normalized_switch not in {"legacy", "compiler", "shadow"}:
        normalized_switch = "legacy"

    typed_result = getattr(parsed_output, "terminal_answer_semantic_result", None)
    typed_kind_enum = getattr(typed_result, "kind", None)
    typed_kind = str(getattr(typed_kind_enum, "name", "UNKNOWN") or "UNKNOWN")
    compiler_ir = getattr(parsed_output, "compiler_ir", None)
    has_action = bool(getattr(compiler_ir, "has_action", False))
    has_checkpoint = bool(
        getattr(compiler_ir, "has_checkpoint", False)
        or getattr(compiler_ir, "has_memory_tags", False)
        or getattr(compiler_ir, "has_subgoal_tags", False)
        or getattr(compiler_ir, "has_memory_checkpoint", False)
    )
    has_visible_text = bool(
        getattr(compiler_ir, "has_visible_answer", False)
        or getattr(compiler_ir, "has_pre_action_text", False)
    )
    invalid_kind = str(getattr(parsed_output, "invalid_kind", "") or "")
    compiler_shape = str(getattr(parsed_output, "compiler_shape", "") or "")
    is_leaked_system_result = bool(
        typed_result is not None and typed_kind_enum == TerminalAnswerKind.LEAKED_SYSTEM_RESULT
    )
    invalid_or_truncated_terminal_text = bool(
        typed_result is not None
        and typed_kind_enum == TerminalAnswerKind.INVALID_OR_TRUNCATED_TERMINAL_TEXT
    )
    checkpoint_with_visible_text_overlap = bool(
        typed_kind_enum == TerminalAnswerKind.CHECKPOINT_WITH_VISIBLE_TEXT or (has_checkpoint and has_visible_text)
    )
    action_or_pre_action_overlap = bool(
        has_action or typed_kind_enum == TerminalAnswerKind.PRE_ACTION_VISIBLE_TEXT_WITH_ACTION
    )
    leaked_system_result_overlap = bool(is_leaked_system_result)
    typed_eligible = bool(
        typed_result is not None
        and typed_kind_enum == TerminalAnswerKind.CHECKPOINT_ONLY
        and has_checkpoint
        and not has_visible_text
        and not has_action
        and not is_leaked_system_result
        and not invalid_kind
    )
    agreement = bool(legacy_checkpoint_only_active == typed_eligible)
    branch_active = bool(legacy_checkpoint_only_active or typed_eligible)
    clean_checkpoint_only_candidate = bool(legacy_checkpoint_only_active and typed_eligible)

    blocking_reasons: list[str] = []
    if checkpoint_with_visible_text_overlap:
        blocking_reasons.append("checkpoint_with_visible_text_overlap")
    if action_or_pre_action_overlap:
        blocking_reasons.append("action_or_pre_action_overlap")
    if leaked_system_result_overlap:
        blocking_reasons.append("leaked_system_result_overlap")
    if invalid_or_truncated_terminal_text:
        blocking_reasons.append("invalid_or_truncated_terminal_text")
    if invalid_kind:
        blocking_reasons.append("invalid_kind")

    if branch_active and not agreement:
        if checkpoint_with_visible_text_overlap:
            mismatch_reason = "checkpoint_visible_text_overlap"
        elif action_or_pre_action_overlap:
            mismatch_reason = "action_or_pre_action_overlap"
        elif leaked_system_result_overlap:
            mismatch_reason = "leaked_system_result_overlap"
        elif invalid_or_truncated_terminal_text:
            mismatch_reason = "invalid_or_truncated_terminal_text"
        else:
            mismatch_reason = "legacy_typed_disagreement"
    elif not branch_active:
        if action_or_pre_action_overlap:
            mismatch_reason = "action_or_pre_action_overlap"
        elif invalid_kind:
            mismatch_reason = "invalid_output"
        else:
            mismatch_reason = "branch_inactive"
    else:
        mismatch_reason = ""

    if normalized_switch == "compiler":
        if clean_checkpoint_only_candidate and agreement and not blocking_reasons:
            authority_source = "compiler"
            fallback_used = False
        else:
            authority_source = "legacy_fallback"
            fallback_used = True
    else:
        if legacy_checkpoint_only_active:
            authority_source = "legacy"
            fallback_used = False
        else:
            authority_source = "legacy_fallback"
            fallback_used = True

    return TerminalAnswerAuthorityDiagnostic(
        branch="terminal_answer.checkpoint_only",
        switch_value=normalized_switch,
        authority_source=authority_source,
        legacy_active=bool(legacy_checkpoint_only_active),
        typed_kind=typed_kind,
        legacy_kind="checkpoint_only" if legacy_checkpoint_only_active else "none",
        agreement=agreement,
        fallback_used=fallback_used,
        behavior_changed=False,
        branch_active=branch_active,
        typed_eligible=typed_eligible,
        effective_value=bool(legacy_checkpoint_only_active),
        invalid_kind=invalid_kind,
        compiler_shape=compiler_shape,
        terminal_answer_kind=typed_kind,
        has_action=has_action,
        has_checkpoint=has_checkpoint,
        has_visible_text=has_visible_text,
        is_leaked_system_result=is_leaked_system_result,
        invalid_or_truncated_terminal_text=invalid_or_truncated_terminal_text,
        checkpoint_with_visible_text_overlap=checkpoint_with_visible_text_overlap,
        leaked_system_result_overlap=leaked_system_result_overlap,
        action_or_pre_action_overlap=action_or_pre_action_overlap,
        clean_checkpoint_only_candidate=clean_checkpoint_only_candidate,
        blocking_reasons=tuple(blocking_reasons),
        mismatch_reason=mismatch_reason,
    )
