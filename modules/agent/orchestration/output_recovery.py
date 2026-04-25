"""Recovery decisions for invalid or incomplete model outputs before dispatch."""

from __future__ import annotations

import re

from .decision_models import OutputRecoveryDecision, ParsedModelOutput
from .response_semantics import ResponseSemantics
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
        self.semantics = ResponseSemantics()

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

    def _set_reflection_repair_pending(self, value: bool, kind: str = "") -> None:
        try:
            setattr(self.state, "think_reflection_repair_pending", bool(value))
            setattr(self.state, "think_reflection_repair_kind", str(kind or "").strip() if value else "")
        except Exception:
            pass

    def _current_active_intent_id(self) -> str:
        active_intent = getattr(self.state, "active_intent", None)
        return str(getattr(active_intent, "intent_id", "") or "").strip()

    def _note_missing_think_reflection_warning(self) -> int:
        intent_id = self._current_active_intent_id()
        current_intent_id = str(getattr(self.state, "missing_think_reflection_warning_intent_id", "") or "").strip()
        current_count = int(getattr(self.state, "missing_think_reflection_warning_count", 0) or 0)
        if not intent_id or intent_id != current_intent_id:
            current_count = 0
        current_count += 1
        try:
            setattr(self.state, "missing_think_reflection_warning_count", current_count)
            setattr(self.state, "missing_think_reflection_warning_intent_id", intent_id)
        except Exception:
            pass
        return current_count

    def _clear_missing_think_reflection_warning(self) -> None:
        try:
            setattr(self.state, "missing_think_reflection_warning_count", 0)
            setattr(self.state, "missing_think_reflection_warning_intent_id", "")
        except Exception:
            pass

    def _has_followup_output(self, parsed_output: ParsedModelOutput) -> bool:
        if bool(getattr(parsed_output, "has_action_segment", False)):
            return True
        if bool(getattr(parsed_output, "has_intent_segment", False)):
            return True
        return bool(str(getattr(parsed_output, "visible_text", "") or "").strip())

    def _is_missing_durable_state_checkpoint(self, parsed_output: ParsedModelOutput) -> bool:
        text = str(getattr(parsed_output, "response", "") or "").strip()
        if not text:
            return False
        if bool(getattr(parsed_output, "operational_checkpoint_satisfied", False)):
            return False
        if not self.semantics.has_substantial_think(text):
            return False
        if not self._has_followup_output(parsed_output):
            return False
        return self.semantics.substantial_think_without_reflection(text)

    def _is_missing_memory_update_done(self, parsed_output: ParsedModelOutput) -> bool:
        text = str(getattr(parsed_output, "response", "") or "").strip()
        if not text:
            return False
        if bool(getattr(parsed_output, "operational_checkpoint_satisfied", False)):
            return False
        if self.semantics.has_memory_update_done(text):
            return False
        if self._is_missing_durable_state_checkpoint(parsed_output):
            return False
        return self.semantics.has_checkpoint_tags(text)

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

    def _is_read_only_shell(self, command_text: str) -> bool:
        lowered = str(command_text or "").strip().lower()
        if not lowered:
            return False
        if any(tok in lowered for tok in (">", "| tee", ">>", "sed -i", "perl -i", "mkdir ", "rm ", "mv ", "cp ", "touch ")):
            return False
        bins = ("find ", "rg ", "grep ", "ls ", "cat ", "head ", "tail ", "wc ", "stat ", "file ", "pwd", "pwd ", "awk ", "sed -n")
        return lowered.startswith(bins)

    def _is_state_changing_action(self, content: dict) -> bool:
        if not isinstance(content, dict):
            return False
        cmd_type = str(content.get("type") or content.get("action") or "").strip().lower()
        if cmd_type in {"edit_file", "create_file", "write_file", "write_file_block", "append_file_block", "delete_file", "replace", "git_add", "git_commit", "git_checkout"}:
            return True
        if cmd_type != "run_shell":
            return False
        return not self._is_read_only_shell(str(content.get("command") or ""))

    def _has_state_changing_action(self, parsed_output: ParsedModelOutput) -> bool:
        for seg in list(getattr(parsed_output, "segments", []) or []):
            if getattr(seg, "type", "") != "action":
                continue
            if self._is_state_changing_action(getattr(seg, "content", None)):
                return True
        return False

    def _state_changing_action_missing_operational_review(self, parsed_output: ParsedModelOutput) -> bool:
        text = str(getattr(parsed_output, "response", "") or "").strip()
        if not text:
            return False
        if not self._is_modify_context():
            return False
        if not self._has_state_changing_action(parsed_output):
            return False
        if bool(getattr(parsed_output, "operational_checkpoint_satisfied", False)):
            return False
        return not self.semantics.has_valid_state_changing_review_before_action(text)

    def _state_changing_modify_checkpoint_reason(self, parsed_output: ParsedModelOutput) -> str:
        text = str(getattr(parsed_output, "response", "") or "").strip()
        if not text:
            return ""
        if not self._is_modify_context():
            return ""
        if not self._has_state_changing_action(parsed_output):
            return ""
        if bool(getattr(parsed_output, "operational_checkpoint_satisfied", False)):
            return ""

        has_plain_think = self.semantics.has_plain_think_prefix(text)
        has_tagged_think = bool(
            getattr(parsed_output, "operational_checkpoint_has_think", False)
            or self.semantics.has_complete_think_before_action(text)
        )
        has_marker = bool(
            getattr(parsed_output, "operational_checkpoint_has_marker", False)
            or self.semantics.has_memory_update_done_before_action(text)
        )
        has_board_commit = bool(getattr(parsed_output, "operational_checkpoint_has_board_commit", False))
        has_tags = bool(
            getattr(parsed_output, "operational_checkpoint_has_tags", False)
            or self.semantics.has_checkpoint_before_action(text)
        )
        if has_tagged_think and has_marker and (has_board_commit or has_tags):
            return ""

        if has_plain_think and not has_tagged_think:
            return "malformed_plain_think_requires_tagged_think"
        if not has_tagged_think:
            return "missing_think"
        if (has_board_commit or has_tags) and not has_marker:
            return "missing_memory_update_done"
        if not has_board_commit and not has_tags:
            return "no_accepted_checkpoint_tags"
        return "malformed_checkpoint"

    def _note_architecture_defect_repeat(self, defect_kind: str) -> int:
        normalized = str(defect_kind or "").strip()
        if not normalized:
            return 0
        current_kind = str(getattr(self.state, "architecture_defect_repeat_kind", "") or "").strip()
        current_count = int(getattr(self.state, "architecture_defect_repeat_count", 0) or 0)
        if current_kind != normalized:
            current_count = 0
        current_count += 1
        try:
            setattr(self.state, "architecture_defect_repeat_kind", normalized)
            setattr(self.state, "architecture_defect_repeat_count", current_count)
        except Exception:
            pass
        return current_count

    def _clear_architecture_defect_repeat(self) -> None:
        try:
            setattr(self.state, "architecture_defect_repeat_kind", "")
            setattr(self.state, "architecture_defect_repeat_count", 0)
        except Exception:
            pass

    def _is_checkpoint_defect_kind(self, invalid_kind: str) -> bool:
        return str(invalid_kind or "").strip() in {
            "missing_think",
            "missing_memory_update_done",
            "no_accepted_checkpoint_tags",
            "malformed_plain_think_requires_tagged_think",
            "malformed_checkpoint",
            "state_changing_action_requires_think_reflection",
        }

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
        missing_durable_checkpoint = self._is_missing_durable_state_checkpoint(parsed_output)
        state_changing_without_reflection = False

        if not missing_durable_checkpoint and not self._state_changing_action_missing_operational_review(parsed_output):
            self._clear_missing_think_reflection_warning()

        if not invalid_kind and self._is_internal_summary_instead_of_final_answer(parsed_output):
            invalid_kind = "internal_summary_instead_of_final_answer"
        if not invalid_kind and self._is_unproven_modify_completion_claim(parsed_output):
            invalid_kind = "modify_completion_claim_without_state_change_proof"
        if not invalid_kind:
            checkpoint_reason = self._state_changing_modify_checkpoint_reason(parsed_output)
            if checkpoint_reason:
                invalid_kind = checkpoint_reason
        if not invalid_kind and self._state_changing_action_missing_operational_review(parsed_output):
            invalid_kind = "malformed_checkpoint"
            state_changing_without_reflection = True
        if not invalid_kind and missing_durable_checkpoint:
            if self._is_modify_context() and self._has_state_changing_action(parsed_output):
                invalid_kind = "state_changing_action_requires_think_reflection"
                state_changing_without_reflection = True
            elif self._is_modify_context():
                warning_count = self._note_missing_think_reflection_warning()
                if warning_count >= 2:
                    invalid_kind = "missing_think_reflection"
                else:
                    self.stage_logger.log_architecture_defect(
                        "missing_think_reflection",
                        "warning_detected",
                        source_stage="output_recovery",
                        universe=self._intent_universe_label(),
                        escalation="modify_first_warning_non_blocking",
                    )
                    self.stage_logger.log(
                        "output_recovery",
                        "pass",
                        reason="missing_think_reflection_detected_non_blocking",
                        universe=self._intent_universe_label(),
                    )
                    return OutputRecoveryDecision.pass_through(
                        reason="missing_think_reflection_detected_non_blocking",
                        source="output_recovery",
                        malformed_action_retries=0,
                        audit_marker_retries=0,
                    )
            else:
                self.stage_logger.log_architecture_defect(
                    "missing_think_reflection",
                    "warning_detected",
                    source_stage="output_recovery",
                    universe=self._intent_universe_label(),
                    escalation="non_modify_non_blocking",
                )
                self.stage_logger.log(
                    "output_recovery",
                    "pass",
                    reason="missing_think_reflection_detected_non_blocking",
                    universe=self._intent_universe_label(),
                )
                return OutputRecoveryDecision.pass_through(
                    reason="missing_think_reflection_detected_non_blocking",
                    source="output_recovery",
                    malformed_action_retries=0,
                    audit_marker_retries=0,
                )
        if not invalid_kind and self._is_missing_memory_update_done(parsed_output):
            invalid_kind = "missing_memory_update_done"
        if not invalid_kind:
            self._clear_architecture_defect_repeat()
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

        if invalid_kind == "malformed_incomplete_think":
            self.stage_logger.log(
                "output_recovery",
                "continue",
                reason=invalid_kind,
                universe=self._intent_universe_label(),
            )
            return OutputRecoveryDecision.continue_with(
                self.prompt_builder.build_incomplete_think_recovery_prompt(),
                reason=invalid_kind,
                source="output_recovery",
                malformed_action_retries=0,
                audit_marker_retries=0,
            )

        if invalid_kind == "malformed_incomplete_action":
            self.stage_logger.log(
                "output_recovery",
                "continue",
                reason=invalid_kind,
                universe=self._intent_universe_label(),
            )
            return OutputRecoveryDecision.continue_with(
                self.prompt_builder.build_incomplete_action_recovery_prompt(),
                reason=invalid_kind,
                source="output_recovery",
                malformed_action_retries=0,
                audit_marker_retries=0,
            )

        if invalid_kind == "malformed_incomplete_intent":
            self.stage_logger.log(
                "output_recovery",
                "continue",
                reason=invalid_kind,
                universe=self._intent_universe_label(),
            )
            return OutputRecoveryDecision.continue_with(
                self.prompt_builder.build_incomplete_intent_recovery_prompt(),
                reason=invalid_kind,
                source="output_recovery",
                malformed_action_retries=0,
                audit_marker_retries=0,
            )

        if invalid_kind == "malformed_incomplete_file_content":
            self.stage_logger.log(
                "output_recovery",
                "continue",
                reason=invalid_kind,
                universe=self._intent_universe_label(),
            )
            return OutputRecoveryDecision.continue_with(
                self.prompt_builder.build_incomplete_file_content_recovery_prompt(),
                reason=invalid_kind,
                source="output_recovery",
                malformed_action_retries=0,
                audit_marker_retries=0,
            )

        if invalid_kind == "truncated_internal_response":
            self.stage_logger.log(
                "output_recovery",
                "continue",
                reason=invalid_kind,
                universe=self._intent_universe_label(),
            )
            return OutputRecoveryDecision.continue_with(
                self.prompt_builder.build_truncated_internal_response_prompt(),
                reason=invalid_kind,
                source="output_recovery",
                malformed_action_retries=0,
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
            self._set_reflection_repair_pending(True, invalid_kind)
            self.stage_logger.log_architecture_defect(
                invalid_kind,
                "detected",
                source_stage="output_recovery",
                universe=self._intent_universe_label(),
            )
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

        if invalid_kind in {
            "missing_think",
            "missing_memory_update_done",
            "no_accepted_checkpoint_tags",
            "malformed_plain_think_requires_tagged_think",
            "malformed_checkpoint",
            "state_changing_action_requires_think_reflection",
        }:
            self._set_reflection_repair_pending(
                invalid_kind == "missing_memory_update_done",
                invalid_kind if invalid_kind == "missing_memory_update_done" else "",
            )
            repeat_count = self._note_architecture_defect_repeat(invalid_kind)
            board_commit = bool(getattr(parsed_output, "operational_checkpoint_has_board_commit", False))
            has_think = bool(getattr(parsed_output, "operational_checkpoint_has_think", False))
            if repeat_count >= 3:
                if board_commit and has_think:
                    self.stage_logger.log_architecture_defect(
                        invalid_kind,
                        "loop_breaker_override",
                        source_stage="output_recovery",
                        universe=self._intent_universe_label(),
                        repeat_count=repeat_count,
                    )
                    self.stage_logger.log(
                        "output_recovery",
                        "pass",
                        reason="recovery_loop_detected_checkpoint_override",
                        universe=self._intent_universe_label(),
                        repeat_count=repeat_count,
                    )
                    self._clear_architecture_defect_repeat()
                    return OutputRecoveryDecision.pass_through(
                        reason="recovery_loop_detected_checkpoint_override",
                        source="output_recovery",
                        malformed_action_retries=0,
                        audit_marker_retries=0,
                    )
                self.stage_logger.log_architecture_defect(
                    invalid_kind,
                    "loop_breaker_triggered",
                    source_stage="output_recovery",
                    universe=self._intent_universe_label(),
                    repeat_count=repeat_count,
                )
                self.stage_logger.log(
                    "output_recovery",
                    "continue",
                    reason="recovery_loop_detected",
                    universe=self._intent_universe_label(),
                    repeat_count=repeat_count,
                )
                return OutputRecoveryDecision.continue_with(
                    self.prompt_builder.build_recovery_loop_detected_prompt(invalid_kind),
                    reason="recovery_loop_detected",
                    source="output_recovery",
                    malformed_action_retries=0,
                    audit_marker_retries=0,
                )
            self.stage_logger.log_architecture_defect(
                invalid_kind,
                "detected",
                source_stage="output_recovery",
                universe=self._intent_universe_label(),
                action_gate="state_changing_modify_action",
                repeat_count=repeat_count,
            )
            self.stage_logger.log(
                "output_recovery",
                "continue",
                reason=invalid_kind,
                universe=self._intent_universe_label(),
                state_changing_without_reflection=state_changing_without_reflection,
                repeat_count=repeat_count,
            )
            return OutputRecoveryDecision.continue_with(
                self.prompt_builder.build_checkpoint_defect_prompt(invalid_kind),
                reason=invalid_kind,
                source="output_recovery",
                malformed_action_retries=0,
                audit_marker_retries=0,
            )

        if invalid_kind == "missing_action_or_answer":
            retries = self._missing_action_or_answer_retries()
            if bool(getattr(self.state, "think_reflection_repair_pending", False)):
                prompt = self.prompt_builder.build_durable_state_repair_prompt(
                    str(getattr(self.state, "think_reflection_repair_kind", "") or "").strip()
                )
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

        if invalid_kind == "plain_think_without_valid_output":
            self.stage_logger.log(
                "output_recovery",
                "continue",
                reason=invalid_kind,
                universe=self._intent_universe_label(),
            )
            return OutputRecoveryDecision.continue_with(
                self.prompt_builder.build_plain_think_without_valid_output_prompt(),
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

        if invalid_kind == "multiple_actions":
            self.stage_logger.log("output_recovery", "continue", reason=invalid_kind, universe=self._intent_universe_label())
            return OutputRecoveryDecision.continue_with(
                self.prompt_builder.build_multiple_actions_prompt(),
                reason=invalid_kind,
                source="output_recovery",
                malformed_action_retries=0,
                audit_marker_retries=0,
            )

        if invalid_kind == "conflicting_intent_transitions":
            self.stage_logger.log("output_recovery", "continue", reason=invalid_kind, universe="transition_in_progress")
            return OutputRecoveryDecision.continue_with(
                self.prompt_builder.build_conflicting_intent_transitions_prompt(),
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

        if invalid_kind == "intent_complete_with_action_not_allowed":
            self.stage_logger.log("output_recovery", "continue", reason=invalid_kind, universe="transition_in_progress")
            return OutputRecoveryDecision.continue_with(
                self.prompt_builder.build_completion_with_action_not_allowed_prompt(),
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
