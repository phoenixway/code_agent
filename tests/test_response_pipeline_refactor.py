import unittest
from types import SimpleNamespace

from modules.agent.orchestration.response_pipeline import ModelResponsePipeline


class DummyParser:
    def parse(self, response):
        return [response] if response else []


class DummyParsedOutput:
    def __init__(self, *, has_action_segment=False, invalid_kind="", visible_text=""):
        self.has_action_segment = has_action_segment
        self.invalid_kind = invalid_kind
        self.visible_text = visible_text


class DummyIntentResponseParser:
    def classify(self, response, segments):
        has_action = "<action" in str(response).lower()
        return DummyParsedOutput(
            has_action_segment=has_action,
            invalid_kind="" if has_action else "missing_action_or_answer",
            visible_text="",
        )


class TextAnswerIntentResponseParser(DummyIntentResponseParser):
    def classify(self, response, segments):
        return DummyParsedOutput(
            has_action_segment=False,
            invalid_kind="missing_action_or_answer",
            visible_text="This is a final answer.",
        )


class DummyIntentTransitions:
    async def handle_model_step(self, **kwargs):
        return SimpleNamespace(handled=False, next_query="", reason="", source="")


class HandledIntentTransitions:
    async def handle_model_step(self, **kwargs):
        return SimpleNamespace(
            handled=True,
            next_query="INTENT_ACCEPTED_NEXT_QUERY",
            reason="intent_accepted",
            source="intent_transition",
        )


class DummyOutputRecovery:
    async def decide(self, parsed_output, malformed_action_retries=0, audit_marker_retries=0):
        return SimpleNamespace(
            handled=False,
            next_query="",
            reason="",
            source="",
            malformed_action_retries=malformed_action_retries,
            audit_marker_retries=audit_marker_retries,
        )


class DummyActionPolicy:
    async def decide(self, ctx, segments, intent_payload=None):
        joined = "\n".join(str(x) for x in segments)
        has_action = "<action" in joined.lower()
        return SimpleNamespace(
            handled=False,
            next_query="",
            reason="",
            source="",
            parsed_action_count=1 if has_action else 0,
        )


class HandledActionPolicy:
    async def decide(self, ctx, segments, intent_payload=None):
        return SimpleNamespace(
            handled=True,
            next_query="ACTION_POLICY_RECOVERY",
            reason="action_not_allowed",
            source="action_policy",
            parsed_action_count=1,
        )


class DummyMemoryBoardStage:
    async def apply(self, ctx, raw_response):
        return SimpleNamespace(
            handled=False,
            response_text=raw_response,
            next_query="",
            reason="",
            source="",
            memory_checkpoint_only=False,
            memory_checkpoint_and_text=False,
            memory_checkpoint_and_action=False,
        )


class MemoryCheckpointOnlyStage:
    async def apply(self, ctx, raw_response):
        return SimpleNamespace(
            handled=True,
            response_text=raw_response,
            next_query="MEMORY_NEXT",
            reason="memory_checkpoint_only",
            source="memory_board",
            memory_checkpoint_only=True,
            memory_checkpoint_and_text=False,
            memory_checkpoint_and_action=False,
        )


class MemoryCheckpointAndActionStage:
    async def apply(self, ctx, raw_response):
        return SimpleNamespace(
            handled=True,
            response_text=raw_response,
            next_query="MEMORY_AND_ACTION_NEXT",
            reason="memory_checkpoint_and_action",
            source="memory_board",
            memory_checkpoint_only=False,
            memory_checkpoint_and_text=False,
            memory_checkpoint_and_action=True,
        )


class DummyPromptBuilder:
    def build_intent_required_prompt(self, reason):
        return f"INTENT_REQUIRED::{reason}"

    def build_plain_text_completion_prompt(self, sm, stop_info):
        return "PLAIN_TEXT_COMPLETION_PROMPT"

    def build_reflection_repair_accepted_prompt(self):
        return "REFLECTION_ACCEPTED"

    def build_repeated_thinking_without_valid_output_prompt(self, stop_info=None):
        return "ENOUGH_THINKING_GIVE_VALID_OUTPUT"

    def build_missing_action_or_answer_prompt(self):
        return "MISSING_ACTION_OR_ANSWER"


class DummyUI:
    def __init__(self):
        self.errors = []

    async def print_error(self, text):
        self.errors.append(text)


class DummyLogger:
    def debug(self, *args, **kwargs): pass
    def info(self, *args, **kwargs): pass
    def warning(self, *args, **kwargs): pass
    def error(self, *args, **kwargs): pass


class ResponsePipelineRefactorIntegrationTests(unittest.IsolatedAsyncioTestCase):
    def _state(self, **overrides):
        base = dict(
            consecutive_memory_checkpoint_only_count=0,
            consecutive_nonproductive_thinking_count=0,
            last_nonproductive_thinking_reason="",
            think_reflection_repair_pending=False,
            terminal_plaintext_completion_pending=False,
            terminal_plaintext_completion_text="",
            orchestration_trace=[],
            orchestration_trace_sequence=0,
            intent_required_until_activated=False,
            intent_required_reason="",
            active_intent=None,
        )
        base.update(overrides)
        return SimpleNamespace(**base)

    def _ctx(self):
        return SimpleNamespace(state_machine=None, malformed_action_retries=0, audit_marker_retries=0)

    def _step(self, response):
        return SimpleNamespace(response=response, intent_payload=None, intent_error=None)

    def _make_pipeline(
        self,
        *,
        state=None,
        intent_response_parser=None,
        intent_transitions=None,
        action_policy=None,
        memory_board_stage=None,
        output_recovery=None,
    ):
        state = state or self._state()
        agent = SimpleNamespace(
            state=state,
            memory_board_engine=None,
            log=DummyLogger(),
            ui=DummyUI(),
            config=SimpleNamespace(
                MEMORY_CHECKPOINT_ONLY_HARD_STOP_STREAK=4,
                REPEATED_THINKING_WITHOUT_VALID_OUTPUT_STREAK=2,
            ),
        )
        return ModelResponsePipeline(
            agent=agent,
            parser=DummyParser(),
            intent_response_parser=intent_response_parser or DummyIntentResponseParser(),
            prompt_builder=DummyPromptBuilder(),
            intent_transitions=intent_transitions or DummyIntentTransitions(),
            output_recovery=output_recovery or DummyOutputRecovery(),
            action_policy=action_policy or DummyActionPolicy(),
            memory_board_stage=memory_board_stage or DummyMemoryBoardStage(),
        ), state, agent.ui

    async def test_intent_transition_resets_nonproductive_thinking_and_continues(self):
        state = self._state(consecutive_nonproductive_thinking_count=3)
        pipeline, state, _ui = self._make_pipeline(state=state, intent_transitions=HandledIntentTransitions())

        result = await pipeline.run_step(self._ctx(), self._step("<intent>{}</intent>"))

        self.assertTrue(result.continue_loop)
        self.assertEqual("intent_accepted", result.reason)
        self.assertEqual("INTENT_ACCEPTED_NEXT_QUERY", result.next_query)
        self.assertEqual(0, state.consecutive_nonproductive_thinking_count)

    async def test_intent_required_gate_blocks_bare_action(self):
        state = self._state(intent_required_until_activated=True, intent_required_reason="intent_required_for_multistep")
        pipeline, _state, _ui = self._make_pipeline(state=state)

        result = await pipeline.run_step(self._ctx(), self._step('<action>{"type":"read_chunk"}</action>'))

        self.assertTrue(result.continue_loop)
        self.assertEqual("intent_required_for_multistep", result.reason)
        self.assertEqual("intent_requirement_gate", result.source)
        self.assertEqual("INTENT_REQUIRED::intent_required_for_multistep", result.next_query)

    async def test_memory_checkpoint_only_hard_stop(self):
        state = self._state(consecutive_memory_checkpoint_only_count=4)
        pipeline, _state, ui = self._make_pipeline(state=state, memory_board_stage=MemoryCheckpointOnlyStage())

        result = await pipeline.run_step(self._ctx(), self._step("<progress scope=\"intent\">x</progress>"))

        self.assertFalse(result.continue_loop)
        self.assertTrue(getattr(result, "stop_loop", False))
        self.assertEqual("memory_checkpoint_only_hard_stop", result.reason)
        self.assertTrue(getattr(result, "memory_checkpoint_only", False))
        self.assertTrue(ui.errors)

    async def test_memory_checkpoint_and_action_resets_nonproductive_thinking(self):
        state = self._state(consecutive_nonproductive_thinking_count=2)
        pipeline, state, _ui = self._make_pipeline(state=state, memory_board_stage=MemoryCheckpointAndActionStage())

        result = await pipeline.run_step(self._ctx(), self._step("<think>one two three four five</think><action>{}</action>"))

        self.assertTrue(result.continue_loop)
        self.assertEqual("memory_checkpoint_and_action", result.reason)
        self.assertEqual(0, state.consecutive_nonproductive_thinking_count)

    async def test_repeated_thinking_without_valid_output_triggers_on_second_turn(self):
        pipeline, state, _ui = self._make_pipeline()
        ctx = self._ctx()
        step = self._step("<think>one two three four five six seven</think>")

        first = await pipeline.run_step(ctx, step)
        self.assertTrue(first.continue_loop)
        self.assertEqual("missing_action_or_answer", first.reason)
        self.assertEqual(1, state.consecutive_nonproductive_thinking_count)

        second = await pipeline.run_step(ctx, step)
        self.assertTrue(second.continue_loop)
        self.assertEqual("repeated_thinking_without_valid_output", second.reason)
        self.assertEqual("thinking_guard", second.source)
        self.assertEqual("ENOUGH_THINKING_GIVE_VALID_OUTPUT", second.next_query)
        self.assertEqual(2, state.consecutive_nonproductive_thinking_count)

    async def test_action_resets_nonproductive_streak_and_dispatches(self):
        state = self._state(
            consecutive_nonproductive_thinking_count=1,
            last_nonproductive_thinking_reason="repeated_thinking_without_valid_output",
            terminal_plaintext_completion_pending=True,
            terminal_plaintext_completion_text="buffer",
        )
        pipeline, state, _ui = self._make_pipeline(state=state)

        result = await pipeline.run_step(self._ctx(), self._step('<think>now action</think><action>{"type":"read_chunk"}</action>'))

        self.assertFalse(result.continue_loop)
        self.assertFalse(getattr(result, "stop_loop", False))
        self.assertTrue(result.handled)
        self.assertEqual("dispatch_ready", result.reason)
        self.assertEqual(1, result.parsed_action_count)
        self.assertEqual(0, state.consecutive_nonproductive_thinking_count)
        self.assertFalse(state.terminal_plaintext_completion_pending)
        self.assertEqual("", state.terminal_plaintext_completion_text)

    async def test_force_plaintext_completion_blocks_action(self):
        state = self._state(active_intent=SimpleNamespace(force_plaintext_completion=True))
        pipeline, _state, _ui = self._make_pipeline(state=state)

        result = await pipeline.run_step(self._ctx(), self._step('<action>{"type":"read_chunk"}</action>'))

        self.assertTrue(result.continue_loop)
        self.assertEqual("intent_force_plaintext_completion", result.reason)
        self.assertEqual("force_plaintext_gate", result.source)
        self.assertEqual("PLAIN_TEXT_COMPLETION_PROMPT", result.next_query)

    async def test_reflection_only_repair_is_accepted_before_generic_recovery(self):
        state = self._state(think_reflection_repair_pending=True)
        pipeline, state, _ui = self._make_pipeline(state=state)

        response = '<finding scope="intent">Found X</finding><decision scope="intent">Do Y</decision>'
        result = await pipeline.run_step(self._ctx(), self._step(response))

        self.assertTrue(result.continue_loop)
        self.assertEqual("think_reflection_repair_completed", result.reason)
        self.assertEqual("REFLECTION_ACCEPTED", result.next_query)
        self.assertFalse(state.think_reflection_repair_pending)

    async def test_plaintext_answer_path_does_not_trigger_repeated_thinking_guard(self):
        state = self._state(consecutive_nonproductive_thinking_count=1)
        pipeline, state, _ui = self._make_pipeline(state=state, intent_response_parser=TextAnswerIntentResponseParser())

        response = "<think>one two three four five six</think>Actual final answer."
        result = await pipeline.run_step(self._ctx(), self._step(response))

        self.assertNotEqual("repeated_thinking_without_valid_output", result.reason)
        self.assertEqual(0, state.consecutive_nonproductive_thinking_count)

    async def test_action_policy_handled_continues_with_policy_prompt(self):
        pipeline, _state, _ui = self._make_pipeline(action_policy=HandledActionPolicy())

        result = await pipeline.run_step(self._ctx(), self._step('<action>{"type":"forbidden"}</action>'))

        self.assertTrue(result.continue_loop)
        self.assertEqual("action_not_allowed", result.reason)
        self.assertEqual("action_policy", result.source)
        self.assertEqual("ACTION_POLICY_RECOVERY", result.next_query)


if __name__ == "__main__":
    unittest.main()
