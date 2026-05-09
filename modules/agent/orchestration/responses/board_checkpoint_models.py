"""Typed observational models for board/checkpoint semantics."""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum


class BoardCheckpointKind(str, Enum):
    NONE = "NONE"
    MEMORY_CHECKPOINT_ONLY = "MEMORY_CHECKPOINT_ONLY"
    MEMORY_CHECKPOINT_WITH_TEXT = "MEMORY_CHECKPOINT_WITH_TEXT"
    MEMORY_CHECKPOINT_WITH_ACTION = "MEMORY_CHECKPOINT_WITH_ACTION"
    PLAN_CHECKPOINT_ONLY = "PLAN_CHECKPOINT_ONLY"
    PLAN_CHECKPOINT_WITH_TEXT = "PLAN_CHECKPOINT_WITH_TEXT"
    PLAN_CHECKPOINT_WITH_ACTION = "PLAN_CHECKPOINT_WITH_ACTION"
    MIXED_BOARD_CHECKPOINT = "MIXED_BOARD_CHECKPOINT"
    UNKNOWN = "UNKNOWN"


class BoardCheckpointSource(str, Enum):
    LEGACY_HANDLER_OUTCOME = "legacy_handler_outcome"
    COMPILER_PREPASS_FACT = "compiler_prepass_fact"
    COMBINED_SHADOW = "combined_shadow"
    FALLBACK = "fallback"


@dataclass(frozen=True)
class BoardCheckpointSemanticResult:
    kind: BoardCheckpointKind = BoardCheckpointKind.UNKNOWN
    source: BoardCheckpointSource = BoardCheckpointSource.FALLBACK
    reason_code: str = ""
    evidence: tuple[str, ...] = ()
    has_visible_text: bool = False
    has_action: bool = False
    clean_text_present: bool = False
    raw_text_present: bool = False
    legacy_plan_outcome: str = ""
    legacy_memory_outcome: str = ""
    compiler_shape: str = ""
    compiler_error_code: str = ""
    compiler_recovery_id: str = ""
    compiler_has_checkpoint: bool = False
    compiler_has_memory_tags: bool = False
    compiler_has_subgoal_tags: bool = False
    compiler_has_memory_checkpoint: bool = False
    compiler_action_count: int = 0
    compiler_visible_text_source: str = ""
    legacy_has_checkpoint: bool = False
    compiler_has_checkpoint_like: bool = False
    legacy_has_visible_text: bool = False
    compiler_has_visible_text: bool = False
    legacy_has_action: bool = False
    compiler_has_action: bool = False
    parity_available: bool = False
    parity_aligned: bool = False
    parity_mismatch_reason: str = ""
    details: dict[str, str] = field(default_factory=dict)


@dataclass(frozen=True)
class EffectiveCheckpointFlags:
    plan_checkpoint_only: bool = False
    plan_checkpoint_and_text: bool = False
    plan_checkpoint_and_action: bool = False
    memory_checkpoint_only: bool = False
    memory_checkpoint_and_text: bool = False
    memory_checkpoint_and_action: bool = False


@dataclass(frozen=True)
class BoardCheckpointAuthorityDiagnostic:
    branch: str = ""
    switch_value: str = "legacy"
    authority_source: str = "legacy"
    legacy_active: bool = False
    typed_kind: str = "UNKNOWN"
    legacy_kind: str = "NONE"
    agreement: bool = False
    fallback_used: bool = False
    behavior_changed: bool = False
    branch_active: bool = False
    compiler_eligible: bool = False
    effective_value: bool = False
