"""Simplified state machine.

Phase 2 keeps only:
- coarse phases
- task kind detection
- broad read-only budgets
- anti-reread / target pin cooperation with simplified policy engine
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from enum import Enum

from .policy_engine import (
    EngineLoopDecision,
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
    def __init__(self, config):
        self.config = config
        self.policy_engine = PolicyEngine()
        self.phase = AgentPhase.OBSERVE
        self.mode = WorkMode.IMPLEMENT
        self.task_kind = TaskKind.MODIFICATION
        self.target_file: str | None = None
        self.history = None
        self.intent_runtime = None

        self.stagnation_count = 0
        self.diagnostic_attempts = 0
        self.last_progress_score = 0
        self.invariant_violations = 0
        self.observe_actions_used = 0
        self.broad_recon_batches_used = 0

        self._phase_allowed_actions = {
            AgentPhase.OBSERVE: {
                "read_file", "read_file_skeleton", "search_content", "search_files",
                "list_directory", "find_files", "git_diff", "run_shell",
            },
            AgentPhase.EDIT_PLAN: {"search_content", "search_files", "read_file", "edit_file", "write_file", "run_shell"},
            AgentPhase.APPLY: {"edit_file", "write_file", "run_shell"},
            AgentPhase.VERIFY: {"read_file", "search_content", "git_diff", "run_shell"},
            AgentPhase.RECOVER: {"read_file", "search_content", "search_files", "list_directory", "edit_file", "write_file", "run_shell"},
        }

    def _classify_task_kind(self, user_input: str) -> TaskKind:
        text = (user_input or "").lower()
        advisory = ("яким має бути наступний крок", "що робити далі", "what next", "next step", "порадь")
        if any(t in text for t in advisory):
            return TaskKind.INSPECTION
        inspection = ("analy", "inspect", "investig", "review", "understand", "аналіз", "дослід", "перевір", "знайти")
        modification = ("fix", "implement", "change", "modify", "edit", "write", "виправ", "реаліз", "зміни", "відредаг", "видалити")
        has_i = any(t in text for t in inspection)
        has_m = any(t in text for t in modification)
        if has_i and has_m:
            return TaskKind.HYBRID
        if has_i:
            return TaskKind.INSPECTION
        return TaskKind.MODIFICATION

    def start_turn(self, user_input: str):
        self.task_kind = self._classify_task_kind(user_input)
        self.mode = WorkMode.RESEARCH if self.task_kind == TaskKind.INSPECTION else WorkMode.IMPLEMENT
        self.phase = AgentPhase.OBSERVE
        self.target_file = None
        self.stagnation_count = 0
        self.diagnostic_attempts = 0
        self.last_progress_score = 0
        self.observe_actions_used = 0
        self.broad_recon_batches_used = 0

    def _read_only_limit(self) -> int:
        return int(getattr(self.config, "RESEARCH_STAGNATION_LIMIT", 6)) if self.mode == WorkMode.RESEARCH else int(getattr(self.config, "IMPLEMENT_STAGNATION_LIMIT", 3))

    def _observe_budget(self) -> int:
        if self.task_kind == TaskKind.INSPECTION:
            return int(getattr(self.config, "OBSERVE_BUDGET_INSPECTION", 6))
        if self.task_kind == TaskKind.HYBRID:
            return int(getattr(self.config, "OBSERVE_BUDGET_HYBRID", 4))
        return int(getattr(self.config, "OBSERVE_BUDGET_MODIFICATION", 2))

    def _has_cross_target_reason(self, command: dict) -> bool:
        reason_fields = (command.get("reason"), command.get("because"), command.get("before_execution"))
        blob = " ".join(str(x) for x in reason_fields if x).lower()
        return any(token in blob for token in ("because", "reason", "why", "бо", "тому", "причин"))

    def _has_reread_reason(self, command: dict) -> bool:
        reason_fields = (command.get("reason"), command.get("because"), command.get("before_execution"), command.get("note"))
        blob = " ".join(str(x) for x in reason_fields if x).lower()
        return any(token in blob for token in ("exact", "verify", "patch", "edit", "implementation", "точн", "перевір", "патч", "редаг"))

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
                return bool(checker(getattr(self.config, "RECENT_SUMMARY_REREAD_WINDOW_SEC", 90)))
            except Exception:
                return False
        return False

    def _allowed_actions_for_phase(self) -> set[str]:
        return set(self._phase_allowed_actions.get(self.phase, set()))

    def _phase_allows_action(self, command: dict) -> bool:
        cmd_type = command.get("type") or command.get("action") or "unknown"
        return cmd_type in self._allowed_actions_for_phase()

    def note_planned_batch(self, action_commands: list[dict]):
        readonly = all((cmd.get("type") or cmd.get("action") or "unknown") in READ_ONLY_ACTIONS for cmd in action_commands if isinstance(cmd, dict))
        if readonly and len(action_commands) >= 2:
            self.broad_recon_batches_used += 1

    def pre_action_policy(self, command: dict) -> PreActionDecision:
        cmd_type = command.get("type") or command.get("action") or "unknown"
        path = command.get("path") if isinstance(command.get("path"), str) else None
        active_intent = getattr(self.intent_runtime, "active_intent", None) if self.intent_runtime is not None else None
        eng = self.policy_engine.evaluate_pre_action(
            PreActionPolicyInput(
                phase=self.phase.value,
                cmd_type=cmd_type,
                path=path,
                fingerprint=self._fingerprint(command),
                target_file=self.target_file,
                forbidden_recover_fingerprint=None,
                has_cross_target_reason=self._has_cross_target_reason(command),
                phase_allows_action=self._phase_allows_action(command),
                phase_allowed_next_actions=sorted(self._allowed_actions_for_phase()),
                observe_budget_exhausted=self.observe_actions_used >= self._observe_budget(),
                broad_recon_budget_exhausted=self.broad_recon_batches_used >= int(getattr(self.config, "MAX_BROAD_RECON_BATCHES", 2)),
                task_kind=self.task_kind.value,
                already_read_current_version=self._already_read_current_version(path),
                reread_reason_ok=self._has_reread_reason(command),
                reread_after_summary=self._reread_after_summary(),
                active_intent_type=(getattr(active_intent, "intent_type", None)),
                active_intent_step_count=int(getattr(active_intent, "step_count", 0) or 0),
                active_intent_safe_steps_limit=int(getattr(active_intent, "safe_steps_limit", 0) or 0),
            )
        )
        return PreActionDecision(
            allow=eng.allow,
            stop_reason=eng.stop_reason,
            recovery_prompt=eng.recovery_prompt,
            required_next_action_types=eng.required_next_action_types,
        )

    def note_action(self, command: dict, result: dict, state_changing_ops: set[str]):
        cmd_type = command.get("type") or command.get("action") or "unknown"
        status = result.get("status")
        path = command.get("path") if isinstance(command.get("path"), str) else None

        if status in {"error", "failed", "denied"}:
            self.phase = AgentPhase.RECOVER
            self.stagnation_count += 1
            return

        if cmd_type in state_changing_ops and status == "success":
            self.phase = AgentPhase.VERIFY
            self.stagnation_count = 0
            self.observe_actions_used = 0
            return

        if cmd_type in READ_ONLY_ACTIONS and status == "success":
            self.observe_actions_used += 1
            self.phase = AgentPhase.OBSERVE if self.phase != AgentPhase.VERIFY else self.phase
            if self.mode == WorkMode.IMPLEMENT and self.target_file is None and cmd_type == "read_file" and path:
                self.target_file = path
            self.last_progress_score = 1
            return

        self.phase = AgentPhase.EDIT_PLAN

    def build_diagnostic_prompt(self) -> str:
        allowed = ", ".join(sorted(self._allowed_actions_for_phase())) or "none"
        return (
            "SYSTEM_DIAGNOSTIC: You are in a no-progress loop.\n"
            f"Task kind: {self.task_kind.value}. Current phase: {self.phase.value}.\n"
            f"Allowed next actions now: {allowed}.\n"
            "Return EXACTLY ONE action and choose a different strategy."
        )

    def decide(self) -> LoopDecision:
        eng: EngineLoopDecision = self.policy_engine.evaluate_loop(
            LoopPolicyInput(
                stagnation_count=self.stagnation_count,
                read_only_limit=self._read_only_limit(),
                diagnostic_attempts=self.diagnostic_attempts,
                max_diagnostics=int(getattr(self.config, "STAGNATION_MAX_DIAGNOSTICS", 1)),
                diagnostic_prompt=self.build_diagnostic_prompt(),
                required_next_action_types=["search_content", "edit_file", "write_file"],
                task_kind=self.task_kind.value,
                phase=self.phase.value,
                observe_budget_exhausted=self.observe_actions_used >= self._observe_budget(),
            )
        )
        if eng.decision == "MODEL_DIAGNOSTIC":
            self.diagnostic_attempts += 1
        return LoopDecision(
            decision=DecisionType(eng.decision),
            prompt=eng.prompt,
            reason=eng.reason,
            required_next_action_types=eng.required_next_action_types,
        )

    @staticmethod
    def _fingerprint(command: dict) -> str:
        ignored = {"before_execution", "during_execution", "after_execution", "return_control", "id"}
        cmd_type = command.get("type") or command.get("action") or "unknown"
        args = {k: v for k, v in command.items() if k not in ignored}
        return f"{cmd_type}:{json.dumps(args, sort_keys=True, ensure_ascii=False)}"

    def _inspection_route_hint(self) -> str:
        return ""