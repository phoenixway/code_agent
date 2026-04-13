"""State machine and policy engine for loop-safe orchestration."""

from __future__ import annotations

import json
from collections import deque
from dataclasses import dataclass, field
from enum import Enum

from .policy_engine import (
    EngineLoopDecision,
    EnginePreActionDecision,
    LoopPolicyInput,
    PolicyEngine,
    PreActionPolicyInput,
)


READ_ONLY_ACTIONS = {
    "read_file",
    "read_file_skeleton",
    "search_content",
    "search_files",
    "list_directory",
    "find_files",
    "git_diff",
}


class AgentPhase(str, Enum):
    OBSERVE = "OBSERVE"
    EDIT_PLAN = "EDIT_PLAN"
    APPLY = "APPLY"
    VERIFY = "VERIFY"
    RECOVER = "RECOVER"


class WorkMode(str, Enum):
    IMPLEMENT = "IMPLEMENT"
    RESEARCH = "RESEARCH"


class TaskKind(str, Enum):
    INSPECTION = "INSPECTION"
    MODIFICATION = "MODIFICATION"
    HYBRID = "HYBRID"


class DecisionType(str, Enum):
    CONTINUE = "CONTINUE"
    MODEL_DIAGNOSTIC = "MODEL_DIAGNOSTIC"
    USER_HANDOFF = "USER_HANDOFF"


@dataclass
class LoopDecision:
    decision: DecisionType
    prompt: str = ""
    reason: str = ""
    required_next_action_types: list[str] = field(default_factory=list)


@dataclass
class PreActionDecision:
    allow: bool
    stop_reason: str = ""
    recovery_prompt: str = ""
    required_next_action_types: list[str] = field(default_factory=list)


class AgentStateMachine:
    """Tracks progress, enforces invariants, and drives recovery policy."""

    def __init__(self, config):
        self.config = config
        self.policy_engine = PolicyEngine()
        self.phase = AgentPhase.OBSERVE
        self.mode = WorkMode.IMPLEMENT
        self.target_file: str | None = None
        self.task_kind = TaskKind.MODIFICATION

        self.stagnation_count = 0
        self.diagnostic_attempts = 0
        self.last_progress_signature: str | None = None
        self.last_progress_score = 0
        self.last_action_fingerprint: str | None = None
        self.forbidden_recover_fingerprint: str | None = None
        self.invariant_violations = 0
        self.recent_signatures = deque(maxlen=40)
        self.seen_paths: set[str] = set()
        self.seen_search_signatures: set[str] = set()
        self.seen_search_result_signatures: set[str] = set()
        self.seen_action_fingerprints: set[str] = set()
        self.multi_file_scope = False
        self.current_file_focus: str | None = None
        self.per_file_readonly_streak = 0
        self.multi_file_readonly_total = 0
        self.block_readonly_until_state_change = False
        self.multi_file_target_dir: str | None = None
        self.multi_file_target_file_count = 0
        self.history = None
        
        # Phase-specific allowed actions
        self._phase_allowed_actions = {
            AgentPhase.OBSERVE: {
                "read_file",
                "read_file_skeleton",
                "search_content",
                "search_files",
                "list_directory",
                "find_files",
                "git_diff",
            },
            AgentPhase.EDIT_PLAN: {
                "search_content",  # narrow searches only
                "edit_file",
                "write_file",
            },
            AgentPhase.APPLY: {
                "edit_file",
                "write_file",
                "run_shell",  # only for control actions
            },
            AgentPhase.VERIFY: {
                "read_file",  # narrow reads only
                "search_content",  # narrow searches only
                "git_diff",
                "run_shell",  # read-only shell commands
            },
            AgentPhase.RECOVER: {
                "search_content",  # diagnostic searches
                "edit_file",
                "write_file",
                "run_shell",  # recovery actions
            },
        }
        
        # Budget for OBSERVE phase
        self.observe_budget = max(1, int(getattr(self.config, "OBSERVE_PHASE_BUDGET", 8)))
        self.observe_actions_used = 0
        self.root_listings_used = 0
        self.list_directory_actions_used = 0
        self.directory_descent_chain = 0
        self.last_directory_path = None
        self.broad_recon_batches_used = 0
        self.inspection_entrypoints_checked.clear()
        self.inspection_searches_used = 0
        self.root_listings_used = 0
        self.list_directory_actions_used = 0
        self.directory_descent_chain = 0
        self.last_directory_path = None
        self.broad_recon_batches_used = 0
        self.root_listings_used = 0
        self.list_directory_actions_used = 0
        self.directory_descent_chain = 0
        self.last_directory_path = None
        self.broad_recon_batches_used = 0
        self.root_listings_used = 0
        self.list_directory_actions_used = 0
        self.directory_descent_chain = 0
        self.last_directory_path: str | None = None
        self.broad_recon_batches_used = 0
        self.project_inspection_mode = False
        self.inspection_profile = "generic"
        self.inspection_entrypoints_checked: set[str] = set()
        self.inspection_searches_used = 0

    def _classify_task_kind(self, user_input: str) -> TaskKind:
        text = (user_input or "").lower()
        inspection_keywords = (
            "analy", "inspect", "investig", "explore", "research", "review", "understand",
            "огляд", "аналіз", "дослід", "перевір", "оцін", "подивись", "розбери", "зрозумій",
        )
        modification_keywords = (
            "fix", "implement", "add", "change", "modify", "edit", "update", "refactor", "write",
            "виправ", "реаліз", "додай", "зміни", "відредаг", "онови", "перероби", "допиши",
        )
        has_inspection = any(k in text for k in inspection_keywords)
        has_modification = any(k in text for k in modification_keywords)
        if has_inspection and has_modification:
            return TaskKind.HYBRID
        if has_inspection:
            return TaskKind.INSPECTION
        return TaskKind.MODIFICATION

    def _detect_project_inspection_mode(self, user_input: str) -> bool:
        text = (user_input or "").lower()
        inspection_terms = (
            "architecture", "repo", "repository", "project", "structure", "module", "desktop", "shared",
            "кotlin", "gradle", "python", "архітектур", "репозитор", "структур", "модул", "десктоп", "shared",
        )
        language_terms = ("kotlin", "gradle", "android", "compose", "kmp", "python", "fastapi", "flask", "django", "pyproject", "requirements")
        return any(t in text for t in inspection_terms) and any(t in text for t in language_terms)

    def _detect_inspection_profile(self, user_input: str) -> str:
        text = (user_input or "").lower()
        kotlin_terms = ("kotlin", "gradle", "android", "compose", "kmp", "desktop", "shared")
        python_terms = ("python", "fastapi", "flask", "django", "pyproject", "requirements", "setup.py")
        if any(t in text for t in kotlin_terms):
            return "kotlin"
        if any(t in text for t in python_terms):
            return "python"
        return "generic"

    def _inspection_entrypoints(self) -> tuple[str, ...]:
        if self.inspection_profile == "kotlin":
            return ("settings.gradle.kts", "settings.gradle", "build.gradle.kts", "build.gradle")
        if self.inspection_profile == "python":
            return ("pyproject.toml", "requirements.txt", "setup.py", "Pipfile", "poetry.lock")
        return tuple()

    def _is_preferred_inspection_entrypoint(self, path: str | None) -> bool:
        if not isinstance(path, str) or not path.strip():
            return False
        normalized = path.replace("\\", "/")
        filename = normalized.split("/")[-1]
        return filename in self._inspection_entrypoints()

    def _inspection_route_hint(self) -> str:
        if not self.project_inspection_mode:
            return ""
        if self.inspection_profile == "kotlin":
            return (
                "Preferred Kotlin inspection route: settings.gradle(.kts) -> build.gradle(.kts) -> search_files(shared|desktop|app|domain|data|navigation|repository|usecase) -> "
                "search_content(@Composable|RoomDatabase|Repository|UseCase|NavHost|Desktop|expect|actual) -> targeted list_directory."
            )
        if self.inspection_profile == "python":
            return (
                "Preferred Python inspection route: pyproject.toml/requirements.txt/setup.py -> search_files(app|core|api|models|services|tests|cli|main) -> "
                "search_content(FastAPI|Flask|Django|Typer|click|BaseModel|SQLAlchemy|pytest) -> targeted list_directory."
            )
        return "Preferred inspection route: config/build files first, then search_files/search_content, and only then targeted list_directory."

    def start_turn(self, user_input: str):
        text = (user_input or "").lower()
        self.task_kind = self._classify_task_kind(user_input)
        self.project_inspection_mode = self._detect_project_inspection_mode(user_input)
        self.inspection_profile = self._detect_inspection_profile(user_input)
        if self.task_kind == TaskKind.INSPECTION:
            self.mode = WorkMode.RESEARCH
        elif self.task_kind == TaskKind.HYBRID and bool(getattr(self.config, "TASK_CONTRACT_FORCE_IMPLEMENT_FOR_HYBRID", True)):
            self.mode = WorkMode.IMPLEMENT
        else:
            self.mode = WorkMode.IMPLEMENT
        multi_file_keywords = (
            "folder",
            "directory",
            "files",
            "multiple files",
            "multi-file",
            "папк",
            "директор",
            "файлів",
            "кілька файлів",
            "кожен файл",
            "кожен аспект",
            "one aspect",
        )
        self.multi_file_scope = any(k in text for k in multi_file_keywords)
        self.target_file = None
        self.phase = AgentPhase.OBSERVE
        self.stagnation_count = 0
        self.diagnostic_attempts = 0
        self.invariant_violations = 0
        self.last_progress_signature = None
        self.last_progress_score = 0
        self.last_action_fingerprint = None
        self.forbidden_recover_fingerprint = None
        self.recent_signatures.clear()
        self.seen_paths.clear()
        self.seen_search_signatures.clear()
        self.seen_search_result_signatures.clear()
        self.seen_action_fingerprints.clear()
        self.current_file_focus = None
        self.per_file_readonly_streak = 0
        self.multi_file_readonly_total = 0
        self.block_readonly_until_state_change = False
        self.multi_file_target_dir = None
        self.multi_file_target_file_count = 0
        self.observe_actions_used = 0

    @staticmethod
    def _fingerprint(command: dict) -> str:
        cmd_type = command.get("type") or command.get("action") or "unknown"
        ignored = {"before_execution", "during_execution", "after_execution", "return_control", "id"}
        args = {k: v for k, v in command.items() if k not in ignored}
        return f"{cmd_type}:{json.dumps(args, sort_keys=True, ensure_ascii=False)}"

    def _read_only_limit(self) -> int:
        if self.mode == WorkMode.RESEARCH:
            return max(1, int(getattr(self.config, "RESEARCH_STAGNATION_LIMIT", 6)))
        return max(1, int(getattr(self.config, "IMPLEMENT_STAGNATION_LIMIT", 3)))

    def _has_cross_target_reason(self, command: dict) -> bool:
        reason_fields = (
            command.get("reason"),
            command.get("because"),
            command.get("before_execution"),
        )
        reason_blob = " ".join(str(x) for x in reason_fields if x).lower()
        return any(token in reason_blob for token in ("because", "reason", "why", "бо", "тому", "причин"))

    def _has_reread_reason(self, command: dict) -> bool:
        reason_fields = (
            command.get("reason"),
            command.get("because"),
            command.get("before_execution"),
            command.get("note"),
        )
        reason_blob = " ".join(str(x) for x in reason_fields if x).lower()
        return any(
            token in reason_blob
            for token in (
                "exact",
                "verify current",
                "verify",
                "patch",
                "edit",
                "implementation",
                "точн",
                "перевір",
                "патч",
                "редаг",
            )
        )

    def _already_read_current_version(self, path: str | None) -> bool:
        if not path or self.history is None:
            return False
        checker = getattr(self.history, "has_current_file_version", None)
        if callable(checker):
            try:
                return bool(checker(path))
            except Exception:
                return False
        return False

    def _reread_after_summary(self) -> bool:
        if self.history is None:
            return False
        checker = getattr(self.history, "was_recently_summarized", None)
        if callable(checker):
            try:
                window = int(getattr(self.config, "RECENT_SUMMARY_REREAD_WINDOW_SEC", 90))
                return bool(checker(window))
            except Exception:
                return False
        return False

    def _allowed_actions_for_phase(self) -> set[str]:
        return set(self._phase_allowed_actions.get(self.phase, set()))

    def _phase_allows_action(self, command: dict) -> bool:
        cmd_type = command.get("type") or command.get("action") or "unknown"
        allowed = self._allowed_actions_for_phase()
        if cmd_type not in allowed:
            return False
        if cmd_type == "run_shell":
            raw = command.get("command")
            if self.phase in {AgentPhase.OBSERVE, AgentPhase.VERIFY}:
                return self._is_read_only_shell_command(raw)
        if self.phase == AgentPhase.EDIT_PLAN and cmd_type == "search_content":
            pattern = str(command.get("pattern") or command.get("query") or "")
            return 0 < len(pattern) <= 120
        return True

    @staticmethod
    def _is_read_only_shell_command(raw_command: object) -> bool:
        import re as _re, shlex as _shlex
        if not isinstance(raw_command, str):
            return False
        cmd = raw_command.strip()
        if not cmd:
            return False
        lowered = cmd.lower()
        if any(tok in lowered for tok in (">", "| tee", ">>", "sed -i", "perl -i", "mkdir ", "rm ", "mv ", "cp ", "touch ")):
            return False
        segments = _re.split(r"\s*(?:&&|\|\||;|\n)\s*", lowered)
        if not segments:
            return False
        allowed_bins = {"cd", "cat", "head", "tail", "grep", "rg", "wc", "find", "stat", "file", "pwd", "ls", "sed", "awk"}
        saw_reader = False
        for segment in segments:
            segment = segment.strip()
            if not segment:
                continue
            try:
                tokens = _shlex.split(segment)
            except Exception:
                return False
            if not tokens:
                continue
            bin_name = tokens[0]
            if bin_name not in allowed_bins:
                return False
            if bin_name == "sed" and "-n" not in tokens:
                return False
            if bin_name != "cd":
                saw_reader = True
        return saw_reader

    @staticmethod
    def _normalize_dir_path(path: str | None) -> str:
        if not isinstance(path, str):
            return ""
        p = path.strip().replace("\\", "/")
        if p in {"", ".", "./"}:
            return "."
        while p.endswith("/") and p != "/":
            p = p[:-1]
        return p or "."

    def _is_root_listing(self, path: str | None) -> bool:
        p = self._normalize_dir_path(path)
        return p in {".", "/", "./"}

    def _is_direct_child_dir(self, previous: str | None, current: str | None) -> bool:
        prev = self._normalize_dir_path(previous)
        curr = self._normalize_dir_path(current)
        if not prev or not curr or prev == curr:
            return False
        if prev == ".":
            return "/" not in curr.strip("/")
        prefix = prev + "/"
        if not curr.startswith(prefix):
            return False
        remainder = curr[len(prefix):].strip("/")
        return bool(remainder) and "/" not in remainder

    def _broad_recon_budgets(self) -> dict[str, bool]:
        return {
            "root_listing_budget_exhausted": self.root_listings_used >= max(1, int(getattr(self.config, "MAX_ROOT_LISTINGS_PER_TURN", 1))),
            "list_directory_budget_exhausted": self.list_directory_actions_used >= max(1, int(getattr(self.config, "MAX_LIST_DIRECTORY_ACTIONS_PER_TURN", 4))),
            "directory_descent_budget_exhausted": self.directory_descent_chain >= max(1, int(getattr(self.config, "MAX_DIRECTORY_DESCENT_CHAIN", 3))),
            "broad_recon_budget_exhausted": self.broad_recon_batches_used >= max(1, int(getattr(self.config, "MAX_BROAD_RECON_BATCHES", 2))),
        }

    def note_planned_batch(self, action_commands: list[dict]):
        cmds = [cmd for cmd in action_commands if isinstance(cmd, dict)]
        if not cmds:
            return
        broad_types = {"read_file", "read_file_skeleton", "search_content", "search_files", "list_directory", "find_files"}
        readonly = all(
            ((cmd.get("type") or cmd.get("action") or "unknown") in READ_ONLY_ACTIONS)
            or (((cmd.get("type") or cmd.get("action") or "unknown") == "run_shell") and self._is_read_only_shell_command(cmd.get("command")))
            for cmd in cmds
        )
        if readonly and sum(1 for cmd in cmds if (cmd.get("type") or cmd.get("action") or "unknown") in broad_types) >= 2:
            self.broad_recon_batches_used += 1

    def pre_action_policy(self, command: dict) -> PreActionDecision:
        cmd_type = command.get("type") or command.get("action") or "unknown"
        fingerprint = self._fingerprint(command)
        path = command.get("path")
        allow_readonly_probe = (
            self.multi_file_scope
            and cmd_type in {"read_file", "read_file_skeleton"}
            and isinstance(path, str)
            and bool(path)
            and path not in self.seen_paths
        )
        budget_flags = self._broad_recon_budgets()
        engine_decision: EnginePreActionDecision = self.policy_engine.evaluate_pre_action(
            PreActionPolicyInput(
                phase=self.phase.value,
                cmd_type=cmd_type,
                path=path if isinstance(path, str) else None,
                fingerprint=fingerprint,
                target_file=self.target_file,
                forbidden_recover_fingerprint=self.forbidden_recover_fingerprint,
                has_cross_target_reason=self._has_cross_target_reason(command),
                multi_file_scope=self.multi_file_scope,
                block_readonly_until_state_change=self.block_readonly_until_state_change,
                allow_readonly_probe=allow_readonly_probe,
                already_read_current_version=self._already_read_current_version(path if isinstance(path, str) else None),
                reread_reason_ok=self._has_reread_reason(command),
                reread_after_summary=self._reread_after_summary(),
                phase_allows_action=self._phase_allows_action(command),
                phase_allowed_next_actions=sorted(self._allowed_actions_for_phase()),
                observe_budget_exhausted=(self.phase == AgentPhase.EDIT_PLAN and self.observe_actions_used >= self.observe_budget),
                root_listing_budget_exhausted=budget_flags["root_listing_budget_exhausted"],
                list_directory_budget_exhausted=budget_flags["list_directory_budget_exhausted"],
                directory_descent_budget_exhausted=budget_flags["directory_descent_budget_exhausted"],
                broad_recon_budget_exhausted=budget_flags["broad_recon_budget_exhausted"],
                task_kind=self.task_kind.value,
                project_inspection_mode=self.project_inspection_mode,
                inspection_profile=self.inspection_profile,
                inspection_entrypoints_checked=len(self.inspection_entrypoints_checked),
                inspection_searches_used=self.inspection_searches_used,
                preferred_inspection_entrypoint=self._is_preferred_inspection_entrypoint(path if isinstance(path, str) else None),
            )
        )
        return PreActionDecision(
            allow=engine_decision.allow,
            stop_reason=engine_decision.stop_reason,
            recovery_prompt=engine_decision.recovery_prompt,
            required_next_action_types=engine_decision.required_next_action_types,
        )

    def _update_target_file(self, command: dict, cmd_type: str, state_changing_ops: set[str]):
        if self.multi_file_scope:
            return
        path = command.get("path")
        if not isinstance(path, str) or not path:
            return
        if cmd_type in state_changing_ops:
            self.target_file = path
            return
        if self.target_file is None and self.mode == WorkMode.IMPLEMENT and cmd_type in {
            "read_file",
            "read_file_skeleton",
            "edit_file",
            "write_file",
        }:
            self.target_file = path

    @staticmethod
    def _normalize_search_pattern(value: object) -> str:
        if not isinstance(value, str):
            return ""
        normalized = value.lower()
        normalized = normalized.replace("\\.", ".").replace("\\|", "|")
        parts = [p.strip() for p in normalized.split("|") if p.strip()]
        if not parts:
            return normalized.strip()
        return "|".join(sorted(set(parts)))

    @staticmethod
    def _normalize_search_result(value: object) -> str:
        if not isinstance(value, str):
            return ""
        normalized = value.lower().strip()
        if "no matches found" in normalized:
            return "no_matches"
        # Collapse numeric noise to compare same result shape across line-number changes.
        normalized = "".join("#" if ch.isdigit() else ch for ch in normalized)
        return normalized[:240]

    def _compute_progress_score(self, command: dict, fingerprint: str, result: dict) -> int:
        cmd_type = command.get("type") or command.get("action") or "unknown"
        path = command.get("path")
        score = 0
        output_text = str((result or {}).get("output", "")).lower()
        no_matches_found = "no matches found" in output_text

        if isinstance(path, str) and path:
            if path not in self.seen_paths:
                score += 2
                self.seen_paths.add(path)
            elif cmd_type == "read_file" and self._already_read_current_version(path):
                score -= 3
                if self._reread_after_summary() and not self._has_reread_reason(command):
                    score -= 2
            if self.target_file and path != self.target_file:
                score -= 1 if self._has_cross_target_reason(command) else 2

        if fingerprint not in self.seen_action_fingerprints:
            score += 1
            self.seen_action_fingerprints.add(fingerprint)
        else:
            score -= 1

        if cmd_type in {"search_content", "search_files"}:
            query_sig = json.dumps(
                {
                    "pattern": self._normalize_search_pattern(command.get("pattern")),
                    "query": self._normalize_search_pattern(command.get("query")),
                    "path": command.get("path"),
                },
                sort_keys=True,
                ensure_ascii=False,
            )
            if query_sig not in self.seen_search_signatures:
                self.seen_search_signatures.add(query_sig)
                # New query shape is progress only if it yields some signal.
                if not no_matches_found:
                    score += 1
            else:
                score -= 1

            if no_matches_found:
                score -= 2

            result_sig = self._normalize_search_result((result or {}).get("output", ""))
            if result_sig:
                if result_sig in self.seen_search_result_signatures:
                    score -= 2
                else:
                    self.seen_search_result_signatures.add(result_sig)
                    if not no_matches_found:
                        score += 1

        return score

    @staticmethod
    def _count_listed_files(output_text: object) -> int:
        text = str(output_text or "")
        if not text:
            return 0
        count = 0
        for line in text.splitlines():
            line = line.strip()
            if line.startswith("[F] "):
                count += 1
        return count

    def _effective_multi_file_readonly_limit(self) -> int:
        base_limit = max(
            4,
            int(getattr(self.config, "MULTI_FILE_READ_ONLY_GLOBAL_LIMIT", 10)),
        )
        if not self.multi_file_scope or self.mode != WorkMode.IMPLEMENT:
            return base_limit
        file_count = int(self.multi_file_target_file_count or 0)
        if file_count <= 0:
            return base_limit
        # Dynamic budget: enough room to inspect most files once before forcing edit/write.
        dynamic_limit = min(64, file_count + 4)
        return max(base_limit, dynamic_limit)

    def note_action(self, command: dict, result: dict, state_changing_ops: set[str]):
        cmd_type = command.get("type") or command.get("action") or "unknown"
        status = result.get("status")
        path = command.get("path") if isinstance(command.get("path"), str) else None
        fingerprint = self._fingerprint(command)
        self.last_action_fingerprint = fingerprint
        self._update_target_file(command, cmd_type, state_changing_ops)

        if status in {"error", "failed", "denied"}:
            self.phase = AgentPhase.RECOVER
            self.stagnation_count += 1
            self.forbidden_recover_fingerprint = fingerprint
            self.recent_signatures.append(fingerprint)
            return

        if cmd_type in state_changing_ops and status == "success":
            self.phase = AgentPhase.VERIFY
            self.stagnation_count = 0
            self.diagnostic_attempts = 0
            self.forbidden_recover_fingerprint = None
            self.invariant_violations = 0
            self.last_progress_signature = f"APPLY:{fingerprint}"
            self.last_progress_score = 3
            self.recent_signatures.append(fingerprint)
            self.current_file_focus = None
            self.per_file_readonly_streak = 0
            self.multi_file_readonly_total = 0
            self.block_readonly_until_state_change = False
            self.observe_actions_used = 0
            return

        if cmd_type in READ_ONLY_ACTIONS and status == "success":
            if self.phase == AgentPhase.OBSERVE:
                self.observe_actions_used += 1
            if self.phase != AgentPhase.VERIFY:
                self.phase = AgentPhase.OBSERVE
            if cmd_type == "list_directory":
                self.list_directory_actions_used += 1
                if self._is_root_listing(path):
                    self.root_listings_used += 1
                if self._is_direct_child_dir(self.last_directory_path, path):
                    self.directory_descent_chain += 1
                else:
                    self.directory_descent_chain = 1 if path else 0
                self.last_directory_path = path or self.last_directory_path
            if self.project_inspection_mode and cmd_type == "read_file" and self._is_preferred_inspection_entrypoint(path):
                self.inspection_entrypoints_checked.add(path)
            if self.project_inspection_mode and cmd_type in {"search_files", "search_content"}:
                self.inspection_searches_used += 1
            if self.multi_file_scope and cmd_type == "list_directory":
                listed = self._count_listed_files((result or {}).get("output", ""))
                if listed > 0:
                    self.multi_file_target_file_count = listed
                    if path:
                        self.multi_file_target_dir = path
            progress_score = self._compute_progress_score(command, fingerprint, result)
            self.last_progress_score = progress_score
            progress_signature = f"{cmd_type}:{command.get('path') or ''}:{fingerprint}"

            if progress_score > 0:
                self.stagnation_count = 0
                self.invariant_violations = 0
                self.last_progress_signature = progress_signature
            else:
                self.stagnation_count += 1
                if self.target_file and command.get("path") and command.get("path") != self.target_file:
                    self.invariant_violations += 1

            if self.multi_file_scope and path:
                if self.mode == WorkMode.IMPLEMENT:
                    self.multi_file_readonly_total += 1
                if path == self.current_file_focus:
                    self.per_file_readonly_streak += 1
                else:
                    self.current_file_focus = path
                    self.per_file_readonly_streak = 1
                per_file_limit = max(
                    2,
                    int(getattr(self.config, "MULTI_FILE_PER_FILE_READ_ONLY_LIMIT", 3)),
                )
                if self.per_file_readonly_streak >= per_file_limit:
                    # Escalate quickly: in multi-file mode we must move from reconnaissance
                    # to deterministic fix/skip for the current file.
                    self.stagnation_count = max(self.stagnation_count, self._read_only_limit())
                    self.last_progress_score = min(self.last_progress_score, -2)
                global_limit = self._effective_multi_file_readonly_limit()
                if self.multi_file_readonly_total >= global_limit:
                    # Hard escalation: in implementation mode, too many read-only actions
                    # across many files means we must switch to edit/write or finalize.
                    self.stagnation_count = max(self.stagnation_count, self._read_only_limit())
                    self.last_progress_score = min(self.last_progress_score, -3)
                    self.block_readonly_until_state_change = True
            if self.observe_actions_used >= self.observe_budget:
                self.phase = AgentPhase.EDIT_PLAN
                self.block_readonly_until_state_change = True
            self.recent_signatures.append(progress_signature)
            return

        # Non read-only successful steps are considered progress.
        self.phase = AgentPhase.EDIT_PLAN
        self.stagnation_count = 0
        self.invariant_violations = 0
        self.last_progress_signature = f"{cmd_type}:{fingerprint}"
        self.last_progress_score = 1
        self.recent_signatures.append(fingerprint)
        self.current_file_focus = None
        self.per_file_readonly_streak = 0
        self.block_readonly_until_state_change = False
        self.observe_actions_used = 0
        self.directory_descent_chain = 0
        self.last_directory_path = None

    def build_diagnostic_prompt(self) -> str:
        target = self.target_file or "<unknown>"
        allowed = ", ".join(sorted(self._allowed_actions_for_phase())) or "none"
        base = (
            "SYSTEM_DIAGNOSTIC: You are in a no-progress loop.\n"
            f"Task kind: {self.task_kind.value}. Current phase: {self.phase.value}.\n"
            f"Stagnation count: {self.stagnation_count}. Target file: {target}.\n"
            f"Last progress score: {self.last_progress_score}.\n"
            f"Allowed next actions now: {allowed}.\n"
            "You repeated read-only actions without measurable progress.\n"
            "Respond with EXACTLY ONE action and avoid repeating previous read_file fingerprints."
        )
        route_hint = self._inspection_route_hint()
        if route_hint:
            base += "\n" + route_hint
        if self.task_kind == TaskKind.HYBRID:
            base += "\nHYBRID TASK RULE: after short reconnaissance, pin a target file/area and move to edit planning. Do not continue broad project-wide inspection."
        elif self.task_kind == TaskKind.MODIFICATION:
            base += "\nMODIFICATION TASK RULE: stop broad reconnaissance now and move to deterministic edit/write."
        else:
            base += "\nINSPECTION TASK RULE: if enough evidence is gathered, finish with a plain-text summary instead of editing files."
        if self.multi_file_scope:
            base += (
                "\nMULTI_FILE_EXECUTION_RULE:\n"
                "Use a compact <plan> to list candidate files and current file index, then return EXACTLY ONE action.\n"
                "Execute strictly per file: read -> decide -> edit/write -> verify -> move to next file."
            )
        return base

    def build_pin_target_prompt(self) -> str:
        target = self.target_file or "<unknown>"
        return (
            "SYSTEM: Target file editing mode.\n"
            f"Task kind: {self.task_kind.value}. Work only on `{target}` unless you provide explicit reason for any other file.\n"
            "For HYBRID/MODIFICATION tasks, prefer edit_file/write_file next.\n"
            "Return EXACTLY ONE action for a deterministic edit strategy."
        )

    def decide(self) -> LoopDecision:
        limit = self._read_only_limit()
        max_diagnostics = max(1, int(getattr(self.config, "STAGNATION_MAX_DIAGNOSTICS", 1)))
        invariant_limit = max(1, int(getattr(self.config, "INVARIANT_VIOLATION_LIMIT", 1)))
        engine_decision: EngineLoopDecision = self.policy_engine.evaluate_loop(
            LoopPolicyInput(
                stagnation_count=self.stagnation_count,
                read_only_limit=limit,
                diagnostic_attempts=self.diagnostic_attempts,
                max_diagnostics=max_diagnostics,
                invariant_violations=self.invariant_violations,
                invariant_limit=invariant_limit,
                diagnostic_prompt=self.build_diagnostic_prompt(),
                required_next_action_types=["search_content", "edit_file", "write_file"],
            )
        )
        if engine_decision.decision == DecisionType.MODEL_DIAGNOSTIC.value:
            self.diagnostic_attempts += 1
        return LoopDecision(
            decision=DecisionType(engine_decision.decision),
            prompt=engine_decision.prompt,
            reason=engine_decision.reason,
            required_next_action_types=engine_decision.required_next_action_types,
        )

    def on_user_recovery_choice(self, choice: str):
        if choice in {"retry_recovery", "open_search", "pin_target_edit", "continue_diagnosis"}:
            self.stagnation_count = 0
            self.diagnostic_attempts = 0
            self.invariant_violations = 0
            self.phase = AgentPhase.RECOVER