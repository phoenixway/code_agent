"""Recovery flow coordinator for orchestrator stop conditions."""

from __future__ import annotations

from dataclasses import dataclass

from ..intent_messages import render_intent_message


@dataclass
class StopHandlingDecision:
    handled: bool
    next_query: str | None = None
    stop_loop: bool = False
    clear_pending_stop: bool = False


class RecoveryCoordinator:
    def __init__(self, agent, prompt_builder):
        self.agent = agent
        self.ui = agent.ui
        self.state = agent.state
        self.config = agent.config
        self.prompt_builder = prompt_builder

    def inspection_can_finish_with_text(self, sm, stop_info: dict | None) -> bool:
        if sm is None:
            return False
        task_kind = getattr(sm, "task_kind", None)
        task_kind_value = getattr(task_kind, "value", str(task_kind))
        if task_kind_value not in {"INSPECTION", "HYBRID"}:
            return False
        reason = str((stop_info or {}).get("reason") or "")
        return reason in {
            "broad_recon_budget_exhausted",
            "observe_budget_exhausted",
            "inspection_task_write_blocked",
            "list_directory_budget_exhausted",
            "directory_descent_budget_exhausted",
            "root_listing_budget_exhausted",
            "action_not_allowed_in_phase",
            "intent_step_limit_soft_exceeded",
            "intent_step_limit_exceeded",
            "intent_step_limit_exceeded_repeated",
        }

    async def choose_suspect_intent_change_action(self, stop_info: dict | None) -> str:
        chooser = getattr(self.ui, "choose_suspect_intent_change_action", None)
        if callable(chooser):
            decision = await chooser(self.prompt_builder.build_suspect_intent_change_message(stop_info))
            if isinstance(decision, str) and decision:
                return decision

        fallback = getattr(self.ui, "confirm_continue", None)
        if callable(fallback):
            decision = await fallback(
                self.prompt_builder.build_suspect_intent_change_message(stop_info)
                + self.prompt_builder.build_suspect_intent_change_confirmation_suffix()
            )
            if decision in (True, "allow_changed_goal", "allow_once"):
                return "allow_changed_goal"
            if decision in (False, "keep_original_goal", None):
                return "keep_original_goal"
            if decision in ("stop", "stop_and_answer", "force_completion_answer"):
                return "stop_and_answer"
        return "keep_original_goal"

    async def choose_intent_overrun_action(self, stop_info: dict | None) -> str | None:
        chooser = getattr(self.ui, "choose_intent_overrun_action", None)
        if callable(chooser):
            return await chooser(self.prompt_builder.build_intent_overrun_message(stop_info))

        fallback = getattr(self.ui, "confirm_continue", None)
        if callable(fallback):
            decision = await fallback(
                self.prompt_builder.build_intent_overrun_message(stop_info)
                + self.prompt_builder.build_intent_overrun_confirmation_suffix()
            )
            if decision in (True, "continue", "continue_silent", "approve_more_steps"):
                return "approve_more_steps"
            if decision in (False, "stop", None, "stop_and_answer", "force_completion_answer"):
                return "stop_and_answer"
        return "stop_and_answer"

    async def handle_defect_detector_stop(self, stop_info: dict | None) -> tuple[bool, str | None]:
        stop_info = stop_info or {}
        reason = str(stop_info.get("reason") or "")

        if reason in {
            "intent_action_not_allowed",
            "intent_step_limit_soft_exceeded",
            "intent_blocked_action_signature",
            "suspect_intent_relabel_repeat",
            "suspect_intent_goal_drift",
        }:
            active_intent = getattr(self.state, "active_intent", None)
            allowed = stop_info.get("next_actions") or getattr(active_intent, "allowed_actions", None) or []
            if reason == "intent_step_limit_soft_exceeded":
                return True, (
                    self.prompt_builder.build_reuse_current_intent_prompt(
                        reason,
                        allowed,
                        goal=getattr(active_intent, "goal", ""),
                    )
                    + "\nPrefer exactly one final allowed <action>, or return a final plain-text answer if the evidence is already enough."
                )
            if reason == "intent_blocked_action_signature":
                blocked_reason = ""
                if hasattr(self.state, "get_blocked_action_reason"):
                    try:
                        blocked_reason = self.state.get_blocked_action_reason(stop_info.get("command") or {}) or ""
                    except Exception:
                        blocked_reason = ""
                note = (
                    "This exact action shape is blocked for the current intent."
                    if not blocked_reason
                    else f"This exact action shape is blocked for the current intent because of: {blocked_reason}."
                )
                base = render_intent_message(
                    stop_info.get("message_key") or "blocked_action_keep_current_intent",
                    default="A specific action is blocked, but the current intent is still valid.",
                )
                return True, (
                    f"SYSTEM: {base}\n"
                    f"Reason: {reason}.\n"
                    f"Allowed actions under the CURRENT intent: {', '.join(allowed) if allowed else 'none'}.\n"
                    f"Current intent goal remains the same: {getattr(active_intent, 'goal', '')}.\n"
                    f"{note}\n"
                    "Do NOT retry the same action with cosmetic changes.\n"
                    "Choose EXACTLY ONE materially different next <action>, or answer from current evidence if enough is already known.\n"
                    "A legitimate intent transition is not globally forbidden, but do not propose one unless the work truly changed."
                )
            if reason in {"suspect_intent_relabel_repeat", "suspect_intent_goal_drift"}:
                decision = await self.choose_suspect_intent_change_action(stop_info)
                if decision == "allow_changed_goal":
                    allow_method = (
                        getattr(self.state, "allow_pending_goal_drift_once", None)
                        if reason == "suspect_intent_goal_drift"
                        else getattr(self.state, "allow_pending_suspect_intent_once", None)
                    )
                    if callable(allow_method):
                        ok, msg = allow_method(self.config)
                        if ok:
                            self.state.add_confirmation(1)
                            return True, self.prompt_builder.build_approved_changed_goal_prompt()
                    return True, self.prompt_builder.build_intent_transition_rejected_prompt(
                        "suspect_intent_relabel_repeat",
                        allowed,
                        goal=getattr(active_intent, "goal", ""),
                    )
                if decision == "stop_and_answer":
                    runtime = getattr(self.state, "intent_runtime", None)
                    if runtime is not None and hasattr(runtime, "force_current_intent_completion"):
                        runtime.force_current_intent_completion()
                    return True, self.prompt_builder.build_plain_text_completion_prompt(
                        getattr(self.state, "state_machine", None),
                        {
                            **(stop_info or {}),
                            "reason": "user_stopped_after_suspect_goal_change",
                        },
                    )
                return True, self.prompt_builder.build_keep_original_goal_prompt(
                    reason,
                    allowed,
                    goal=getattr(active_intent, "goal", ""),
                )
            return True, self.prompt_builder.build_reuse_current_intent_prompt(
                reason,
                allowed,
                goal=getattr(active_intent, "goal", ""),
            )

        if reason in {"intent_step_limit_exceeded", "intent_step_limit_exceeded_repeated"}:
            active_intent = getattr(self.state, "active_intent", None)
            allowed = stop_info.get("next_actions") or getattr(active_intent, "allowed_actions", None) or []
            decision = await self.choose_intent_overrun_action(stop_info)
            runtime = getattr(self.state, "intent_runtime", None)

            if decision == "approve_more_steps":
                granted = False
                if runtime is not None and hasattr(runtime, "grant_two_more_steps"):
                    runtime.grant_two_more_steps()
                    granted = True
                elif runtime is not None and hasattr(runtime, "extend_current_intent_limit"):
                    runtime.extend_current_intent_limit(2)
                    granted = True

                self.state.add_confirmation(1)
                note = (
                    "User approved a small additional step budget for the CURRENT intent. Return EXACTLY ONE valid next <action> now."
                    if granted
                    else "User approved continuation for the CURRENT intent. Return EXACTLY ONE valid next <action> now."
                )
                return True, (
                    self.prompt_builder.build_reuse_current_intent_prompt(
                        "user_approved_more_steps_after_hard_limit",
                        allowed,
                        goal=getattr(active_intent, "goal", ""),
                    )
                    + f"\n{note}"
                )

            if runtime is not None and hasattr(runtime, "force_current_intent_completion"):
                runtime.force_current_intent_completion()
            return True, self.prompt_builder.build_plain_text_completion_prompt(
                getattr(self.state, "state_machine", None),
                {
                    **(stop_info or {}),
                    "reason": "user_stopped_after_hard_limit_answer_from_current_evidence",
                },
            )

        reason_map = {
            "defect_repeated_action_cycle": "Defect detector: модель повторює 3 кроки в циклі. Продовжити?",
            "defect_same_action_repeat": "Defect detector: модель кілька разів повторює одну й ту саму дію. Продовжити?",
            "intent_retry_limit_exceeded": "Defect detector: агент перевищив retry_limit поточного intent. Продовжити?",
        }
        message = reason_map.get(reason)
        if not message:
            return False, None
        decision = await self.ui.confirm_continue(message)
        if decision in (False, "stop", None):
            await self.ui.print_system("Execution stopped by defect detector.")
            return True, None
        self.state.add_confirmation(1)
        if bool(getattr(self.config, "INTENT_REQUIRE_ON_DEFECT", True)):
            self.state.require_intent(reason)
            return True, self.prompt_builder.build_intent_required_prompt(reason, stop_info.get("next_actions") or [])
        return True, self.prompt_builder.build_typed_stop_recovery_prompt(stop_info)

    async def handle_dispatch_stop(
        self,
        stop_info: dict | None,
        sm,
    ) -> StopHandlingDecision:
        handled_defect, next_query = await self.handle_defect_detector_stop(stop_info)
        if handled_defect:
            if next_query:
                return StopHandlingDecision(
                    handled=True,
                    next_query=next_query,
                    clear_pending_stop=True,
                )
            return StopHandlingDecision(
                handled=True,
                stop_loop=True,
            )

        if stop_info and stop_info.get("reason") in {"repeating_failure", "repeating_no_progress"}:
            decision = await self.ui.confirm_loop_recovery(
                "Detected repeated no-progress failures. Choose next step."
            )
            if decision == "retry_recovery":
                if sm is not None and hasattr(sm, "on_user_recovery_choice"):
                    sm.on_user_recovery_choice(decision)
                self.state.set_retry_budgets(
                    self.config.RECOVERABLE_ERROR_RETRY_BUDGET,
                    self.config.CRITICAL_ERROR_RETRY_BUDGET,
                )
                recovery_actions = stop_info.get("next_actions") or []
                return StopHandlingDecision(
                    handled=True,
                    next_query=self.prompt_builder.build_retry_recovery_query(recovery_actions),
                    clear_pending_stop=True,
                )
            if decision == "open_search":
                if sm is not None and hasattr(sm, "on_user_recovery_choice"):
                    sm.on_user_recovery_choice(decision)
                self.state.set_retry_budgets(
                    self.config.RECOVERABLE_ERROR_RETRY_BUDGET,
                    self.config.CRITICAL_ERROR_RETRY_BUDGET,
                )
                error_details = (
                    "code="
                    f"{self.state.last_error_code or 'UNSPECIFIED'}, "
                    f"msg={self.state.last_error_message or ''}"
                )
                return StopHandlingDecision(
                    handled=True,
                    next_query=self.prompt_builder.build_open_search_recovery_query(error_details),
                    clear_pending_stop=True,
                )

        if stop_info:
            if stop_info.get("reason") == "malformed_read_file_payload":
                return StopHandlingDecision(
                    handled=True,
                    next_query=self.prompt_builder.build_malformed_read_file_payload_prompt(),
                    clear_pending_stop=True,
                )

            if stop_info.get("reason") == "malformed_read_file_skeleton_payload":
                return StopHandlingDecision(
                    handled=True,
                    next_query=self.prompt_builder.build_malformed_read_file_skeleton_payload_prompt(),
                    clear_pending_stop=True,
                )

            if stop_info.get("reason") == "malformed_read_chunk_payload":
                return StopHandlingDecision(
                    handled=True,
                    next_query=self.prompt_builder.build_malformed_read_chunk_payload_prompt(),
                    clear_pending_stop=True,
                )

            if self.inspection_can_finish_with_text(sm, stop_info):
                return StopHandlingDecision(
                    handled=True,
                    next_query=self.prompt_builder.build_plain_text_completion_prompt(sm, stop_info),
                    clear_pending_stop=True,
                )

            if stop_info.get("recoverable"):
                return StopHandlingDecision(
                    handled=True,
                    next_query=self.prompt_builder.build_orchestrated_recovery_prompt(stop_info),
                    clear_pending_stop=True,
                )

        return StopHandlingDecision(handled=False)
