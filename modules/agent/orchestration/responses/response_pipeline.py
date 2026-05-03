"""Typed pre-dispatch response handling pipeline for orchestrator model steps."""

from __future__ import annotations

from ..shared.decision_models import ResponsePipelineOutcome
from .response_pipeline_prevalidation import ResponsePipelinePrevalidationMixin
from .response_pipeline_stages import ResponsePipelineStagesMixin
from .response_guards import ResponseGuardPolicy
from .response_semantics import ResponseSemantics
from .stage_logging import OrchestrationStageLogger
from ..protocol import ProtocolCompiler


class ModelResponsePipeline(ResponsePipelinePrevalidationMixin, ResponsePipelineStagesMixin):
    STRUCTURAL_INVALID_KINDS = {
        "malformed_incomplete_think",
        "nested_think",
        "action_inside_think",
        "file_content_inside_think",
        "intent_inside_think",
        "malformed_action",
        "action_payload_xml_fields",
        "action_payload_tool_code",
        "action_payload_array",
        "intent_body_contains_action",
        "intent_payload_inside_action",
        "control_tag_leak_in_visible_text",
        "mixed_visible_text_and_control_protocol",
        "mixed_intent_transition_and_visible_answer",
    }

    def __init__(
        self,
        agent,
        parser,
        intent_response_parser,
        prompt_builder,
        intent_transitions,
        output_recovery,
        action_policy,
        plan_board_stage,
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
        self.plan_board_stage = plan_board_stage
        self.memory_board_stage = memory_board_stage
        self.stage_logger = OrchestrationStageLogger(getattr(agent, "log", None), self.state)
        self.protocol_compiler = ProtocolCompiler()
        self.memory_checkpoint_hard_stop_streak = int(
            getattr(getattr(agent, "config", None), "MEMORY_CHECKPOINT_ONLY_HARD_STOP_STREAK", 4) or 4
        )
        self.nonproductive_thinking_hard_stop_streak = int(
            getattr(getattr(agent, "config", None), "REPEATED_THINKING_WITHOUT_VALID_OUTPUT_STREAK", 2) or 2
        )
        self.semantics = ResponseSemantics()
        self.guards = ResponseGuardPolicy(self.state)

    @property
    def ui(self):
        return self.agent.ui

    def _multiple_actions_are_pure_read_only(self, segments) -> bool:
        checker = getattr(self.intent_response_parser, "multiple_actions_are_pure_read_only", None)
        if callable(checker):
            try:
                return bool(checker(segments))
            except Exception:
                return False
        return False

    async def run_step(self, ctx, step) -> ResponsePipelineOutcome:
        raw_response, reflection_state, early_outcome = await self._run_initial_stages(ctx, step)
        if early_outcome is not None:
            return early_outcome

        reflection_repair_pending, reflection_repair_kind = reflection_state
        checkpoint_state, checkpoint_outcome = await self._run_checkpoint_stage(
            ctx,
            raw_response,
            reflection_repair_pending=reflection_repair_pending,
            reflection_repair_kind=reflection_repair_kind,
        )
        if checkpoint_outcome is not None:
            return checkpoint_outcome

        classified = self._run_classification_stage(step, raw_response, checkpoint_state)
        return await self._run_post_classification_stage(ctx, step, checkpoint_state, classified)
