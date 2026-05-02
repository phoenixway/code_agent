"""Execution stages for the pre-dispatch response pipeline."""

from __future__ import annotations

from dataclasses import dataclass

from .decision_models import ResponsePipelineOutcome


@dataclass
class CheckpointStageState:
    response: str
    reflection_repair_pending: bool
    reflection_repair_kind: str
    plan_checkpoint_only: bool
    plan_checkpoint_and_text: bool
    plan_checkpoint_and_action: bool
    memory_checkpoint_only: bool
    memory_checkpoint_and_text: bool
    memory_checkpoint_and_action: bool
    memory_board_decision: object


@dataclass
class ClassifiedStageState:
    response: str
    parsed_output: object
    segments: list
    parsed_action_count: int
    checkpoint_has_think: bool
    checkpoint_has_marker: bool
    checkpoint_has_tags: bool
    checkpoint_has_board_commit: bool
    checkpoint_satisfied: bool


class ResponsePipelineStagesMixin:
    async def _run_initial_stages(self, ctx, step):
        raw_response = str(step.response or "")
        normalized = self._normalize_response_stage(
            raw_response,
            allow_autorepair=getattr(step, "intent_payload", None) is None,
            source="run_step",
        )
        raw_response = normalized.normalized_response

        terminal_completion_decision = self._reject_truncated_terminal_completion_before_transition(raw_response, step)
        if terminal_completion_decision is not None:
            return raw_response, None, terminal_completion_decision

        atomicity_decision = await self._reject_invalid_intent_followup_before_transition(ctx, raw_response, step)
        if atomicity_decision is not None:
            return raw_response, None, atomicity_decision

        intent_decision = await self.intent_transitions.handle_model_step(
            intent_payload=step.intent_payload,
            intent_error=step.intent_error,
            response_text=raw_response,
            state_machine=ctx.state_machine,
        )
        if intent_decision.handled:
            self.guards.set_nonproductive_thinking_state(False)
            self.stage_logger.log(
                "response_pipeline",
                "continue",
                reason=intent_decision.reason,
                source="intent_transition",
            )
            return raw_response, None, ResponsePipelineOutcome.continue_with(
                intent_decision.next_query,
                reason=intent_decision.reason,
                source="intent_transition",
            )

        reflection_repair_pending = self.guards.reflection_repair_pending()
        reflection_repair_kind = self.guards.reflection_repair_kind()

        if getattr(self.state, "intent_required_until_activated", False) and "<action" in raw_response.lower():
            self.stage_logger.log(
                "response_pipeline",
                "continue",
                reason=getattr(self.state, "intent_required_reason", "intent_required"),
                source="intent_requirement_gate",
            )
            return raw_response, None, ResponsePipelineOutcome.continue_with(
                self.prompt_builder.build_intent_required_prompt(
                    getattr(self.state, "intent_required_reason", "intent_required")
                ),
                reason=getattr(self.state, "intent_required_reason", "intent_required"),
                source="intent_requirement_gate",
            )

        return raw_response, (reflection_repair_pending, reflection_repair_kind), None

    async def _run_checkpoint_stage(self, ctx, raw_response: str, *, reflection_repair_pending: bool, reflection_repair_kind: str):
        plan_board_decision = await self.plan_board_stage.apply(ctx, raw_response)
        response_after_plan = plan_board_decision.response_text
        plan_checkpoint_only = bool(getattr(plan_board_decision, "plan_checkpoint_only", False))
        plan_checkpoint_and_text = bool(getattr(plan_board_decision, "plan_checkpoint_and_text", False))
        plan_checkpoint_and_action = bool(getattr(plan_board_decision, "plan_checkpoint_and_action", False))
        if plan_board_decision.handled:
            return None, ResponsePipelineOutcome.continue_with(
                plan_board_decision.next_query,
                response_text=response_after_plan,
                reason=plan_board_decision.reason,
                source=plan_board_decision.source,
            )

        memory_board_decision = await self.memory_board_stage.apply(ctx, response_after_plan)
        response = memory_board_decision.response_text
        memory_checkpoint_only = bool(getattr(memory_board_decision, "memory_checkpoint_only", False))
        memory_checkpoint_and_text = bool(getattr(memory_board_decision, "memory_checkpoint_and_text", False))
        memory_checkpoint_and_action = bool(getattr(memory_board_decision, "memory_checkpoint_and_action", False))

        def _repair_checkpoint_completed() -> bool:
            if not bool(getattr(self.state, "last_memory_update_done", False)):
                return False
            if reflection_repair_kind == "missing_memory_update_done":
                return True
            memory_committed = int(getattr(self.state, "last_memory_board_accepted_count", 0) or 0) > 0
            plan_committed = plan_checkpoint_only or plan_checkpoint_and_text or plan_checkpoint_and_action
            return memory_committed or plan_committed

        if reflection_repair_pending and memory_checkpoint_only:
            if _repair_checkpoint_completed():
                self.stage_logger.log_architecture_defect(
                    reflection_repair_kind or "missing_think_reflection",
                    "repair_completed",
                    source_stage="memory_board",
                )
                self.guards.set_reflection_repair_pending(False)
                self.guards.set_nonproductive_thinking_state(False)
                self.stage_logger.log(
                    "response_pipeline",
                    "continue",
                    reason="think_reflection_repair_completed",
                    source="think_reflection_guard",
                )
                return None, ResponsePipelineOutcome.continue_with(
                    self.prompt_builder.build_reflection_repair_accepted_prompt(),
                    response_text=response,
                    reason="think_reflection_repair_completed",
                    source="think_reflection_guard",
                )
            self.stage_logger.log_architecture_defect(
                reflection_repair_kind or "missing_think_reflection",
                "repair_enforced",
                source_stage="memory_board",
            )
            self.stage_logger.log(
                "response_pipeline",
                "continue",
                reason=reflection_repair_kind or "missing_think_reflection",
                source="think_reflection_guard",
            )
            return None, ResponsePipelineOutcome.continue_with(
                self.prompt_builder.build_durable_state_repair_prompt(reflection_repair_kind),
                response_text=response,
                reason=reflection_repair_kind or "missing_think_reflection",
                source="think_reflection_guard",
                memory_checkpoint_only=True,
                memory_checkpoint_and_text=False,
                memory_checkpoint_and_action=False,
            )

        if memory_board_decision.handled and (memory_checkpoint_and_text or memory_checkpoint_and_action):
            self.guards.set_nonproductive_thinking_state(False)
            memory_board_decision.handled = False

        if memory_board_decision.handled:
            if memory_checkpoint_only:
                self.guards.set_reflection_repair_pending(False)
                streak = self.guards.memory_checkpoint_streak()
                if streak >= self.memory_checkpoint_hard_stop_streak:
                    message = (
                        "Execution stopped: repeated memory-checkpoint-only turns without a substantive continuation. "
                        "The model kept updating memory but did not converge to a concrete action or final answer."
                    )
                    try:
                        await self.ui.print_error(message)
                    except Exception:
                        pass
                    self.stage_logger.log(
                        "response_pipeline",
                        "stop",
                        reason="memory_checkpoint_only_hard_stop",
                        source="memory_board",
                        streak=streak,
                    )
                    return None, ResponsePipelineOutcome.stop(
                        response_text=response,
                        reason="memory_checkpoint_only_hard_stop",
                        source="memory_board",
                        malformed_action_retries=0,
                        audit_marker_retries=0,
                        memory_checkpoint_only=True,
                        memory_checkpoint_and_text=False,
                        memory_checkpoint_and_action=False,
                    )
                if self.semantics.has_substantial_think(raw_response):
                    nonproductive_streak = self.guards.set_nonproductive_thinking_state(
                        True, "repeated_thinking_without_valid_output"
                    )
                    if nonproductive_streak >= self.nonproductive_thinking_hard_stop_streak:
                        self.stage_logger.log(
                            "response_pipeline",
                            "continue",
                            reason="repeated_thinking_without_valid_output",
                            source="thinking_guard",
                            streak=nonproductive_streak,
                        )
                        return None, ResponsePipelineOutcome.continue_with(
                            self.prompt_builder.build_repeated_thinking_without_valid_output_prompt(
                                {"reason": "repeated_thinking_without_valid_output"}
                            ),
                            response_text=response,
                            reason="repeated_thinking_without_valid_output",
                            source="thinking_guard",
                            memory_checkpoint_only=memory_checkpoint_only,
                            memory_checkpoint_and_text=memory_checkpoint_and_text,
                            memory_checkpoint_and_action=memory_checkpoint_and_action,
                        )
            return None, ResponsePipelineOutcome.continue_with(
                memory_board_decision.next_query,
                response_text=response,
                reason=memory_board_decision.reason,
                source=memory_board_decision.source,
                memory_checkpoint_only=memory_checkpoint_only,
                memory_checkpoint_and_text=memory_checkpoint_and_text,
                memory_checkpoint_and_action=memory_checkpoint_and_action,
            )

        return CheckpointStageState(
            response=response,
            reflection_repair_pending=reflection_repair_pending,
            reflection_repair_kind=reflection_repair_kind,
            plan_checkpoint_only=plan_checkpoint_only,
            plan_checkpoint_and_text=plan_checkpoint_and_text,
            plan_checkpoint_and_action=plan_checkpoint_and_action,
            memory_checkpoint_only=memory_checkpoint_only,
            memory_checkpoint_and_text=memory_checkpoint_and_text,
            memory_checkpoint_and_action=memory_checkpoint_and_action,
            memory_board_decision=memory_board_decision,
        ), None

    def _run_classification_stage(self, step, raw_response: str, checkpoint_state: CheckpointStageState):
        response = checkpoint_state.response
        segments = self.parser.parse(response)
        parsed_output = self._classify_intent_output(response, segments, allow_think_autorepair=True)
        parsed_output.model_stop_reason = str(getattr(step, "model_stop_reason", "") or "").strip()
        checkpoint_has_think = self.semantics.has_complete_think_before_action(raw_response)
        checkpoint_has_marker = bool(
            getattr(self.state, "last_memory_update_done", False)
            or self.semantics.has_memory_update_done_before_action(raw_response)
        )
        checkpoint_has_tags = self.semantics.has_checkpoint_before_action(raw_response)
        checkpoint_has_board_commit = bool(checkpoint_state.memory_checkpoint_and_action or checkpoint_state.plan_checkpoint_and_action)
        checkpoint_source_satisfied = bool(
            checkpoint_has_board_commit
            or checkpoint_has_marker
        )
        checkpoint_satisfied = bool(
            checkpoint_has_think
            and checkpoint_source_satisfied
        )
        parsed_output.operational_checkpoint_has_think = checkpoint_has_think
        parsed_output.operational_checkpoint_has_marker = checkpoint_has_marker
        parsed_output.operational_checkpoint_has_board_commit = checkpoint_has_board_commit
        parsed_output.operational_checkpoint_has_tags = checkpoint_has_tags
        parsed_output.operational_checkpoint_satisfied = checkpoint_satisfied
        parsed_action_count = sum(1 for seg in segments if getattr(seg, "type", "") == "action")
        self.stage_logger.log(
            "response_pipeline",
            "classified",
            segment_count=len(segments),
            invalid_kind=parsed_output.invalid_kind or "",
            has_action_segment=parsed_output.has_action_segment,
            model_stop_reason=parsed_output.model_stop_reason,
            operational_checkpoint_satisfied=checkpoint_satisfied,
            operational_checkpoint_has_think=checkpoint_has_think,
            operational_checkpoint_has_marker=checkpoint_has_marker,
            operational_checkpoint_has_board_commit=checkpoint_has_board_commit,
            operational_checkpoint_has_tags=checkpoint_has_tags,
            think_repair_applied=bool(getattr(parsed_output, "auto_closed_think", False)),
            think_repair_reason=str(getattr(parsed_output, "auto_closed_think_reason", "") or ""),
            think_repair_tag=str(getattr(parsed_output, "auto_closed_think_tag", "") or ""),
        )
        return ClassifiedStageState(
            response=response,
            parsed_output=parsed_output,
            segments=segments,
            parsed_action_count=parsed_action_count,
            checkpoint_has_think=checkpoint_has_think,
            checkpoint_has_marker=checkpoint_has_marker,
            checkpoint_has_tags=checkpoint_has_tags,
            checkpoint_has_board_commit=checkpoint_has_board_commit,
            checkpoint_satisfied=checkpoint_satisfied,
        )

    async def _run_post_classification_stage(self, ctx, step, checkpoint_state: CheckpointStageState, classified: ClassifiedStageState):
        response = classified.response
        parsed_output = classified.parsed_output
        segments = classified.segments
        parsed_action_count = classified.parsed_action_count
        raw_response = str(step.response or "")
        reflection_repair_pending = checkpoint_state.reflection_repair_pending
        reflection_repair_kind = checkpoint_state.reflection_repair_kind
        memory_checkpoint_and_text = checkpoint_state.memory_checkpoint_and_text
        memory_checkpoint_and_action = checkpoint_state.memory_checkpoint_and_action
        memory_board_decision = checkpoint_state.memory_board_decision

        active_intent = getattr(self.state, "active_intent", None)
        if (
            active_intent is not None
            and bool(getattr(active_intent, "force_plaintext_completion", False))
            and parsed_output.has_action_segment
        ):
            self.guards.set_nonproductive_thinking_state(False)
            self.stage_logger.log(
                "response_pipeline",
                "continue",
                reason="intent_force_plaintext_completion",
                source="force_plaintext_gate",
            )
            return ResponsePipelineOutcome.continue_with(
                self.prompt_builder.build_plain_text_completion_prompt(
                    ctx.state_machine,
                    {
                        "reason": "intent_force_plaintext_completion",
                        "recoverable": True,
                        "error_code": "INTENT_FORCE_PLAINTEXT_COMPLETION",
                        "next_actions": [],
                        "intent_allowed_actions": [],
                        "next_actions_source": "intent",
                    },
                ),
                response_text=response,
                segments=segments,
                parsed_output=parsed_output,
                parsed_action_count=0,
                malformed_action_retries=0,
                audit_marker_retries=0,
                reason="intent_force_plaintext_completion",
                source="force_plaintext_gate",
            )

        if reflection_repair_pending and self.semantics.is_reflection_only_repair_turn(
            raw_response, parsed_output, parsed_action_count
        ):
            self.guards.set_reflection_repair_pending(False)
            self.guards.set_nonproductive_thinking_state(False)
            self.stage_logger.log(
                "response_pipeline",
                "continue",
                reason="think_reflection_repair_completed",
                source="think_reflection_guard",
            )
            return ResponsePipelineOutcome.continue_with(
                self.prompt_builder.build_reflection_repair_accepted_prompt(),
                response_text=response,
                segments=segments,
                parsed_output=parsed_output,
                parsed_action_count=0,
                malformed_action_retries=0,
                audit_marker_retries=0,
                reason="think_reflection_repair_completed",
                source="think_reflection_guard",
            )

        plaintext_answer_path = self.semantics.is_plaintext_answer_path(raw_response, parsed_output, parsed_action_count)
        reflection_only_repair = self.semantics.is_reflection_only_repair_turn(
            raw_response, parsed_output, parsed_action_count
        )

        durable_state_repair = self.semantics.is_durable_state_repair_turn(
            raw_response,
            parsed_output,
            parsed_action_count,
            required_kind=reflection_repair_kind,
        )

        if reflection_repair_pending:
            if durable_state_repair:
                self.stage_logger.log_architecture_defect(
                    reflection_repair_kind or "missing_think_reflection",
                    "repair_completed",
                    source_stage="response_pipeline",
                )
                self.guards.set_reflection_repair_pending(False)
                self.guards.set_nonproductive_thinking_state(False)
                self.stage_logger.log(
                    "response_pipeline",
                    "continue",
                    reason="think_reflection_repair_completed",
                    source="think_reflection_guard",
                )
                return ResponsePipelineOutcome.continue_with(
                    self.prompt_builder.build_reflection_repair_accepted_prompt(),
                    response_text=response,
                    segments=segments,
                    parsed_output=parsed_output,
                    parsed_action_count=0,
                    malformed_action_retries=0,
                    audit_marker_retries=0,
                    reason="think_reflection_repair_completed",
                    source="think_reflection_guard",
                )
            self.stage_logger.log_architecture_defect(
                reflection_repair_kind or "missing_think_reflection",
                "repair_enforced",
                source_stage="response_pipeline",
            )
            self.stage_logger.log(
                "response_pipeline",
                "continue",
                reason=reflection_repair_kind or "missing_think_reflection",
                source="think_reflection_guard",
            )
            return ResponsePipelineOutcome.continue_with(
                self.prompt_builder.build_durable_state_repair_prompt(reflection_repair_kind),
                response_text=response,
                segments=segments,
                parsed_output=parsed_output,
                parsed_action_count=0,
                malformed_action_retries=0,
                audit_marker_retries=0,
                reason=reflection_repair_kind or "missing_think_reflection",
                source="think_reflection_guard",
            )

        if self.guards.is_nonproductive_thinking_turn(
            self.semantics,
            raw_response,
            parsed_output,
            parsed_action_count,
            plaintext_answer_path=plaintext_answer_path,
            intent_transition_handled=False,
            memory_checkpoint_and_action=memory_checkpoint_and_action,
            memory_checkpoint_and_text=memory_checkpoint_and_text,
            reflection_only_repair=reflection_only_repair,
        ):
            nonproductive_streak = self.guards.set_nonproductive_thinking_state(
                True, "repeated_thinking_without_valid_output"
            )
            if nonproductive_streak >= self.nonproductive_thinking_hard_stop_streak:
                self.stage_logger.log(
                    "response_pipeline",
                    "continue",
                    reason="repeated_thinking_without_valid_output",
                    source="thinking_guard",
                    streak=nonproductive_streak,
                )
                return ResponsePipelineOutcome.continue_with(
                    self.prompt_builder.build_repeated_thinking_without_valid_output_prompt(
                        {"reason": "repeated_thinking_without_valid_output"}
                    ),
                    response_text=response,
                    segments=segments,
                    parsed_output=parsed_output,
                    parsed_action_count=parsed_action_count,
                    malformed_action_retries=0,
                    audit_marker_retries=0,
                    reason="repeated_thinking_without_valid_output",
                    source="thinking_guard",
                )
        else:
            self.guards.set_nonproductive_thinking_state(False)

        if (
            memory_checkpoint_and_text
            and parsed_action_count <= 0
            and not bool(getattr(parsed_output, "has_action_segment", False))
        ):
            self.guards.set_reflection_repair_pending(False)
            self.guards.set_nonproductive_thinking_state(False)
            self.stage_logger.log(
                "response_pipeline",
                "dispatch",
                reason="memory_checkpoint_and_text",
                source="memory_board",
                action_count=0,
            )
            return ResponsePipelineOutcome.dispatch_ready(
                response_text=response,
                segments=segments,
                parsed_output=parsed_output,
                parsed_action_count=0,
                malformed_action_retries=0,
                audit_marker_retries=0,
                reason="dispatch_ready",
                source="response_pipeline",
                memory_checkpoint_and_text=True,
            )

        if (
            parsed_action_count <= 0
            and not bool(getattr(parsed_output, "has_action_segment", False))
            and self.semantics.looks_like_leaked_system_result(response)
        ):
            self.guards.set_reflection_repair_pending(False)
            self.guards.set_nonproductive_thinking_state(False)
            self.stage_logger.log(
                "response_pipeline",
                "continue",
                reason="leaked_system_result_in_assistant_text",
                source="output_recovery",
            )
            return ResponsePipelineOutcome.continue_with(
                self.prompt_builder.build_leaked_system_result_recovery_prompt(),
                response_text=response,
                segments=segments,
                parsed_output=parsed_output,
                parsed_action_count=0,
                malformed_action_retries=0,
                audit_marker_retries=0,
                reason="leaked_system_result_in_assistant_text",
                source="output_recovery",
            )

        recovery_decision = await self.output_recovery.decide(
            parsed_output,
            malformed_action_retries=ctx.malformed_action_retries,
            audit_marker_retries=ctx.audit_marker_retries,
        )
        if recovery_decision.handled:
            if bool(getattr(self.state, "terminal_plaintext_completion_pending", False)):
                self.stage_logger.log(
                    "response_pipeline",
                    "stop",
                    reason=recovery_decision.reason or "terminal_plaintext_completion",
                    source="output_recovery",
                )
                return ResponsePipelineOutcome.stop(
                    response_text=response,
                    malformed_action_retries=recovery_decision.malformed_action_retries,
                    audit_marker_retries=recovery_decision.audit_marker_retries,
                    reason=recovery_decision.reason or "terminal_plaintext_completion",
                    source="output_recovery",
                )
            self.stage_logger.log(
                "response_pipeline",
                "continue",
                reason=recovery_decision.reason,
                source="output_recovery",
            )
            return ResponsePipelineOutcome.continue_with(
                recovery_decision.next_query,
                response_text=response,
                segments=segments,
                parsed_output=parsed_output,
                parsed_action_count=parsed_action_count,
                malformed_action_retries=recovery_decision.malformed_action_retries,
                audit_marker_retries=recovery_decision.audit_marker_retries,
                reason=recovery_decision.reason,
                source="output_recovery",
            )

        if str(getattr(parsed_output, "invalid_kind", "") or "").strip() in self.STRUCTURAL_INVALID_KINDS:
            self.stage_logger.log(
                "response_pipeline",
                "continue",
                reason=parsed_output.invalid_kind,
                source="structural_invalid_guard",
            )
            return ResponsePipelineOutcome.continue_with(
                self.prompt_builder.build_missing_action_or_answer_prompt(),
                response_text=response,
                segments=segments,
                parsed_output=parsed_output,
                parsed_action_count=0,
                malformed_action_retries=0,
                audit_marker_retries=0,
                reason=parsed_output.invalid_kind,
                source="structural_invalid_guard",
            )

        action_policy_decision = await self.action_policy.decide(
            ctx,
            segments,
            intent_payload=step.intent_payload,
        )
        parsed_action_count = action_policy_decision.parsed_action_count
        if parsed_action_count > 1 and not self._multiple_actions_are_pure_read_only(segments):
            self.stage_logger.log(
                "response_pipeline",
                "continue",
                reason="multiple_actions",
                source="transaction_guard",
                action_count=parsed_action_count,
            )
            return ResponsePipelineOutcome.continue_with(
                self.prompt_builder.build_multiple_actions_prompt(),
                response_text=response,
                segments=segments,
                parsed_output=parsed_output,
                parsed_action_count=parsed_action_count,
                malformed_action_retries=0,
                audit_marker_retries=0,
                reason="multiple_actions",
                source="transaction_guard",
            )
        if parsed_action_count > 1:
            self.stage_logger.log(
                "response_pipeline",
                "pass",
                reason="pure_readonly_batch_allowed",
                source="transaction_guard",
                action_count=parsed_action_count,
            )
        if parsed_action_count > 0 or bool(getattr(parsed_output, "has_action_segment", False)):
            self.guards.set_nonproductive_thinking_state(False)

        if action_policy_decision.handled:
            if bool(getattr(self.state, "terminal_plaintext_completion_pending", False)):
                terminal_text = self._terminal_plaintext_text_or_empty(
                    str(getattr(self.state, "terminal_plaintext_completion_text", "") or response or "")
                )
                setattr(self.state, "terminal_plaintext_completion_text", terminal_text)
                self.stage_logger.log(
                    "response_pipeline",
                    "stop",
                    reason=action_policy_decision.reason or "terminal_plaintext_completion",
                    source=action_policy_decision.source or "action_policy",
                )
                return ResponsePipelineOutcome.stop(
                    response_text=response,
                    malformed_action_retries=0,
                    audit_marker_retries=0,
                    reason=action_policy_decision.reason or "terminal_plaintext_completion",
                    source=action_policy_decision.source or "action_policy",
                )
            return ResponsePipelineOutcome.continue_with(
                action_policy_decision.next_query,
                response_text=response,
                segments=segments,
                parsed_output=parsed_output,
                parsed_action_count=parsed_action_count,
                reason=action_policy_decision.reason,
                source=action_policy_decision.source,
            )

        if parsed_action_count > 0 or bool(getattr(parsed_output, "has_action_segment", False)):
            self.guards.clear_terminal_plaintext_completion()

        zero_action_invalid = (
            parsed_action_count <= 0
            and not parsed_output.has_action_segment
            and bool(str(parsed_output.invalid_kind or "").strip())
        )
        if zero_action_invalid:
            self.stage_logger.log(
                "response_pipeline",
                "continue",
                reason=parsed_output.invalid_kind,
                source="zero_action_invalid_guard",
            )
            return ResponsePipelineOutcome.continue_with(
                self.prompt_builder.build_missing_action_or_answer_prompt(),
                response_text=response,
                segments=segments,
                parsed_output=parsed_output,
                parsed_action_count=0,
                malformed_action_retries=0,
                audit_marker_retries=0,
                reason=parsed_output.invalid_kind,
                source="zero_action_invalid_guard",
            )

        self.guards.set_reflection_repair_pending(False)
        self.guards.set_nonproductive_thinking_state(False)
        self.stage_logger.log(
            "response_pipeline",
            "dispatch",
            action_count=parsed_action_count,
        )
        return ResponsePipelineOutcome.dispatch_ready(
            response_text=response,
            segments=segments,
            parsed_output=parsed_output,
            parsed_action_count=parsed_action_count,
            malformed_action_retries=0,
            audit_marker_retries=0,
            reason="dispatch_ready",
            source="response_pipeline",
            memory_checkpoint_and_text=bool(getattr(memory_board_decision, "memory_checkpoint_and_text", False)),
        )
