"""Simplified state machine.

Keeps only:
- task kind detection
- broad read-only budgets
- anti-reread / target pin cooperation with simplified policy engine
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from enum import Enum

from .allowed_actions_resolver import AllowedActionsContext, AllowedActionsResolver
from .policy_engine import (
    EngineLoopDecision,
    LoopPolicyInput,
    PolicyEngine,
    PreActionPolicyInput,
)

READ_ONLY_ACTIONS = {
    "read_file",
    "read_chunk",
    "read_file_skeleton",
    "search_content",
    "search_files",
    "list_directory",
    "find_files",
    "git_diff",
    "run_shell",
}


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
    required_next_action_source: str = ""
    intent_allowed_actions: list[str] = field(default_factory=list)
    recommended_next_actions: list[str] = field(default_factory=list)
    keep_current_intent: bool = False


class AgentStateMachine:
    def __init__(self, config):
        self.config = config
        self.policy_engine = PolicyEngine()
        self.allowed_actions_resolver = AllowedActionsResolver()
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

    def _is_read_only_action(self, command: dict) -> bool:
        if not isinstance(command, dict):
            return False
        cmd_type = command.get("type") or command.get("action") or "unknown"
        if cmd_type != "run_shell":
            return cmd_type in READ_ONLY_ACTIONS
        raw = command.get("command")
        if not isinstance(raw, str):
            return False
        lowered = raw.strip().lower()
        if not lowered:
            return False
        if any(tok in lowered for tok in (">", "| tee", ">>", "sed -i", "perl -i", "mkdir ", "rm ", "mv ", "cp ", "touch ")):
            return False
        bins = ("find ", "rg ", "grep ", "ls ", "cat ", "head ", "tail ", "wc ", "stat ", "file ", "pwd", "pwd ", "awk ", "sed -n")
        return lowered.startswith(bins)

    def _classify_task_kind(self, user_input: str) -> TaskKind:
        text = (user_input or "").lower()
        advisory = ("яким має бути наступний крок", "що робити далі", "what next", "next step", "порадь")
        if any(t in text for t in advisory):
            return TaskKind.INSPECTION

        implementation_lookup = (
            "де реалізовано",
            "де реалізована",
            "де реалізований",
            "де знаходиться реалізація",
            "де цей файл",
            "де ця кнопка",
            "де цей екран",
            "де відкривається",
            "де викликається",
            "в якому файлі",
            "який файл",
            "which file",
            "what file",
            "which screen",
            "which composable",
            "where is",
            "where are",
            "implemented in",
            "find where",
            "locate where",
        )
        if any(t in text for t in implementation_lookup):
            return TaskKind.INSPECTION

        inspection = (
            "analy",
            "inspect",
            "investig",
            "review",
            "understand",
            "analyze",
            "locate",
            "identify",
            "where",
            "which",
            "аналіз",
            "дослід",
            "перевір",
            "знайти",
            "знайди",
            "визнач",
            "який файл",
            "в якому файлі",
            "де ",
        )
        modification = (
            "fix",
            "implement",
            "change",
            "modify",
            "edit",
            "write",
            "виправ",
            "зміни",
            "відредаг",
            "видалити",
            "додай",
            "додати",
            "онови",
            "оновити",
            "перероби",
            "переробити",
            "реалізуй",
            "реалізувати",
        )
        has_i = any(t in text for t in inspection)
        has_m = any(t in text for t in modification)
        if has_i and has_m:
            return TaskKind.HYBRID
        if has_i:
            return TaskKind.INSPECTION

        # FIXME:
        # task_kind is a bootstrap heuristic used before a formal contract fully
        # governs the work. Defaulting to MODIFICATION created too many false
        # positives and poisoned downstream recovery/completion logic.
        return TaskKind.HYBRID

    def start_turn(self, user_input: str):
        self.task_kind = self._classify_task_kind(user_input)
        self.mode = WorkMode.RESEARCH if self.task_kind == TaskKind.INSPECTION else WorkMode.IMPLEMENT
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

    def _latest_history_version(self, path: str | None) -> int | None:
        if not path or self.history is None:
            return None
        getter = getattr(self.history, "get_latest_file_version", None)
        if callable(getter):
            try:
                version = getter(path)
                return int(version) if version is not None else None
            except Exception:
                return None
        return None

    def _fresh_read_after_edit_mismatch_allowed(self, path: str | None) -> bool:
        if not path:
            return False
        state = getattr(self.intent_runtime, "state", None) if self.intent_runtime is not None else None
        if state is None:
            return False
        blocked_path = str(getattr(state, "pending_edit_mismatch_path", "") or "").strip()
        blocked_intent = str(getattr(state, "pending_edit_mismatch_intent_id", "") or "").strip()
        active_intent = getattr(self.intent_runtime, "active_intent", None)
        active_intent_id = str(getattr(active_intent, "intent_id", "") or "").strip()
        return bool(blocked_path and path == blocked_path and blocked_intent == active_intent_id)

    def _reread_repeat_count(self, path: str | None) -> int:
        if not path:
            return 0
        state = getattr(self.intent_runtime, "state", None) if self.intent_runtime is not None else None
        if state is None:
            return 0
        blocked_path = str(getattr(state, "reread_blocked_path", "") or "").strip()
        blocked_intent = str(getattr(state, "reread_blocked_intent_id", "") or "").strip()
        active_intent = getattr(self.intent_runtime, "active_intent", None)
        active_intent_id = str(getattr(active_intent, "intent_id", "") or "").strip()
        if path != blocked_path or active_intent_id != blocked_intent:
            return 0
        return int(getattr(state, "reread_blocked_count", 0) or 0)

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

    def note_planned_batch(self, action_commands: list[dict]):
        readonly = all(self._is_read_only_action(cmd) for cmd in action_commands if isinstance(cmd, dict))
        if readonly and len(action_commands) >= 2:
            self.broad_recon_batches_used += 1

    def pre_action_policy(self, command: dict) -> PreActionDecision:
        cmd_type = command.get("type") or command.get("action") or "unknown"
        path = command.get("path") if isinstance(command.get("path"), str) else None
        active_intent = getattr(self.intent_runtime, "active_intent", None) if self.intent_runtime is not None else None
        eng = self.policy_engine.evaluate_pre_action(
            PreActionPolicyInput(
                cmd_type=cmd_type,
                path=path,
                fingerprint=self._fingerprint(command),
                target_file=self.target_file,
                forbidden_recover_fingerprint=None,
                has_cross_target_reason=self._has_cross_target_reason(command),
                observe_budget_exhausted=self.observe_actions_used >= self._observe_budget(),
                broad_recon_budget_exhausted=self.broad_recon_batches_used >= int(getattr(self.config, "MAX_BROAD_RECON_BATCHES", 2)),
                task_kind=self.task_kind.value,
                already_read_current_version=self._already_read_current_version(path),
                reread_reason_ok=self._has_reread_reason(command),
                reread_after_summary=self._reread_after_summary(),
                history_version=self._latest_history_version(path),
                fresh_read_after_edit_mismatch_allowed=self._fresh_read_after_edit_mismatch_allowed(path),
                reread_repeat_count=self._reread_repeat_count(path),
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
            required_next_action_source=getattr(eng, "required_next_action_source", ""),
        ) if eng.allow else self._resolve_pre_action_denial(eng, active_intent)

    def _resolve_pre_action_denial(self, eng: EngineLoopDecision, active_intent) -> PreActionDecision:
        resolved = self.allowed_actions_resolver.resolve_stop_info(
            AllowedActionsContext(
                reason=getattr(eng, "stop_reason", "") or "",
                source=getattr(eng, "required_next_action_source", "") or "",
                next_actions=getattr(eng, "required_next_action_types", []) or [],
                active_intent_allowed_actions=getattr(active_intent, "allowed_actions", []) if active_intent is not None else [],
                active_intent_type=getattr(active_intent, "intent_type", "") if active_intent is not None else "",
            )
        )
        return PreActionDecision(
            allow=False,
            stop_reason=getattr(eng, "stop_reason", ""),
            recovery_prompt=getattr(eng, "recovery_prompt", ""),
            required_next_action_types=resolved.allowed_actions or resolved.recommended_actions,
            required_next_action_source=resolved.authoritative_source,
            intent_allowed_actions=resolved.intent_actions,
            recommended_next_actions=resolved.recommended_actions,
            keep_current_intent=resolved.keep_current_intent,
        )

    def note_action(self, command: dict, result: dict, state_changing_ops: set[str]):
        cmd_type = command.get("type") or command.get("action") or "unknown"
        status = result.get("status")
        path = command.get("path") if isinstance(command.get("path"), str) else None
        is_read_only = self._is_read_only_action(command)
        is_state_changing = (cmd_type in state_changing_ops) and not is_read_only
        active_intent = getattr(self.intent_runtime, "active_intent", None) if self.intent_runtime is not None else None
        active_intent_type = getattr(active_intent, "intent_type", None)

        if status in {"error", "failed", "denied"}:
            self.stagnation_count += 1
            return

        if is_state_changing and status == "success":
            if self.mode == WorkMode.IMPLEMENT and path:
                self.target_file = path
            self.stagnation_count = 0
            self.observe_actions_used = 0
            return

        if is_read_only and status == "success":
            self.observe_actions_used += 1
            if self.mode == WorkMode.IMPLEMENT and self.target_file is None and cmd_type == "read_file" and path:
                self.target_file = path
            self.last_progress_score = 1
            return

    def build_diagnostic_prompt(self) -> str:
        allowed = ", ".join(sorted({
            "search_content",
            "search_files",
            "read_file",
            "read_chunk",
            "edit_file",
            "write_file",
        })) or "none"
        return (
            "SYSTEM_DIAGNOSTIC: You are in a no-progress loop.\n"
            f"Task kind: {self.task_kind.value}.\n"
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
                required_next_action_types=["search_content", "search_files", "read_file", "read_chunk", "edit_file", "write_file"],
                task_kind=self.task_kind.value,
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
