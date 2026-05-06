"""Invalid-kind routing for output-recovery decisions."""

from __future__ import annotations

from ..shared.decision_models import OutputRecoveryDecision, ParsedModelOutput


class OutputRecoveryRoutingMixin:
    COMPILER_INVALID_KIND_BY_CODE = {
        "E_UNCLOSED_THINK": "malformed_incomplete_think",
        "E_ACTION_INSIDE_THINK": "action_inside_think",
        "E_INTENT_INSIDE_THINK": "intent_inside_think",
        "E_FILE_CONTENT_INSIDE_THINK": "file_content_inside_think",
        "E_FILE_CONTENT_UNCLOSED": "malformed_incomplete_file_content",
        "E_MIXED_VISIBLE_TEXT_AND_CONTROL": "mixed_visible_text_and_control_protocol",
        "E_FILE_CONTENT_REQUIRES_ACTION": "file_content_must_follow_action",
    }
    COMPILER_ROUTED_INVALID_KINDS = {
        "malformed_incomplete_think",
        "action_inside_think",
        "intent_inside_think",
        "file_content_inside_think",
        "malformed_incomplete_file_content",
        "mixed_visible_text_and_control_protocol",
        "action_payload_array",
        "multiple_actions",
        "file_content_must_follow_action",
    }

    async def decide(
        self,
        parsed_output: ParsedModelOutput,
        *,
        malformed_action_retries: int,
        audit_marker_retries: int,
    ) -> OutputRecoveryDecision:
        self._last_parsed_output_for_handoff = parsed_output
        invalid_kind = self._resolved_invalid_kind(parsed_output)
        compiler_strategy_decision = self._compiler_strategy_decision(
            parsed_output,
            invalid_kind=invalid_kind,
            malformed_action_retries=malformed_action_retries,
            audit_marker_retries=audit_marker_retries,
        )
        if compiler_strategy_decision is not None:
            return compiler_strategy_decision
        missing_durable_checkpoint = self._is_missing_durable_state_checkpoint(parsed_output)
        state_changing_without_reflection = False
        raw_chars = len(str(getattr(parsed_output, "response", "") or ""))

        if not missing_durable_checkpoint and not self._state_changing_action_missing_operational_review(parsed_output):
            self._clear_missing_think_reflection_warning()

        if not invalid_kind and self._is_internal_summary_instead_of_final_answer(parsed_output):
            invalid_kind = "internal_summary_instead_of_final_answer"
        if not invalid_kind and self._build_fix_final_answer_missing_build_status(parsed_output):
            invalid_kind = "build_fix_final_answer_missing_build_status"
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
            if self._has_any_action_proposal(parsed_output) and self.semantics.has_complete_think_before_action(
                str(getattr(parsed_output, "response", "") or "")
            ):
                self._clear_malformed_think_count()
            self._clear_compiler_recovery_fingerprint()
            self._clear_architecture_defect_repeat()
            self._clear_recovery_loop_handoff_repeat()
            self._clear_large_malformed_response()
            self.stage_logger.log("output_recovery", "pass")
            return OutputRecoveryDecision.pass_through(
                reason="no_invalid_kind",
                source="output_recovery",
                malformed_action_retries=0,
                audit_marker_retries=0,
            )

        if invalid_kind in {
            "malformed_incomplete_think",
            "nested_think",
            "action_inside_think",
            "file_content_inside_think",
            "intent_inside_think",
            "malformed_incomplete_file_content",
        } and raw_chars > 10000:
            large_count = self._note_large_malformed_response(invalid_kind)
            if large_count >= 2:
                return self._terminal_large_malformed_response_decision(
                    invalid_kind=invalid_kind,
                    raw_chars=raw_chars,
                    parsed_output=parsed_output,
                )

        if invalid_kind == "malformed_action":
            next_retries = malformed_action_retries + 1
            if self.logger:
                self.logger.warning(
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

        if invalid_kind in {
            "malformed_incomplete_think",
            "nested_think",
            "action_inside_think",
            "file_content_inside_think",
            "intent_inside_think",
        }:
            repeat_count = self._note_malformed_think_count(invalid_kind)
            if repeat_count >= 3:
                return self._terminal_malformed_think_handoff_decision(invalid_kind)
            if repeat_count >= 2:
                prompt = self.prompt_builder.build_exact_think_skeleton_prompt()
            else:
                prompt = self.prompt_builder.build_incomplete_think_recovery_prompt()
            self.stage_logger.log(
                "output_recovery",
                "continue",
                reason=invalid_kind,
                universe=self._intent_universe_label(),
                repeat_count=repeat_count,
            )
            return OutputRecoveryDecision.continue_with(
                prompt,
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

        if invalid_kind == "file_content_must_follow_action":
            self.stage_logger.log(
                "output_recovery",
                "continue",
                reason=invalid_kind,
                universe=self._intent_universe_label(),
            )
            return OutputRecoveryDecision.continue_with(
                self.prompt_builder.build_file_content_must_follow_action_prompt(),
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

        if invalid_kind == "mixed_visible_text_and_control_protocol":
            builder = getattr(self.prompt_builder, "build_mixed_visible_text_and_control_protocol_prompt", None)
            prompt = (
                builder()
                if callable(builder)
                else (
                    "SYSTEM: Your response mixed a user-visible answer with internal protocol/tool use.\n"
                    "Choose exactly one:\n"
                    "1. Return only the final plain-text answer, with no <think>, <intent>, <action>, or other control tags.\n"
                    "2. Or return internal protocol only: optional <think>, then memory/subgoal tags if needed, <memory_update_done />, and exactly one <action>.\n"
                    "Do not put visible prose before internal protocol."
                )
            )
            self.stage_logger.log(
                "output_recovery",
                "continue",
                reason=invalid_kind,
                universe=self._intent_universe_label(),
            )
            return OutputRecoveryDecision.continue_with(
                prompt,
                reason=invalid_kind,
                source="output_recovery",
                malformed_action_retries=0,
                audit_marker_retries=0,
            )

        if invalid_kind == "mixed_intent_transition_and_visible_answer":
            builder = getattr(self.prompt_builder, "build_mixed_intent_transition_and_visible_answer_prompt", None)
            prompt = (
                builder()
                if callable(builder)
                else (
                    "SYSTEM: Your response mixed an intent transition with user-visible answer text in the same step.\n"
                    "Choose exactly one valid shape:\n"
                    "1. Return only the required top-level <intent> transition.\n"
                    "2. Or return only the final plain-text answer, with no <intent>, <action>, or other control tags.\n"
                    "3. Or return a valid atomic intent/action bundle if the next step truly needs tool use.\n"
                    "Do not put user-visible prose after an intent transition.\n"
                    "Return the corrected response from the beginning."
                )
            )
            self.stage_logger.log(
                "output_recovery",
                "continue",
                reason=invalid_kind,
                universe=self._intent_universe_label(),
            )
            return OutputRecoveryDecision.continue_with(
                prompt,
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

        if invalid_kind == "control_tag_leak_in_visible_text":
            self.stage_logger.log(
                "output_recovery",
                "continue",
                reason=invalid_kind,
                universe=self._intent_universe_label(),
            )
            return OutputRecoveryDecision.continue_with(
                self.prompt_builder.build_control_tag_leak_recovery_prompt(),
                reason=invalid_kind,
                source="output_recovery",
                malformed_action_retries=0,
                audit_marker_retries=0,
            )

        if invalid_kind == "audit_marker_echo":
            next_retries = audit_marker_retries + 1
            if self.logger:
                self.logger.warning(
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
                loop_count = self._note_recovery_loop_handoff_repeat(invalid_kind)
                if loop_count >= 3:
                    return self._terminal_recovery_loop_decision(invalid_kind)
                self.stage_logger.log_architecture_defect(
                    invalid_kind,
                    "loop_breaker_triggered",
                    source_stage="output_recovery",
                    universe=self._intent_universe_label(),
                    repeat_count=repeat_count,
                    loop_count=loop_count,
                )
                self.stage_logger.log(
                    "output_recovery",
                    "continue",
                    reason="recovery_loop_detected",
                    universe=self._intent_universe_label(),
                    repeat_count=repeat_count,
                    loop_count=loop_count,
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

        if invalid_kind == "build_fix_final_answer_missing_build_status":
            self.stage_logger.log("output_recovery", "continue", reason=invalid_kind, universe=self._intent_universe_label())
            return OutputRecoveryDecision.continue_with(
                self.prompt_builder.build_build_fix_final_answer_missing_build_status_prompt(),
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

        if invalid_kind == "action_payload_array":
            self.stage_logger.log("output_recovery", "continue", reason=invalid_kind, universe=self._intent_universe_label())
            return OutputRecoveryDecision.continue_with(
                self.prompt_builder.build_action_payload_array_prompt(),
                reason=invalid_kind,
                source="output_recovery",
                malformed_action_retries=0,
                audit_marker_retries=0,
            )

        if invalid_kind == "intent_body_contains_action":
            self.stage_logger.log("output_recovery", "continue", reason=invalid_kind, universe="transition_in_progress")
            return OutputRecoveryDecision.continue_with(
                self.prompt_builder.build_intent_body_contains_action_prompt(),
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

    def _resolved_invalid_kind(self, parsed_output: ParsedModelOutput) -> str:
        legacy_invalid_kind = str(getattr(parsed_output, "invalid_kind", "") or "").strip()
        compiler_code = str(getattr(parsed_output, "compiler_error_code", "") or "").strip()
        compiler_invalid_kind = self._compiler_invalid_kind_from_output(parsed_output)
        if compiler_invalid_kind and (not legacy_invalid_kind or legacy_invalid_kind in self.COMPILER_ROUTED_INVALID_KINDS):
            return compiler_invalid_kind
        if legacy_invalid_kind:
            return legacy_invalid_kind
        if compiler_code and compiler_invalid_kind:
            return compiler_invalid_kind
        return ""

    def _compiler_invalid_kind_from_output(self, parsed_output: ParsedModelOutput) -> str:
        compiler_code = str(getattr(parsed_output, "compiler_error_code", "") or "").strip()
        if compiler_code == "E_ATOMIC_BUNDLE_REQUIRES_EXACTLY_ONE_ACTION":
            recovery_id = str(getattr(parsed_output, "compiler_recovery_id", "") or "").strip()
            response_text = str(getattr(parsed_output, "response", "") or "")
            if self._compiler_action_array_hint(parsed_output, response_text=response_text, recovery_id=recovery_id):
                return "action_payload_array"
            return "multiple_actions"
        return self.COMPILER_INVALID_KIND_BY_CODE.get(compiler_code, "")

    def _compiler_action_array_hint(self, parsed_output: ParsedModelOutput, *, response_text: str, recovery_id: str) -> bool:
        legacy_invalid_kind = str(getattr(parsed_output, "invalid_kind", "") or "").strip()
        if legacy_invalid_kind == "action_payload_array":
            return True
        if recovery_id == "atomic_bundle_exactly_one_action":
            compact = "".join(str(response_text or "").split())
            if "<action>[" in compact.lower():
                return True
        return False

    def _compiler_strategy_decision(
        self,
        parsed_output: ParsedModelOutput,
        *,
        invalid_kind: str,
        malformed_action_retries: int,
        audit_marker_retries: int,
    ) -> OutputRecoveryDecision | None:
        registry = getattr(self, "compiler_recovery_registry", None)
        if registry is None:
            return None
        compiler_code = str(getattr(parsed_output, "compiler_error_code", "") or "").strip()
        compiler_recovery_id = str(getattr(parsed_output, "compiler_recovery_id", "") or "").strip()
        if not compiler_code:
            return None
        strategy = registry.resolve(
            error_code=compiler_code,
            recovery_id=compiler_recovery_id,
            invalid_kind=invalid_kind,
        )
        if strategy is None:
            return None
        handler = getattr(self, f"_compiler_strategy_{strategy.handler_key}", None)
        if not callable(handler):
            return None
        return handler(
            parsed_output,
            invalid_kind=invalid_kind,
            malformed_action_retries=malformed_action_retries,
            audit_marker_retries=audit_marker_retries,
        )

    def _compiler_strategy_malformed_think(
        self,
        parsed_output: ParsedModelOutput,
        *,
        invalid_kind: str,
        malformed_action_retries: int,
        audit_marker_retries: int,
    ) -> OutputRecoveryDecision:
        raw_chars = len(str(getattr(parsed_output, "response", "") or ""))
        if raw_chars > 10000:
            large_count = self._note_large_malformed_response(invalid_kind)
            if large_count >= 2:
                return self._terminal_large_malformed_response_decision(
                    invalid_kind=invalid_kind,
                    raw_chars=raw_chars,
                    parsed_output=parsed_output,
                )
        repeat_count = self._note_malformed_think_count(invalid_kind)
        if repeat_count >= 3:
            return self._terminal_malformed_think_handoff_decision(invalid_kind)
        prompt = (
            self.prompt_builder.build_exact_think_skeleton_prompt()
            if repeat_count >= 2
            else self.prompt_builder.build_incomplete_think_recovery_prompt()
        )
        self.stage_logger.log(
            "output_recovery",
            "continue",
            reason=invalid_kind,
            source="compiler_recovery_strategy",
            universe=self._intent_universe_label(),
            repeat_count=repeat_count,
            compiler_error_code=str(getattr(parsed_output, "compiler_error_code", "") or ""),
            compiler_recovery_id=str(getattr(parsed_output, "compiler_recovery_id", "") or ""),
        )
        return OutputRecoveryDecision.continue_with(
            prompt,
            reason=invalid_kind,
            source="compiler_recovery_strategy",
            malformed_action_retries=malformed_action_retries,
            audit_marker_retries=audit_marker_retries,
        )

    def _compiler_strategy_incomplete_file_content(
        self,
        parsed_output: ParsedModelOutput,
        *,
        invalid_kind: str,
        malformed_action_retries: int,
        audit_marker_retries: int,
    ) -> OutputRecoveryDecision:
        self.stage_logger.log(
            "output_recovery",
            "continue",
            reason=invalid_kind,
            source="compiler_recovery_strategy",
            universe=self._intent_universe_label(),
            compiler_error_code=str(getattr(parsed_output, "compiler_error_code", "") or ""),
            compiler_recovery_id=str(getattr(parsed_output, "compiler_recovery_id", "") or ""),
        )
        return OutputRecoveryDecision.continue_with(
            self.prompt_builder.build_incomplete_file_content_recovery_prompt(),
            reason=invalid_kind,
            source="compiler_recovery_strategy",
            malformed_action_retries=malformed_action_retries,
            audit_marker_retries=audit_marker_retries,
        )

    def _compiler_strategy_mixed_visible_control(
        self,
        parsed_output: ParsedModelOutput,
        *,
        invalid_kind: str,
        malformed_action_retries: int,
        audit_marker_retries: int,
    ) -> OutputRecoveryDecision:
        repeat_fingerprint = self._compiler_repeat_fingerprint(parsed_output, invalid_kind=invalid_kind)
        repeat_count = self._note_compiler_recovery_fingerprint(repeat_fingerprint)
        builder = getattr(self.prompt_builder, "build_mixed_visible_text_and_control_protocol_prompt", None)
        prompt = (
            builder()
            if callable(builder)
            else (
                "SYSTEM: Your response mixed a user-visible answer with internal protocol/tool use.\n"
                "Choose exactly one:\n"
                "1. Return only the final plain-text answer, with no <think>, <intent>, <action>, or other control tags.\n"
                "2. Or return internal protocol only: optional <think>, then memory/subgoal tags if needed, <memory_update_done />, and exactly one <action>.\n"
                "Do not put visible prose before internal protocol."
            )
        )
        if repeat_count >= 2:
            prompt += (
                "\nSYSTEM: This same protocol shape error happened again."
                "\nReturn exactly one shape only."
                "\nDo not mix visible prose with any control block."
            )
        if repeat_count >= 3:
            return self._terminal_recovery_loop_decision(invalid_kind)
        self.stage_logger.log(
            "output_recovery",
            "continue",
            reason=invalid_kind,
            source="compiler_recovery_strategy",
            universe=self._intent_universe_label(),
            repeat_count=repeat_count,
            repeat_fingerprint=repeat_fingerprint,
            compiler_error_code=str(getattr(parsed_output, "compiler_error_code", "") or ""),
            compiler_recovery_id=str(getattr(parsed_output, "compiler_recovery_id", "") or ""),
        )
        return OutputRecoveryDecision.continue_with(
            prompt,
            reason=invalid_kind,
            source="compiler_recovery_strategy",
            malformed_action_retries=malformed_action_retries,
            audit_marker_retries=audit_marker_retries,
        )

    def _compiler_strategy_file_content_order(
        self,
        parsed_output: ParsedModelOutput,
        *,
        invalid_kind: str,
        malformed_action_retries: int,
        audit_marker_retries: int,
    ) -> OutputRecoveryDecision:
        self.stage_logger.log(
            "output_recovery",
            "continue",
            reason=invalid_kind,
            source="compiler_recovery_strategy",
            universe=self._intent_universe_label(),
            compiler_error_code=str(getattr(parsed_output, "compiler_error_code", "") or ""),
            compiler_recovery_id=str(getattr(parsed_output, "compiler_recovery_id", "") or ""),
        )
        return OutputRecoveryDecision.continue_with(
            self.prompt_builder.build_file_content_must_follow_action_prompt(),
            reason=invalid_kind,
            source="compiler_recovery_strategy",
            malformed_action_retries=malformed_action_retries,
            audit_marker_retries=audit_marker_retries,
        )

    def _compiler_strategy_action_array(
        self,
        parsed_output: ParsedModelOutput,
        *,
        invalid_kind: str,
        malformed_action_retries: int,
        audit_marker_retries: int,
    ) -> OutputRecoveryDecision:
        repeat_fingerprint = self._compiler_repeat_fingerprint(parsed_output, invalid_kind=invalid_kind)
        repeat_count = self._note_compiler_recovery_fingerprint(repeat_fingerprint)
        if repeat_count >= 3:
            return self._terminal_recovery_loop_decision(invalid_kind)
        prompt = self.prompt_builder.build_action_payload_array_prompt()
        if repeat_count >= 2:
            prompt = (
                "SYSTEM: The same atomic bundle action-shape error happened again.\n"
                "Return only one valid <intent mode=\"activate\">...</intent> block now.\n"
                "Do not include <action>, <file_content>, visible text, or multiple blocks.\n"
                "Do not return an action array."
            )
        self.stage_logger.log(
            "output_recovery",
            "continue",
            reason=invalid_kind,
            source="compiler_recovery_strategy",
            universe=self._intent_universe_label(),
            repeat_count=repeat_count,
            repeat_fingerprint=repeat_fingerprint,
            compiler_error_code=str(getattr(parsed_output, "compiler_error_code", "") or ""),
            compiler_recovery_id=str(getattr(parsed_output, "compiler_recovery_id", "") or ""),
        )
        return OutputRecoveryDecision.continue_with(
            prompt,
            reason=invalid_kind,
            source="compiler_recovery_strategy",
            malformed_action_retries=malformed_action_retries,
            audit_marker_retries=audit_marker_retries,
        )

    def _compiler_strategy_multiple_actions(
        self,
        parsed_output: ParsedModelOutput,
        *,
        invalid_kind: str,
        malformed_action_retries: int,
        audit_marker_retries: int,
    ) -> OutputRecoveryDecision:
        repeat_fingerprint = self._compiler_repeat_fingerprint(parsed_output, invalid_kind=invalid_kind)
        repeat_count = self._note_compiler_recovery_fingerprint(repeat_fingerprint)
        if repeat_count >= 3:
            return self._terminal_recovery_loop_decision(invalid_kind)
        prompt = self.prompt_builder.build_multiple_actions_prompt()
        if repeat_count >= 2:
            prompt = (
                "SYSTEM: The same atomic bundle action-shape error happened again.\n"
                "Return only one valid <intent mode=\"activate\">...</intent> block now.\n"
                "Do not include <action>, <file_content>, visible text, or multiple blocks.\n"
                "Do not return multiple <action> blocks."
            )
        self.stage_logger.log(
            "output_recovery",
            "continue",
            reason=invalid_kind,
            source="compiler_recovery_strategy",
            universe=self._intent_universe_label(),
            repeat_count=repeat_count,
            repeat_fingerprint=repeat_fingerprint,
            compiler_error_code=str(getattr(parsed_output, "compiler_error_code", "") or ""),
            compiler_recovery_id=str(getattr(parsed_output, "compiler_recovery_id", "") or ""),
        )
        return OutputRecoveryDecision.continue_with(
            prompt,
            reason=invalid_kind,
            source="compiler_recovery_strategy",
            malformed_action_retries=malformed_action_retries,
            audit_marker_retries=audit_marker_retries,
        )

    def _compiler_repeat_fingerprint(self, parsed_output: ParsedModelOutput, *, invalid_kind: str) -> str:
        compiler_code = str(getattr(parsed_output, "compiler_error_code", "") or "").strip()
        compiler_recovery_id = str(getattr(parsed_output, "compiler_recovery_id", "") or "").strip()
        return "|".join(
            part
            for part in (
                compiler_code,
                compiler_recovery_id,
                str(invalid_kind or "").strip(),
            )
            if part
        )
