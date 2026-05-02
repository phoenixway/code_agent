import unittest
from types import SimpleNamespace

from modules.agent.orchestration.intent_transition_apply import IntentTransitionApplyMixin
from modules.agent.orchestration.intent_transition_routing import IntentTransitionRoutingMixin
from modules.agent.orchestration.intent_transitions import IntentTransitionHandler
from modules.agent.orchestration.output_recovery import ModelOutputRecoveryHandler
from modules.agent.orchestration.output_recovery_routing import OutputRecoveryRoutingMixin
from modules.agent.orchestration.output_recovery_terminal import OutputRecoveryTerminalMixin
from modules.agent.orchestration.parsing import IntentResponseParser
from modules.agent.orchestration.parsing_actions import ParsingActionsMixin
from modules.agent.orchestration.parsing_intent import ParsingIntentMixin
from modules.agent.orchestration.parsing_normalization import ParsingNormalizationMixin
from modules.agent.orchestration.prompting import OrchestratorPromptBuilder
from modules.agent.orchestration.response_pipeline import ModelResponsePipeline
from modules.agent.orchestration.response_pipeline_prevalidation import ResponsePipelinePrevalidationMixin
from modules.agent.orchestration.response_pipeline_stages import ResponsePipelineStagesMixin


class _DummyLogger:
    def debug(self, *args, **kwargs): pass
    def info(self, *args, **kwargs): pass
    def warning(self, *args, **kwargs): pass
    def error(self, *args, **kwargs): pass


class _DummyUI:
    async def print_error(self, text):
        return None


class _DummyPromptBuilder:
    def build_intent_required_prompt(self, reason):
        return f"INTENT_REQUIRED::{reason}"


class _DummyRecovery:
    async def handle_defect_detector_stop(self, stop_info):
        return SimpleNamespace(handled=False, next_query=None)


class _DummyParser:
    def parse(self, response):
        return []


class _DummyIntentResponseParser:
    def classify(self, response, segments, allow_think_autorepair=True):
        return SimpleNamespace(
            invalid_kind="",
            has_action_segment=False,
            visible_text="",
            model_stop_reason="",
        )

    def normalize_model_response(self, response, allow_think_autorepair=True):
        return SimpleNamespace(
            raw_response=response,
            normalized_response=response,
            think_repair_applied=False,
            think_repair_reason="",
            think_repair_confidence="",
            think_repair_tag="",
            think_repair_insert_at=-1,
            think_repair_blocked_by_atomicity=False,
            repairs_applied=(),
            repair_blocked_reason="",
        )


class _DummyActionPolicy:
    async def decide(self, ctx, segments, intent_payload=None):
        return SimpleNamespace(
            handled=False,
            next_query="",
            reason="",
            source="",
            parsed_action_count=0,
        )


class _DummyBoardStage:
    async def apply(self, ctx, raw_response):
        return SimpleNamespace(
            handled=False,
            response_text=raw_response,
            next_query="",
            reason="",
            source="",
            plan_checkpoint_only=False,
            plan_checkpoint_and_text=False,
            plan_checkpoint_and_action=False,
            memory_checkpoint_only=False,
            memory_checkpoint_and_text=False,
            memory_checkpoint_and_action=False,
        )


class _DummyOutputRecovery:
    async def decide(self, parsed_output, malformed_action_retries=0, audit_marker_retries=0):
        return SimpleNamespace(
            handled=False,
            next_query="",
            reason="",
            source="output_recovery",
            malformed_action_retries=0,
            audit_marker_retries=0,
        )


class _DummyState:
    def __init__(self):
        self.active_intent = None
        self.orchestration_trace = []
        self.orchestration_trace_sequence = 0
        self.intent_required_until_activated = False
        self.intent_required_reason = ""
        self.terminal_plaintext_completion_pending = False
        self.terminal_plaintext_completion_text = ""
        self.consecutive_memory_checkpoint_only_count = 0
        self.consecutive_nonproductive_thinking_count = 0
        self.last_nonproductive_thinking_reason = ""
        self.think_reflection_repair_pending = False
        self.think_reflection_repair_kind = ""

    def apply_intent_contract(self, payload, config):
        return True, "intent_activated"


class _DummyAgent:
    def __init__(self):
        self.state = _DummyState()
        self.config = SimpleNamespace(
            MEMORY_CHECKPOINT_ONLY_HARD_STOP_STREAK=4,
            REPEATED_THINKING_WITHOUT_VALID_OUTPUT_STREAK=2,
            MALFORMED_ACTION_GRACE_STEPS=1,
            INTENT_COMPLETION_ALLOWANCE=1,
        )
        self.log = _DummyLogger()
        self.ui = _DummyUI()
        self.memory_board_engine = None
        self.memory_board_store = None
        self.planner = None
        self.recovery_policy_resolver = None
        self.allowed_actions_resolver = None


class OrchestrationFacadeContractTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.agent = _DummyAgent()

    def test_prompt_builder_facade_exposes_expected_entry_points(self):
        builder = OrchestratorPromptBuilder(self.agent)

        self.assertTrue(isinstance(builder, object))
        self.assertTrue(hasattr(builder, "build_system_message"))
        self.assertTrue(hasattr(builder, "build_intent_runtime_context_message"))
        self.assertTrue(hasattr(builder, "build_malformed_action_strict_recovery_prompt"))
        self.assertTrue(hasattr(builder, "build_mixed_visible_text_and_control_protocol_prompt"))

    def test_parser_facade_includes_split_mixins_and_public_methods(self):
        parser = IntentResponseParser()

        self.assertTrue(isinstance(parser, ParsingNormalizationMixin))
        self.assertTrue(isinstance(parser, ParsingIntentMixin))
        self.assertTrue(isinstance(parser, ParsingActionsMixin))
        self.assertTrue(hasattr(parser, "normalize_model_response"))
        self.assertTrue(hasattr(parser, "extract_intent_update_and_strip"))
        self.assertTrue(hasattr(parser, "classify"))
        self.assertTrue(hasattr(parser, "multiple_actions_are_pure_read_only"))

    def test_output_recovery_facade_includes_terminal_and_routing_mixins(self):
        handler = ModelOutputRecoveryHandler(self.agent, OrchestratorPromptBuilder(self.agent))

        self.assertTrue(isinstance(handler, OutputRecoveryTerminalMixin))
        self.assertTrue(isinstance(handler, OutputRecoveryRoutingMixin))
        self.assertTrue(hasattr(handler, "decide"))
        self.assertTrue(hasattr(handler, "_terminal_recovery_loop_decision"))

    def test_intent_transition_facade_includes_apply_and_routing_mixins(self):
        handler = IntentTransitionHandler(self.agent, OrchestratorPromptBuilder(self.agent), _DummyRecovery())

        self.assertTrue(isinstance(handler, IntentTransitionApplyMixin))
        self.assertTrue(isinstance(handler, IntentTransitionRoutingMixin))
        self.assertTrue(hasattr(handler, "apply_payload_decision"))
        self.assertTrue(hasattr(handler, "handle_model_step"))

    async def test_response_pipeline_runs_stages_in_canonical_order(self):
        class RecordingPipeline(ModelResponsePipeline):
            def __init__(self, *args, **kwargs):
                super().__init__(*args, **kwargs)
                self.calls = []

            async def _run_initial_stages(self, ctx, step):
                self.calls.append("initial")
                return "raw", (False, ""), None

            async def _run_checkpoint_stage(self, ctx, raw_response, *, reflection_repair_pending, reflection_repair_kind):
                self.calls.append("checkpoint")
                return SimpleNamespace(
                    response="raw",
                    reflection_repair_pending=False,
                    reflection_repair_kind="",
                    memory_checkpoint_and_text=False,
                    memory_checkpoint_and_action=False,
                    memory_board_decision=SimpleNamespace(memory_checkpoint_and_text=False),
                ), None

            def _run_classification_stage(self, step, raw_response, checkpoint_state):
                self.calls.append("classification")
                return SimpleNamespace(
                    response="raw",
                    parsed_output=SimpleNamespace(has_action_segment=False, invalid_kind=""),
                    segments=[],
                    parsed_action_count=0,
                )

            async def _run_post_classification_stage(self, ctx, step, checkpoint_state, classified):
                self.calls.append("post_classification")
                return "done"

        pipeline = RecordingPipeline(
            agent=self.agent,
            parser=_DummyParser(),
            intent_response_parser=_DummyIntentResponseParser(),
            prompt_builder=_DummyPromptBuilder(),
            intent_transitions=IntentTransitionHandler(self.agent, OrchestratorPromptBuilder(self.agent), _DummyRecovery()),
            output_recovery=_DummyOutputRecovery(),
            action_policy=_DummyActionPolicy(),
            plan_board_stage=_DummyBoardStage(),
            memory_board_stage=_DummyBoardStage(),
        )

        result = await pipeline.run_step(SimpleNamespace(), SimpleNamespace(response="x"))

        self.assertEqual("done", result)
        self.assertEqual(
            ["initial", "checkpoint", "classification", "post_classification"],
            pipeline.calls,
        )

    def test_response_pipeline_facade_includes_split_mixins(self):
        pipeline = ModelResponsePipeline(
            agent=self.agent,
            parser=_DummyParser(),
            intent_response_parser=_DummyIntentResponseParser(),
            prompt_builder=_DummyPromptBuilder(),
            intent_transitions=IntentTransitionHandler(self.agent, OrchestratorPromptBuilder(self.agent), _DummyRecovery()),
            output_recovery=_DummyOutputRecovery(),
            action_policy=_DummyActionPolicy(),
            plan_board_stage=_DummyBoardStage(),
            memory_board_stage=_DummyBoardStage(),
        )

        self.assertTrue(isinstance(pipeline, ResponsePipelinePrevalidationMixin))
        self.assertTrue(isinstance(pipeline, ResponsePipelineStagesMixin))
        self.assertTrue(hasattr(pipeline, "run_step"))
        self.assertTrue(hasattr(pipeline, "_run_initial_stages"))
