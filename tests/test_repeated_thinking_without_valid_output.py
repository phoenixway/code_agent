import unittest
from types import SimpleNamespace

from modules.agent.orchestration.response_pipeline import ModelResponsePipeline


class DummyUI:
    async def print_error(self, _text):
        return None


class DummyParser:
    def parse(self, response_text):
        return []


class DummyParsedOutput:
    def __init__(self, *, has_action_segment=False, invalid_kind="", visible_text=""):
        self.has_action_segment = has_action_segment
        self.invalid_kind = invalid_kind
        self.visible_text = visible_text


class DummyIntentResponseParser:
    def classify(self, response, segments):
        return DummyParsedOutput(
            has_action_segment=False,
            invalid_kind="missing_action_or_answer",
            visible_text="",
        )


class DummyIntentTransitions:
    async def handle_model_step(self, **kwargs):
        return SimpleNamespace(
            handled=False,
            reason="",
            source="",
            next_query="",
        )


class DummyOutputRecovery:
    async def decide(self, parsed_output, malformed_action_retries=0, audit_marker_retries=0):
        return SimpleNamespace(
            handled=False,
            reason="",
            next_query="",
            malformed_action_retries=0,
            audit_marker_retries=0,
        )


class DummyActionPolicy:
    async def decide(self, ctx, segments, intent_payload=None):
        return SimpleNamespace(
            handled=False,
            continue_loop=False,
            next_query="",
            reason="",
            source="",
            parsed_action_count=0,
        )


class DummyMemoryBoardStage:
    async def apply(self, ctx, raw_response):
        return SimpleNamespace(
            handled=False,
            response_text=raw_response,
            reason="",
            source="",
            next_query="",
            memory_checkpoint_only=False,
            memory_checkpoint_and_text=False,
            memory_checkpoint_and_action=False,
        )


class DummyPlanBoardStage:
    async def apply(self, ctx, raw_response):
        return SimpleNamespace(
            handled=False,
            response_text=raw_response,
            reason="",
            source="plan_board",
            next_query="",
        )


class DummyPromptBuilder:
    def build_repeated_thinking_without_valid_output_prompt(self, stop_info=None):
        return "ENOUGH_THINKING_GIVE_VALID_OUTPUT"

    def build_plain_text_completion_prompt(self, sm, stop_info):
        return "PLAIN"

    def build_intent_required_prompt(self, reason):
        return f"INTENT_REQUIRED::{reason}"

    def build_missing_action_or_answer_prompt(self):
        return "MISSING_ACTION_OR_ANSWER"

    def build_reflection_repair_accepted_prompt(self):
        return "REFLECTION_OK"


class ResponsePipelineRepeatedThinkingTests(unittest.IsolatedAsyncioTestCase):
    def _make_pipeline(self):
        state = SimpleNamespace(
            consecutive_nonproductive_thinking_count=0,
            last_nonproductive_thinking_reason="",
            think_reflection_repair_pending=False,
            terminal_plaintext_completion_pending=False,
            terminal_plaintext_completion_text="",
            active_intent=None,
            orchestration_trace=[],
            orchestration_trace_sequence=0,
        )
        agent = SimpleNamespace(
            state=state,
            ui=DummyUI(),
            memory_board_engine=None,
            log=None,
            config=SimpleNamespace(
                MEMORY_CHECKPOINT_ONLY_HARD_STOP_STREAK=4,
                REPEATED_THINKING_WITHOUT_VALID_OUTPUT_STREAK=2,
            ),
        )
        pipeline = ModelResponsePipeline(
            agent=agent,
            parser=DummyParser(),
            intent_response_parser=DummyIntentResponseParser(),
            prompt_builder=DummyPromptBuilder(),
            intent_transitions=DummyIntentTransitions(),
            output_recovery=DummyOutputRecovery(),
            action_policy=DummyActionPolicy(),
            plan_board_stage=DummyPlanBoardStage(),
            memory_board_stage=DummyMemoryBoardStage(),
        )
        return pipeline, state

    async def test_repeated_thinking_without_valid_output_triggers_recovery_on_second_turn(self):
        pipeline, state = self._make_pipeline()
        ctx = SimpleNamespace(
            malformed_action_retries=0,
            audit_marker_retries=0,
            state_machine=None,
            user_input="continue",
        )
        step = SimpleNamespace(
            response=(
                "<think>I now have enough detail. Next I should update the function signature, "
                "wire the optional vault field, and then proceed to editing.</think>"
            ),
            intent_payload=None,
            intent_error=None,
        )

        first = await pipeline.run_step(ctx, step)
        self.assertTrue(first.continue_loop)
        self.assertEqual("missing_action_or_answer", first.reason)
        self.assertEqual(1, state.consecutive_nonproductive_thinking_count)

        second = await pipeline.run_step(ctx, step)
        self.assertTrue(second.continue_loop)
        self.assertEqual("repeated_thinking_without_valid_output", second.reason)
        self.assertEqual("ENOUGH_THINKING_GIVE_VALID_OUTPUT", second.next_query)
        self.assertEqual(2, state.consecutive_nonproductive_thinking_count)

    async def test_valid_output_resets_nonproductive_thinking_streak(self):
        class ActionIntentResponseParser(DummyIntentResponseParser):
            def classify(self, response, segments):
                return DummyParsedOutput(
                    has_action_segment=True,
                    invalid_kind="",
                    visible_text="",
                )

        class ActionPolicy(DummyActionPolicy):
            async def decide(self, ctx, segments, intent_payload=None):
                return SimpleNamespace(
                    handled=False,
                    continue_loop=False,
                    next_query="",
                    reason="",
                    source="",
                    parsed_action_count=1,
                )

        state = SimpleNamespace(
            consecutive_nonproductive_thinking_count=1,
            last_nonproductive_thinking_reason="repeated_thinking_without_valid_output",
            think_reflection_repair_pending=False,
            terminal_plaintext_completion_pending=False,
            terminal_plaintext_completion_text="",
            active_intent=None,
            orchestration_trace=[],
            orchestration_trace_sequence=0,
        )
        agent = SimpleNamespace(
            state=state,
            ui=DummyUI(),
            memory_board_engine=None,
            log=None,
            config=SimpleNamespace(
                MEMORY_CHECKPOINT_ONLY_HARD_STOP_STREAK=4,
                REPEATED_THINKING_WITHOUT_VALID_OUTPUT_STREAK=2,
            ),
        )
        pipeline = ModelResponsePipeline(
            agent=agent,
            parser=DummyParser(),
            intent_response_parser=ActionIntentResponseParser(),
            prompt_builder=DummyPromptBuilder(),
            intent_transitions=DummyIntentTransitions(),
            output_recovery=DummyOutputRecovery(),
            action_policy=ActionPolicy(),
            plan_board_stage=DummyPlanBoardStage(),
            memory_board_stage=DummyMemoryBoardStage(),
        )
        ctx = SimpleNamespace(
            malformed_action_retries=0,
            audit_marker_retries=0,
            state_machine=None,
            user_input="continue",
        )
        action_step = SimpleNamespace(
            response='<think>Enough planning. Edit now.</think><action>{"type":"edit_file"}</action>',
            intent_payload=None,
            intent_error=None,
        )

        result = await pipeline.run_step(ctx, action_step)
        self.assertFalse(result.continue_loop)
        self.assertEqual(0, state.consecutive_nonproductive_thinking_count)

        # outcome should not trigger repeated-thinking recovery
        self.assertNotEqual("repeated_thinking_without_valid_output", getattr(result, "reason", ""))

        # and it should not ask for another query/recovery prompt
        self.assertFalse(bool(getattr(result, "next_query", "")))

if __name__ == "__main__":
    unittest.main()
