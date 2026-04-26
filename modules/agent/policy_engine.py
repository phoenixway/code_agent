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
    required_next_action_source: str = ""


@dataclass
class EngineLoopDecision:
    decision: str
    prompt: str = ""
    reason: str = ""
    required_next_action_types: list[str] = field(default_factory=list)


@dataclass
class PreActionPolicyInput:
    cmd_type: str
    path: str | None
    fingerprint: str
    target_file: str | None
    forbidden_recover_fingerprint: str | None
    has_cross_target_reason: bool
    observe_budget_exhausted: bool = False
    broad_recon_budget_exhausted: bool = False
    task_kind: str = "MODIFICATION"
    already_read_current_version: bool = False
    reread_reason_ok: bool = False
    reread_after_summary: bool = False
    history_version: int | None = None
    fresh_read_after_edit_mismatch_allowed: bool = False
    reread_repeat_count: int = 0
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
    observe_budget_exhausted: bool = False


class PolicyEngine:
    READ_ONLY_ACTIONS = {
        "read_file", "read_chunk", "read_file_skeleton", "extract_kotlin_function", "extract_symbol", "search_content", "search_files",
        "list_directory", "find_files", "git_diff", "run_shell",
    }

    STATE_CHANGING_ACTIONS = {
        "create_file", "write_file", "write_file_block", "append_file_block", "edit_file", "replace", "delete_file",
    }

    def _active_investigation_can_continue(self, ctx: PreActionPolicyInput) -> bool:
        return (
            ctx.active_intent_type == "INVESTIGATE"
            and ctx.cmd_type in self.READ_ONLY_ACTIONS
            and ctx.active_intent_step_count < max(0, ctx.active_intent_safe_steps_limit)
        )

    def evaluate_pre_action(self, ctx: PreActionPolicyInput) -> EnginePreActionDecision:
        # Highest-priority escape hatch:
        # if a formal INVESTIGATE intent is active and still within its own safe_steps_limit,
        # do not let old phase gating or broad-read budgets kill the investigation early.
        if self._active_investigation_can_continue(ctx):
            return EnginePreActionDecision(allow=True)

        if (
            ctx.cmd_type == "read_file"
            and bool(ctx.path)
            and bool(ctx.fresh_read_after_edit_mismatch_allowed)
        ):
            return EnginePreActionDecision(allow=True)

        version_hint = f" version v{int(ctx.history_version)}" if ctx.history_version else " current history version"

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
                    f"SYSTEM: File content is already available as history{version_hint}, and you just summarized context. "
                    "Use that content now. Do not call read_file again."
                ),
                required_next_action_types=["search_content", "edit_file", "write_file"],
                required_next_action_source="recommended",
            )

        if (
            ctx.cmd_type == "read_file"
            and bool(ctx.path)
            and ctx.already_read_current_version
            and not ctx.reread_reason_ok
        ):
            if int(ctx.reread_repeat_count or 0) >= 2:
                return EnginePreActionDecision(
                    allow=False,
                    stop_reason="reread_already_in_history_use_existing_content",
                    recovery_prompt=(
                        f"SYSTEM: File content is already available as history{version_hint}. "
                        "Use that content now. Do not call read_file again."
                    ),
                    required_next_action_types=["search_content", "edit_file", "write_file"],
                    required_next_action_source="recommended",
                )
            return EnginePreActionDecision(
                allow=False,
                stop_reason="reread_already_in_history",
                recovery_prompt=(
                    f"SYSTEM: File content is already available as history{version_hint}. "
                    "Use that content now. Do not call read_file again."
                ),
                required_next_action_types=["search_content", "edit_file", "write_file"],
                required_next_action_source="recommended",
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
                required_next_action_source="recommended",
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
