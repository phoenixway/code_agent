"""Pure observational builder for board/checkpoint semantic results."""

from __future__ import annotations

from .board_checkpoint_models import (
    BoardCheckpointAuthorityDiagnostic,
    BoardCheckpointKind,
    EffectiveCheckpointFlags,
    BoardCheckpointSemanticResult,
    BoardCheckpointSource,
)




def checkpoint_outcome_category(*, checkpoint_only: bool, checkpoint_and_text: bool, checkpoint_and_action: bool) -> str:
    if checkpoint_and_action:
        return "checkpoint_and_action"
    if checkpoint_and_text:
        return "checkpoint_and_text"
    if checkpoint_only:
        return "checkpoint_only"
    return "none"


def legacy_derived_checkpoint_kind(result: BoardCheckpointSemanticResult | None) -> BoardCheckpointKind | None:
    if result is None:
        return None
    if result.source not in {
        BoardCheckpointSource.LEGACY_HANDLER_OUTCOME,
        BoardCheckpointSource.COMBINED_SHADOW,
    }:
        return None
    return result.kind


def is_legacy_derived_memory_checkpoint_only(
    result: BoardCheckpointSemanticResult | None,
    *,
    legacy_memory_checkpoint_only: bool,
) -> bool:
    return bool(
        legacy_memory_checkpoint_only
        and legacy_derived_checkpoint_kind(result) == BoardCheckpointKind.MEMORY_CHECKPOINT_ONLY
    )


def is_legacy_derived_memory_checkpoint_and_text(
    result: BoardCheckpointSemanticResult | None,
    *,
    legacy_memory_checkpoint_and_text: bool,
) -> bool:
    return bool(
        legacy_memory_checkpoint_and_text
        and legacy_derived_checkpoint_kind(result) == BoardCheckpointKind.MEMORY_CHECKPOINT_WITH_TEXT
    )


def is_legacy_derived_plan_checkpoint_only(
    result: BoardCheckpointSemanticResult | None,
    *,
    legacy_plan_checkpoint_only: bool,
) -> bool:
    return bool(
        legacy_plan_checkpoint_only
        and legacy_derived_checkpoint_kind(result) == BoardCheckpointKind.PLAN_CHECKPOINT_ONLY
    )


def is_legacy_derived_memory_checkpoint_and_action(
    result: BoardCheckpointSemanticResult | None,
    *,
    legacy_memory_checkpoint_and_action: bool,
) -> bool:
    return bool(
        legacy_memory_checkpoint_and_action
        and legacy_derived_checkpoint_kind(result) == BoardCheckpointKind.MEMORY_CHECKPOINT_WITH_ACTION
    )


def is_legacy_derived_plan_checkpoint_and_text(
    result: BoardCheckpointSemanticResult | None,
    *,
    legacy_plan_checkpoint_and_text: bool,
) -> bool:
    return bool(
        legacy_plan_checkpoint_and_text
        and legacy_derived_checkpoint_kind(result) == BoardCheckpointKind.PLAN_CHECKPOINT_WITH_TEXT
    )


def is_legacy_derived_plan_checkpoint_and_action(
    result: BoardCheckpointSemanticResult | None,
    *,
    legacy_plan_checkpoint_and_action: bool,
) -> bool:
    return bool(
        legacy_plan_checkpoint_and_action
        and legacy_derived_checkpoint_kind(result) == BoardCheckpointKind.PLAN_CHECKPOINT_WITH_ACTION
    )


def _resolve_checkpoint_typed_primary_candidate(
    result: BoardCheckpointSemanticResult | None,
    *,
    expected_kind: BoardCheckpointKind,
    legacy_flag: bool,
    other_legacy_flags: list[bool],
) -> bool:
    """
    Generic, behavior-preserving resolver for typed-primary candidates.

    For now, this is a structural placeholder that always returns the legacy
    flag, ensuring no behavior change. The structure allows for future
    strengthening of the typed-primary logic.
    """
    kind = legacy_derived_checkpoint_kind(result)
    if kind is None:
        return legacy_flag

    if any(other_legacy_flags):
        return legacy_flag

    if kind == expected_kind:
        return legacy_flag

    return legacy_flag


def resolve_memory_checkpoint_only_typed_primary(
    result: BoardCheckpointSemanticResult | None,
    *,
    legacy_memory_checkpoint_only: bool,
    legacy_memory_checkpoint_and_text: bool = False,
    legacy_memory_checkpoint_and_action: bool = False,
) -> bool:
    """Resolve memory-checkpoint-only with typed-primary logic."""
    return _resolve_checkpoint_typed_primary_candidate(
        result,
        expected_kind=BoardCheckpointKind.MEMORY_CHECKPOINT_ONLY,
        legacy_flag=legacy_memory_checkpoint_only,
        other_legacy_flags=[
            legacy_memory_checkpoint_and_text,
            legacy_memory_checkpoint_and_action,
        ],
    )


def resolve_memory_checkpoint_and_text_typed_primary(
    result: BoardCheckpointSemanticResult | None,
    *,
    legacy_memory_checkpoint_only: bool,
    legacy_memory_checkpoint_and_text: bool,
    legacy_memory_checkpoint_and_action: bool,
) -> bool:
    """Resolve memory-checkpoint-and-text with typed-primary logic."""
    return _resolve_checkpoint_typed_primary_candidate(
        result,
        expected_kind=BoardCheckpointKind.MEMORY_CHECKPOINT_WITH_TEXT,
        legacy_flag=legacy_memory_checkpoint_and_text,
        other_legacy_flags=[
            legacy_memory_checkpoint_only,
            legacy_memory_checkpoint_and_action,
        ],
    )


def resolve_memory_checkpoint_and_action_typed_primary(
    result: BoardCheckpointSemanticResult | None,
    *,
    legacy_memory_checkpoint_only: bool,
    legacy_memory_checkpoint_and_text: bool,
    legacy_memory_checkpoint_and_action: bool,
) -> bool:
    """Resolve memory-checkpoint-and-action with typed-primary logic."""
    return _resolve_checkpoint_typed_primary_candidate(
        result,
        expected_kind=BoardCheckpointKind.MEMORY_CHECKPOINT_WITH_ACTION,
        legacy_flag=legacy_memory_checkpoint_and_action,
        other_legacy_flags=[
            legacy_memory_checkpoint_only,
            legacy_memory_checkpoint_and_text,
        ],
    )


def resolve_plan_checkpoint_only_typed_primary(
    result: BoardCheckpointSemanticResult | None,
    *,
    legacy_plan_checkpoint_only: bool,
    legacy_plan_checkpoint_and_text: bool,
    legacy_plan_checkpoint_and_action: bool,
) -> bool:
    """Resolve plan-checkpoint-only with typed-primary logic."""
    return _resolve_checkpoint_typed_primary_candidate(
        result,
        expected_kind=BoardCheckpointKind.PLAN_CHECKPOINT_ONLY,
        legacy_flag=legacy_plan_checkpoint_only,
        other_legacy_flags=[
            legacy_plan_checkpoint_and_text,
            legacy_plan_checkpoint_and_action,
        ],
    )


def resolve_plan_checkpoint_and_text_typed_primary(
    result: BoardCheckpointSemanticResult | None,
    *,
    legacy_plan_checkpoint_only: bool,
    legacy_plan_checkpoint_and_text: bool,
    legacy_plan_checkpoint_and_action: bool,
) -> bool:
    """Resolve plan-checkpoint-and-text with typed-primary logic."""
    return _resolve_checkpoint_typed_primary_candidate(
        result,
        expected_kind=BoardCheckpointKind.PLAN_CHECKPOINT_WITH_TEXT,
        legacy_flag=legacy_plan_checkpoint_and_text,
        other_legacy_flags=[
            legacy_plan_checkpoint_only,
            legacy_plan_checkpoint_and_action,
        ],
    )


def resolve_plan_checkpoint_and_text_authority(
    result: BoardCheckpointSemanticResult | None,
    *,
    legacy_plan_checkpoint_and_text: bool,
    switch_value: str,
) -> BoardCheckpointAuthorityDiagnostic:
    """Resolve plan-checkpoint-and-text and return diagnostic metadata for authority selection."""
    normalized_switch = str(switch_value or "legacy").strip().lower()
    if normalized_switch not in {"legacy", "compiler", "shadow"}:
        normalized_switch = "legacy"

    legacy_kind = "PLAN_CHECKPOINT_WITH_TEXT" if legacy_plan_checkpoint_and_text else "NONE"
    typed_kind = "UNKNOWN"
    compiler_eligible = False

    if result is not None:
        has_clean_compiler_pct_facts = (
            result.compiler_has_checkpoint
            and result.compiler_has_subgoal_tags
            and not result.compiler_has_memory_tags
            and not result.compiler_has_action
            and result.compiler_has_visible_text
            and not result.compiler_error_code
        )
        if has_clean_compiler_pct_facts:
            typed_kind = "PLAN_CHECKPOINT_WITH_TEXT"
            compiler_eligible = result.source in {
                BoardCheckpointSource.COMPILER_PREPASS_FACT,
                BoardCheckpointSource.COMBINED_SHADOW,
            }

    agreement = legacy_plan_checkpoint_and_text == compiler_eligible
    branch_active = bool(legacy_plan_checkpoint_and_text or compiler_eligible)

    if normalized_switch != "compiler":
        return BoardCheckpointAuthorityDiagnostic(
            branch="board_checkpoint.plan_checkpoint_with_text",
            switch_value=normalized_switch,
            authority_source="legacy",
            legacy_active=legacy_plan_checkpoint_and_text,
            typed_kind=typed_kind,
            legacy_kind=legacy_kind,
            agreement=agreement,
            fallback_used=False,
            behavior_changed=False,
            branch_active=branch_active,
            compiler_eligible=compiler_eligible,
            effective_value=legacy_plan_checkpoint_and_text,
        )

    if compiler_eligible:
        return BoardCheckpointAuthorityDiagnostic(
            branch="board_checkpoint.plan_checkpoint_with_text",
            switch_value=normalized_switch,
            authority_source="compiler",
            legacy_active=legacy_plan_checkpoint_and_text,
            typed_kind=typed_kind,
            legacy_kind=legacy_kind,
            agreement=agreement,
            fallback_used=False,
            behavior_changed=not legacy_plan_checkpoint_and_text,
            branch_active=True,
            compiler_eligible=True,
            effective_value=True,
        )

    return BoardCheckpointAuthorityDiagnostic(
        branch="board_checkpoint.plan_checkpoint_with_text",
        switch_value=normalized_switch,
        authority_source="legacy_fallback",
        legacy_active=legacy_plan_checkpoint_and_text,
        typed_kind=typed_kind,
        legacy_kind=legacy_kind,
        agreement=agreement,
        fallback_used=True,
        behavior_changed=False,
        branch_active=branch_active,
        compiler_eligible=compiler_eligible,
        effective_value=legacy_plan_checkpoint_and_text,
    )


def resolve_plan_checkpoint_and_action_typed_primary(
    result: BoardCheckpointSemanticResult | None,
    *,
    legacy_plan_checkpoint_only: bool,
    legacy_plan_checkpoint_and_text: bool,
    legacy_plan_checkpoint_and_action: bool,
) -> bool:
    """Resolve plan-checkpoint-and-action with typed-primary logic."""
    return _resolve_checkpoint_typed_primary_candidate(
        result,
        expected_kind=BoardCheckpointKind.PLAN_CHECKPOINT_WITH_ACTION,
        legacy_flag=legacy_plan_checkpoint_and_action,
        other_legacy_flags=[
            legacy_plan_checkpoint_only,
            legacy_plan_checkpoint_and_text,
        ],
    )


def resolve_plan_checkpoint_only_with_compiler_switch(
    result: BoardCheckpointSemanticResult | None,
    *,
    legacy_plan_checkpoint_only: bool,
    switch_enabled: bool,
) -> bool:
    """Resolve plan-checkpoint-only with compiler authority switch."""
    switch_value = "compiler" if switch_enabled else "legacy"
    return resolve_plan_checkpoint_only_authority(result, legacy_plan_checkpoint_only=legacy_plan_checkpoint_only, switch_value=switch_value).effective_value


def resolve_plan_checkpoint_only_authority(
    result: BoardCheckpointSemanticResult | None,
    *,
    legacy_plan_checkpoint_only: bool,
    switch_value: str,
) -> BoardCheckpointAuthorityDiagnostic:
    """Resolve plan-checkpoint-only and return diagnostic metadata for authority selection."""
    normalized_switch = str(switch_value or "legacy").strip().lower()
    if normalized_switch not in {"legacy", "compiler", "shadow"}:
        normalized_switch = "legacy"

    legacy_kind = "PLAN_CHECKPOINT_ONLY" if legacy_plan_checkpoint_only else "NONE"
    typed_kind = "UNKNOWN"
    compiler_eligible = False

    if result is not None:
        has_clean_compiler_pco_facts = (
            result.compiler_has_checkpoint
            and result.compiler_has_subgoal_tags
            and not result.compiler_has_memory_tags
            and not result.compiler_has_action
            and not result.compiler_has_visible_text
            and not result.compiler_error_code
        )
        if has_clean_compiler_pco_facts:
            typed_kind = "PLAN_CHECKPOINT_ONLY"
            compiler_eligible = result.source in {
                BoardCheckpointSource.COMPILER_PREPASS_FACT,
                BoardCheckpointSource.COMBINED_SHADOW,
            }

    agreement = legacy_plan_checkpoint_only == compiler_eligible
    branch_active = bool(legacy_plan_checkpoint_only or compiler_eligible)

    if normalized_switch != "compiler":
        return BoardCheckpointAuthorityDiagnostic(
            branch="board_checkpoint.plan_checkpoint_only",
            switch_value=normalized_switch,
            authority_source="legacy",
            legacy_active=legacy_plan_checkpoint_only,
            typed_kind=typed_kind,
            legacy_kind=legacy_kind,
            agreement=agreement,
            fallback_used=False,
            behavior_changed=False,
            branch_active=branch_active,
            compiler_eligible=compiler_eligible,
            effective_value=legacy_plan_checkpoint_only,
        )

    if legacy_plan_checkpoint_only:
        return BoardCheckpointAuthorityDiagnostic(
            branch="board_checkpoint.plan_checkpoint_only",
            switch_value=normalized_switch,
            authority_source="legacy",
            legacy_active=True,
            typed_kind=typed_kind,
            legacy_kind=legacy_kind,
            agreement=agreement,
            fallback_used=False,
            behavior_changed=False,
            branch_active=branch_active,
            compiler_eligible=compiler_eligible,
            effective_value=True,
        )

    if compiler_eligible:
        return BoardCheckpointAuthorityDiagnostic(
            branch="board_checkpoint.plan_checkpoint_only",
            switch_value=normalized_switch,
            authority_source="compiler",
            legacy_active=False,
            typed_kind=typed_kind,
            legacy_kind=legacy_kind,
            agreement=agreement,
            fallback_used=False,
            behavior_changed=True,
            branch_active=True,
            compiler_eligible=True,
            effective_value=True,
        )

    return BoardCheckpointAuthorityDiagnostic(
        branch="board_checkpoint.plan_checkpoint_only",
        switch_value=normalized_switch,
        authority_source="legacy_fallback",
        legacy_active=legacy_plan_checkpoint_only,
        typed_kind=typed_kind,
        legacy_kind=legacy_kind,
        agreement=agreement,
        fallback_used=True,
        behavior_changed=False,
        branch_active=branch_active,
        compiler_eligible=compiler_eligible,
        effective_value=legacy_plan_checkpoint_only,
    )


def resolve_legacy_derived_checkpoint_effective_flags(
    result: BoardCheckpointSemanticResult | None,
    *,
    plan_checkpoint_only: bool,
    plan_checkpoint_and_text: bool,
    plan_checkpoint_and_action: bool,
    memory_checkpoint_only: bool,
    memory_checkpoint_and_text: bool,
    memory_checkpoint_and_action: bool,
) -> EffectiveCheckpointFlags:
    typed_plan_checkpoint_only = is_legacy_derived_plan_checkpoint_only(
        result,
        legacy_plan_checkpoint_only=plan_checkpoint_only,
    )
    typed_plan_checkpoint_and_text = is_legacy_derived_plan_checkpoint_and_text(
        result,
        legacy_plan_checkpoint_and_text=plan_checkpoint_and_text,
    )
    typed_plan_checkpoint_and_action = is_legacy_derived_plan_checkpoint_and_action(
        result,
        legacy_plan_checkpoint_and_action=plan_checkpoint_and_action,
    )
    typed_memory_checkpoint_only = is_legacy_derived_memory_checkpoint_only(
        result,
        legacy_memory_checkpoint_only=memory_checkpoint_only,
    )
    typed_memory_checkpoint_and_text = is_legacy_derived_memory_checkpoint_and_text(
        result,
        legacy_memory_checkpoint_and_text=memory_checkpoint_and_text,
    )
    typed_memory_checkpoint_and_action = is_legacy_derived_memory_checkpoint_and_action(
        result,
        legacy_memory_checkpoint_and_action=memory_checkpoint_and_action,
    )
    return EffectiveCheckpointFlags(
        plan_checkpoint_only=bool(typed_plan_checkpoint_only or plan_checkpoint_only),
        plan_checkpoint_and_text=bool(typed_plan_checkpoint_and_text or plan_checkpoint_and_text),
        plan_checkpoint_and_action=bool(typed_plan_checkpoint_and_action or plan_checkpoint_and_action),
        memory_checkpoint_only=bool(typed_memory_checkpoint_only or memory_checkpoint_only),
        memory_checkpoint_and_text=bool(typed_memory_checkpoint_and_text or memory_checkpoint_and_text),
        memory_checkpoint_and_action=bool(typed_memory_checkpoint_and_action or memory_checkpoint_and_action),
    )


def build_board_checkpoint_semantic_result(
    compiler_analysis,
    *,
    raw_response: str,
    response_text: str,
    plan_checkpoint_only: bool,
    plan_checkpoint_and_text: bool,
    plan_checkpoint_and_action: bool,
    memory_checkpoint_only: bool,
    memory_checkpoint_and_text: bool,
    memory_checkpoint_and_action: bool,
) -> BoardCheckpointSemanticResult:
    ir = getattr(compiler_analysis, "ir", None) if compiler_analysis is not None else None
    compiler_shape = str(getattr(getattr(compiler_analysis, "shape", None), "name", "") or "")
    compiler_error_code = str(getattr(getattr(compiler_analysis, "error", None), "code", "") or "")
    compiler_recovery_id = str(getattr(getattr(compiler_analysis, "error", None), "recovery_id", "") or "")
    compiler_has_checkpoint = bool(getattr(ir, "has_checkpoint", False))
    compiler_has_memory_tags = bool(getattr(ir, "has_memory_tags", False))
    compiler_has_subgoal_tags = bool(getattr(ir, "has_subgoal_tags", False))
    compiler_has_memory_checkpoint = bool(getattr(ir, "has_memory_checkpoint", False))
    compiler_visible_text_source = str(getattr(ir, "visible_text_source", "") or "")
    compiler_has_visible_answer = bool(getattr(ir, "has_visible_answer", False))
    compiler_has_pre_action_text = bool(getattr(ir, "has_pre_action_text", False))
    compiler_has_action = bool(getattr(ir, "has_action", False))

    plan_outcome = checkpoint_outcome_category(
        checkpoint_only=plan_checkpoint_only,
        checkpoint_and_text=plan_checkpoint_and_text,
        checkpoint_and_action=plan_checkpoint_and_action,
    )
    memory_outcome = checkpoint_outcome_category(
        checkpoint_only=memory_checkpoint_only,
        checkpoint_and_text=memory_checkpoint_and_text,
        checkpoint_and_action=memory_checkpoint_and_action,
    )

    non_none_outcomes = [value for value in (plan_outcome, memory_outcome) if value != "none"]
    if len(non_none_outcomes) > 1:
        kind = BoardCheckpointKind.MIXED_BOARD_CHECKPOINT
        reason_code = "mixed_plan_and_memory_checkpoint_outcomes"
    elif memory_outcome == "checkpoint_only":
        kind = BoardCheckpointKind.MEMORY_CHECKPOINT_ONLY
        reason_code = "legacy_memory_checkpoint_only"
    elif memory_outcome == "checkpoint_and_text":
        kind = BoardCheckpointKind.MEMORY_CHECKPOINT_WITH_TEXT
        reason_code = "legacy_memory_checkpoint_and_text"
    elif memory_outcome == "checkpoint_and_action":
        kind = BoardCheckpointKind.MEMORY_CHECKPOINT_WITH_ACTION
        reason_code = "legacy_memory_checkpoint_and_action"
    elif plan_outcome == "checkpoint_only":
        kind = BoardCheckpointKind.PLAN_CHECKPOINT_ONLY
        reason_code = "legacy_plan_checkpoint_only"
    elif plan_outcome == "checkpoint_and_text":
        kind = BoardCheckpointKind.PLAN_CHECKPOINT_WITH_TEXT
        reason_code = "legacy_plan_checkpoint_and_text"
    elif plan_outcome == "checkpoint_and_action":
        kind = BoardCheckpointKind.PLAN_CHECKPOINT_WITH_ACTION
        reason_code = "legacy_plan_checkpoint_and_action"
    elif compiler_analysis is None:
        kind = BoardCheckpointKind.UNKNOWN
        reason_code = "compiler_analysis_unavailable"
    else:
        kind = BoardCheckpointKind.NONE
        reason_code = "no_checkpoint_outcome"

    if compiler_analysis is None and non_none_outcomes:
        source = BoardCheckpointSource.LEGACY_HANDLER_OUTCOME
    elif compiler_analysis is None:
        source = BoardCheckpointSource.FALLBACK
    elif non_none_outcomes:
        source = BoardCheckpointSource.COMBINED_SHADOW
    else:
        source = BoardCheckpointSource.COMPILER_PREPASS_FACT

    clean_text_present = bool(str(response_text or "").strip())
    raw_text_present = bool(str(raw_response or "").strip())
    legacy_has_visible_text = bool(plan_checkpoint_and_text or memory_checkpoint_and_text)
    compiler_has_visible_text = bool(compiler_has_visible_answer or compiler_has_pre_action_text)
    has_visible_text = bool(legacy_has_visible_text or compiler_has_visible_text)
    legacy_has_action = bool(plan_checkpoint_and_action or memory_checkpoint_and_action)
    has_action = bool(legacy_has_action or compiler_has_action)
    parity_available = compiler_analysis is not None and ir is not None
    legacy_has_checkpoint = bool(non_none_outcomes)
    compiler_has_checkpoint_like = bool(
        compiler_has_checkpoint
        or compiler_has_memory_tags
        or compiler_has_subgoal_tags
        or compiler_has_memory_checkpoint
    )
    parity_mismatch_reason = ""
    if not parity_available:
        parity_mismatch_reason = "compiler_analysis_unavailable"
    elif compiler_error_code:
        parity_mismatch_reason = "compiler_invalid_prepass"
    elif legacy_has_checkpoint != compiler_has_checkpoint_like:
        parity_mismatch_reason = "checkpoint_presence_mismatch"
    elif legacy_has_checkpoint:  # Both sides see a checkpoint, check deeper
        if legacy_has_action != compiler_has_action:
            parity_mismatch_reason = "checkpoint_action_mismatch"
        elif legacy_has_visible_text != compiler_has_visible_text:
            parity_mismatch_reason = "checkpoint_text_mismatch"

    parity_aligned = bool(parity_available and not parity_mismatch_reason)

    evidence: list[str] = []
    if plan_outcome != "none":
        evidence.append(f"legacy_plan_outcome:{plan_outcome}")
    if memory_outcome != "none":
        evidence.append(f"legacy_memory_outcome:{memory_outcome}")
    if compiler_has_checkpoint:
        evidence.append("compiler_has_checkpoint")
    if compiler_has_memory_tags:
        evidence.append("compiler_has_memory_tags")
    if compiler_has_subgoal_tags:
        evidence.append("compiler_has_subgoal_tags")
    if compiler_has_memory_checkpoint:
        evidence.append("compiler_has_memory_checkpoint")
    if compiler_visible_text_source:
        evidence.append(f"compiler_visible_text_source:{compiler_visible_text_source}")

    return BoardCheckpointSemanticResult(
        kind=kind,
        source=source,
        reason_code=reason_code,
        evidence=tuple(evidence),
        has_visible_text=has_visible_text,
        has_action=has_action,
        clean_text_present=clean_text_present,
        raw_text_present=raw_text_present,
        legacy_plan_outcome=plan_outcome,
        legacy_memory_outcome=memory_outcome,
        compiler_shape=compiler_shape,
        compiler_error_code=compiler_error_code,
        compiler_recovery_id=compiler_recovery_id,
        compiler_has_checkpoint=compiler_has_checkpoint,
        compiler_has_memory_tags=compiler_has_memory_tags,
        compiler_has_subgoal_tags=compiler_has_subgoal_tags,
        compiler_has_memory_checkpoint=compiler_has_memory_checkpoint,
        compiler_visible_text_source=compiler_visible_text_source,
        legacy_has_checkpoint=legacy_has_checkpoint,
        compiler_has_checkpoint_like=compiler_has_checkpoint_like,
        legacy_has_visible_text=legacy_has_visible_text,
        compiler_has_visible_text=compiler_has_visible_text,
        legacy_has_action=legacy_has_action,
        compiler_has_action=compiler_has_action,
        parity_available=parity_available,
        parity_aligned=parity_aligned,
        parity_mismatch_reason=parity_mismatch_reason,
        details={
            "raw_text_present": str(raw_text_present).lower(),
            "clean_text_present": str(clean_text_present).lower(),
        },
    )
