from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


def _clean_optional_dict(value: dict[str, Any]) -> dict[str, Any]:
    """Return a JSON-serializable-ish dict without None values at the top level."""
    return {key: item for key, item in value.items() if item is not None}


@dataclass(frozen=True)
class CompilerMetadataSnapshot:
    error_code: str = ""
    recovery_id: str = ""
    invalid_kind: str = ""
    source: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "error_code": self.error_code,
            "recovery_id": self.recovery_id,
            "invalid_kind": self.invalid_kind,
            "source": self.source,
        }


@dataclass(frozen=True)
class RegistryResolutionSnapshot:
    resolved: bool = False
    strategy_id: str = ""
    handler_key: str = ""
    allowed_next_shapes: tuple[str, ...] = ()

    def to_dict(self) -> dict[str, Any]:
        return {
            "resolved": self.resolved,
            "strategy_id": self.strategy_id,
            "handler_key": self.handler_key,
            "allowed_next_shapes": list(self.allowed_next_shapes),
        }


@dataclass(frozen=True)
class EffectiveDecisionSnapshot:
    outcome_kind: str = ""
    reason: str = ""
    source: str = ""
    prompt_family: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "outcome_kind": self.outcome_kind,
            "reason": self.reason,
            "source": self.source,
            "prompt_family": self.prompt_family,
        }


@dataclass(frozen=True)
class AuthorityResolutionSnapshot:
    branch: str = ""
    switch_value: str = ""
    authority_source: str = ""
    selected_by_switch: bool = False
    fallback_reason: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "branch": self.branch,
            "switch_value": self.switch_value,
            "authority_source": self.authority_source,
            "selected_by_switch": self.selected_by_switch,
            "fallback_reason": self.fallback_reason,
        }


@dataclass(frozen=True)
class SemanticDecisionRecord:
    domain: str
    stage: str
    decision: str
    reason: str = ""
    source: str = ""
    diagnostic_only: bool = True
    authority_affecting: bool = False
    behavior_affecting: bool = False
    compiler_metadata: CompilerMetadataSnapshot | None = None
    registry_resolution: RegistryResolutionSnapshot | None = None
    effective_decision: EffectiveDecisionSnapshot | None = None
    authority_resolution: AuthorityResolutionSnapshot | None = None
    details: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return _clean_optional_dict(
            {
                "domain": self.domain,
                "stage": self.stage,
                "decision": self.decision,
                "reason": self.reason,
                "source": self.source,
                "diagnostic_only": self.diagnostic_only,
                "authority_affecting": self.authority_affecting,
                "behavior_affecting": self.behavior_affecting,
                "compiler_metadata": (
                    self.compiler_metadata.to_dict() if self.compiler_metadata is not None else None
                ),
                "registry_resolution": (
                    self.registry_resolution.to_dict() if self.registry_resolution is not None else None
                ),
                "effective_decision": (
                    self.effective_decision.to_dict() if self.effective_decision is not None else None
                ),
                "authority_resolution": (
                    self.authority_resolution.to_dict() if self.authority_resolution is not None else None
                ),
                "details": dict(self.details),
            }
        )
