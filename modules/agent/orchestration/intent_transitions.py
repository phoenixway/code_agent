"""Intent payload application and transition handling."""

from __future__ import annotations

import re

from .decision_models import IntentDecision, IntentHandlingDecision
from .stage_logging import OrchestrationStageLogger


class IntentTransitionHandler:
    REMAINING_OPEN_CONTROL_TAG_RE = re.compile(r"<\s*(intent|action)\b", re.IGNORECASE)

    def __init__(self, agent, prompt_builder, recovery):
        self.agent = agent
        self.state = agent.state
        self.config = agent.config
        self.prompt_builder = prompt_builder
        self.recovery = recovery
        self.stage_logger = OrchestrationStageLogger(getattr(agent, "log", None), self.state)

    def _intent_universe_label(self) -> str:
        if getattr(self.state, "active_intent", None) is not None:
            return "active_contract"
        return "no_active_contract"

    def _remaining_transition_bundle_too_dense(self, response_text: str) -> bool:
        text = str(response_text or "").strip()
        if not text:
            return False
        return bool(self.REMAINING_OPEN_CONTROL_TAG_RE.search(text))

    def _finalize_completed_intent(self) -> None:
        runtime = getattr(self.state, "intent_runtime", None)
        finalized = False

        for method_name in ("finalize_current_intent_completion", "close_current_intent", "clear_current_intent"):
            method = getattr(runtime, method_name, None) if runtime is not None else None
            if callable(method):
                try:
                    method()
                    finalized = True
                    break
                except Exception:
                    pass

        if not finalized:
            for method_name in ("complete_current_intent", "clear_active_intent"):
                method = getattr(self.state, method_name, None)
                if callable(method):
                    try:
                        method()
                        finalized = True
                        break
                    except Exception:
                        pass

        if not finalized:
            try:
                self.state.active_intent = None
            except Exception:
                pass

        if hasattr(self.state, "pending_loop_stop_info"):
            self.state.pending_loop_stop_info = None

    def apply_payload_decision(self, payload: dict) -> IntentDecision:
        active_before = getattr(self.state, "active_intent", None)
        ok, intent_msg = self.state.apply_intent_contract(payload, self.config)
        runtime = getattr(self.state, "intent_runtime", None)
        warning = getattr(runtime, "last_apply_warning", "") if runtime is not None else ""
        transition_info = getattr(runtime, "last_transition_info", {}) if runtime is not None else {}
        active_intent = getattr(self.state, "active_intent", None)
        if isinstance(transition_info, dict):
            transition_info = {
                **transition_info,
                "before_active_intent_id": getattr(active_before, "intent_id", ""),
                "before_active_intent_type": getattr(active_before, "intent_type", ""),
                "after_active_intent_id": getattr(active_intent, "intent_id", ""),
                "after_active_intent_type": getattr(active_intent, "intent_type", ""),
            }

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
            if self._remaining_transition_bundle_too_dense(response_text):
                self.stage_logger.log(
                    "intent_transition",
                    "continue",
                    reason="transition_bundle_too_dense",
                    source="intent_runtime",
                    universe="transition_in_progress",
                    transition=intent_decision.transition_info.get("transition", ""),
                    before_active_intent_id=intent_decision.transition_info.get("before_active_intent_id", ""),
                    after_active_intent_id=intent_decision.transition_info.get("after_active_intent_id", ""),
                )
                return IntentHandlingDecision(
                    handled=True,
                    next_query=self.prompt_builder.build_transition_bundle_too_dense_prompt(),
                    clear_pending_stop=True,
                    reason="transition_bundle_too_dense",
                )

            self._finalize_completed_intent()
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

        if self._remaining_transition_bundle_too_dense(response_text):
            self.stage_logger.log(
                "intent_transition",
                "continue",
                reason="transition_bundle_too_dense",
                source="intent_runtime",
                universe="transition_in_progress",
                transition=intent_decision.transition_info.get("transition", ""),
                before_active_intent_id=intent_decision.transition_info.get("before_active_intent_id", ""),
                after_active_intent_id=intent_decision.transition_info.get("after_active_intent_id", ""),
            )
            return IntentHandlingDecision(
                handled=True,
                next_query=self.prompt_builder.build_transition_bundle_too_dense_prompt(),
                clear_pending_stop=True,
                reason="transition_bundle_too_dense",
            )

        self.stage_logger.log(
            "intent_transition",
            "pass",
            reason="intent_applied_with_remaining_response",
            source="intent_runtime",
            universe="transition_in_progress",
            transition=intent_decision.transition_info.get("transition", ""),
            before_active_intent_id=intent_decision.transition_info.get("before_active_intent_id", ""),
            after_active_intent_id=intent_decision.transition_info.get("after_active_intent_id", ""),
        )
        return IntentHandlingDecision(handled=False)
