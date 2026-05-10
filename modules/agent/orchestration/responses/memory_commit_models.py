"""Typed models for memory board commit authority."""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(frozen=True)
class MemoryCommitCandidate:
    """Represents a typed candidate for a memory commit decision."""

    branch: str = ""
    candidate_available: bool = False
    checkpoint_kind: str = ""
    has_memory_checkpoint: bool = False
    has_plan_checkpoint: bool = False
    has_action: bool = False
    has_visible_text: bool = False
    compiler_error_code: str = ""
    expected_handled: bool = False
    expected_reason: str = ""
    expected_source: str = ""
    expected_response_text: str = ""
    expected_next_query: str | None = None
    expected_commit_attempted: bool = False
    expected_commit_accepted_count: int = 0
    expected_commit_rejected_count: int = 0
    expected_last_memory_update_done: bool = False
    blocking_reasons: tuple[str, ...] = ()


@dataclass(frozen=True)
class MemoryCommitAuthorityDiagnostic:
    """Diagnostic information about memory commit authority resolution."""

    branch: str = ""
    switch_value: str = "legacy"
    authority_source: str = "legacy"
    effective_source: str = "legacy"
    selected_by_switch: bool = False
    candidate_available: bool = False
    candidate_branch: str = ""
    legacy_branch: str = ""
    typed_kind: str = "UNKNOWN"
    compiler_shape: str = ""
    compiler_error_code: str = ""
    has_memory_checkpoint: bool = False
    has_plan_checkpoint: bool = False
    has_action: bool = False
    has_visible_text: bool = False
    commit_attempted_agreement: bool = False
    accepted_count_agreement: bool = False
    rejected_count_agreement: bool = False
    handled_agreement: bool = False
    reason_agreement: bool = False
    source_agreement: bool = False
    next_query_agreement: bool = False
    state_flags_agreement: bool = False
    commit_equivalent: bool = False
    fallback_used: bool = False
    behavior_changed: bool = False
    blocking_reasons: tuple[str, ...] = ()


@dataclass(frozen=True)
class EffectiveMemoryCommit:
    """Represents the effective memory commit decision, which remains legacy for now."""

    handled: bool
    reason: str
    source: str
    response_text: str
    next_query: str | None
    commit_attempted: bool
    accepted_count: int
    rejected_count: int
    last_memory_update_done: bool


@dataclass(frozen=True)
class MemoryCommitAuthorityDecision:
    """Wraps the effective memory commit decision and its authority diagnostic."""

    effective_commit: EffectiveMemoryCommit
    diagnostic: MemoryCommitAuthorityDiagnostic
