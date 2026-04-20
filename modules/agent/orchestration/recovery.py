"""Recovery flow coordinator for orchestrator stop conditions."""

from __future__ import annotations

from .decision_models import RecoveryDecision
from .decision_models import RecoveryContext
from .recovery_policy import RecoveryPolicyResolver
from .stage_logging import OrchestrationStageLogger
from ..intent_messages import render_intent_message

StopHandlingDecision = RecoveryDecision


class RecoveryCoordinator:
    def __init__(self, agent, prompt_builder):
        self.agent = agent
        self.state = agent.state
        self.config = agent.config
        self.prompt_builder = prompt_builder
        self.stage_logger = OrchestrationStageLogger(getattr(agent, "log", None), self.state)
        self.recovery_policy_resolver = getattr(agent, "recovery_policy_resolver", None) or RecoveryPolicyResolver(
            getattr(agent, "allowed_actions_resolver", None)
        )

    def _intent_universe_label(self) -> str:
        if getattr(self.state, "active_intent", None) is not None:
            return "active_contract"
        return "no_active_contract"

    @property
    def ui(self):
        return self.agent.ui

    def _recovery_context(self, stop_info: dict | RecoveryContext | None) -> RecoveryContext:
        return self.recovery_policy_resolver.normalize_context(
            stop_info,
            active_intent=getattr(self.state, "active_intent", None),
        )

    def _intent_actions_from_stop_info(self, stop_info: dict | None, active_intent) -> list[str]:
        ctx = self._recovery_context(stop_info)
        resolved = ctx.resolved_action_policy()
        if resolved is not None and resolved.intent_actions:
            return resolved.intent_actions
        if resolved is not None and resolved.authoritative_source == "intent" and resolved.allowed_actions:
            return resolved.allowed_actions
        intent_actions = ctx.intent_allowed_actions
        if isinstance(intent_actions, list) and intent_actions:
            return intent_actions
        legacy = ctx.next_actions
        if str(ctx.next_actions_source or "").strip().lower() == "intent" and isinstance(legacy, list) and legacy:
            return legacy
        return list(getattr(active_intent, "allowed_actions", None) or [])

    def inspection_can_finish_with_text(self, sm, stop_info: dict | None) -> bool:
        if sm is None:
            return False
        task_kind = getattr(sm, "task_kind", None)
        task_kind_value = getattr(task_kind, "value", str(task_kind))
        if task_kind_value not in {"INSPECTION", "HYBRID"}:
            return False
        reason = self._recovery_context(stop_info).reason
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

    async def handle_defect_detector_stop(self, stop_info: dict | None) -> RecoveryDecision:
        ctx = self._recovery_context(stop_info)
        stop_info = ctx.to_stop_info()
        reason = ctx.reason
        self.stage_logger.log(
            "dispatch_recovery",
            "evaluate",
            reason=reason,
            source="defect_detector",
            universe=self._intent_universe_label(),
        )

        if reason in {
            "intent_action_not_allowed",
            "intent_step_limit_soft_exceeded",
            "intent_blocked_action_signature",
            "unnecessary_intent_reactivation_or_replace",
            "suspect_intent_relabel_repeat",
            "suspect_intent_goal_drift",
        }:
            active_intent = getattr(self.state, "active_intent", None)
            allowed = self._intent_actions_from_stop_info(stop_info, active_intent)
            if reason == "intent_step_limit_soft_exceeded":
                return RecoveryDecision.continue_with(
                    self.prompt_builder.build_keep_current_intent_recovery_prompt(
                        {
                            **(stop_info or {}),
                            "reason": "intent_step_limit_soft_exceeded",
                            "next_actions": allowed,
                            "intent_allowed_actions": allowed,
                            "next_actions_source": "intent",
                        }
                    ),
                    reason=reason,
                    source="defect_detector",
                )
            if reason == "intent_blocked_action_signature":
                blocked_reason = ""
                if hasattr(self.state, "get_blocked_action_reason"):
                    try:
                        blocked_reason = self.state.get_blocked_action_reason(stop_info.get("command") or {}) or ""
                    except Exception:
                        blocked_reason = ""
                note = (
                    "This exact action shape is blocked for the current intent contract."
                    if not blocked_reason
                    else f"This exact action shape is blocked for the current intent contract because of: {blocked_reason}."
                )
                base = render_intent_message(
                    stop_info.get("message_key") or "blocked_action_keep_current_intent",
                    default="A specific action is blocked, but the current intent contract is still valid.",
                )
                return RecoveryDecision.continue_with(
                    (
                        f"SYSTEM: {base}\n"
                        f"Reason: {reason}.\n"
                        "This blocked tool step does NOT close or invalidate the current intent contract.\n"
                        f"Allowed actions under the CURRENT intent contract: {', '.join(allowed) if allowed else 'none'}.\n"
                        f"Current intent goal remains the same: {getattr(active_intent, 'goal', '')}.\n"
                        f"{note}\n"
                        "Do NOT retry the same action with cosmetic changes.\n"
                        "Choose a materially different next <action>, or answer from current evidence if enough is already known.\n"
                        "A legitimate intent contract transition is not globally forbidden, but do not propose one unless the work truly changed."
                    ),
                    reason=reason,
                    source="defect_detector",
                )
            if reason == "unnecessary_intent_reactivation_or_replace":
                return RecoveryDecision.continue_with(
                    self.prompt_builder.build_keep_current_intent_recovery_prompt(
                        {
                            **(stop_info or {}),
                            "reason": "unnecessary_intent_reactivation_or_replace",
                            "next_actions": allowed,
                            "intent_allowed_actions": allowed,
                            "next_actions_source": "intent",
                        }
                    ),
                    reason=reason,
                    source="defect_detector",
                )
            if reason == "suspect_intent_relabel_repeat":
                return RecoveryDecision.continue_with(
                    self.prompt_builder.build_keep_original_goal_prompt(
                        reason,
                        allowed,
                        goal=getattr(active_intent, "goal", ""),
                    ),
                    reason=reason,
                    source="defect_detector",
                )
            if reason == "suspect_intent_goal_drift":
                decision = await self.choose_suspect_intent_change_action(stop_info)
                if decision == "allow_changed_goal":
                    allow_method = (
                        getattr(self.state, "allow_pending_goal_drift_once", None)
                    )
                    if callable(allow_method):
                        ok, msg = allow_method(self.config)
                        if ok:
                            self.state.add_confirmation(1)
                            return RecoveryDecision.continue_with(
                                self.prompt_builder.build_approved_changed_goal_prompt(),
                                reason=reason,
                                source="defect_detector",
                            )
                    return RecoveryDecision.continue_with(
                        self.prompt_builder.build_intent_transition_rejected_prompt(
                            "suspect_intent_relabel_repeat",
                            allowed,
                            goal=getattr(active_intent, "goal", ""),
                        ),
                        reason=reason,
                        source="defect_detector",
                    )
                if decision == "stop_and_answer":
                    runtime = getattr(self.state, "intent_runtime", None)
                    if runtime is not None and hasattr(runtime, "force_current_intent_completion"):
                        runtime.force_current_intent_completion()
                    return RecoveryDecision.continue_with(
                        self.prompt_builder.build_plain_text_completion_prompt(
                            getattr(self.state, "state_machine", None),
                            {
                                **(stop_info or {}),
                                "reason": "user_stopped_after_suspect_goal_change",
                            },
                        ),
                        reason=reason,
                        source="defect_detector",
                    )
                return RecoveryDecision.continue_with(
                    self.prompt_builder.build_keep_original_goal_prompt(
                        reason,
                        allowed,
                        goal=getattr(active_intent, "goal", ""),
                    ),
                    reason=reason,
                    source="defect_detector",
                )
            return RecoveryDecision.continue_with(
                self.prompt_builder.build_reuse_current_intent_prompt(
                    reason,
                    allowed,
                    goal=getattr(active_intent, "goal", ""),
                ),
                reason=reason,
                source="defect_detector",
            )

        if reason in {"intent_step_limit_exceeded", "intent_step_limit_exceeded_repeated"}:
            active_intent = getattr(self.state, "active_intent", None)
            allowed = self._intent_actions_from_stop_info(stop_info, active_intent)
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
                    "User approved additional budget for this same intent contract.\n"
                    "Priority now is to finish quickly from current evidence.\n"
                    "Do not reopen exploration or repeat already completed investigation.\n"
                    "Continue from the last valid point already reached under the same contract.\n"
                    "If the goal is already answerable, complete the intent and answer now."
                    if granted
                    else "User approved additional budget for this same intent contract.\n"
                    "Priority now is to finish quickly from current evidence.\n"
                    "Do not reopen exploration or repeat already completed investigation.\n"
                    "Continue from the last valid point already reached under the same contract.\n"
                    "If the goal is already answerable, complete the intent and answer now."
                )
                return RecoveryDecision.continue_with(
                    self.prompt_builder.build_keep_current_intent_recovery_prompt(
                        {
                            **(stop_info or {}),
                            "reason": "user_approved_more_steps_after_hard_limit",
                            "next_actions": allowed,
                            "intent_allowed_actions": allowed,
                            "next_actions_source": "intent",
                        }
                    ) + f"\n{note}",
                    reason=reason,
                    source="defect_detector",
                )

            if runtime is not None and hasattr(runtime, "force_current_intent_completion"):
                runtime.force_current_intent_completion()
            return RecoveryDecision.continue_with(
                self.prompt_builder.build_plain_text_completion_prompt(
                    getattr(self.state, "state_machine", None),
                    {
                        **(stop_info or {}),
                        "reason": "user_stopped_after_hard_limit_answer_from_current_evidence",
                    },
                ),
                reason=reason,
                source="defect_detector",
            )

        reason_map = {
            "defect_repeated_action_cycle": "Defect detector: модель повторює 3 кроки в циклі. Продовжити?",
            "defect_same_action_repeat": "Defect detector: модель кілька разів повторює одну й ту саму дію. Продовжити?",
            "intent_retry_limit_exceeded": "Defect detector: агент перевищив retry_limit поточного intent. Продовжити?",
        }
        message = reason_map.get(reason)
        if not message:
            return RecoveryDecision.pass_through(reason=reason, source="defect_detector")
        decision = await self.ui.confirm_continue(message)
        if decision in (False, "stop", None):
            await self.ui.print_system("Execution stopped by defect detector.")
            return RecoveryDecision.stop(reason=reason, source="defect_detector")
        self.state.add_confirmation(1)
        if bool(getattr(self.config, "INTENT_REQUIRE_ON_DEFECT", True)):
            if hasattr(self.state, "require_intent"):
                self.state.require_intent(reason)
            return RecoveryDecision.continue_with(
                self.prompt_builder.build_intent_required_prompt(reason, stop_info.get("next_actions") or []),
                reason=reason,
                source="defect_detector",
            )
        return RecoveryDecision.continue_with(
            self.prompt_builder.build_typed_stop_recovery_prompt(stop_info),
            reason=reason,
            source="defect_detector",
        )

    async def handle_dispatch_stop(
        self,
        stop_info: dict | None,
        sm,
    ) -> StopHandlingDecision:
        ctx = self._recovery_context(stop_info)
        stop_info = ctx.to_stop_info()
        defect_decision = await self.handle_defect_detector_stop(stop_info)
        if defect_decision.handled:
            self.stage_logger.log(
                "dispatch_recovery",
                "continue" if defect_decision.next_query else "stop",
                reason=defect_decision.reason,
                source=defect_decision.source,
            )
            if defect_decision.next_query:
                return StopHandlingDecision.continue_with(
                    defect_decision.next_query,
                    reason=defect_decision.reason,
                    source=defect_decision.source,
                    clear_pending_stop=True,
                )
            return StopHandlingDecision.stop(
                reason=defect_decision.reason,
                source=defect_decision.source,
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
                return StopHandlingDecision.continue_with(
                    self.prompt_builder.build_retry_recovery_query(recovery_actions),
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
                return StopHandlingDecision.continue_with(
                    self.prompt_builder.build_open_search_recovery_query(error_details),
                    clear_pending_stop=True,
                )

        if stop_info:
            if stop_info.get("reason") == "malformed_read_file_payload":
                return StopHandlingDecision.continue_with(
                    self.prompt_builder.build_malformed_read_file_payload_prompt(),
                    clear_pending_stop=True,
                )

            if stop_info.get("reason") == "malformed_read_file_skeleton_payload":
                return StopHandlingDecision.continue_with(
                    self.prompt_builder.build_malformed_read_file_skeleton_payload_prompt(),
                    clear_pending_stop=True,
                )

            if stop_info.get("reason") == "malformed_read_chunk_payload":
                active_intent = getattr(self.state, "active_intent", None)
                allowed = self._intent_actions_from_stop_info(stop_info, active_intent)
                count_getter = getattr(self.state, "get_stop_reason_count", None)
                malformed_count = count_getter("malformed_read_chunk_payload") if callable(count_getter) else 0
                if malformed_count >= 2:
                    return StopHandlingDecision.continue_with(
                        self.prompt_builder.build_repeated_malformed_read_chunk_payload_prompt(
                            allowed,
                            goal=getattr(active_intent, "goal", "") if active_intent is not None else "",
                        ),
                        clear_pending_stop=True,
                    )
                return StopHandlingDecision.continue_with(
                    self.prompt_builder.build_malformed_read_chunk_payload_prompt(),
                    clear_pending_stop=True,
                )

            if self.inspection_can_finish_with_text(sm, stop_info):
                return StopHandlingDecision.continue_with(
                    self.prompt_builder.build_plain_text_completion_prompt(sm, stop_info),
                    clear_pending_stop=True,
                )

            if stop_info.get("recoverable"):
                if str(stop_info.get("error_code") or "").strip().upper() == "VALIDATION_ERROR":
                    active_intent = getattr(self.state, "active_intent", None)
                    if active_intent is not None:
                        allowed = self._intent_actions_from_stop_info(stop_info, active_intent)
                        details = stop_info.get("error_details") or {}
                        mismatch_type = str(details.get("mismatch_type") or "")
                        note = ""
                        if mismatch_type == "multiple_similar_blocks":
                            note = (
                                "\nThe last edit failed because the search block matched multiple similar regions."
                                "\nDo not open a new intent contract."
                                "\nPrefer one deterministic recovery step inside the SAME intent contract:"
                                "\n- read the exact target block,"
                                "\n- then retry edit_file with exact copied whitespace,"
                                "\n- or switch to write_file with full validated content."
                            )
                        return StopHandlingDecision.continue_with(
                            self.prompt_builder.build_keep_current_intent_recovery_prompt(
                                {
                                    **(stop_info or {}),
                                    "reason": "retry_or_continuation_after_failure",
                                    "next_actions": allowed,
                                    "intent_allowed_actions": allowed,
                                    "next_actions_source": "intent",
                                }
                            ) + note,
                            clear_pending_stop=True,
                        )

                return StopHandlingDecision.continue_with(
                    self.prompt_builder.build_orchestrated_recovery_prompt(stop_info),
                    clear_pending_stop=True,
                )

        self.stage_logger.log("dispatch_recovery", "pass")
        return StopHandlingDecision.pass_through()
