"""Declarative policy engine for orchestrator state-machine decisions."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Callable


@dataclass
class EnginePreActionDecision:
    allow: bool
    stop_reason: str = ""
    recovery_prompt: str = ""
    required_next_action_types: list[str] = field(default_factory=list)


@dataclass
class EngineLoopDecision:
    decision: str
    prompt: str = ""
    reason: str = ""
    required_next_action_types: list[str] = field(default_factory=list)


@dataclass
class PreActionPolicyInput:
    phase: str
    cmd_type: str
    path: str | None
    fingerprint: str
    target_file: str | None
    forbidden_recover_fingerprint: str | None
    has_cross_target_reason: bool


@dataclass
class LoopPolicyInput:
    stagnation_count: int
    read_only_limit: int
    diagnostic_attempts: int
    max_diagnostics: int
    invariant_violations: int
    invariant_limit: int
    diagnostic_prompt: str
    required_next_action_types: list[str]


@dataclass
class _Rule:
    predicate: Callable
    build: Callable


class PolicyEngine:
    """Evaluates pre-action and loop decisions via rule tables."""

    def evaluate_pre_action(self, ctx: PreActionPolicyInput) -> EnginePreActionDecision:
        rules = [
            _Rule(
                predicate=lambda c: (
                    c.phase == "RECOVER"
                    and bool(c.forbidden_recover_fingerprint)
                    and c.fingerprint == c.forbidden_recover_fingerprint
                ),
                build=lambda _c: EnginePreActionDecision(
                    allow=False,
                    stop_reason="recover_repeated_fingerprint",
                    recovery_prompt=(
                        "SYSTEM: You are repeating the same action fingerprint after recovery. "
                        "Choose a different tool or change arguments."
                    ),
                    required_next_action_types=["search_content", "edit_file", "write_file"],
                ),
            ),
            _Rule(
                predicate=lambda c: (
                    bool(c.target_file)
                    and c.cmd_type in {"read_file", "read_file_skeleton"}
                    and bool(c.path)
                    and c.path != c.target_file
                    and not c.has_cross_target_reason
                ),
                build=lambda _c: EnginePreActionDecision(
                    allow=False,
                    stop_reason="cross_target_read_without_reason",
                    recovery_prompt=(
                        "SYSTEM: Target file is pinned. Reading another file requires explicit reason "
                        "in the action payload. Add reason or continue on pinned target."
                    ),
                    required_next_action_types=["search_content", "edit_file", "write_file"],
                ),
            ),
        ]

        for rule in rules:
            if rule.predicate(ctx):
                return rule.build(ctx)
        return EnginePreActionDecision(allow=True)

    def evaluate_loop(self, ctx: LoopPolicyInput) -> EngineLoopDecision:
        rules = [
            _Rule(
                predicate=lambda c: c.invariant_violations >= c.invariant_limit,
                build=lambda c: EngineLoopDecision(
                    decision="MODEL_DIAGNOSTIC",
                    prompt=c.diagnostic_prompt,
                    reason="invariant_violation_detected",
                    required_next_action_types=c.required_next_action_types,
                ),
            ),
            _Rule(
                predicate=lambda c: (
                    c.stagnation_count >= c.read_only_limit
                    and c.diagnostic_attempts < c.max_diagnostics
                ),
                build=lambda c: EngineLoopDecision(
                    decision="MODEL_DIAGNOSTIC",
                    prompt=c.diagnostic_prompt,
                    reason="stagnation_detected",
                    required_next_action_types=c.required_next_action_types,
                ),
            ),
            _Rule(
                predicate=lambda c: (
                    c.stagnation_count >= c.read_only_limit
                    and c.diagnostic_attempts >= c.max_diagnostics
                ),
                build=lambda c: EngineLoopDecision(
                    decision="USER_HANDOFF",
                    reason="stagnation_persisted_after_diagnostic",
                    required_next_action_types=c.required_next_action_types,
                ),
            ),
        ]

        for rule in rules:
            if rule.predicate(ctx):
                return rule.build(ctx)
        return EngineLoopDecision(decision="CONTINUE")

