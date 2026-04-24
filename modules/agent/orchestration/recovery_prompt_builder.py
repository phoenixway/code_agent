"""Recovery/reuse prompt builder for orchestration."""

from __future__ import annotations

from .prompt_builder_shared import PromptBuilderSharedMixin


class RecoveryPromptBuilder(PromptBuilderSharedMixin):
    def __init__(self, agent):
        self._init_prompt_builder_shared(agent)

    def build_intent_required_prompt(self, reason: str, allowed_actions: list[str] | None = None) -> str:
        next_hint = ""
        if allowed_actions:
            next_hint = f"\nAllowed actions for the next intent contract: {', '.join(allowed_actions)}."
        universe = self._intent_universe()
        active_intent = self._current_active_intent()
        if not universe.has_active_contract or active_intent is None:
            return (
                "SYSTEM: A formal intent contract is required before further tool use.\n"
                f"Reason: {reason}.{next_hint}\n"
                "There is currently NO active accepted intent contract for this work.\n"
                "Continue from already gathered evidence. Do not restart the task from zero.\n"
                "Return EXACTLY ONE <intent> JSON block first.\n"
                "Until activation succeeds, do not assume contract-scoped permissions or allowed_actions.\n"
                "Optional schema fields:\n"
                "- intent_id\n- intent_type\n- goal\n- allowed_actions\n- safe_steps_limit\n- retry_limit\n- mode\n"
                "If you also need an action now, place the <intent> block before the action."
            )
        return (
            "SYSTEM: A formal intent transition/update is required before further tool use.\n"
            f"Reason: {reason}.{next_hint}\n"
            "A formal runtime intent contract is already relevant for this work.\n"
            "Return the required <intent> block first, then the next valid step if needed."
        )

    def build_invalid_intent_contract_prompt(self, reason: str, allowed_actions: list[str] | None = None) -> str:
        next_hint = ""
        if allowed_actions:
            next_hint = f"\nAllowed actions for the next intent contract: {', '.join(allowed_actions)}."
        return (
            "SYSTEM: Your last <intent> block was syntactically invalid and was not accepted by runtime.\n"
            f"Reason: {reason}.{next_hint}\n"
            "There is still NO active accepted intent contract unless runtime explicitly says otherwise.\n"
            "Continue from already gathered evidence. Do not restart from zero.\n"
            "Return EXACTLY ONE corrected <intent> JSON block now.\n"
            "Do not return a bare <action> before the corrected <intent> is accepted."
        )

    def build_reuse_current_intent_prompt(self, reason: str, allowed_actions: list[str] | None = None, *, goal: str | None = None) -> str:
        next_hint = f"\nAllowed actions under the CURRENT intent contract: {', '.join(allowed_actions)}." if allowed_actions else ""
        goal_hint = f"\nCurrent contract goal remains the same: {goal.strip()}." if isinstance(goal, str) and goal.strip() else ""
        return (
            "SYSTEM: Continue under the current intent contract.\n"
            f"Reason: {reason}.{next_hint}{goal_hint}\n"
            "The current runtime contract remains active for this same user-facing goal.\n"
            "Do not reactivate, replace, relabel, or restart this work without a valid runtime reason.\n"
            "Do not repeat the blocked or low-value action pattern.\n"
            "Priority now is to finish this work quickly from the strongest current evidence.\n"
            "Continue from the strongest valid state already reached under the same contract.\n"
            "Do not reopen exploration just because continuation is allowed.\n"
            "Return the next valid output, or complete the intent and answer now if current evidence is already sufficient."
        )

    def build_limit_aware_reuse_prompt(self, reason: str, allowed_actions: list[str] | None = None, *, goal: str | None = None, requested_steps: int | None = None) -> str:
        active_intent = self._current_active_intent()
        intent_id = str(getattr(active_intent, "intent_id", "") or "").strip() if active_intent is not None else ""
        intent_type = str(getattr(active_intent, "intent_type", "") or "").strip().upper() if active_intent is not None else ""
        if requested_steps is None:
            requested_steps = int(getattr(self.config, "INTENT_REUSE_EXTENSION_STEPS", 4) or 4)
        next_hint = f"\nAllowed actions under the CURRENT intent contract: {', '.join(allowed_actions)}." if allowed_actions else ""
        goal_hint = f"\nCurrent contract goal remains the same: {goal.strip()}." if isinstance(goal, str) and goal.strip() else ""
        return (
            "SYSTEM: The current intent contract still matches the user's goal, but its step budget is exhausted or near exhaustion.\n"
            f"Reason: {reason}.{next_hint}{goal_hint}\n"
            "Do NOT silently continue under the exhausted budget.\n"
            "Do NOT activate a fresh unrelated intent for the same goal.\n"
            "Return EXACTLY ONE <intent> JSON block with mode=\"reuse\" for the SAME active intent_id to request refreshed steps for this same intent lineage.\n"
            f"Use requested_steps={max(1, int(requested_steps))}.\n"
            f"Keep intent_id={intent_id or '<active_intent_id>'} and intent_type={intent_type or '<active_intent_type>'}.\n"
            "Use switch_reason=\"current_intent_exhausted\" unless runtime explicitly indicates a different legitimate continuation reason.\n"
            "Do not emit an <action> in the same reply.\n"
            "Do not change the goal text. Reuse is for same goal + same lineage + refreshed budget."
        )

    def build_repeated_thinking_without_valid_output_prompt(self, stop_info: dict | None = None) -> str:
        reason = str((stop_info or {}).get("reason") or "repeated_thinking_without_valid_output").strip()
        return (
            "SYSTEM: Enough internal planning/thinking for now.\n"
            f"Reason: {reason}.\n"
            "Your recent replies contained substantial <think> content, but did not produce a valid executable or final output.\n"
            "The NEXT reply must be immediately valid.\n"
            "Valid outputs now are:\n"
            "- one valid <action>\n"
            "- one valid read-only batch of tool calls if batching is allowed\n"
            "- one plain-text final answer\n"
            "- one valid <intent> request/transition if runtime truly requires it\n"
            "- or a valid combination of thinking plus memory tags plus one of the allowed outputs above\n"
            "Do NOT return another planning/thinking-only reply.\n"
            "Do NOT restate the next step without performing it.\n"
            "Return a valid output now."
        )

    def build_keep_current_intent_recovery_prompt(self, stop_info: dict | None) -> str:
        ctx = self._recovery_context(stop_info)
        stop_info = ctx.to_stop_info()
        reason = ctx.reason.strip()
        allowed_actions = self._current_intent_allowed_actions()
        goal = self._current_intent_goal()
        next_hint = f"\nAllowed actions under the CURRENT intent contract: {', '.join(allowed_actions)}." if allowed_actions else ""

        message_defaults = {
            "intent_step_limit_soft_exceeded": "Continue under the current intent contract.",
            "user_approved_more_steps_after_hard_limit": "Continue under the current intent contract.",
            "intent_blocked_action_signature": "A specific action is blocked, but the current intent contract is still valid.",
            "action_not_allowed_in_phase": "The current intent contract remains valid, but a legacy recovery suggestion conflicted with it.",
            "retry_or_continuation_after_failure": "The previous step failed, but the current intent contract still remains valid.",
            "unnecessary_intent_reactivation_or_replace": "The active intent contract is already present and remains active.",
            "suspect_intent_relabel_repeat": "The current intent contract is still valid.",
        }
        message_keys = {
            "intent_step_limit_soft_exceeded": "keep_current_intent_soft_limit",
            "user_approved_more_steps_after_hard_limit": "keep_current_intent_after_user_more_steps",
            "intent_blocked_action_signature": stop_info.get("message_key") or "blocked_action_keep_current_intent",
            "action_not_allowed_in_phase": "keep_current_intent_conflicting_phase_actions",
            "retry_or_continuation_after_failure": stop_info.get("message_key") or "blocked_action_keep_current_intent",
            "unnecessary_intent_reactivation_or_replace": stop_info.get("message_key") or "unnecessary_intent_reactivation_or_replace",
            "suspect_intent_relabel_repeat": stop_info.get("message_key") or "suspect_intent_relabel_repeat",
        }
        header = self._render_recovery_message(
            message_keys.get(reason, "blocked_action_keep_current_intent"),
            message_defaults.get(reason, "Continue under the current intent contract."),
            next_hint=next_hint,
        )

        base_lines = [f"SYSTEM: {header}" if not header.startswith("SYSTEM:") else header, f"Reason: {reason}."]
        if allowed_actions:
            base_lines.append(f"Allowed actions under the CURRENT intent contract: {', '.join(allowed_actions)}.")
        if goal:
            base_lines.append(f"Current contract goal remains the same: {goal}.")
        base_lines.extend([
            "The current intent contract remains valid and its goal remains the same.",
            "Intent here means the formal runtime contract for the current user-facing goal and allowed actions, not a new local intention or next micro-step.",
            "Priority now is to finish quickly from the strongest evidence already gathered.",
            "Continue from the strongest valid state already reached under the same contract.",
            "Do not restart the task from the beginning unless a concrete missing detail is identified or runtime explicitly changes the contract.",
            "Do not repeat already completed investigation.",
            "Do not reopen exploration just because continuation is allowed.",
            "Do not keep the intent open if the goal is already answerable.",
            "Do not repeat the action pattern that was just blocked or low-value.",
        ])
        return "\n".join(base_lines)

    def build_no_active_intent_recovery_prompt(self, stop_info: dict | None) -> str:
        ctx = self._recovery_context(stop_info)
        stop_info = ctx.to_stop_info()
        reason = ctx.reason.strip()
        required = stop_info.get("next_actions") or []
        source = str(ctx.next_actions_source or "").strip().lower()
        if source == "recommended" and required:
            required_hint = f"Runtime-suggested next actions: {', '.join(required)}.\nThese are recovery hints, not proof that contract-scoped tool use is already allowed."
        else:
            required_hint = f"Allowed next actions: {', '.join(required)}." if required else "Allowed next actions: none."
        return (
            "SYSTEM: No active intent contract is currently in force.\n"
            f"Reason: {reason}.\n"
            f"{required_hint}\n"
            "Continue from already gathered evidence and conclusions. Do not restart the task from zero.\n"
            "If the next step needs governed multi-step execution, activate a formal <intent> now.\n"
            "Until activation succeeds, do not assume contract-scoped permissions or allowed_actions.\n"
            "If current evidence is already sufficient, return a plain-text answer instead of more tool use.\n"
            "Return the next valid step accordingly."
        )

    def build_suspect_intent_change_message(self, stop_info: dict | None) -> str:
        ctx = self._recovery_context(stop_info)
        suspicion = ctx.suspicion or {}
        old_goal = str(suspicion.get("old_goal") or "")
        new_goal = str(suspicion.get("new_goal") or "")
        reason = ctx.reason or "suspect_intent_relabel_repeat"
        parts = [
            "Модель підозріло змінила поточний intent contract у межах тієї самої лінії роботи.",
            f"Причина: {reason}.",
        ]
        if old_goal:
            parts.append(f"Стара ціль контракту: {old_goal}")
        if new_goal:
            parts.append(f"Нова ціль контракту: {new_goal}")
        parts.extend([
            "Обери один із варіантів:",
            "- Keep original goal: змусити модель триматися попередньої цілі контракту.",
            "- Allow changed goal: дозволити нову ціль один раз.",
            "- Stop and answer from current evidence: зупинити tool use і відповісти з уже зібраного.",
        ])
        return "\n".join(parts)

    def build_suspect_intent_change_confirmation_suffix(self) -> str:
        return "\nТак = Allow changed goal. Ні = Keep original goal."

    def build_intent_overrun_confirmation_suffix(self) -> str:
        return "\nТак = Approve more steps. Ні = Stop and answer from current evidence."

    def build_action_format_recovery_prompt(
        self,
        header: str,
        *,
        forbid_audit_markers: bool = False,
        state_changing_only: bool = False,
        single_readonly_action_only: bool = False,
    ) -> str:
        lines = [f"SYSTEM: {header}", "Return the next valid output for the next step."]
        if state_changing_only:
            lines.extend([
                "For this recovery step, prefer exactly one valid state-changing <action> if tool use is still needed.",
                "Do not return read-only batching here.",
                "If no tool is needed, return a plain-text answer.",
            ])
        elif single_readonly_action_only:
            lines.extend([
                "For this recovery step, prefer exactly one valid read-only <action> if tool use is still needed.",
                "Do not return a batch.",
                "Do not return multiple <action> blocks.",
                "Make the next search/action narrower and more targeted than before.",
                "If no tool is needed or current evidence is already sufficient, return a plain-text answer instead.",
            ])
        else:
            lines.extend([
                "For read-only investigation, multiple separate <action>...</action> blocks are allowed.",
                "Compatible format: one <action>...</action> block may contain a JSON array of read-only action objects.",
                "For any state-changing step, return only one valid <action>.",
                "Do not use JSON arrays for state-changing actions.",
                "If no tool is needed, return a plain-text answer.",
            ])
        lines.extend([
            "No prose outside <action> when returning an <action> block.",
            "If you return plain text instead, do not include any <action> block.",
            "If unsure, prefer one simple valid next step.",
        ])
        if forbid_audit_markers:
            lines.append("Do not output audit/history markers such as SYSTEM_TOOL_AUDIT or <previously_performed_action>.")
        return "\n".join(lines)

    def typed_recovery_header(self, stop_info: dict | None) -> str:
        return self._typed_recovery_header_default(stop_info)

    def build_typed_stop_recovery_prompt(self, stop_info: dict | None) -> str:
        ctx = self._recovery_context(stop_info)
        stop_info = ctx.to_stop_info()
        reason = ctx.reason.strip()
        state_changing_only = reason in {"repeating_failure", "repeating_no_progress", "observe_budget_exhausted"}
        single_readonly_action_only = reason in {
            "too_broad_search",
            "low_value_broad_search_repeat",
            "history_self_reference_hit",
            "search_batch_aborted_after_first_action",
            "planned_turn_working_material_too_large",
            "planned_full_read_too_large",
            "intent_blocked_action_signature",
        }
        prompt = self.build_action_format_recovery_prompt(
            self.typed_recovery_header(stop_info),
            forbid_audit_markers=True,
            state_changing_only=state_changing_only,
            single_readonly_action_only=single_readonly_action_only,
        )
        if reason in {"planned_turn_working_material_too_large", "planned_full_read_too_large", "intent_blocked_action_signature"}:
            active_intent = getattr(self.state, "active_intent", None)
            active_goal = getattr(active_intent, "goal", "") if active_intent is not None else ""
            prompt += (
                "\nDo NOT send another <intent> block now."
                f"\nCurrent contract goal remains the same: {active_goal}."
                "\nContinue under the current intent contract."
                "\nContinue toward the same goal using the updated allowed tools and constraints."
                "\nDo not repeat the blocked or low-value action pattern."
                "\nDo not restart the task from the beginning. Continue from already gathered evidence under the same contract."
                "\nReturn the next valid output under the current contract."
                "\nReturn EXACTLY ONE materially different read-only action."
                "\nUse it only if tool use is still needed."
                "\nIf current evidence is already sufficient, return a plain-text answer instead."
            )
        if single_readonly_action_only:
            prompt += "\nFor search_content, prefer explicit import patterns, narrower directories, or stronger exclude_dirs. Avoid repeating the same broad batch."
        return prompt