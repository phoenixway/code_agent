"""Intent payload application and transition handling."""

from __future__ import annotations

from .decision_models import IntentDecision, IntentHandlingDecision
from .stage_logging import OrchestrationStageLogger


class IntentTransitionHandler:
    def __init__(self, agent, prompt_builder, recovery):
        self.agent = agent
        self.state = agent.state
        self.config = agent.config
        self.prompt_builder = prompt_builder
        self.recovery = recovery
        self.stage_logger = OrchestrationStageLogger(getattr(agent, "log", None), self.state)

    def apply_payload_decision(self, payload: dict) -> IntentDecision:
        ok, intent_msg = self.state.apply_intent_contract(payload, self.config)
        runtime = getattr(self.state, "intent_runtime", None)
        warning = getattr(runtime, "last_apply_warning", "") if runtime is not None else ""
        transition_info = getattr(runtime, "last_transition_info", {}) if runtime is not None else {}
        active_intent = getattr(self.state, "active_intent", None)

        rejection_stop_info = None
        if not ok:
            rejection_stop_info = getattr(self.state, "last_defect_info", None) or {
                "reason": intent_msg,
                "recoverable": True,
                "next_actions": getattr(active_intent, "allowed_actions", None) or [],
            }
            if isinstance(transition_info, dict) and transition_info.get("transition") == "policy_rejected":
                rejection_stop_info = {
                    **rejection_stop_info,
                    "reason": transition_info.get("reason", intent_msg),
                    "recoverable": True,
                    "error_code": transition_info.get("error_code", ""),
                    "message_key": transition_info.get("message_key", ""),
                    "policy_metadata": transition_info.get("metadata", {}) or {},
                }

        return IntentDecision(
            applied=ok,
            message=intent_msg,
            warning=warning,
            active_intent=active_intent,
            transition_info=transition_info if isinstance(transition_info, dict) else {},
            rejection_stop_info=rejection_stop_info,
            completion_requested=(intent_msg == "intent_completed"),
        )

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

        if intent_error and (intent_required_until_activated or not has_active_intent):
            if self.agent.log:
                self.agent.log.warning(
                    "Intent.parse_error intent_error=%s intent_required_until_activated=%s has_active_intent=%s response_preview=%r",
                    intent_error,
                    intent_required_until_activated,
                    has_active_intent,
                    (response_text or "")[:500],
                )
            if hasattr(self.state, "require_intent"):
                self.state.require_intent("invalid_intent_json")
            self.stage_logger.log(
                "intent_transition",
                "continue",
                reason="intent_required_parse_error",
                source="intent_parser",
                intent_error=intent_error,
                intent_required_until_activated=intent_required_until_activated,
                has_active_intent=has_active_intent,
            )
            return IntentHandlingDecision(
                handled=True,
                next_query=self.prompt_builder.build_invalid_intent_contract_prompt(intent_error),
                reason="intent_required_parse_error",
            )

        if intent_payload is None:
            self.stage_logger.log("intent_transition", "pass")
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
            recovery_decision = await self.recovery.handle_defect_detector_stop(intent_decision.rejection_stop_info)
            if recovery_decision.handled:
                self.stage_logger.log(
                    "intent_transition",
                    "continue",
                    reason=intent_decision.message,
                    source="defect_recovery",
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

        if not str(response_text or "").strip():
            if hasattr(self.state, "note_intent_only_response"):
                self.state.note_intent_only_response()
            if intent_decision.completion_requested:
                self.stage_logger.log(
                    "intent_transition",
                    "continue",
                    reason="intent_completed",
                    source="intent_runtime",
                )
                return IntentHandlingDecision(
                    handled=True,
                    next_query=self.prompt_builder.build_intent_completed_prompt(),
                    reason="intent_completed",
                )
            active_intent = intent_decision.active_intent or getattr(self.state, "active_intent", None)
            active_goal = getattr(active_intent, "goal", "") if active_intent is not None else ""
            self.stage_logger.log(
                "intent_transition",
                "continue",
                reason="intent_accepted_without_followup",
                source="intent_runtime",
            )
            return IntentHandlingDecision(
                handled=True,
                next_query=(
                    "SYSTEM: Intent accepted and now remains active until runtime explicitly completes, replaces, rejects, or closes it. "
                    "Return the next valid step under the SAME current intent contract. "
                    "If tool use is needed, return the next <action>. "
                    "Do not emit another activate intent for the same ongoing work. "
                    f"Current contract goal remains the same: {active_goal}."
                ),
                reason="intent_accepted_without_followup",
            )

        self.stage_logger.log(
            "intent_transition",
            "pass",
            reason="intent_applied_with_remaining_response",
            source="intent_runtime",
        )
        return IntentHandlingDecision(handled=False)