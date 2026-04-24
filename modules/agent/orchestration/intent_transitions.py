"""Intent payload application and transition handling."""

from __future__ import annotations

import re

from .decision_models import IntentDecision, IntentHandlingDecision
from .stage_logging import OrchestrationStageLogger


class IntentTransitionHandler:
    REMAINING_OPEN_CONTROL_TAG_RE = re.compile(r"<\s*(intent|action)\b", re.IGNORECASE)
    REMAINING_ACTION_TAG_RE = re.compile(r"<\s*action\b", re.IGNORECASE)
    INTENT_TAG_RE = re.compile(r"<intent(?:\s+[^>]*)?>.*?</intent>", re.IGNORECASE | re.DOTALL)
    THINK_TAG_RE = re.compile(r"<think(?:\s+[^>]*)?>.*?</think>", re.IGNORECASE | re.DOTALL)
    MEMORY_BLOCK_RE = re.compile(r"<(fact|finding|decision|preference|progress)\b[^>]*>.*?</\1>", re.IGNORECASE | re.DOTALL)
    MEMORY_TAG_RE = re.compile(r"</?(fact|finding|decision|preference|progress)\b[^>]*>", re.IGNORECASE)

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
        masked = self.THINK_TAG_RE.sub(" ", text)
        return bool(self.REMAINING_OPEN_CONTROL_TAG_RE.search(masked))

    def _remaining_has_action_only(self, response_text: str) -> bool:
        text = str(response_text or "").strip()
        if not text:
            return False
        masked = self.THINK_TAG_RE.sub(" ", text)
        if "<intent" in masked.lower():
            return False
        return bool(self.REMAINING_ACTION_TAG_RE.search(masked))


    def _remaining_has_plaintext_answer_only(self, response_text: str) -> bool:
        text = str(response_text or "").strip()
        if not text:
            return False
        masked = self.THINK_TAG_RE.sub(" ", text)
        if re.search(r"<\s*(intent|action)\b", masked, re.IGNORECASE):
            return False
        masked = self.MEMORY_BLOCK_RE.sub(" ", masked)
        masked = self.MEMORY_TAG_RE.sub(" ", masked)
        return bool(re.sub(r"<[^>]+>", " ", masked).strip())

    def _response_without_think_and_intent(self, response_text: str) -> str:
        text = str(response_text or "").strip()
        if not text:
            return ""
        masked = self.THINK_TAG_RE.sub(" ", text)
        masked = self.INTENT_TAG_RE.sub(" ", masked)
        return masked.strip()

    def _reuse_has_inline_single_action(self, intent_payload: dict | None, response_text: str) -> bool:
        payload_mode = str((intent_payload or {}).get("mode") or "").strip().lower()
        if payload_mode != "reuse":
            return False
        masked = self._response_without_think_and_intent(response_text)
        if not masked:
            return False
        if re.search(r"<\s*intent\b", masked, re.IGNORECASE):
            return False
        action_count = len(self.REMAINING_ACTION_TAG_RE.findall(masked))
        return action_count == 1

    def _reuse_has_inline_plaintext_answer(self, intent_payload: dict | None, response_text: str) -> bool:
        payload_mode = str((intent_payload or {}).get("mode") or "").strip().lower()
        if payload_mode != "reuse":
            return False
        masked = self._response_without_think_and_intent(response_text)
        if not masked:
            return False
        if re.search(r"<\s*(intent|action)\b", masked, re.IGNORECASE):
            return False
        masked = self.MEMORY_BLOCK_RE.sub(" ", masked)
        masked = self.MEMORY_TAG_RE.sub(" ", masked)
        return bool(re.sub(r"<[^>]+>", " ", masked).strip())


    def _inherit_memory_to_successor(self, intent_decision: IntentDecision) -> None:
        transition_info = dict(intent_decision.transition_info or {})
        if transition_info.get("transition") != "intent_replaced":
            return
        if not bool(transition_info.get("same_lineage")):
            return
        from_intent_id = str(transition_info.get("before_active_intent_id") or "").strip()
        to_intent_id = str(transition_info.get("after_active_intent_id") or "").strip()
        lineage_id = str(transition_info.get("lineage_id") or "").strip()
        if not from_intent_id or not to_intent_id or from_intent_id == to_intent_id:
            return
        memory_board_store = getattr(self.agent, "memory_board_store", None)
        inheritor = getattr(memory_board_store, "inherit_intent_scope", None)
        if not callable(inheritor):
            return
        try:
            copied = int(inheritor(
                from_intent_id=from_intent_id,
                to_intent_id=to_intent_id,
                lineage_id=lineage_id,
                source="intent_transition",
            ) or 0)
            transition_info["inherited_memory_entries"] = copied
            intent_decision.transition_info = transition_info
        except Exception:
            pass

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

    def _mark_terminal_plaintext_completion(self, response_text: str) -> None:
        text = str(response_text or "").strip()
        try:
            setattr(self.state, "terminal_plaintext_completion_pending", bool(text))
            setattr(self.state, "terminal_plaintext_completion_text", text)
            if hasattr(self.state, "readonly_steps_this_turn"):
                self.state.readonly_steps_this_turn = 0
        except Exception:
            pass

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
            if transition_info.get("transition") == "intent_completed":
                self.state.last_completed_intent_type = str(
                    transition_info.get("before_active_intent_type", "") or ""
                ).strip().upper()
            if transition_info.get("transition") == "intent_reused_with_step_refresh" and hasattr(self.state, "pending_loop_stop_info"):
                self.state.pending_loop_stop_info = None

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