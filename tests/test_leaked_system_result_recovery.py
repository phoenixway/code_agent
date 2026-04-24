import unittest
from types import SimpleNamespace

from modules.agent.orchestration.dispatch_outcome import DispatchOutcomeHandler
from modules.agent.orchestration.response_pipeline import ModelResponsePipeline
from modules.agent.orchestration.response_semantics import ResponseSemantics


class LeakedSystemResultSemanticsTests(unittest.TestCase):
    def test_detects_canonical_system_result_prefixes(self):
        semantics = ResponseSemantics()
        self.assertTrue(semantics.looks_like_leaked_system_result("SYSTEM RESULT (read_chunk): val x = 1"))
        self.assertTrue(semantics.looks_like_leaked_system_result("SYSTEM RESULT for search_content: No matches found."))
        self.assertTrue(semantics.looks_like_leaked_system_result("Some intro\nSYSTEM RESULT for `search_content`: No matches found."))

    def test_does_not_flag_normal_prose(self):
        semantics = ResponseSemantics()
        self.assertFalse(semantics.looks_like_leaked_system_result("The system result was useful, so I continued."))
        self.assertFalse(semantics.looks_like_leaked_system_result("Готово. Я використав результати інструментів і завершив задачу."))


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
            visible_text="" if has_action else str(response).strip(),
        )


class DummyIntentTransitions:
    async def handle_model_step(self, **kwargs):
        return SimpleNamespace(handled=False, next_query="", reason="", source="")


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


class DummyMemoryBoardStage:
    async def apply(self, ctx, raw_response):
        return SimpleNamespace(
            handled=False,
            response_text=raw_response,
            next_query="",
            reason="memory_board_pass",
            source="memory_board",
            memory_checkpoint_only=False,
            memory_checkpoint_and_text=False,
            memory_checkpoint_and_action=False,
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

    def build_leaked_system_result_recovery_prompt(self):
        return "LEAKED_SYSTEM_RESULT_RECOVERY"


class DummyLogger:
    def debug(self, *args, **kwargs): pass
    def info(self, *args, **kwargs): pass
    def warning(self, *args, **kwargs): pass
    def error(self, *args, **kwargs): pass


class LeakedSystemResultPipelineTests(unittest.IsolatedAsyncioTestCase):
    def _make_pipeline(self):
        state = SimpleNamespace(
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
        agent = SimpleNamespace(
            state=state,
            memory_board_engine=None,
            log=DummyLogger(),
            ui=SimpleNamespace(print_error=self._noop_async),
            config=SimpleNamespace(
                MEMORY_CHECKPOINT_ONLY_HARD_STOP_STREAK=4,
                REPEATED_THINKING_WITHOUT_VALID_OUTPUT_STREAK=2,
            ),
        )
        return ModelResponsePipeline(
            agent=agent,
            parser=DummyParser(),
            intent_response_parser=DummyIntentResponseParser(),
            prompt_builder=DummyPromptBuilder(),
            intent_transitions=DummyIntentTransitions(),
            output_recovery=DummyOutputRecovery(),
            action_policy=DummyActionPolicy(),
            memory_board_stage=DummyMemoryBoardStage(),
        )

    async def _noop_async(self, *args, **kwargs):
        return None

    async def test_pipeline_recovers_before_dispatching_leaked_system_result_text(self):
        pipeline = self._make_pipeline()
        ctx = SimpleNamespace(state_machine=None, malformed_action_retries=0, audit_marker_retries=0)
        step = SimpleNamespace(
            response="SYSTEM RESULT (read_chunk): val items = remember(...)\nSYSTEM RESULT for search_content: No matches found.",
            intent_payload=None,
            intent_error=None,
        )

        result = await pipeline.run_step(ctx, step)

        self.assertTrue(result.continue_loop)
        self.assertEqual("leaked_system_result_in_assistant_text", result.reason)
        self.assertEqual("output_recovery", result.source)
        self.assertEqual("LEAKED_SYSTEM_RESULT_RECOVERY", result.next_query)

    async def test_pipeline_allows_normal_plaintext(self):
        pipeline = self._make_pipeline()
        ctx = SimpleNamespace(state_machine=None, malformed_action_retries=0, audit_marker_retries=0)
        step = SimpleNamespace(
            response="Готово. Я завершив задачу без службових transcript-маркерів.",
            intent_payload=None,
            intent_error=None,
        )

        result = await pipeline.run_step(ctx, step)

        self.assertNotEqual("leaked_system_result_in_assistant_text", result.reason)


class LeakedSystemResultDispatchSanitizerTests(unittest.TestCase):
    def test_dispatch_sanitizer_removes_system_result_lines(self):
        handler = object.__new__(DispatchOutcomeHandler)
        text = "SYSTEM RESULT (read_chunk): val x = 1\nSYSTEM RESULT for search_content: No matches found.\n"

        cleaned, changed = handler._strip_leaked_system_results_from_ui_text(text)

        self.assertTrue(changed)
        self.assertNotIn("SYSTEM RESULT", cleaned)

    def test_dispatch_sanitizer_keeps_normal_answer(self):
        handler = object.__new__(DispatchOutcomeHandler)
        text = "Готово. Я оновив display layer і додав vault fallback."

        cleaned, changed = handler._strip_leaked_system_results_from_ui_text(text)

        self.assertFalse(changed)
        self.assertEqual(text, cleaned)


if __name__ == "__main__":
    unittest.main()
