"""Resolver for memory board commit authority."""

from __future__ import annotations

from .board_checkpoint_models import BoardCheckpointSemanticResult
from .memory_commit_models import (
    EffectiveMemoryCommit,
    MemoryCommitAuthorityDecision,
    MemoryCommitAuthorityDiagnostic,
    MemoryCommitCandidate,
)


def build_memory_checkpoint_only_commit_candidate(
    semantic_result: BoardCheckpointSemanticResult | None,
) -> MemoryCommitCandidate:
    """Builds a typed commit candidate for MEMORY_CHECKPOINT_ONLY."""
    if not semantic_result:
        return MemoryCommitCandidate(blocking_reasons=("no_semantic_result",))

    is_mco = (
        semantic_result.kind.name == "MEMORY_CHECKPOINT_ONLY"
        and semantic_result.compiler_has_memory_checkpoint
        and not semantic_result.compiler_has_subgoal_tags
        and not semantic_result.compiler_has_action
        and not semantic_result.compiler_has_visible_text
        and not semantic_result.compiler_error_code
    )

    if not is_mco:
        return MemoryCommitCandidate(blocking_reasons=("not_clean_memory_checkpoint_only",))

    return MemoryCommitCandidate(
        branch="MEMORY_CHECKPOINT_ONLY",
        candidate_available=True,
        checkpoint_kind=semantic_result.kind.name,
        has_memory_checkpoint=True,
        has_plan_checkpoint=False,
        has_action=False,
        has_visible_text=False,
        compiler_error_code="",
        expected_handled=True,
        expected_reason="memory_checkpoint_only",
        expected_source="memory_board",
        expected_response_text="",
        expected_next_query=None,  # Cannot be predicted from typed facts
        expected_commit_attempted=True,
        expected_commit_accepted_count=0,  # Cannot be predicted
        expected_commit_rejected_count=0,  # Cannot be predicted
        expected_last_memory_update_done=True,
        blocking_reasons=("commit_counts_not_typed", "next_query_not_typed"),
    )


def resolve_memory_checkpoint_only_commit_authority(
    semantic_result: BoardCheckpointSemanticResult | None,
    legacy_branch: str,
    legacy_handled: bool,
    legacy_reason: str,
    legacy_source: str,
    legacy_response_text: str,
    legacy_next_query: str | None,
    legacy_commit_attempted: bool,
    legacy_accepted_count: int,
    legacy_rejected_count: int,
    legacy_last_memory_update_done: bool,
    switch_value: str,
) -> MemoryCommitAuthorityDecision:
    """Resolves commit authority for the MEMORY_CHECKPOINT_ONLY branch."""
    candidate = build_memory_checkpoint_only_commit_candidate(semantic_result)

    handled_agreement = candidate.expected_handled == legacy_handled if candidate.candidate_available else False
    reason_agreement = candidate.expected_reason == legacy_reason if candidate.candidate_available else False
    source_agreement = candidate.expected_source == legacy_source if candidate.candidate_available else False
    commit_attempted_agreement = (
        candidate.expected_commit_attempted == legacy_commit_attempted if candidate.candidate_available else False
    )
    state_flags_agreement = (
        candidate.expected_last_memory_update_done == legacy_last_memory_update_done
        if candidate.candidate_available
        else False
    )

    # For observed-equivalence, we don't predict counts/query from typed facts.
    # We check if the observed legacy values are consistent with a clean MCO.
    if candidate.candidate_available and semantic_result:
        if not semantic_result.compiler_has_memory_tags:
            # Marker-only MCO, e.g. <memory_update_done />
            accepted_count_agreement = legacy_accepted_count == 0
        else:
            # MCO with memory content, e.g. <fact>...</fact>
            accepted_count_agreement = legacy_accepted_count == 1
    else:
        accepted_count_agreement = False
    rejected_count_agreement = legacy_rejected_count == 0 if candidate.candidate_available else False
    next_query_agreement = bool(legacy_next_query) if candidate.candidate_available else False

    commit_equivalent = all(
        [
            handled_agreement,
            reason_agreement,
            source_agreement,
            commit_attempted_agreement,
            state_flags_agreement,
            accepted_count_agreement,
            rejected_count_agreement,
            next_query_agreement,
        ]
    )

    authority_source = "legacy"
    fallback_used = False
    selected_by_switch = False
    if switch_value == "compiler":
        if candidate.candidate_available and commit_equivalent:
            authority_source = "compiler"
            selected_by_switch = True
        else:
            authority_source = "legacy_fallback"
            fallback_used = True

    effective_commit = EffectiveMemoryCommit(
        handled=legacy_handled,
        reason=legacy_reason,
        source=legacy_source,
        response_text=legacy_response_text,
        next_query=legacy_next_query,
        commit_attempted=legacy_commit_attempted,
        accepted_count=legacy_accepted_count,
        rejected_count=legacy_rejected_count,
        last_memory_update_done=legacy_last_memory_update_done,
    )

    diagnostic = MemoryCommitAuthorityDiagnostic(
        branch="board_memory.memory_checkpoint_only",
        switch_value=switch_value,
        authority_source=authority_source,
        effective_source="legacy",
        selected_by_switch=selected_by_switch,
        candidate_available=candidate.candidate_available,
        candidate_branch=candidate.branch,
        legacy_branch=legacy_branch,
        typed_kind=semantic_result.kind.name if semantic_result else "UNKNOWN",
        compiler_shape=semantic_result.compiler_shape if semantic_result else "",
        compiler_error_code=semantic_result.compiler_error_code if semantic_result else "",
        has_memory_checkpoint=semantic_result.compiler_has_memory_checkpoint if semantic_result else False,
        has_plan_checkpoint=semantic_result.compiler_has_subgoal_tags if semantic_result else False,
        has_action=semantic_result.compiler_has_action if semantic_result else False,
        has_visible_text=semantic_result.compiler_has_visible_text if semantic_result else False,
        commit_attempted_agreement=commit_attempted_agreement,
        accepted_count_agreement=accepted_count_agreement,
        rejected_count_agreement=rejected_count_agreement,
        handled_agreement=handled_agreement,
        reason_agreement=reason_agreement,
        source_agreement=source_agreement,
        next_query_agreement=next_query_agreement,
        state_flags_agreement=state_flags_agreement,
        commit_equivalent=commit_equivalent,
        fallback_used=fallback_used,
        behavior_changed=authority_source == "compiler" and legacy_branch != candidate.branch,
        blocking_reasons=candidate.blocking_reasons,
    )

    return MemoryCommitAuthorityDecision(effective_commit=effective_commit, diagnostic=diagnostic)
