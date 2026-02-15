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
        self.seen_action_fingerprints: set[str] = set()

    def start_turn(self, user_input: str):
        text = (user_input or "").lower()
        research_keywords = (
            "analy",
            "investig",
            "explore",
            "research",
            "огляд",
            "аналіз",
            "дослід",
            "пошук",
            "find",
            "search",
        )
        self.mode = (
            WorkMode.RESEARCH
            if any(k in text for k in research_keywords)
            else WorkMode.IMPLEMENT
        )
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
        self.seen_action_fingerprints.clear()

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

    def pre_action_policy(self, command: dict) -> PreActionDecision:
        cmd_type = command.get("type") or command.get("action") or "unknown"
        fingerprint = self._fingerprint(command)
        path = command.get("path")
        engine_decision: EnginePreActionDecision = self.policy_engine.evaluate_pre_action(
            PreActionPolicyInput(
                phase=self.phase.value,
                cmd_type=cmd_type,
                path=path if isinstance(path, str) else None,
                fingerprint=fingerprint,
                target_file=self.target_file,
                forbidden_recover_fingerprint=self.forbidden_recover_fingerprint,
                has_cross_target_reason=self._has_cross_target_reason(command),
            )
        )
        return PreActionDecision(
            allow=engine_decision.allow,
            stop_reason=engine_decision.stop_reason,
            recovery_prompt=engine_decision.recovery_prompt,
            required_next_action_types=engine_decision.required_next_action_types,
        )

    def _update_target_file(self, command: dict, cmd_type: str, state_changing_ops: set[str]):
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

    def _compute_progress_score(self, command: dict, fingerprint: str) -> int:
        cmd_type = command.get("type") or command.get("action") or "unknown"
        path = command.get("path")
        score = 0

        if isinstance(path, str) and path:
            if path not in self.seen_paths:
                score += 2
                self.seen_paths.add(path)
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
                    "pattern": command.get("pattern"),
                    "query": command.get("query"),
                    "path": command.get("path"),
                },
                sort_keys=True,
                ensure_ascii=False,
            )
            if query_sig not in self.seen_search_signatures:
                score += 1
                self.seen_search_signatures.add(query_sig)

        return score

    def note_action(self, command: dict, result: dict, state_changing_ops: set[str]):
        cmd_type = command.get("type") or command.get("action") or "unknown"
        status = result.get("status")
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
            return

        if cmd_type in READ_ONLY_ACTIONS and status == "success":
            self.phase = AgentPhase.OBSERVE
            progress_score = self._compute_progress_score(command, fingerprint)
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
            self.recent_signatures.append(progress_signature)
            return

        # Non read-only successful steps are considered progress.
        self.phase = AgentPhase.EDIT_PLAN
        self.stagnation_count = 0
        self.invariant_violations = 0
        self.last_progress_signature = f"{cmd_type}:{fingerprint}"
        self.last_progress_score = 1
        self.recent_signatures.append(fingerprint)

    def build_diagnostic_prompt(self) -> str:
        target = self.target_file or "<unknown>"
        return (
            "SYSTEM_DIAGNOSTIC: You are in a no-progress loop.\n"
            f"Stagnation count: {self.stagnation_count}. Target file: {target}.\n"
            f"Last progress score: {self.last_progress_score}.\n"
            "You repeated read-only actions without measurable progress.\n"
            "Respond with EXACTLY ONE action and avoid repeating previous read_file fingerprints.\n"
            "First explain briefly in <think> why progress stalled, then choose one of:\n"
            "1) search_content with a tighter pattern, 2) edit_file with exact block, 3) write_file with concise validated content."
        )

    def build_pin_target_prompt(self) -> str:
        target = self.target_file or "<unknown>"
        return (
            "SYSTEM: Target file editing mode.\n"
            f"Work only on `{target}` unless you provide explicit reason for any other file.\n"
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
