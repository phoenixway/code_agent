"""Simplified policy engine.

Phase 2 goal:
- keep hard safety rails
- remove most scenario-specific policy jungle
- rely on intent contracts + defect detector for investigative control
"""

from __future__ import annotations

from dataclasses import dataclass, field


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
    phase_allows_action: bool = True
    phase_allowed_next_actions: list[str] = field(default_factory=list)
    observe_budget_exhausted: bool = False
    broad_recon_budget_exhausted: bool = False
    task_kind: str = "MODIFICATION"
    already_read_current_version: bool = False
    reread_reason_ok: bool = False
    reread_after_summary: bool = False
    active_intent_type: str | None = None
    active_intent_step_count: int = 0
    active_intent_safe_steps_limit: int = 0


@dataclass
class LoopPolicyInput:
    stagnation_count: int
    read_only_limit: int
    diagnostic_attempts: int
    max_diagnostics: int
    diagnostic_prompt: str
    required_next_action_types: list[str]
    task_kind: str = "MODIFICATION"
    phase: str = "OBSERVE"
    observe_budget_exhausted: bool = False


class PolicyEngine:
    READ_ONLY_ACTIONS = {
        "read_file", "read_file_skeleton", "search_content", "search_files",
        "list_directory", "find_files", "git_diff", "run_shell",
    }

    STATE_CHANGING_ACTIONS = {
        "create_file", "write_file", "edit_file", "replace", "delete_file",
    }

    def _active_investigation_can_continue(self, ctx: PreActionPolicyInput) -> bool:
        return (
            ctx.active_intent_type == "INVESTIGATE"
            and ctx.cmd_type in self.READ_ONLY_ACTIONS
            and ctx.active_intent_step_count < max(0, ctx.active_intent_safe_steps_limit)
        )

    def _active_modify_can_override_stale_observe(self, ctx: PreActionPolicyInput) -> bool:
        return (
            ctx.active_intent_type == "MODIFY"
            and ctx.task_kind == "MODIFICATION"
            and ctx.phase == "OBSERVE"
            and not ctx.phase_allows_action
            and ctx.cmd_type in self.STATE_CHANGING_ACTIONS
        )

    def evaluate_pre_action(self, ctx: PreActionPolicyInput) -> EnginePreActionDecision:
        # Highest-priority escape hatch:
        # if a formal INVESTIGATE intent is active and still within its own safe_steps_limit,
        # do not let old phase gating or broad-read budgets kill the investigation early.
        if self._active_investigation_can_continue(ctx):
            return EnginePreActionDecision(allow=True)

        # Important modify escape hatch:
        # if runtime already switched to a formal MODIFY intent, stale OBSERVE phase gating
        # from the previous investigation must not block state-changing work like write_file.
        if self._active_modify_can_override_stale_observe(ctx):
            return EnginePreActionDecision(allow=True)

        if not ctx.phase_allows_action:
            return EnginePreActionDecision(
                allow=False,
                stop_reason="action_not_allowed_in_phase",
                recovery_prompt=(
                    f"SYSTEM: Action `{ctx.cmd_type}` is not allowed in phase {ctx.phase}. "
                    f"Allowed next actions: {', '.join(ctx.phase_allowed_next_actions) or 'none'}."
                ),
                required_next_action_types=ctx.phase_allowed_next_actions,
            )

        if (
            ctx.cmd_type == "read_file"
            and bool(ctx.path)
            and ctx.already_read_current_version
            and not ctx.reread_reason_ok
            and ctx.reread_after_summary
        ):
            return EnginePreActionDecision(
                allow=False,
                stop_reason="reread_after_summary",
                recovery_prompt=(
                    "SYSTEM: This file is already available in history at the current version, and you just summarized context. "
                    "Re-reading it without a specific reason is blocked."
                ),
                required_next_action_types=["search_content", "edit_file", "write_file"],
            )

        if (
            ctx.cmd_type == "read_file"
            and bool(ctx.path)
            and ctx.already_read_current_version
            and not ctx.reread_reason_ok
        ):
            return EnginePreActionDecision(
                allow=False,
                stop_reason="reread_already_in_history",
                recovery_prompt=(
                    "SYSTEM: This file is already available in history at the current version. "
                    "Re-reading it without a specific reason is blocked."
                ),
                required_next_action_types=["search_content", "edit_file", "write_file"],
            )

        if (
            bool(ctx.target_file)
            and ctx.task_kind == "MODIFICATION"
            and ctx.cmd_type in {"read_file", "read_file_skeleton"}
            and bool(ctx.path)
            and ctx.path != ctx.target_file
            and not ctx.has_cross_target_reason
        ):
            return EnginePreActionDecision(
                allow=False,
                stop_reason="cross_target_read_without_reason",
                recovery_prompt=(
                    "SYSTEM: Target file is pinned. Reading another file now requires an explicit reason."
                ),
                required_next_action_types=["search_content", "edit_file", "write_file"],
            )

        if ctx.task_kind == "INSPECTION" and ctx.observe_budget_exhausted and ctx.broad_recon_budget_exhausted:
            return EnginePreActionDecision(
                allow=False,
                stop_reason="broad_recon_budget_exhausted",
                recovery_prompt=(
                    "SYSTEM: Broad reconnaissance budget is exhausted for investigation. "
                    "Summarize with the evidence already gathered or activate a fresh formal intent."
                ),
                required_next_action_types=["search_content", "read_file"],
            )

        # Observe budget is no longer a hard stop for HYBRID/MODIFICATION work.
        # Intent limits + defect detector handle broad/no-progress exploration better.
        return EnginePreActionDecision(allow=True)

    def evaluate_loop(self, ctx: LoopPolicyInput) -> EngineLoopDecision:
        if ctx.stagnation_count >= ctx.read_only_limit and ctx.diagnostic_attempts < ctx.max_diagnostics:
            return EngineLoopDecision(
                decision="MODEL_DIAGNOSTIC",
                prompt=ctx.diagnostic_prompt,
                reason="stagnation_detected",
                required_next_action_types=ctx.required_next_action_types,
            )
        if ctx.stagnation_count >= ctx.read_only_limit and ctx.diagnostic_attempts >= ctx.max_diagnostics:
            return EngineLoopDecision(
                decision="USER_HANDOFF",
                reason="stagnation_persisted_after_diagnostic",
                required_next_action_types=ctx.required_next_action_types,
            )
        return EngineLoopDecision(decision="CONTINUE")