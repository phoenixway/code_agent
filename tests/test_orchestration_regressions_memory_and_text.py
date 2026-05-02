import unittest
from types import SimpleNamespace


class DummyLogger:
    def debug(self, *args, **kwargs):
        pass

    def info(self, *args, **kwargs):
        pass

    def warning(self, *args, **kwargs):
        pass

    def error(self, *args, **kwargs):
        pass


class DummyUI:
    def __init__(self):
        self.messages = []
        self.system_messages = []
        self.thoughts = []
        self.tool_calls = []
        self.tool_updates = []

    async def print_message(self, text, role="assistant"):
        self.messages.append((role, text))

    async def print_system(self, text):
        self.system_messages.append(text)

    async def print_thought(self, text):
        self.thoughts.append(text)

    async def print_tool_call(self, command):
        self.tool_calls.append(command)
        return SimpleNamespace(command=command)

    async def start_action(self, _text):
        return None

    async def update_tool_call(self, widget, command, result):
        self.tool_updates.append((widget, command, result))


class DummyHistory:
    def __init__(self):
        self.messages = []

    def add_message(self, role, content, *args, **kwargs):
        self.messages.append((role, content, kwargs))


class DummyParser:
    def __init__(self, segments=None, reconstructed_text=""):
        self._segments = list(segments or [])
        self._reconstructed_text = reconstructed_text

    def parse(self, _response):
        return list(self._segments)

    def reconstruct(self, _segments):
        return self._reconstructed_text


class DummyIntentResponseParser:
    def __init__(self, parsed_output):
        self.parsed_output = parsed_output

    def classify(self, _response, _segments):
        return self.parsed_output


class DummyPromptBuilder:
    def build_missing_action_or_answer_prompt(self):
        return "PROMPT: missing action or answer"

    def build_intent_required_prompt(self, reason):
        return f"PROMPT: intent required ({reason})"

    def build_plain_text_completion_prompt(self, _state_machine, _stop_info):
        return "PROMPT: plain text completion"


class DummyIntentTransitions:
    def __init__(self, handled=False, next_query=None, reason="", source="intent_transition"):
        self.decision = SimpleNamespace(
            handled=handled,
            next_query=next_query,
            reason=reason,
            source=source,
        )

    async def handle_model_step(self, **kwargs):
        return self.decision


class DummyActionPolicy:
    def __init__(self, handled=False, next_query=None, reason="", source="action_policy", parsed_action_count=0):
        self.decision = SimpleNamespace(
            handled=handled,
            next_query=next_query,
            reason=reason,
            source=source,
            parsed_action_count=parsed_action_count,
        )

    async def decide(self, *args, **kwargs):
        return self.decision


class DummyOutputRecovery:
    def __init__(self, handled=False, next_query=None, reason="", source="output_recovery"):
        self.decision = SimpleNamespace(
            handled=handled,
            next_query=next_query,
            reason=reason,
            source=source,
            malformed_action_retries=0,
            audit_marker_retries=0,
        )

    async def decide(self, *args, **kwargs):
        return self.decision


class DummyMemoryBoardEngine:
    def __init__(self, parsed_count=0, accepted_count=0, rejected_count=0, clean_text=""):
        self.result = SimpleNamespace(
            parsed_count=parsed_count,
            accepted_count=accepted_count,
            rejected_count=rejected_count,
            clean_text=clean_text,
        )

    def apply_response_text(self, *args, **kwargs):
        return self.result


class DummyResponseProcessor:
    async def process_single_action(self, command):
        return {"status": "success", "output": f"ok:{command.get('type') or command.get('action')}"}


class DummyConfig:
    MAX_READONLY_BATCH_ACTIONS = 6
    TURN_WORKING_MATERIAL_SAFE_RATIO = 0.72
    STATE_CHANGING_OPS = ["run_shell", "create_file", "replace", "edit_file", "git_add", "git_commit", "git_checkout", "delete_file"]
    READ_ONLY_REPEAT_THRESHOLD = 3
    LOOP_ERROR_REPEAT_THRESHOLD = 2
    RECOVERABLE_ERROR_RETRY_BUDGET = 2
    CRITICAL_ERROR_RETRY_BUDGET = 1
    RECENT_SUMMARY_REREAD_WINDOW_SEC = 90


class DummyState:
    def __init__(self):
        self.orchestration_trace = []
        self.orchestration_trace_sequence = 0
        self.last_memory_checkpoint_only = False
        self.consecutive_memory_checkpoint_only_count = 0
        self.last_memory_board_parsed_count = 0
        self.last_memory_board_accepted_count = 0
        self.last_memory_board_rejected_count = 0
        self.memory_tag_expected_next_step = False
        self.memory_tag_reason = ""
        self.memory_tag_expected_intent_id = ""
        self.intent_required_until_activated = False
        self.intent_required_reason = ""
        self.think_reflection_repair_pending = False
        self.terminal_plaintext_completion_pending = False
        self.terminal_plaintext_completion_text = ""
        self.active_intent = None
        self.pending_loop_stop_info = None
        self.current_turn_id = 0
        self.confirmation_count = 0
        self.session_tokens = 0
        self.current_task = None
        self.last_batch_actions_executed = 0
        self.last_batch_actions_total = 0
        self.intent_step_batch_mode = ""
        self.intent_step_batch_consumed = False
        self.consecutive_same_action_count = 0
        self.state_machine = None
        self.intent_runtime = None

    def consume_forbidden_action_if_matches(self, _command):
        return False

    def record_action_result(self, _command, _result, _config):
        return {"same_action_repeats": 0, "same_error_repeats": 0, "defect_info": None}

    def reset_retry_budgets(self, *_args, **_kwargs):
        pass

    def consume_malformed_grace(self):
        return False

    def consume_retry_budget(self, _recoverable):
        return True

    def check_intent_pre_action(self, _command):
        return None


class DummyAgent:
    def __init__(self):
        self.ui = DummyUI()
        self.state = DummyState()
        self.log = DummyLogger()
        self.history = DummyHistory()
        self.memory_board_engine = None
        self.config = DummyConfig()
        self.processor = DummyResponseProcessor()
        self.allowed_actions_resolver = None


class Segment(SimpleNamespace):
    pass


class MemoryCheckpointAndTextTests(unittest.IsolatedAsyncioTestCase):
    async def test_memory_board_stage_distinguishes_checkpoint_and_text(self):
        from modules.agent.orchestration.runtime.memory_board_stage import MemoryBoardStageHandler

        agent = DummyAgent()
        agent.memory_board_engine = DummyMemoryBoardEngine(
            parsed_count=1,
            accepted_count=1,
            rejected_count=0,
            clean_text="<progress scope=\"intent\">saved</progress> Final answer.",
        )
        prompt_builder = SimpleNamespace(_current_active_intent_id=lambda: "intent-1")
        handler = MemoryBoardStageHandler(agent, prompt_builder)
        ctx = SimpleNamespace(user_input="go on")

        decision = await handler.apply(ctx, "ignored raw response")

        self.assertFalse(decision.handled)
        self.assertFalse(decision.continue_loop)
        self.assertFalse(decision.memory_checkpoint_only)
        self.assertTrue(getattr(decision, "memory_checkpoint_and_text", False))
        self.assertIn("Final answer", decision.response_text)
        self.assertEqual(agent.state.consecutive_memory_checkpoint_only_count, 0)

    async def test_response_pipeline_does_not_loop_on_memory_checkpoint_and_text(self):
        from modules.agent.orchestration.responses import ModelResponsePipeline

        agent = DummyAgent()
        parsed_output = SimpleNamespace(
            invalid_kind="missing_action_or_answer",
            has_action_segment=False,
            visible_text="Final answer.",
        )
        parser = DummyParser(
            segments=[Segment(type="text", content="Final answer.")],
            reconstructed_text="Final answer.",
        )
        pipeline = ModelResponsePipeline(
            agent,
            parser,
            DummyIntentResponseParser(parsed_output),
            DummyPromptBuilder(),
            DummyIntentTransitions(handled=False),
            DummyOutputRecovery(handled=False),
            DummyActionPolicy(handled=False, parsed_action_count=0),
            plan_board_stage=SimpleNamespace(
                apply=self._async_return(
                    SimpleNamespace(
                        handled=False,
                        continue_loop=False,
                        next_query=None,
                        reason="plan_board_pass",
                        source="plan_board",
                        response_text="Final answer.",
                    )
                )
            ),
            memory_board_stage=SimpleNamespace(
                apply=self._async_return(
                    SimpleNamespace(
                        handled=False,
                        continue_loop=False,
                        next_query=None,
                        reason="memory_checkpoint_and_text",
                        source="memory_board",
                        response_text="Final answer.",
                        memory_checkpoint_only=False,
                        memory_checkpoint_and_text=True,
                    )
                )
            ),
        )
        ctx = SimpleNamespace(state_machine=None, malformed_action_retries=0, audit_marker_retries=0)
        step = SimpleNamespace(response="raw", intent_payload=None, intent_error=None)

        outcome = await pipeline.run_step(ctx, step)

        self.assertFalse(outcome.continue_loop)
        self.assertFalse(outcome.stop_loop)
        self.assertEqual(outcome.reason, "dispatch_ready")
        self.assertEqual(outcome.parsed_action_count, 0)
        self.assertEqual(len(outcome.segments), 1)

    async def test_dispatch_outcome_text_only_renders_once_and_stops(self):
        from modules.agent.orchestration.runtime.dispatch_outcome import DispatchOutcomeHandler

        agent = DummyAgent()
        parser = DummyParser(reconstructed_text="Final answer.")
        handler = DispatchOutcomeHandler(agent, parser, recovery=SimpleNamespace(handle_dispatch_stop=self._async_return(None)))
        ctx = SimpleNamespace(current_query="go on", active_loop=True, state_machine=None)

        decision = await handler.handle(ctx, processed_segs=[Segment(type="text", content="Final answer.")], sys_results=[], should_stop=False)

        self.assertTrue(decision.stop_loop)
        self.assertEqual(decision.reason, "text_only_response_forwarded")
        self.assertEqual(agent.ui.messages, [("assistant", "Final answer.")])
        self.assertFalse(ctx.active_loop)
        self.assertEqual(ctx.current_query, "go on", "dispatch_outcome should not re-stash rendered assistant text into current_query")

    async def test_action_dispatcher_does_not_raw_render_text_segments(self):
        from modules.agent.action_dispatcher import ActionDispatcher

        agent = DummyAgent()
        dispatcher = ActionDispatcher(agent)
        state = agent.state
        segments = [Segment(type="text", content="<think>raw</think> visible")]

        processed_segments, system_results, should_stop = await dispatcher.dispatch_segments(segments, state)

        self.assertEqual(len(processed_segments), 1)
        self.assertEqual(processed_segments[0].content, "<think>raw</think> visible")
        self.assertEqual(agent.ui.messages, [], "dispatcher must not print raw assistant text segments directly")
        self.assertEqual(system_results, [])
        self.assertFalse(should_stop)

    async def test_memory_checkpoint_only_still_continues(self):
        from modules.agent.orchestration.runtime.memory_board_stage import MemoryBoardStageHandler

        agent = DummyAgent()
        agent.memory_board_engine = DummyMemoryBoardEngine(
            parsed_count=1,
            accepted_count=1,
            rejected_count=0,
            clean_text="<progress scope=\"intent\">saved</progress>",
        )
        prompt_builder = SimpleNamespace(_current_active_intent_id=lambda: "intent-1")
        handler = MemoryBoardStageHandler(agent, prompt_builder)
        ctx = SimpleNamespace(user_input="go on")

        decision = await handler.apply(ctx, "ignored raw response")

        self.assertTrue(decision.handled)
        self.assertTrue(decision.continue_loop)
        self.assertTrue(decision.memory_checkpoint_only)
        self.assertFalse(getattr(decision, "memory_checkpoint_and_text", False))
        self.assertEqual(decision.reason, "memory_checkpoint_only")
        self.assertEqual(agent.state.consecutive_memory_checkpoint_only_count, 1)

    def _async_return(self, value):
        async def _inner(*args, **kwargs):
            return value
        return _inner


if __name__ == "__main__":
    unittest.main()
