"""Runtime contract for model-declared intents.

This module intentionally stays simple:
- model may declare a formal intent contract
- runtime validates allowed_actions and numeric limits
- runtime tracks steps/retries and exposes light pre/post checks
- current intent may receive runtime constraint updates after recovery events
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field

try:
    from modules.agent.intent_policy_engine import IntentPolicyEngine
    from modules.agent.intent_policy_models import IntentPolicyContext, BlockedActionPolicyContext
except ImportError:
    try:
        from .intent_policy_engine import IntentPolicyEngine
        from .intent_policy_models import IntentPolicyContext, BlockedActionPolicyContext
    except ImportError:
        from intent_policy_engine import IntentPolicyEngine
        from intent_policy_models import IntentPolicyContext, BlockedActionPolicyContext

KNOWN_TOOL_ACTIONS = {
    "read_file",
    "read_chunk",
    "read_file_skeleton",
    "extract_kotlin_function",
    "search_content",
    "search_files",
    "list_directory",
    "find_files",
    "git_diff",
    "run_shell",
    "create_file",
    "write_file",
    "edit_file",
    "replace",
    "delete_file",
    "git_add",
    "git_commit",
    "git_checkout",
}


@dataclass
class IntentContract:
    intent_id: str
    intent_type: str
    goal: str
    allowed_actions: list[str]
    safe_steps_limit: int
    retry_limit: int
    mode: str = "activate"
    switch_reason: str = ""
    switch_explanation: str = ""
    completion_reason: str = ""
    completion_explanation: str = ""
    step_count: int = 0
    retry_count: int = 0
    lineage_id: str = ""
    user_visible_note: str = ""
    hard_limit_hit_count: int = 0
    user_step_extension: int = 0
    user_one_shot_steps_remaining: int = 0
    user_unlimited_override: bool = False
    force_plaintext_completion: bool = False
    action_constraints: dict = field(default_factory=dict)
    original_allowed_actions: list[str] = field(default_factory=list)
    blocked_action_signatures: set[str] = field(default_factory=set)
    blocked_action_reasons: dict[str, str] = field(default_factory=dict)
    canonical_goal: str = ""
    goal_frozen: bool = True


class IntentRuntime:
    SUPPORTED_TYPES = {"INVESTIGATE", "VERIFY", "MODIFY", "CLEANUP", "SUMMARIZE"}
    MODIFY_DEFAULT_ACTIONS = (
        "edit_file",
        "write_file",
        "create_file",
        "run_shell",
        "read_chunk",
        "read_file_skeleton",
        "extract_kotlin_function",
        "search_content",
        "search_files",
        "read_file",
    )
    SUPPORTED_MODES = {"activate", "retry", "replace", "complete"}

    def __init__(self, config):
        self.config = config
        self.policy_engine = IntentPolicyEngine(config)
        self.active_intent: IntentContract | None = None
        self.intent_required_until_activated = False
        self.intent_required_reason = ""
        self.last_transition_info = {}
        self.last_apply_warning = ""

    def reset(self):
        self.active_intent = None
        self.intent_required_until_activated = False
        self.intent_required_reason = ""

    def require_intent(self, reason: str):
        self.intent_required_until_activated = True
        self.intent_required_reason = str(reason or "").strip()

    def clear_requirement(self):
        self.intent_required_until_activated = False
        self.intent_required_reason = ""

    def _normalize_goal(self, goal: str) -> str:
        goal = str(goal or "").lower().strip()
        goal = re.sub(r"[^a-zа-яіїє0-9]+", " ", goal)
        return re.sub(r"\s+", " ", goal).strip()

    def _goal_similarity(self, a: str, b: str) -> float:
        na = set(self._normalize_goal(a).split())
        nb = set(self._normalize_goal(b).split())
        if not na or not nb:
            return 0.0
        return len(na & nb) / max(1, len(na | nb))

    def _reuse_retry_on_same_subtask(self, contract: IntentContract) -> bool:
        if self.active_intent is None:
            return False
        if contract.intent_id == self.active_intent.intent_id:
            return True
        sim = self._goal_similarity(contract.goal, self.active_intent.goal)
        threshold = float(getattr(self.config, "INTENT_RETRY_GOAL_SIMILARITY_THRESHOLD", 0.45))
        return sim >= threshold


    def _goal_tokens(self, goal: str) -> list[str]:
        return [t for t in self._normalize_goal(goal).split() if t]

    def _looks_like_local_step_goal(self, goal: str) -> bool:
        normalized = self._normalize_goal(goal)
        if not normalized:
            return True
        local_markers = {
            "inspect", "read", "find", "locate", "analyze", "examine", "search",
            "прочитати", "читати", "знайти", "пошук", "проаналізувати", "дослідити",
            "переглянути", "локалізувати", "оглянути",
        }
        tokens = set(normalized.split())
        has_local_marker = bool(tokens & local_markers)
        if len(tokens) <= 5 and has_local_marker:
            return True
        bad_prefixes = (
            "inspect ", "read ", "find ", "locate ", "analyze ", "examine ", "search ",
            "прочитати ", "знайти ", "проаналізувати ", "дослідити ", "переглянути ",
        )
        return normalized.startswith(bad_prefixes)

    def _goal_has_meaningful_shape(self, goal: str) -> bool:
        normalized = self._normalize_goal(goal)
        if not normalized:
            return False
        if len(normalized) < 24:
            return False
        if self._looks_like_local_step_goal(goal):
            return False
        return len(normalized.split()) >= 5

    def _goal_core_loss(self, old_goal: str, new_goal: str) -> bool:
        old_tokens = set(self._goal_tokens(old_goal))
        new_tokens = set(self._goal_tokens(new_goal))
        if not old_tokens or not new_tokens:
            return False
        overlap = len(old_tokens & new_tokens) / max(1, len(old_tokens))
        return overlap < 0.45 or self._looks_like_local_step_goal(new_goal)

    def _allowed_actions_overlap(self, a: list[str], b: list[str]) -> float:
        sa = set(a or [])
        sb = set(b or [])
        if not sa or not sb:
            return 0.0
        return len(sa & sb) / max(1, len(sa | sb))

    def _normalize_allowed_actions_for_intent_type(
        self,
        intent_type: str,
        allowed_actions: list[str],
    ) -> list[str]:
        cleaned: list[str] = []
        for action in allowed_actions or []:
            if action in KNOWN_TOOL_ACTIONS and action not in cleaned:
                cleaned.append(action)

        if intent_type != "MODIFY":
            return cleaned

        has_state_changing = any(
            action in {"edit_file", "write_file", "create_file"}
            for action in cleaned
        )
        if has_state_changing:
            return cleaned

        for action in self.MODIFY_DEFAULT_ACTIONS:
            if action in KNOWN_TOOL_ACTIONS and action not in cleaned:
                cleaned.append(action)
        return cleaned

    def _same_lineage(self, contract: IntentContract) -> bool:
        if self.active_intent is None:
            return False
        if contract.intent_id == self.active_intent.intent_id:
            return True
        if contract.intent_type != self.active_intent.intent_type:
            return False
        baseline_goal = self.active_intent.canonical_goal or self.active_intent.goal
        candidate_goal = contract.canonical_goal or contract.goal
        goal_sim = self._goal_similarity(candidate_goal, baseline_goal)
        actions_overlap = self._allowed_actions_overlap(contract.allowed_actions, self.active_intent.allowed_actions)
        return (
            goal_sim >= float(getattr(self.config, "INTENT_RELABEL_GOAL_SIMILARITY_THRESHOLD", 0.6))
            and actions_overlap >= float(getattr(self.config, "INTENT_RELABEL_ACTION_OVERLAP_THRESHOLD", 0.6))
        )

    def _normalize_transition_reason(self, value: object) -> str:
        return str(value or "").strip().lower()

    def _allowed_switch_reasons(self) -> set[str]:
        return {
            "user_requested_new_task",
            "current_intent_completed",
            "current_intent_exhausted",
            "work_type_changed",
            "current_intent_no_longer_fits",
        }

    def _allowed_completion_reasons(self) -> set[str]:
        return {
            "goal_completed",
            "user_requested_stop",
            "forced_plaintext_completion",
            "handoff_to_user",
        }

    def _is_legitimate_switch_reason(self, reason: str) -> bool:
        return self._normalize_transition_reason(reason) in self._allowed_switch_reasons()

    def _is_legitimate_completion_reason(self, reason: str) -> bool:
        return self._normalize_transition_reason(reason) in self._allowed_completion_reasons()

    def _reason_allows_transition(self, contract: IntentContract, active: IntentContract | None, same_lineage: bool) -> bool:
        if active is None:
            return True
        reason = self._normalize_transition_reason(contract.switch_reason)
        if contract.mode == "retry":
            return True
        if contract.mode == "complete":
            return self._is_legitimate_completion_reason(contract.completion_reason)
        if contract.intent_type != active.intent_type:
            return True
        if not same_lineage:
            return True
        return self._is_legitimate_switch_reason(reason)

    def should_bypass_relabel_suspicion(self, contract: IntentContract, transition_info: dict | None = None) -> bool:
        if contract.mode == "complete":
            return True
        if contract.mode == "retry":
            return True
        active = self.active_intent
        same_lineage = bool((transition_info or {}).get("same_lineage")) if transition_info is not None else self._same_lineage(contract)
        if active is None:
            return True
        if contract.intent_type != active.intent_type:
            return True
        return self._is_legitimate_switch_reason(contract.switch_reason) or not same_lineage


    def _normalize_shell_command_for_signature(self, command: object) -> str:
        raw = str(command or "").strip()
        raw = re.sub(r"\s+", " ", raw)
        return raw[:400]

    def make_action_signature(self, command: dict) -> str:
        if not isinstance(command, dict):
            return "unknown"
        cmd_type = str(command.get("type") or command.get("action") or "unknown").strip()
        path = str(command.get("path") or "").strip()

        if cmd_type == "read_file":
            return f"read_file|{path}"

        if cmd_type == "read_chunk":
            start_line = command.get("start_line")
            end_line = command.get("end_line")
            if start_line is not None or end_line is not None:
                return f"read_chunk|{path}|lines:{start_line}:{end_line}"
            start_byte = command.get("start_byte")
            end_byte = command.get("end_byte")
            return f"read_chunk|{path}|bytes:{start_byte}:{end_byte}"

        if cmd_type in {"search_content", "search_files"}:
            pattern = str(command.get("pattern") or "").strip()
            return f"{cmd_type}|{path}|{pattern}"

        if cmd_type == "run_shell":
            normalized = self._normalize_shell_command_for_signature(command.get("command"))
            return f"run_shell|{normalized}"

        return f"{cmd_type}|{path}"

    def block_action_for_current_intent(self, command: dict, reason: str) -> bool:
        if self.active_intent is None or not isinstance(command, dict):
            return False
        signature = self.make_action_signature(command)
        if not signature:
            return False
        self.active_intent.blocked_action_signatures.add(signature)
        self.active_intent.blocked_action_reasons[signature] = str(reason or "").strip()
        return True

    def get_blocked_action_reason(self, command: dict) -> str:
        if self.active_intent is None or not isinstance(command, dict):
            return ""
        signature = self.make_action_signature(command)
        return str(self.active_intent.blocked_action_reasons.get(signature) or "")

    def is_action_blocked_for_current_intent(self, command: dict) -> bool:
        if self.active_intent is None or not isinstance(command, dict):
            return False
        signature = self.make_action_signature(command)
        return signature in self.active_intent.blocked_action_signatures

    def _normalize_constraints(self, raw: dict | None) -> dict:
        if not isinstance(raw, dict):
            return {}
        out: dict = {}

        if "max_full_reads_per_step" in raw:
            try:
                out["max_full_reads_per_step"] = max(0, int(raw.get("max_full_reads_per_step")))
            except Exception:
                pass

        same_path = raw.get("forbid_same_full_read_path")
        if isinstance(same_path, str) and same_path.strip():
            out["forbid_same_full_read_path"] = same_path.strip()

        require_chunk = raw.get("require_chunk_for_paths")
        if isinstance(require_chunk, list):
            cleaned = [str(p).strip() for p in require_chunk if str(p).strip()]
            if cleaned:
                out["require_chunk_for_paths"] = cleaned

        if "forbid_new_intent" in raw:
            out["forbid_new_intent"] = bool(raw.get("forbid_new_intent"))
        if "reuse_current_intent" in raw:
            out["reuse_current_intent"] = bool(raw.get("reuse_current_intent"))

        if "replace_allowed_actions" in raw and isinstance(raw.get("replace_allowed_actions"), list):
            allowed = []
            for item in raw.get("replace_allowed_actions", []):
                action = str(item or "").strip()
                if action in KNOWN_TOOL_ACTIONS and action not in allowed:
                    allowed.append(action)
            if allowed:
                out["replace_allowed_actions"] = allowed

        if "add_allowed_actions" in raw and isinstance(raw.get("add_allowed_actions"), list):
            allowed = []
            for item in raw.get("add_allowed_actions", []):
                action = str(item or "").strip()
                if action in KNOWN_TOOL_ACTIONS and action not in allowed:
                    allowed.append(action)
            if allowed:
                out["add_allowed_actions"] = allowed

        if "remove_allowed_actions" in raw and isinstance(raw.get("remove_allowed_actions"), list):
            allowed = []
            for item in raw.get("remove_allowed_actions", []):
                action = str(item or "").strip()
                if action in KNOWN_TOOL_ACTIONS and action not in allowed:
                    allowed.append(action)
            if allowed:
                out["remove_allowed_actions"] = allowed

        return out

    def _merge_constraints(self, base: dict | None, updates: dict | None) -> dict:
        merged = dict(base or {})
        normalized = self._normalize_constraints(updates)
        for key, value in normalized.items():
            if key == "require_chunk_for_paths":
                existing = [str(p).strip() for p in merged.get(key, []) if str(p).strip()]
                for path in value:
                    if path not in existing:
                        existing.append(path)
                merged[key] = existing
            elif key == "max_full_reads_per_step":
                old = merged.get(key)
                if old is None:
                    merged[key] = value
                else:
                    try:
                        merged[key] = min(int(old), int(value))
                    except Exception:
                        merged[key] = value
            else:
                merged[key] = value
        return merged

    def inspect_transition(self, payload: dict) -> tuple[IntentContract | None, dict | None, str | None]:
        contract, error = self.validate_payload(payload)
        if error:
            return None, None, error
        active = self.active_intent
        info = {
            "same_lineage": False,
            "goal_similarity": 0.0,
            "actions_overlap": 0.0,
            "old_intent_id": getattr(active, "intent_id", ""),
            "old_goal": getattr(active, "goal", ""),
            "old_allowed_actions": list(getattr(active, "allowed_actions", []) or []),
            "new_intent_id": contract.intent_id,
            "new_goal": contract.goal,
            "new_allowed_actions": contract.allowed_actions[:],
            "mode": contract.mode,
            "switch_reason": contract.switch_reason,
            "completion_reason": contract.completion_reason,
        }
        if active is not None:
            info["goal_similarity"] = self._goal_similarity(contract.goal, active.goal)
            info["actions_overlap"] = self._allowed_actions_overlap(contract.allowed_actions, active.allowed_actions)
            info["same_lineage"] = self._same_lineage(contract)
        return contract, info, None

    def _build_policy_context(self, proposed_intent: IntentContract | None, transition_info: dict | None = None) -> IntentPolicyContext:
        active = self.active_intent
        return IntentPolicyContext(
            active_intent=active,
            proposed_intent=proposed_intent,
            transition_info=dict(transition_info or {}),
            recent_problem_actions=[],
            blocked_action_signatures=set(active.blocked_action_signatures or set()) if active is not None else set(),
            blocked_action_reasons=dict(active.blocked_action_reasons or {}) if active is not None else {},
            pending_loop_stop_info=None,
            current_user_input="",
        )

    def validate_payload(self, payload: dict) -> tuple[IntentContract | None, str | None]:
        if not isinstance(payload, dict):
            return None, "intent_payload_must_be_object"

        mode = str(payload.get("mode") or "activate").strip().lower()
        if mode not in self.SUPPORTED_MODES:
            return None, "unsupported_intent_mode"

        active = self.active_intent
        intent_id = str(payload.get("intent_id") or "").strip()
        if mode == "complete":
            if active is None:
                return None, "intent_complete_without_active_intent"
            if not intent_id:
                intent_id = active.intent_id
            if intent_id != active.intent_id:
                return None, "intent_complete_wrong_active_id"

            completion_reason = self._normalize_transition_reason(payload.get("completion_reason"))
            completion_explanation = str(payload.get("completion_explanation") or "").strip()
            if not self._is_legitimate_completion_reason(completion_reason):
                return None, "intent_completion_reason_required"

            return IntentContract(
                intent_id=active.intent_id,
                intent_type=active.intent_type,
                goal=active.goal,
                allowed_actions=active.allowed_actions[:],
                original_allowed_actions=active.original_allowed_actions[:] if active.original_allowed_actions else active.allowed_actions[:],
                safe_steps_limit=active.safe_steps_limit,
                retry_limit=active.retry_limit,
                mode="complete",
                completion_reason=completion_reason,
                completion_explanation=completion_explanation[:240],
                lineage_id=active.lineage_id or active.intent_id,
                user_visible_note=active.user_visible_note,
                step_count=active.step_count,
                retry_count=active.retry_count,
                hard_limit_hit_count=active.hard_limit_hit_count,
                user_step_extension=active.user_step_extension,
                user_one_shot_steps_remaining=active.user_one_shot_steps_remaining,
                user_unlimited_override=active.user_unlimited_override,
                force_plaintext_completion=active.force_plaintext_completion,
                action_constraints=dict(active.action_constraints or {}),
                blocked_action_signatures=set(active.blocked_action_signatures or set()),
                blocked_action_reasons=dict(active.blocked_action_reasons or {}),
                canonical_goal=active.canonical_goal or active.goal,
                goal_frozen=active.goal_frozen,
            ), None

        intent_type = str(payload.get("intent_type") or "").strip().upper()
        goal = str(payload.get("goal") or "").strip()
        user_visible_note = str(payload.get("user_visible_note") or payload.get("chat_note") or "").strip()
        switch_reason = self._normalize_transition_reason(payload.get("switch_reason"))
        switch_explanation = str(payload.get("switch_explanation") or "").strip()

        if not intent_id:
            return None, "intent_id_required"
        if intent_type not in self.SUPPORTED_TYPES:
            return None, "unsupported_intent_type"
        if not goal:
            return None, "intent_goal_required"
        if not self._goal_has_meaningful_shape(goal):
            return None, "intent_goal_too_local_or_underspecified"

        raw_allowed = payload.get("allowed_actions")
        if not isinstance(raw_allowed, list) or not raw_allowed:
            return None, "intent_allowed_actions_required"
        allowed_actions = []
        for item in raw_allowed:
            action = str(item or "").strip()
            if action in KNOWN_TOOL_ACTIONS and action not in allowed_actions:
                allowed_actions.append(action)
        allowed_actions = self._normalize_allowed_actions_for_intent_type(
            intent_type,
            allowed_actions,
        )
        if not allowed_actions:
            return None, "intent_allowed_actions_empty"

        if active is not None and mode in {"activate", "replace"} and not self._is_legitimate_switch_reason(switch_reason):
            if self._same_lineage(IntentContract(intent_id=intent_id, intent_type=intent_type, goal=goal[:240], allowed_actions=allowed_actions[:], original_allowed_actions=allowed_actions[:], safe_steps_limit=1, retry_limit=1)):
                return None, "intent_switch_reason_required"

        try:
            safe_steps_limit = int(payload.get("safe_steps_limit", getattr(self.config, "INTENT_DEFAULT_SAFE_STEPS", 4)))
            retry_limit = int(payload.get("retry_limit", getattr(self.config, "INTENT_DEFAULT_RETRY_LIMIT", 2)))
        except Exception:
            return None, "intent_limits_invalid"

        safe_steps_limit = max(1, min(safe_steps_limit, int(getattr(self.config, "INTENT_MAX_SAFE_STEPS", 8))))
        retry_limit = max(1, min(retry_limit, int(getattr(self.config, "INTENT_MAX_RETRY_LIMIT", 4))))
        action_constraints = self._normalize_constraints(payload.get("action_constraints"))

        return IntentContract(
            intent_id=intent_id,
            intent_type=intent_type,
            goal=goal[:240],
            canonical_goal=goal[:240],
            goal_frozen=True,
            allowed_actions=allowed_actions[:],
            original_allowed_actions=allowed_actions[:],
            safe_steps_limit=safe_steps_limit,
            retry_limit=retry_limit,
            mode=mode,
            switch_reason=switch_reason,
            switch_explanation=switch_explanation[:240],
            lineage_id=intent_id,
            user_visible_note=user_visible_note[:240],
            action_constraints=action_constraints,
        ), None

    def apply_payload(self, payload: dict) -> tuple[bool, str]:
        contract, info, error = self.inspect_transition(payload)
        if error:
            return False, error

        self.last_apply_warning = ""
        self.last_transition_info = {}

        policy_ctx = self._build_policy_context(contract, info)
        decision = self.policy_engine.evaluate_transition(policy_ctx)
        if not decision.allowed:
            self.last_transition_info = {
                "transition": "policy_rejected",
                "reason": decision.reason,
                "error_code": decision.error_code,
                "message_key": decision.message_key,
                "metadata": dict(decision.metadata or {}),
                "same_lineage": bool((info or {}).get("same_lineage")),
            }
            return False, decision.reason

        active = self.active_intent
        same_lineage = bool((info or {}).get("same_lineage"))

        if contract.mode == "complete":
            if active is None:
                return False, "intent_complete_without_active_intent"
            if contract.intent_id != active.intent_id:
                return False, "intent_complete_wrong_active_id"
            self.last_transition_info = {
                "transition": "intent_completed",
                "same_lineage": True,
                "completion_reason": contract.completion_reason,
                "completion_explanation": contract.completion_explanation,
                "completed_intent_id": active.intent_id,
                "completed_goal": active.goal,
                "policy_message_key": decision.message_key,
            }
            self.active_intent = None
            self.clear_requirement()
            return True, "intent_completed"

        if active is not None and active.action_constraints.get("forbid_new_intent") and same_lineage:
            if contract.mode in {"activate", "replace"} and contract.intent_id != active.intent_id:
                if not self._is_legitimate_switch_reason(contract.switch_reason):
                    return False, "intent_new_block_forbidden_for_current_lineage"

        if contract.mode == "retry":
            if active is None:
                return False, "intent_retry_without_active_intent"

            if not self._reuse_retry_on_same_subtask(contract):
                self.last_apply_warning = "intent_retry_degraded_to_replace"
                contract.mode = "replace"
            else:
                canonical_goal = active.canonical_goal or active.goal
                active.retry_count += 1
                active.intent_type = contract.intent_type
                active.goal = canonical_goal
                active.allowed_actions = contract.allowed_actions[:]
                active.original_allowed_actions = contract.original_allowed_actions[:]
                active.safe_steps_limit = contract.safe_steps_limit
                active.retry_limit = contract.retry_limit
                active.user_visible_note = contract.user_visible_note
                active.lineage_id = active.lineage_id or active.intent_id
                active.step_count = 0
                active.force_plaintext_completion = False
                active.switch_reason = contract.switch_reason
                active.switch_explanation = contract.switch_explanation
                active.action_constraints = self._merge_constraints(active.action_constraints, contract.action_constraints)
                active.blocked_action_signatures = set(active.blocked_action_signatures or set())
                active.blocked_action_reasons = dict(active.blocked_action_reasons or {})
                active.canonical_goal = active.canonical_goal or canonical_goal
                active.goal_frozen = True
                self.clear_requirement()
                self.last_transition_info = {
                    "transition": "intent_retried",
                    "same_lineage": True,
                    "switch_reason": contract.switch_reason,
                    "policy_message_key": decision.message_key,
                }
                if active.retry_count > active.retry_limit:
                    return False, "intent_retry_limit_exceeded"
                return True, "intent_retried"

        if active is not None and not self._reason_allows_transition(contract, active, same_lineage):
            return False, "intent_transition_trigger_required"

        if contract.mode == "replace" or active is None or contract.intent_id != getattr(active, "intent_id", ""):
            if active is not None and same_lineage:
                contract.lineage_id = active.lineage_id or active.intent_id
                contract.retry_count = min(active.retry_count, contract.retry_limit)
                contract.hard_limit_hit_count = active.hard_limit_hit_count
                contract.canonical_goal = active.canonical_goal or active.goal
                contract.goal_frozen = True
                contract.goal = active.goal
                contract.user_step_extension = active.user_step_extension
                contract.user_one_shot_steps_remaining = active.user_one_shot_steps_remaining
                contract.user_unlimited_override = active.user_unlimited_override
                contract.force_plaintext_completion = active.force_plaintext_completion
                contract.action_constraints = self._merge_constraints(active.action_constraints, contract.action_constraints)
                contract.blocked_action_signatures = set(active.blocked_action_signatures or set())
                contract.blocked_action_reasons = dict(active.blocked_action_reasons or {})
                if bool(getattr(self.config, "INTENT_RELABEL_PRESERVE_STEPS_ON_REFRESH", True)):
                    contract.step_count = min(active.step_count, contract.safe_steps_limit + max(0, contract.user_step_extension))
                self.last_transition_info = {
                    "transition": "intent_replaced",
                    "same_lineage": True,
                    "switch_reason": contract.switch_reason,
                    "policy_message_key": decision.message_key,
                }
            else:
                contract.lineage_id = contract.intent_id
                self.last_transition_info = {
                    "transition": "intent_activated",
                    "same_lineage": False,
                    "switch_reason": contract.switch_reason,
                    "policy_message_key": decision.message_key,
                }
            self.active_intent = contract
            self.clear_requirement()
            return True, self.last_transition_info["transition"]

        contract.retry_count = active.retry_count
        contract.lineage_id = active.lineage_id or active.intent_id
        contract.user_visible_note = contract.user_visible_note or active.user_visible_note
        if same_lineage:
            contract.canonical_goal = active.canonical_goal or active.goal
            contract.goal_frozen = True
            contract.goal = active.goal
            contract.hard_limit_hit_count = active.hard_limit_hit_count
            contract.user_step_extension = active.user_step_extension
            contract.user_one_shot_steps_remaining = active.user_one_shot_steps_remaining
            contract.user_unlimited_override = active.user_unlimited_override
            contract.force_plaintext_completion = active.force_plaintext_completion
            contract.action_constraints = self._merge_constraints(active.action_constraints, contract.action_constraints)
            contract.original_allowed_actions = active.original_allowed_actions[:] if active.original_allowed_actions else contract.original_allowed_actions[:]
            contract.blocked_action_signatures = set(active.blocked_action_signatures or set())
            contract.blocked_action_reasons = dict(active.blocked_action_reasons or {})
        if bool(getattr(self.config, "INTENT_RELABEL_PRESERVE_STEPS_ON_REFRESH", True)) and same_lineage:
            contract.step_count = min(active.step_count, contract.safe_steps_limit + max(0, contract.user_step_extension))
        self.active_intent = contract
        self.clear_requirement()
        self.last_transition_info = {
            "transition": "intent_refreshed",
            "same_lineage": same_lineage,
            "switch_reason": contract.switch_reason,
            "policy_message_key": decision.message_key,
        }
        return True, "intent_refreshed"

    def _apply_allowed_action_updates(self, normalized: dict) -> None:
        if self.active_intent is None:
            return

        current = list(self.active_intent.allowed_actions or [])
        if not current:
            current = list(self.active_intent.original_allowed_actions or [])

        replacement = normalized.get("replace_allowed_actions")
        if replacement:
            current = list(replacement)

        remove = set(normalized.get("remove_allowed_actions") or [])
        if remove:
            current = [a for a in current if a not in remove]

        add = normalized.get("add_allowed_actions") or []
        for action in add:
            if action not in current:
                current.append(action)

        # Keep ordering stable and valid.
        cleaned = []
        for action in current:
            if action in KNOWN_TOOL_ACTIONS and action not in cleaned:
                cleaned.append(action)

        if cleaned:
            self.active_intent.allowed_actions = cleaned

    def apply_constraint_updates(self, updates: dict | None) -> bool:
        if self.active_intent is None or not isinstance(updates, dict):
            return False
        normalized = self._normalize_constraints(updates)
        self.active_intent.action_constraints = self._merge_constraints(
            self.active_intent.action_constraints,
            normalized,
        )
        self._apply_allowed_action_updates(normalized)

        # Sensible default: if a path now requires chunking, full read_file should disappear
        # from effective allowed actions unless caller explicitly kept it via replace/add rules.
        require_chunk_paths = self.active_intent.action_constraints.get("require_chunk_for_paths") or []
        if require_chunk_paths and "replace_allowed_actions" not in normalized:
            if "read_file" in self.active_intent.allowed_actions:
                self.active_intent.allowed_actions = [
                    a for a in self.active_intent.allowed_actions if a != "read_file"
                ]
            for safe_action in ("read_chunk", "read_file_skeleton", "search_content", "search_files", "run_shell"):
                if safe_action in KNOWN_TOOL_ACTIONS and safe_action not in self.active_intent.allowed_actions:
                    self.active_intent.allowed_actions.append(safe_action)
        return True

    def _effective_nominal_limit(self) -> int:
        if self.active_intent is None:
            return 0
        return int(self.active_intent.safe_steps_limit) + max(0, int(self.active_intent.user_step_extension))

    def _effective_hard_limit(self) -> int:
        allowance = int(getattr(self.config, "INTENT_COMPLETION_ALLOWANCE", 1))
        return self._effective_nominal_limit() + max(0, allowance)

    def can_continue_current_intent_after_failure(self) -> bool:
        if self.active_intent is None:
            return False
        if self.active_intent.user_unlimited_override:
            return True
        return self.active_intent.step_count < self._effective_nominal_limit()

    def can_soft_continue_after_step_limit(self) -> bool:
        if self.active_intent is None:
            return False
        if self.active_intent.user_unlimited_override:
            return True
        return self.active_intent.step_count < self._effective_hard_limit()

    def grant_two_more_steps(self) -> bool:
        if self.active_intent is None:
            return False
        grant = max(1, int(getattr(self.config, "INTENT_USER_ONE_SHOT_STEPS", 2)))
        self.active_intent.user_step_extension += grant
        self.active_intent.force_plaintext_completion = False
        return True

    def grant_user_approved_step_budget(self, extra_steps: int | None = None) -> bool:
        if self.active_intent is None:
            return False
        if extra_steps is None:
            extra_steps = int(getattr(self.config, "INTENT_USER_ONE_SHOT_STEPS", 2))
        self.active_intent.user_step_extension += max(1, int(extra_steps))
        self.active_intent.force_plaintext_completion = False
        return True

    def extend_current_intent_limit(self, extra_steps: int | None = None) -> bool:
        if self.active_intent is None:
            return False
        if extra_steps is None:
            extra_steps = int(getattr(self.config, "INTENT_USER_EXTENSION_STEPS", 4))
        self.active_intent.user_step_extension += max(1, int(extra_steps))
        self.active_intent.force_plaintext_completion = False
        return True

    def enable_unlimited_for_current_intent(self) -> bool:
        if self.active_intent is None:
            return False
        if not bool(getattr(self.config, "INTENT_ALLOW_UNLIMITED_OVERRIDE", True)):
            return False
        # Kept only for backward compatibility. The preferred hard-limit flow is
        # explicit user approval of a small additional step budget.
        self.active_intent.user_unlimited_override = True
        self.active_intent.force_plaintext_completion = False
        return True

    def force_current_intent_completion(self) -> bool:
        if self.active_intent is None:
            return False
        self.active_intent.force_plaintext_completion = True
        return True

    def pre_action_check(self, command: dict) -> dict | None:
        if self.active_intent is None:
            return None
        if self.active_intent.force_plaintext_completion:
            return {
                "reason": "intent_force_plaintext_completion",
                "recoverable": True,
                "error_code": "INTENT_FORCE_PLAINTEXT_COMPLETION",
                "next_actions": [],
                "intent_allowed_actions": [],
                "next_actions_source": "intent",
                "policy_allowed_actions": [],
                "policy_recommended_actions": [],
                "policy_blocked_actions": list(self.active_intent.allowed_actions[:]),
                "policy_intent_actions": [],
                "policy_authoritative_source": "intent",
                "policy_keep_current_intent": True,
                "command": command.copy(),
                "message": (
                    "User requested final answer from already gathered evidence. "
                    "Do not use more tools under this intent now."
                ),
            }

        if self.is_action_blocked_for_current_intent(command):
            blocked_reason = self.get_blocked_action_reason(command) or "blocked_for_current_intent"
            decision = self.policy_engine.evaluate_blocked_action(
                BlockedActionPolicyContext(
                    active_intent=self.active_intent,
                    command=command.copy(),
                    blocked_reason=blocked_reason,
                )
            )
            return {
                "reason": decision.reason,
                "recoverable": decision.recoverable,
                "error_code": decision.error_code,
                "next_actions": list(decision.next_actions or []),
                "intent_allowed_actions": list(decision.next_actions or []),
                "next_actions_source": "intent",
                "policy_allowed_actions": list(decision.next_actions or []),
                "policy_recommended_actions": [],
                "policy_blocked_actions": [],
                "policy_intent_actions": list(decision.next_actions or []),
                "policy_authoritative_source": "intent",
                "policy_keep_current_intent": True,
                "command": command.copy(),
                "message": (
                    "This exact action shape is blocked for the current intent. "
                    "The current intent is still valid. "
                    "Do not retry the same action with cosmetic changes. "
                    "Choose a materially different allowed action."
                ),
                "message_key": decision.message_key,
                "policy_metadata": dict(decision.metadata or {}),
            }

        cmd_type = command.get("type") or command.get("action") or "unknown"
        if cmd_type not in self.active_intent.allowed_actions:
            return {
                "reason": "intent_action_not_allowed",
                "recoverable": True,
                "error_code": "INTENT_ACTION_NOT_ALLOWED",
                "next_actions": self.active_intent.allowed_actions[:],
                "intent_allowed_actions": self.active_intent.allowed_actions[:],
                "next_actions_source": "intent",
                "policy_allowed_actions": self.active_intent.allowed_actions[:],
                "policy_recommended_actions": [],
                "policy_blocked_actions": [cmd_type],
                "policy_intent_actions": self.active_intent.allowed_actions[:],
                "policy_authoritative_source": "intent",
                "policy_keep_current_intent": True,
                "command": command.copy(),
            }

        constraints = self.active_intent.action_constraints or {}
        path = str(command.get("path") or "").strip()
        if cmd_type == "read_file":
            require_chunk_for_paths = {
                str(p).strip() for p in constraints.get("require_chunk_for_paths", []) if str(p).strip()
            }
            forbid_same_full_read_path = str(constraints.get("forbid_same_full_read_path") or "").strip()
            is_chunked = command.get("start_byte") is not None or command.get("end_byte") is not None

            if path and path in require_chunk_for_paths and not is_chunked:
                next_actions = [a for a in self.active_intent.allowed_actions if a != "read_file"]
                if "read_chunk" not in next_actions:
                    next_actions.insert(0, "read_chunk")
                return {
                    "reason": "intent_requires_chunk_for_path",
                    "recoverable": True,
                    "error_code": "INTENT_REQUIRES_CHUNK_FOR_PATH",
                    "next_actions": next_actions,
                    "intent_allowed_actions": next_actions,
                    "next_actions_source": "intent",
                    "policy_allowed_actions": next_actions,
                    "policy_recommended_actions": [],
                    "policy_blocked_actions": ["read_file"],
                    "policy_intent_actions": next_actions,
                    "policy_authoritative_source": "intent",
                    "policy_keep_current_intent": True,
                    "command": command.copy(),
                    "message": (
                        "This file may not be read with full read_file under the current intent. "
                        "Use read_chunk, read_file_skeleton, search_content/search_files, or run_shell with rg/fd."
                    ),
                }

            if path and forbid_same_full_read_path and path == forbid_same_full_read_path and not is_chunked:
                next_actions = [a for a in self.active_intent.allowed_actions if a != "read_file"]
                if "read_chunk" not in next_actions:
                    next_actions.insert(0, "read_chunk")
                return {
                    "reason": "intent_forbid_same_full_read_path",
                    "recoverable": True,
                    "error_code": "INTENT_FORBID_SAME_FULL_READ_PATH",
                    "next_actions": next_actions,
                    "intent_allowed_actions": next_actions,
                    "next_actions_source": "intent",
                    "policy_allowed_actions": next_actions,
                    "policy_recommended_actions": [],
                    "policy_blocked_actions": ["read_file"],
                    "policy_intent_actions": next_actions,
                    "policy_authoritative_source": "intent",
                    "policy_keep_current_intent": True,
                    "command": command.copy(),
                    "message": (
                        "Do not repeat the same full read_file action for this path. "
                        "Use read_chunk, read_file_skeleton, search_content/search_files, or run_shell with rg/fd."
                    ),
                }
        return None

    def note_action(self, command: dict) -> dict | None:
        if self.active_intent is None:
            return None
        self.active_intent.step_count += 1

        if self.active_intent.user_unlimited_override:
            return None

        limit = self._effective_nominal_limit()
        hard_limit = self._effective_hard_limit()

        if self.active_intent.step_count > hard_limit:
            if self.active_intent.user_one_shot_steps_remaining > 0:
                self.active_intent.user_one_shot_steps_remaining -= 1
                return None

            self.active_intent.hard_limit_hit_count += 1
            repeated = self.active_intent.hard_limit_hit_count > 1
            return {
                "reason": "intent_step_limit_exceeded_repeated" if repeated else "intent_step_limit_exceeded",
                "recoverable": True,
                "error_code": "INTENT_STEP_LIMIT_EXCEEDED_REPEATED" if repeated else "INTENT_STEP_LIMIT_EXCEEDED",
                "next_actions": self.active_intent.allowed_actions[:],
                "intent_allowed_actions": self.active_intent.allowed_actions[:],
                "next_actions_source": "intent",
                "policy_allowed_actions": self.active_intent.allowed_actions[:],
                "policy_recommended_actions": [],
                "policy_blocked_actions": [],
                "policy_intent_actions": self.active_intent.allowed_actions[:],
                "policy_authoritative_source": "intent",
                "policy_keep_current_intent": True,
                "message": (
                    "Current intent exceeded its hard step limit repeatedly for the same lineage. "
                    "Hand off the decision to the user: approve more steps, or stop and answer from current evidence."
                    if repeated else
                    "Current intent exceeded its hard step limit. "
                    "Do not continue automatically. Hand off the decision to the user: approve more steps, or stop and answer from current evidence."
                ),
                "command": command.copy(),
            }

        if self.active_intent.step_count > limit:
            return {
                "reason": "intent_step_limit_soft_exceeded",
                "recoverable": True,
                "error_code": "INTENT_STEP_LIMIT_SOFT_EXCEEDED",
                "next_actions": self.active_intent.allowed_actions[:],
                "intent_allowed_actions": self.active_intent.allowed_actions[:],
                "next_actions_source": "intent",
                "policy_allowed_actions": self.active_intent.allowed_actions[:],
                "policy_recommended_actions": [],
                "policy_blocked_actions": [],
                "policy_intent_actions": self.active_intent.allowed_actions[:],
                "policy_authoritative_source": "intent",
                "policy_keep_current_intent": True,
                "message": (
                    "Current intent reached its nominal step limit. "
                    "Prefer one final allowed action or a plain-text conclusion. "
                    "Do not refresh/relabel the same intent unless strategy materially changes."
                ),
                "command": command.copy(),
            }

        return None

    def summary(self) -> str:
        if self.active_intent is None:
            return ""
        i = self.active_intent
        constraints = i.action_constraints or {}
        constraint_bits = []
        if constraints.get("max_full_reads_per_step") is not None:
            constraint_bits.append(f"max_full_reads={constraints.get('max_full_reads_per_step')}")
        if constraints.get("forbid_same_full_read_path"):
            constraint_bits.append("forbid_same_full_read_path=set")
        if constraints.get("require_chunk_for_paths"):
            constraint_bits.append(f"require_chunk_paths={len(constraints.get('require_chunk_for_paths') or [])}")
        if constraints.get("forbid_new_intent"):
            constraint_bits.append("forbid_new_intent=true")
        if constraints.get("reuse_current_intent"):
            constraint_bits.append("reuse_current_intent=true")
        constraints_summary = (", constraints=" + ";".join(constraint_bits)) if constraint_bits else ""
        return (
            f"intent_id={i.intent_id}, type={i.intent_type}, "
            f"steps={i.step_count}/{i.safe_steps_limit}, retries={i.retry_count}/{i.retry_limit}, "
            f"allowed={','.join(i.allowed_actions)}{constraints_summary}"
        )
