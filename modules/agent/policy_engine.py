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
    multi_file_scope: bool = False
    block_readonly_until_state_change: bool = False
    allow_readonly_probe: bool = False
    already_read_current_version: bool = False
    reread_reason_ok: bool = False
    reread_after_summary: bool = False
    phase_allows_action: bool = True
    phase_allowed_next_actions: list[str] = field(default_factory=list)
    observe_budget_exhausted: bool = False
    root_listing_budget_exhausted: bool = False
    list_directory_budget_exhausted: bool = False
    directory_descent_budget_exhausted: bool = False
    broad_recon_budget_exhausted: bool = False
    task_kind: str = "MODIFICATION"
    project_inspection_mode: bool = False
    inspection_profile: str = "generic"
    inspection_entrypoints_checked: int = 0
    inspection_searches_used: int = 0
    preferred_inspection_entrypoint: bool = False


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
        def _inspection_entrypoint_prompt(profile: str) -> str:
            if profile == "kotlin":
                return (
                    "SYSTEM: Project inspection mode for Kotlin/Gradle is active. "
                    "Do not begin with directory-by-directory traversal. Read settings.gradle(.kts) / build.gradle(.kts) first, "
                    "or use search_files/search_content to locate app/shared/desktop/domain modules."
                )
            if profile == "python":
                return (
                    "SYSTEM: Project inspection mode for Python is active. "
                    "Do not begin with directory-by-directory traversal. Read pyproject.toml / requirements.txt / setup.py first, "
                    "or use search_files/search_content to locate app/api/models/services/tests."
                )
            return (
                "SYSTEM: Project inspection mode is active. Avoid deep directory traversal as a first move. "
                "Read project config/build files first, then use search_files/search_content, and only then use targeted list_directory."
            )
        rules = [
            _Rule(
                predicate=lambda c: (
                    c.project_inspection_mode
                    and c.cmd_type == "list_directory"
                    and c.inspection_entrypoints_checked == 0
                    and c.inspection_searches_used == 0
                ),
                build=lambda c: EnginePreActionDecision(
                    allow=False,
                    stop_reason="inspection_mode_requires_entrypoints_first",
                    recovery_prompt=_inspection_entrypoint_prompt(c.inspection_profile),
                    required_next_action_types=["read_file", "search_files", "search_content"],
                ),
            ),
            _Rule(
                predicate=lambda c: (
                    c.project_inspection_mode
                    and c.cmd_type == "list_directory"
                    and c.inspection_entrypoints_checked > 0
                    and c.inspection_searches_used == 0
                ),
                build=lambda c: EnginePreActionDecision(
                    allow=False,
                    stop_reason="inspection_mode_prefers_search_after_entrypoints",
                    recovery_prompt=(
                        "SYSTEM: Project entrypoints were already inspected. Before more directory traversal, use search_files/search_content to narrow the candidate modules/files. "
                        "Use list_directory only for targeted confirmation of a specific directory."
                    ),
                    required_next_action_types=["search_files", "search_content", "read_file"],
                ),
            ),
            _Rule(
                predicate=lambda c: (
                    c.task_kind == "HYBRID"
                    and c.observe_budget_exhausted
                    and c.cmd_type in {"read_file", "read_file_skeleton", "search_content", "search_files", "list_directory", "find_files", "git_diff"}
                ),
                build=lambda _c: EnginePreActionDecision(
                    allow=False,
                    stop_reason="hybrid_task_contract_requires_edit_plan",
                    recovery_prompt=(
                        "SYSTEM: This is a HYBRID task. Initial reconnaissance is complete enough. "
                        "Do not continue broad inspection now. Move to search_content with a narrow target, edit_file, or write_file."
                    ),
                    required_next_action_types=["search_content", "edit_file", "write_file"],
                ),
            ),
            _Rule(
                predicate=lambda c: (
                    c.task_kind == "MODIFICATION"
                    and c.observe_budget_exhausted
                    and c.cmd_type in {"read_file", "read_file_skeleton", "search_content", "search_files", "list_directory", "find_files", "git_diff"}
                ),
                build=lambda _c: EnginePreActionDecision(
                    allow=False,
                    stop_reason="modification_task_contract_requires_edit_plan",
                    recovery_prompt=(
                        "SYSTEM: This is a MODIFICATION task. Observation budget is exhausted. "
                        "Stop broad inspection and move to edit_file/write_file, or one narrow search_content if strictly necessary."
                    ),
                    required_next_action_types=["search_content", "edit_file", "write_file"],
                ),
            ),
            _Rule(
                predicate=lambda c: (
                    c.task_kind == "INSPECTION"
                    and c.cmd_type in {"edit_file", "write_file", "create_file", "replace"}
                ),
                build=lambda _c: EnginePreActionDecision(
                    allow=False,
                    stop_reason="inspection_task_write_blocked",
                    recovery_prompt=(
                        "SYSTEM: This task was classified as INSPECTION. Prefer analysis and plain-text conclusions. "
                        "Do not start state-changing file edits unless the user explicitly asked to modify code."
                    ),
                    required_next_action_types=["search_content", "search_files", "read_file"],
                ),
            ),
            _Rule(
                predicate=lambda c: c.root_listing_budget_exhausted and c.cmd_type == "list_directory",
                build=lambda _c: EnginePreActionDecision(
                    allow=False,
                    stop_reason="root_listing_budget_exhausted",
                    recovery_prompt=(
                        "SYSTEM: Root-level directory listing budget is exhausted for this turn. "
                        "Do not list the repository root again. Switch to search_files/search_content or move to edit_file/write_file."
                    ),
                    required_next_action_types=["search_files", "search_content", "edit_file", "write_file"],
                ),
            ),
            _Rule(
                predicate=lambda c: c.list_directory_budget_exhausted and c.cmd_type == "list_directory",
                build=lambda _c: EnginePreActionDecision(
                    allow=False,
                    stop_reason="list_directory_budget_exhausted",
                    recovery_prompt=(
                        "SYSTEM: list_directory budget is exhausted for this turn. "
                        "Stop directory-by-directory traversal and switch to search_files/search_content or a deterministic edit step."
                    ),
                    required_next_action_types=["search_files", "search_content", "edit_file", "write_file"],
                ),
            ),
            _Rule(
                predicate=lambda c: c.directory_descent_budget_exhausted and c.cmd_type == "list_directory",
                build=lambda _c: EnginePreActionDecision(
                    allow=False,
                    stop_reason="directory_descent_budget_exhausted",
                    recovery_prompt=(
                        "SYSTEM: Directory descent chain budget is exhausted. "
                        "Stop stepping through nested folders one level at a time. Use search_files/search_content or edit/write now."
                    ),
                    required_next_action_types=["search_files", "search_content", "edit_file", "write_file"],
                ),
            ),
            _Rule(
                predicate=lambda c: c.broad_recon_budget_exhausted and c.cmd_type in {"read_file", "read_file_skeleton", "search_content", "search_files", "list_directory", "find_files", "git_diff"},
                build=lambda _c: EnginePreActionDecision(
                    allow=False,
                    stop_reason="broad_recon_budget_exhausted",
                    recovery_prompt=(
                        "SYSTEM: Broad reconnaissance batch budget is exhausted. "
                        "Do not continue broad project-wide inspection. Narrow with search_content/search_files or move to edit_file/write_file."
                    ),
                    required_next_action_types=["search_files", "search_content", "edit_file", "write_file"],
                ),
            ),
            _Rule(
                predicate=lambda c: not c.phase_allows_action,
                build=lambda c: EnginePreActionDecision(
                    allow=False,
                    stop_reason="action_not_allowed_in_phase",
                    recovery_prompt=(
                        f"SYSTEM: Action `{c.cmd_type}` is not allowed in phase {c.phase}. "
                        f"Allowed next actions: {', '.join(c.phase_allowed_next_actions) or 'none'}."
                    ),
                    required_next_action_types=c.phase_allowed_next_actions,
                ),
            ),
            _Rule(
                predicate=lambda c: c.observe_budget_exhausted and c.cmd_type in {
                    "read_file", "read_file_skeleton", "search_content", "search_files", "list_directory", "find_files", "git_diff"
                },
                build=lambda _c: EnginePreActionDecision(
                    allow=False,
                    stop_reason="observe_budget_exhausted",
                    recovery_prompt=(
                        "SYSTEM: OBSERVE phase budget is exhausted. Transition to EDIT_PLAN now. "
                        "Do one narrow search_content if strictly needed, otherwise use edit_file/write_file or finish with plain text."
                    ),
                    required_next_action_types=["search_content", "edit_file", "write_file"],
                ),
            ),
            _Rule(
                predicate=lambda c: (
                    c.cmd_type == "read_file"
                    and bool(c.path)
                    and c.already_read_current_version
                    and not c.reread_reason_ok
                    and c.reread_after_summary
                ),
                build=lambda _c: EnginePreActionDecision(
                    allow=False,
                    stop_reason="reread_after_summary",
                    recovery_prompt=(
                        "SYSTEM: This file is already available in history at the current version, and you just summarized context. "
                        "Re-reading it without a specific reason is blocked. Use existing context, narrow with search_content, or proceed to edit_file/write_file."
                    ),
                    required_next_action_types=["search_content", "edit_file", "write_file"],
                ),
            ),
            _Rule(
                predicate=lambda c: (
                    c.cmd_type == "read_file"
                    and bool(c.path)
                    and c.already_read_current_version
                    and not c.reread_reason_ok
                ),
                build=lambda _c: EnginePreActionDecision(
                    allow=False,
                    stop_reason="reread_already_in_history",
                    recovery_prompt=(
                        "SYSTEM: This file is already available in history at the current version. "
                        "Re-reading it without a specific reason is blocked. Use existing context, search_content, or proceed to edit_file/write_file."
                    ),
                    required_next_action_types=["search_content", "edit_file", "write_file"],
                ),
            ),
            _Rule(
                predicate=lambda c: (
                    c.multi_file_scope
                    and c.block_readonly_until_state_change
                    and c.cmd_type in {
                        "read_file", "read_file_skeleton", "search_content", "search_files", "list_directory", "find_files", "git_diff",
                    }
                    and not c.allow_readonly_probe
                ),
                build=lambda _c: EnginePreActionDecision(
                    allow=False,
                    stop_reason="multi_file_readonly_budget_exhausted",
                    recovery_prompt=(
                        "SYSTEM: Multi-file read-only budget is exhausted in IMPLEMENT mode. "
                        "Do not repeat already checked read/search/list actions now. "
                        "Reading a NEW target is allowed, but repeated probes are blocked. "
                        "Next step must be edit_file or write_file, or finish with plain text if no edits are needed."
                    ),
                    required_next_action_types=["edit_file", "write_file"],
                ),
            ),
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
                    and not c.multi_file_scope
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
                predicate=lambda c: (
                    c.task_kind == "HYBRID"
                    and c.observe_budget_exhausted
                    and c.cmd_type in {"read_file", "read_file_skeleton", "search_content", "search_files", "list_directory", "find_files", "git_diff"}
                ),
                build=lambda _c: EnginePreActionDecision(
                    allow=False,
                    stop_reason="hybrid_task_contract_requires_edit_plan",
                    recovery_prompt=(
                        "SYSTEM: This is a HYBRID task. Initial reconnaissance is complete enough. "
                        "Do not continue broad inspection now. Move to search_content with a narrow target, edit_file, or write_file."
                    ),
                    required_next_action_types=["search_content", "edit_file", "write_file"],
                ),
            ),
            _Rule(
                predicate=lambda c: (
                    c.task_kind == "MODIFICATION"
                    and c.observe_budget_exhausted
                    and c.cmd_type in {"read_file", "read_file_skeleton", "search_content", "search_files", "list_directory", "find_files", "git_diff"}
                ),
                build=lambda _c: EnginePreActionDecision(
                    allow=False,
                    stop_reason="modification_task_contract_requires_edit_plan",
                    recovery_prompt=(
                        "SYSTEM: This is a MODIFICATION task. Observation budget is exhausted. "
                        "Stop broad inspection and move to edit_file/write_file, or one narrow search_content if strictly necessary."
                    ),
                    required_next_action_types=["search_content", "edit_file", "write_file"],
                ),
            ),
            _Rule(
                predicate=lambda c: (
                    c.task_kind == "INSPECTION"
                    and c.cmd_type in {"edit_file", "write_file", "create_file", "replace"}
                ),
                build=lambda _c: EnginePreActionDecision(
                    allow=False,
                    stop_reason="inspection_task_write_blocked",
                    recovery_prompt=(
                        "SYSTEM: This task was classified as INSPECTION. Prefer analysis and plain-text conclusions. "
                        "Do not start state-changing file edits unless the user explicitly asked to modify code."
                    ),
                    required_next_action_types=["search_content", "search_files", "read_file"],
                ),
            ),
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
