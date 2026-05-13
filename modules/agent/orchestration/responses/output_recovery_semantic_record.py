from __future__ import annotations

from typing import Any

from .semantic_decision_record import (
    CompilerMetadataSnapshot,
    EffectiveDecisionSnapshot,
    RegistryResolutionSnapshot,
    SemanticDecisionRecord,
)


def _metadata_value(compiler_meta: dict[str, Any] | None, key: str) -> str:
    if not compiler_meta:
        return ""
    return str(compiler_meta.get(key) or "")


def _strategy_value(strategy: Any | None, key: str) -> Any:
    if strategy is None:
        return ""
    if isinstance(strategy, dict):
        return strategy.get(key) or ""
    return getattr(strategy, key, "") or ""


def _strategy_allowed_next_shapes(strategy: Any | None) -> tuple[str, ...]:
    value = _strategy_value(strategy, "allowed_next_shapes")
    if not value:
        return ()
    return tuple(str(item) for item in value)


def build_output_recovery_semantic_decision_record(
    *,
    decision: str,
    compiler_meta: dict[str, Any] | None = None,
    registry_strategy: Any | None = None,
    reason: str = "",
    source: str = "",
    outcome_kind: str = "",
    prompt_family: str = "",
    details: dict[str, Any] | None = None,
) -> SemanticDecisionRecord:
    """Build a passive semantic decision record for output-recovery diagnostics.

    This helper only packages already-computed facts. It must not call runtime
    policy, dispatch, recovery routing, parser/compiler, logging, trace export,
    or replay code.
    """
    strategy_resolved = registry_strategy is not None
    effective_reason = reason or _metadata_value(compiler_meta, "invalid_kind")

    return SemanticDecisionRecord(
        domain="output_recovery",
        stage="output_recovery",
        decision=decision,
        reason=effective_reason,
        source=source,
        diagnostic_only=True,
        authority_affecting=False,
        behavior_affecting=False,
        compiler_metadata=CompilerMetadataSnapshot(
            error_code=_metadata_value(compiler_meta, "error_code"),
            recovery_id=_metadata_value(compiler_meta, "recovery_id"),
            invalid_kind=_metadata_value(compiler_meta, "invalid_kind"),
            source=_metadata_value(compiler_meta, "source"),
        ),
        registry_resolution=RegistryResolutionSnapshot(
            resolved=strategy_resolved,
            strategy_id=str(_strategy_value(registry_strategy, "id")),
            handler_key=str(_strategy_value(registry_strategy, "handler_key")),
            allowed_next_shapes=_strategy_allowed_next_shapes(registry_strategy),
        ),
        effective_decision=EffectiveDecisionSnapshot(
            outcome_kind=outcome_kind,
            reason=effective_reason,
            source=source,
            prompt_family=prompt_family,
        ),
        details=dict(details or {}),
    )
