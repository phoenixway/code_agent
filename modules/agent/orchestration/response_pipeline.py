"""Typed pre-dispatch response handling pipeline for orchestrator model steps."""

from __future__ import annotations

from .decision_models import ResponsePipelineOutcome
from .stage_logging import OrchestrationStageLogger


class ModelResponsePipeline:
    def __init__(
        self,
        agent,
        parser,
        intent_response_parser,
        prompt_builder,
        intent_transitions,
        output_recovery,
        action_policy,
        memory_board_stage,
    ):
        self.agent = agent
        self.state = agent.state
        self.memory_board_engine = getattr(agent, "memory_board_engine", None)
        self.parser = parser
        self.intent_response_parser = intent_response_parser
        self.prompt_builder = prompt_builder
        self.intent_transitions = intent_transitions
        self.output_recovery = output_recovery
        self.action_policy = action_policy
        self.memory_board_stage = memory_board_stage
        self.stage_logger = OrchestrationStageLogger(getattr(agent, "log", None), self.state)

    async def run_step(self, ctx, step) -> ResponsePipelineOutcome:
        intent_decision = await self.intent_transitions.handle_model_step(
            intent_payload=step.intent_payload,
            intent_error=step.intent_error,
            response_text=step.response,
            state_machine=ctx.state_machine,
        )
        if intent_decision.handled:
            self.stage_logger.log(
                "response_pipeline",
                "continue",
                reason=intent_decision.reason,
                source="intent_transition",
            )
            return ResponsePipelineOutcome.continue_with(
                intent_decision.next_query,
                reason=intent_decision.reason,
                source="intent_transition",
            )

        response = step.response
        if getattr(self.state, "intent_required_until_activated", False) and "<action" in response.lower():
            self.stage_logger.log(
                "response_pipeline",
                "continue",
                reason=getattr(self.state, "intent_required_reason", "intent_required"),
                source="intent_requirement_gate",
            )
            return ResponsePipelineOutcome.continue_with(
                self.prompt_builder.build_intent_required_prompt(
                    getattr(self.state, "intent_required_reason", "intent_required")
                ),
                reason=getattr(self.state, "intent_required_reason", "intent_required"),
                source="intent_requirement_gate",
            )

        memory_board_decision = await self.memory_board_stage.apply(ctx, response)
        response = memory_board_decision.response_text
        if memory_board_decision.handled:
            return ResponsePipelineOutcome.continue_with(
                memory_board_decision.next_query,
                response_text=response,
                reason=memory_board_decision.reason,
                source=memory_board_decision.source,
            )

        segments = self.parser.parse(response)
        parsed_output = self.intent_response_parser.classify(response, segments)
        self.stage_logger.log(
            "response_pipeline",
            "classified",
            segment_count=len(segments),
            invalid_kind=parsed_output.invalid_kind or "",
            has_action_segment=parsed_output.has_action_segment,
        )
        action_policy_decision = await self.action_policy.decide(
            ctx,
            segments,
            intent_payload=step.intent_payload,
        )
        parsed_action_count = action_policy_decision.parsed_action_count

        if action_policy_decision.handled:
            return ResponsePipelineOutcome.continue_with(
                action_policy_decision.next_query,
                response_text=response,
                segments=segments,
                parsed_output=parsed_output,
                parsed_action_count=parsed_action_count,
                reason=action_policy_decision.reason,
                source=action_policy_decision.source,
            )

        recovery_decision = await self.output_recovery.decide(
            parsed_output,
            malformed_action_retries=ctx.malformed_action_retries,
            audit_marker_retries=ctx.audit_marker_retries,
        )
        if recovery_decision.handled:
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
        )
