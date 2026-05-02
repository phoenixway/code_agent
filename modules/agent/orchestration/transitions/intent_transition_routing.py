"""Main model-step routing for intent transitions."""

from __future__ import annotations

from ..decision_models import IntentHandlingDecision


class IntentTransitionRoutingMixin:
    async def handle_model_step(
        self,
        *,
        intent_payload: dict | None,
        intent_error: str | None,
        response_text: str,
        state_machine=None,
    ) -> IntentHandlingDecision:
        intent_required_until_activated = bool(getattr(self.state, "intent_required_until_activated", False))
        has_active_intent = getattr(self.state, "active_intent", None) is not None

        if intent_error == "intent_body_contains_action":
            if not has_active_intent or intent_required_until_activated:
                if hasattr(self.state, "require_intent"):
                    self.state.require_intent("intent_body_contains_action")
            self.stage_logger.log(
                "intent_transition",
                "continue",
                reason="intent_body_contains_action",
                source="intent_parser",
                intent_error=intent_error,
                intent_required_until_activated=intent_required_until_activated,
                has_active_intent=has_active_intent,
            )
            return IntentHandlingDecision(
                handled=True,
                next_query=self.prompt_builder.build_intent_body_contains_action_prompt(),
                reason="intent_body_contains_action",
            )

        if intent_error and (intent_required_until_activated or not has_active_intent):
            if self.agent.log:
                self.agent.log.warning(
                    "Intent.parse_error intent_error=%s intent_required_until_activated=%s has_active_intent=%s response_preview=%r",
                    intent_error,
                    intent_required_until_activated,
                    has_active_intent,
                    (response_text or "")[:500],
                )
            resumable_intent_id, resumable_intent_type, resumable_goal = self._resumable_intent_meta()
            recovery_reason = "invalid_intent_resumable_available" if resumable_intent_id else "invalid_intent_json"
            if hasattr(self.state, "require_intent"):
                self.state.require_intent(recovery_reason)
            self.stage_logger.log(
                "intent_transition",
                "continue",
                reason=recovery_reason,
                source="intent_parser",
                intent_error=intent_error,
                intent_required_until_activated=intent_required_until_activated,
                has_active_intent=has_active_intent,
            )
            if resumable_intent_id:
                next_query = self.prompt_builder.build_invalid_intent_resumable_available_prompt(
                    intent_error,
                    resumable_intent_id=resumable_intent_id,
                    resumable_intent_type=resumable_intent_type,
                    resumable_goal=resumable_goal,
                )
            else:
                next_query = self.prompt_builder.build_invalid_intent_contract_prompt(intent_error)
            return IntentHandlingDecision(
                handled=True,
                next_query=next_query,
                reason=recovery_reason,
            )

        if intent_payload is not None:
            payload_mode = str((intent_payload or {}).get("mode") or "").strip().lower()
            if payload_mode == "complete" and getattr(self.state, "active_intent", None) is None:
                if self._remaining_has_plaintext_answer_only(response_text):
                    self._mark_terminal_plaintext_completion(response_text)
                    self.stage_logger.log(
                        "intent_transition",
                        "pass",
                        reason="ignored_redundant_complete_without_active_intent",
                        source="intent_runtime",
                        universe="no_active_contract",
                    )
                    return IntentHandlingDecision(handled=False)
                self.stage_logger.log(
                    "intent_transition",
                    "continue",
                    reason="intent_complete_without_active_intent",
                    source="prompt_fallback",
                    universe="no_active_contract",
                )
                return IntentHandlingDecision(
                    handled=True,
                    next_query=self.prompt_builder.build_intent_completed_prompt(),
                    reason="intent_complete_without_active_intent",
                )

        if intent_payload is None:
            self._clear_transition_defect()
            self.stage_logger.log(
                "intent_transition",
                "pass",
                universe=self._intent_universe_label(),
            )
            return IntentHandlingDecision(handled=False)

        intent_decision = self.apply_payload_decision(intent_payload)
        if self.agent.log:
            self.agent.log.debug(
                "Intent.apply ok=%s msg=%s warning=%s summary=%s",
                intent_decision.applied,
                intent_decision.message,
                intent_decision.warning,
                getattr(self.state, "active_intent_summary", lambda: "")(),
            )
            self.agent.log.debug("Intent.apply.payload=%s", intent_payload)
            self.agent.log.debug("Intent.apply.transition_info=%s", intent_decision.transition_info)

        if not intent_decision.applied:
            defect_count = self._note_transition_defect(intent_decision.message)
            if defect_count >= 3 and intent_decision.message in {
                "intent_reuse_without_active_intent",
                "intent_switch_reason_required",
                "conflicting_intent_transitions",
            }:
                self.stage_logger.log(
                    "intent_transition",
                    "stop",
                    reason="terminal_repeated_intent_transition_defect",
                    source="intent_runtime",
                    universe=self._intent_universe_label(),
                    defect_reason=intent_decision.message,
                    repeat_count=defect_count,
                )
                return IntentHandlingDecision(
                    handled=True,
                    next_query=None,
                    stop_loop=True,
                    reason="terminal_repeated_intent_transition_defect",
                )

            if intent_decision.message == "intent_reuse_without_active_intent":
                strict = defect_count >= 2
                self.stage_logger.log(
                    "intent_transition",
                    "continue",
                    reason=intent_decision.message,
                    source="intent_runtime",
                    universe="no_active_contract",
                    repeat_count=defect_count,
                )
                return IntentHandlingDecision(
                    handled=True,
                    next_query=self.prompt_builder.build_reuse_without_active_intent_activate_only_prompt(
                        strict=strict
                    ),
                    reason=intent_decision.message,
                )

            if (
                intent_decision.message == "unnecessary_intent_reactivation_or_replace"
                and getattr(self.state, "active_intent", None) is not None
                and self._remaining_has_action_only(response_text)
            ):
                self.stage_logger.log(
                    "intent_transition",
                    "pass",
                    reason="ignored_redundant_intent_reactivation_with_followup_action",
                    source="intent_runtime",
                    universe="active_contract",
                    transition=intent_decision.transition_info.get("transition", ""),
                    before_active_intent_id=intent_decision.transition_info.get("before_active_intent_id", ""),
                    after_active_intent_id=intent_decision.transition_info.get("after_active_intent_id", ""),
                )
                return IntentHandlingDecision(handled=False)

            recovery_decision = await self.recovery.handle_defect_detector_stop(intent_decision.rejection_stop_info)
            if recovery_decision.handled:
                self.stage_logger.log(
                    "intent_transition",
                    "continue",
                    reason=intent_decision.message,
                    source="defect_recovery",
                    universe=self._intent_universe_label(),
                    transition=intent_decision.transition_info.get("transition", ""),
                    before_active_intent_id=intent_decision.transition_info.get("before_active_intent_id", ""),
                    after_active_intent_id=intent_decision.transition_info.get("after_active_intent_id", ""),
                )
                return IntentHandlingDecision(
                    handled=True,
                    next_query=recovery_decision.next_query,
                    stop_loop=not bool(recovery_decision.next_query),
                    clear_pending_stop=bool(recovery_decision.next_query),
                    reason=intent_decision.message,
                )
            self.stage_logger.log(
                "intent_transition",
                "continue",
                reason=intent_decision.message,
                source="prompt_fallback",
                universe=self._intent_universe_label(),
                transition=intent_decision.transition_info.get("transition", ""),
                before_active_intent_id=intent_decision.transition_info.get("before_active_intent_id", ""),
                after_active_intent_id=intent_decision.transition_info.get("after_active_intent_id", ""),
            )
            return IntentHandlingDecision(
                handled=True,
                next_query=self.prompt_builder.build_intent_transition_rejected_prompt(
                    intent_decision.message,
                    getattr(getattr(self.state, "active_intent", None), "allowed_actions", None) or [],
                    goal=getattr(getattr(self.state, "active_intent", None), "goal", ""),
                ),
                reason=intent_decision.message,
            )

        self._inherit_memory_to_successor(intent_decision)
        self._clear_transition_defect()

        if state_machine is not None:
            state_machine.intent_runtime = getattr(self.state, "intent_runtime", None)

        if self.agent.log:
            active = intent_decision.active_intent
            self.agent.log.info(
                "Intent.active accepted=%s intent_id=%s intent_type=%s goal=%s allowed_actions=%s",
                True,
                getattr(active, "intent_id", "") if active is not None else "",
                getattr(active, "intent_type", "") if active is not None else "",
                getattr(active, "goal", "") if active is not None else "",
                ",".join(getattr(active, "allowed_actions", []) or []) if active is not None else "",
            )

        payload_mode = str((intent_payload or {}).get("mode") or "").strip().lower()
        if self._transition_only_intent_required():
            if self._remaining_has_any_action(response_text):
                blocked_action = str(getattr(self.state, "transition_only_blocked_action", "") or "").strip()
                self._clear_transition_only_intent_required()
                if payload_mode == "reuse":
                    self._clear_reuse_only_intent_required()
                self.stage_logger.log(
                    "intent_transition",
                    "continue",
                    reason="transition_only_recovery_cannot_bundle_action",
                    source="intent_runtime",
                    universe="transition_in_progress",
                )
                return IntentHandlingDecision(
                    handled=True,
                    next_query=self.prompt_builder.build_transition_only_intent_cannot_bundle_action_prompt(
                        blocked_action=blocked_action
                    ),
                    reason="transition_only_recovery_cannot_bundle_action",
                )
            self._clear_transition_only_intent_required()
        if payload_mode == "reuse" and self._reuse_only_intent_required():
            if self._remaining_has_any_action(response_text):
                blocked_action = str(getattr(self.state, "reuse_only_blocked_action", "") or "").strip()
                self._clear_reuse_only_intent_required()
                self.stage_logger.log(
                    "intent_transition",
                    "continue",
                    reason="reuse_only_transition_cannot_bundle_action",
                    source="intent_runtime",
                    universe="transition_in_progress",
                )
                return IntentHandlingDecision(
                    handled=True,
                    next_query=self.prompt_builder.build_reuse_only_transition_cannot_bundle_action_prompt(
                        blocked_action=blocked_action
                    ),
                    reason="reuse_only_transition_cannot_bundle_action",
                )
            self._clear_reuse_only_intent_required()

        if not str(response_text or "").strip() or self._has_no_followup_after_intent(response_text):
            if hasattr(self.state, "note_intent_only_response"):
                self.state.note_intent_only_response()
            if intent_decision.completion_requested:
                self._finalize_completed_intent()
                self.stage_logger.log(
                    "intent_transition",
                    "continue",
                    reason="intent_completed",
                    source="intent_runtime",
                    universe="transition_in_progress",
                    transition=intent_decision.transition_info.get("transition", ""),
                    before_active_intent_id=intent_decision.transition_info.get("before_active_intent_id", ""),
                    after_active_intent_id=intent_decision.transition_info.get("after_active_intent_id", ""),
                )
                return IntentHandlingDecision(
                    handled=True,
                    next_query=self.prompt_builder.build_intent_completed_prompt(),
                    clear_pending_stop=True,
                    reason="intent_completed",
                )
            active_intent = intent_decision.active_intent or getattr(self.state, "active_intent", None)
            active_goal = getattr(active_intent, "goal", "") if active_intent is not None else ""
            self.stage_logger.log(
                "intent_transition",
                "continue",
                reason="intent_accepted_without_followup",
                source="intent_runtime",
                universe="transition_in_progress",
                transition=intent_decision.transition_info.get("transition", ""),
                before_active_intent_id=intent_decision.transition_info.get("before_active_intent_id", ""),
                after_active_intent_id=intent_decision.transition_info.get("after_active_intent_id", ""),
            )
            return IntentHandlingDecision(
                handled=True,
                next_query=self.prompt_builder.build_intent_accepted_without_followup_prompt(active_goal),
                reason="intent_accepted_without_followup",
            )

        if intent_decision.completion_requested:
            if self._remaining_has_any_action(response_text):
                self.stage_logger.log(
                    "intent_transition",
                    "continue",
                    reason="intent_complete_with_action_not_allowed",
                    source="intent_runtime",
                    universe="transition_in_progress",
                    transition=intent_decision.transition_info.get("transition", ""),
                    before_active_intent_id=intent_decision.transition_info.get("before_active_intent_id", ""),
                    after_active_intent_id=intent_decision.transition_info.get("after_active_intent_id", ""),
                )
                return IntentHandlingDecision(
                    handled=True,
                    next_query=self.prompt_builder.build_completion_with_action_not_allowed_prompt(),
                    clear_pending_stop=True,
                    reason="intent_complete_with_action_not_allowed",
                )

            followup_conflict = self._remaining_followup_conflict_reason(response_text)
            if followup_conflict:
                self.stage_logger.log(
                    "intent_transition",
                    "continue",
                    reason=followup_conflict,
                    source="intent_runtime",
                    universe="transition_in_progress",
                    transition=intent_decision.transition_info.get("transition", ""),
                    before_active_intent_id=intent_decision.transition_info.get("before_active_intent_id", ""),
                    after_active_intent_id=intent_decision.transition_info.get("after_active_intent_id", ""),
                )
                return IntentHandlingDecision(
                    handled=True,
                    next_query=self.prompt_builder.build_followup_conflict_prompt(followup_conflict),
                    clear_pending_stop=True,
                    reason=followup_conflict,
                )

            self._finalize_completed_intent()
            self._mark_terminal_plaintext_completion(response_text)
            self.stage_logger.log(
                "intent_transition",
                "pass",
                reason="intent_completed_with_plaintext_answer",
                source="intent_runtime",
                universe="no_active_contract",
                transition=intent_decision.transition_info.get("transition", ""),
                before_active_intent_id=intent_decision.transition_info.get("before_active_intent_id", ""),
                after_active_intent_id=intent_decision.transition_info.get("after_active_intent_id", ""),
            )
            return IntentHandlingDecision(handled=False)

        if self._reuse_has_inline_plaintext_answer(intent_payload, response_text):
            self.stage_logger.log(
                "intent_transition",
                "pass",
                reason="intent_reuse_applied_with_inline_plaintext_answer",
                source="intent_runtime",
                universe="transition_in_progress",
                transition=intent_decision.transition_info.get("transition", ""),
                before_active_intent_id=intent_decision.transition_info.get("before_active_intent_id", ""),
                after_active_intent_id=intent_decision.transition_info.get("after_active_intent_id", ""),
            )
            return IntentHandlingDecision(handled=False)

        if self._reuse_has_inline_single_action(intent_payload, response_text):
            self.stage_logger.log(
                "intent_transition",
                "pass",
                reason="intent_reuse_applied_with_inline_followup_action",
                source="intent_runtime",
                universe="transition_in_progress",
                transition=intent_decision.transition_info.get("transition", ""),
                before_active_intent_id=intent_decision.transition_info.get("before_active_intent_id", ""),
                after_active_intent_id=intent_decision.transition_info.get("after_active_intent_id", ""),
            )
            return IntentHandlingDecision(handled=False)

        if self._remaining_has_action_only(response_text):
            self.stage_logger.log(
                "intent_transition",
                "pass",
                reason="intent_applied_with_followup_action",
                source="intent_runtime",
                universe="transition_in_progress",
                transition=intent_decision.transition_info.get("transition", ""),
                before_active_intent_id=intent_decision.transition_info.get("before_active_intent_id", ""),
                after_active_intent_id=intent_decision.transition_info.get("after_active_intent_id", ""),
            )
            return IntentHandlingDecision(handled=False)

        followup_conflict = self._remaining_followup_conflict_reason(response_text)
        if followup_conflict:
            self.stage_logger.log(
                "intent_transition",
                "continue",
                reason=followup_conflict,
                source="intent_runtime",
                universe="transition_in_progress",
                transition=intent_decision.transition_info.get("transition", ""),
                before_active_intent_id=intent_decision.transition_info.get("before_active_intent_id", ""),
                after_active_intent_id=intent_decision.transition_info.get("after_active_intent_id", ""),
            )
            return IntentHandlingDecision(
                handled=True,
                next_query=self.prompt_builder.build_followup_conflict_prompt(followup_conflict),
                clear_pending_stop=True,
                reason=followup_conflict,
            )

        active_intent = intent_decision.active_intent or getattr(self.state, "active_intent", None)
        active_goal = getattr(active_intent, "goal", "") if active_intent is not None else ""
        self.stage_logger.log(
            "intent_transition",
            "continue",
            reason="intent_accepted_awaiting_next_output",
            source="intent_runtime",
            universe="transition_in_progress",
            transition=intent_decision.transition_info.get("transition", ""),
            before_active_intent_id=intent_decision.transition_info.get("before_active_intent_id", ""),
            after_active_intent_id=intent_decision.transition_info.get("after_active_intent_id", ""),
        )
        return IntentHandlingDecision(
            handled=True,
            next_query=self.prompt_builder.build_intent_accepted_without_followup_prompt(active_goal),
            reason="intent_accepted_awaiting_next_output",
        )
