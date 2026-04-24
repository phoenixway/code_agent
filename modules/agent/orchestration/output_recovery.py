"""Recovery decisions for invalid or incomplete model outputs before dispatch."""

from __future__ import annotations

import re

from .decision_models import OutputRecoveryDecision, ParsedModelOutput
from .stage_logging import OrchestrationStageLogger


class ModelOutputRecoveryHandler:
    MODIFY_COMPLETION_CLAIM_RE = re.compile(
        r"(?is)\b("
        r"готово|"
        r"зміни\s+внесен(?:о|і)|"
        r"код\s+змінен(?:о|ий)|"
        r"виправлен(?:о|ий|а)|"
        r"я\s+(?:додав|додала|змінив|змінила|оновив|оновила|виправив|виправила|реалізував|реалізувала)|"
        r"тепер\s+працює|"
        r"done|"
        r"changes?\s+applied|"
        r"code\s+(?:changed|updated|fixed)|"
        r"i\s+(?:added|changed|updated|fixed|implemented)"
        r")"
    )


    NEGATED_MODIFY_COMPLETION_RE = re.compile(
        r"(?is)(?:\b(?:no|not|nothing)\b[^\n\r]{0,40}\b(?:changes?\s+applied|code\s+(?:changed|updated|fixed)|i\s+(?:added|changed|updated|fixed|implemented))\b|"
        r"\b(?:не|ще\s+не|нічого\s+не)\b[^\n\r]{0,60}\b(?:зміни\s+внесен(?:о|і)|код\s+змінен(?:о|ий)|виправлен(?:о|ий|а)|я\s+(?:додав|додала|змінив|змінила|оновив|оновила|виправив|виправила|реалізував|реалізувала))\b)"
    )

    NON_COMPLETION_PROGRESS_RE = re.compile(
        r"(?is)\b("
        r"no\s+changes?\s+applied\s+yet|"
        r"nothing\s+has\s+been\s+applied\s+yet|"
        r"still\s+need\s+to|"
        r"need\s+(?:refreshed\s+)?budget|"
        r"request\s+(?:a\s+formal\s+)?intent\s+reuse|"
        r"not\s+applied\s+yet|"
        r"no\s+changes?\s+have\s+been\s+applied|"
        r"змін\s+ще\s+не\s+внесено|"
        r"нічого\s+ще\s+не\s+застосовано|"
        r"ще\s+не\s+застосовано|"
        r"потрібно\s+оновити\s+бюджет|"
        r"потрібен\s+оновлений\s+бюджет|"
        r"потрібно\s+запросити\s+reuse|"
        r"no\s+changes\s+applied\s+yet"
        r")\b"
    )

    INTERNAL_SUMMARY_HEADING_RE = re.compile(
        r"(?im)^\s*("
        r"active goal|"
        r"established facts|"
        r"current best answer|"
        r"active plan\s*/\s*strategy|"
        r"execution state|"
        r"pending checks|"
        r"avoid regression|"
        r"important errors\s*/\s*policy events|"
        r"next best step|"
        r"execution snapshot"
        r")\s*:"
    )

    def __init__(self, agent, prompt_builder):
        self.agent = agent
        self.state = agent.state
        self.config = agent.config
        self.prompt_builder = prompt_builder
        self.stage_logger = OrchestrationStageLogger(getattr(agent, "log", None), self.state)

    def _intent_universe_label(self) -> str:
        if getattr(self.state, "active_intent", None) is not None:
            return "active_contract"
        return "no_active_contract"

    def _missing_action_or_answer_retries(self) -> int:
        getter = getattr(self.state, "get_stop_reason_count", None)
        if callable(getter):
            try:
                return int(getter("missing_action_or_answer") or 0)
            except Exception:
                return 0
        return 0

    def _accepted_memory_checkpoint_only(self) -> bool:
        return bool(getattr(self.state, "last_memory_checkpoint_only", False))

    def _is_modify_context(self) -> bool:
        active_intent = getattr(self.state, "active_intent", None)
        if active_intent is not None:
            active_type = str(getattr(active_intent, "intent_type", "") or "").strip().upper()
            return active_type == "MODIFY"

        last_completed_intent_type = str(getattr(self.state, "last_completed_intent_type", "") or "").strip().upper()
        if last_completed_intent_type == "MODIFY":
            return True

        # FIXME:
        # task_kind is a bootstrap heuristic only. It must not override an active
        # accepted intent contract. Use it only as a last-resort fallback when no
        # active intent exists and no recent completed intent gives a better signal.
        state_machine = getattr(self.state, "state_machine", None)
        task_kind = getattr(state_machine, "task_kind", None)
        task_kind_value = str(getattr(task_kind, "value", task_kind or "")).strip().upper()
        return task_kind_value == "MODIFICATION"

    def _has_current_turn_state_change_proof(self) -> bool:
        return int(getattr(self.state, "current_turn_state_change_count", 0) or 0) > 0

    def _is_negated_or_non_completion_modify_text(self, text: str) -> bool:
        normalized = str(text or "").strip()
        if not normalized:
            return False
        if self.NON_COMPLETION_PROGRESS_RE.search(normalized):
            return True
        return bool(self.NEGATED_MODIFY_COMPLETION_RE.search(normalized))

    def _is_unproven_modify_completion_claim(self, parsed_output: ParsedModelOutput) -> bool:
        if parsed_output.has_action_segment:
            return False
        if not self._is_modify_context():
            return False
        if self._has_current_turn_state_change_proof():
            return False
        text = str(getattr(parsed_output, "visible_text", "") or "").strip()
        if not text:
            return False
        if self._is_negated_or_non_completion_modify_text(text):
            return False
        return bool(self.MODIFY_COMPLETION_CLAIM_RE.search(text))

    def _is_internal_summary_instead_of_final_answer(self, parsed_output: ParsedModelOutput) -> bool:
        if parsed_output.has_action_segment:
            return False
        text = str(getattr(parsed_output, "visible_text", "") or "").strip()
        if not text:
            return False

        heading_hits = self.INTERNAL_SUMMARY_HEADING_RE.findall(text)
        if len(heading_hits) >= 2:
            return True

        lowered = text.lower()
        if (
            "the user asked to summarize conversation history" in lowered
            or "compress heavily" in lowered
            or "continue the current task normally" in lowered
        ) and len(heading_hits) >= 1:
            return True

        return False

    @property
    def ui(self):
        return self.agent.ui

    async def decide(
        self,
        parsed_output: ParsedModelOutput,
        *,
        malformed_action_retries: int,
        audit_marker_retries: int,
    ) -> OutputRecoveryDecision:
        invalid_kind = str(parsed_output.invalid_kind or "").strip()
        if not invalid_kind and self._is_internal_summary_instead_of_final_answer(parsed_output):
            invalid_kind = "internal_summary_instead_of_final_answer"
        if not invalid_kind and self._is_unproven_modify_completion_claim(parsed_output):
            invalid_kind = "modify_completion_claim_without_state_change_proof"
        if not invalid_kind:
            self.stage_logger.log("output_recovery", "pass")
            return OutputRecoveryDecision.pass_through(
                reason="no_invalid_kind",
                source="output_recovery",
                malformed_action_retries=0,
                audit_marker_retries=0,
            )

        if invalid_kind == "malformed_action":
            next_retries = malformed_action_retries + 1
            if self.agent.log:
                self.agent.log.warning(
                    "Malformed action response detected (retry %s/1).",
                    next_retries,
                )
            if next_retries > 1:
                await self.ui.print_error(
                    "Execution stopped: model returned malformed action format repeatedly."
                )
                return OutputRecoveryDecision(
                    handled=True,
                    continue_loop=False,
                    stop_loop=True,
                    malformed_action_retries=next_retries,
                    audit_marker_retries=0,
                    reason=invalid_kind,
                )
            self.state.set_malformed_grace(self.config.MALFORMED_ACTION_GRACE_STEPS)
            self.state.forbid_next_action_fingerprint(
                getattr(self.state, "last_completed_fingerprint", None)
            )
            self.stage_logger.log(
                "output_recovery",
                "continue",
                reason=invalid_kind,
                retries=next_retries,
            )
            return OutputRecoveryDecision.continue_with(
                self.prompt_builder.build_malformed_action_strict_recovery_prompt(),
                reason=invalid_kind,
                source="output_recovery",
                malformed_action_retries=next_retries,
                audit_marker_retries=0,
            )

        if invalid_kind == "tool_history_echo":
            self.stage_logger.log("output_recovery", "continue", reason=invalid_kind, universe=self._intent_universe_label())
            return OutputRecoveryDecision.continue_with(
                self.prompt_builder.build_tool_history_echo_without_action_prompt(),
                reason=invalid_kind,
                source="output_recovery",
                malformed_action_retries=0,
                audit_marker_retries=0,
            )

        if invalid_kind == "audit_marker_echo":
            next_retries = audit_marker_retries + 1
            if self.agent.log:
                self.agent.log.warning(
                    "Audit-marker echo without action detected (retry %s/1).",
                    next_retries,
                )
            if next_retries > 1:
                await self.ui.print_error(
                    "Execution stopped: model repeatedly echoed audit trail without a valid action."
                )
                self.stage_logger.log(
                    "output_recovery",
                    "stop",
                    reason=invalid_kind,
                    retries=next_retries,
                )
                return OutputRecoveryDecision(
                    handled=True,
                    continue_loop=False,
                    stop_loop=True,
                    malformed_action_retries=0,
                    audit_marker_retries=next_retries,
                    reason=invalid_kind,
                )
            self.stage_logger.log(
                "output_recovery",
                "continue",
                reason=invalid_kind,
                retries=next_retries,
            )
            return OutputRecoveryDecision.continue_with(
                self.prompt_builder.build_audit_marker_echo_strict_recovery_prompt(),
                reason=invalid_kind,
                source="output_recovery",
                malformed_action_retries=0,
                audit_marker_retries=next_retries,
            )

        if invalid_kind == "missing_think_reflection":
            self.stage_logger.log(
                "output_recovery",
                "continue",
                reason=invalid_kind,
                universe=self._intent_universe_label(),
            )
            return OutputRecoveryDecision.continue_with(
                self.prompt_builder.build_missing_think_reflection_prompt(),
                reason=invalid_kind,
                source="output_recovery",
                malformed_action_retries=0,
                audit_marker_retries=0,
            )

        if invalid_kind == "missing_action_or_answer":
            retries = self._missing_action_or_answer_retries()
            if bool(getattr(self.state, "think_reflection_repair_pending", False)):
                prompt = self.prompt_builder.build_reflection_repair_accepted_prompt()
            else:
                prompt = self.prompt_builder.build_missing_action_or_answer_prompt()
            if retries >= 1:
                prompt += (
                    "\nSYSTEM: This happened again under the current contract."
                    "\nDo not continue reasoning without execution."
                    "\nReturn EXACTLY ONE valid <action>...</action> block now, or return a final plain-text answer if the goal is already satisfied."
                )
            self.stage_logger.log(
                "output_recovery",
                "continue",
                reason=invalid_kind,
                universe=self._intent_universe_label(),
                retries=retries,
            )
            return OutputRecoveryDecision.continue_with(
                prompt,
                reason=invalid_kind,
                source="output_recovery",
                malformed_action_retries=0,
                audit_marker_retries=0,
            )

        if invalid_kind == "internal_summary_instead_of_final_answer":
            self.stage_logger.log("output_recovery", "continue", reason=invalid_kind, universe=self._intent_universe_label())
            return OutputRecoveryDecision.continue_with(
                self.prompt_builder.build_internal_summary_instead_of_final_answer_prompt(),
                reason=invalid_kind,
                source="output_recovery",
                malformed_action_retries=0,
                audit_marker_retries=0,
            )

        if invalid_kind == "modify_completion_claim_without_state_change_proof":
            self.stage_logger.log("output_recovery", "continue", reason=invalid_kind, universe=self._intent_universe_label())
            return OutputRecoveryDecision.continue_with(
                self.prompt_builder.build_modify_completion_claim_without_proof_prompt(),
                reason=invalid_kind,
                source="output_recovery",
                malformed_action_retries=0,
                audit_marker_retries=0,
            )

        if invalid_kind == "intent_only_without_next_step":
            self.stage_logger.log("output_recovery", "continue", reason=invalid_kind, universe=self._intent_universe_label())
            return OutputRecoveryDecision.continue_with(
                self.prompt_builder.build_intent_only_without_next_step_prompt(),
                reason=invalid_kind,
                source="output_recovery",
                malformed_action_retries=0,
                audit_marker_retries=0,
            )

        if invalid_kind == "transition_bundle_too_dense":
            self.stage_logger.log("output_recovery", "continue", reason=invalid_kind, universe="transition_in_progress")
            return OutputRecoveryDecision.continue_with(
                self.prompt_builder.build_transition_bundle_too_dense_prompt(),
                reason=invalid_kind,
                source="output_recovery",
                malformed_action_retries=0,
                audit_marker_retries=0,
            )

        return OutputRecoveryDecision.pass_through(
            reason="unhandled_invalid_kind",
            source="output_recovery",
            malformed_action_retries=0,
            audit_marker_retries=0,
        )