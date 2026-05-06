import types
import unittest

from modules.agent.orchestration.shared.decision_models import ParsedModelOutput
from modules.agent.orchestration.runtime.memory_board_stage import MemoryBoardStageHandler
from modules.agent.orchestration.responses import ModelOutputRecoveryHandler
from modules.agent.orchestration.transitions import IntentTransitionHandler


class _DummyLog:
    def debug(self, *args, **kwargs):
        pass
    info = warning = error = debug


class _DummyState:
    def __init__(self):
        self.consecutive_memory_checkpoint_only_count = 0
        self.last_memory_checkpoint_only = False
        self.active_intent = None
        self.last_completed_intent_type = ""
        self.current_turn_state_change_count = 0
        self.state_machine = None


class _DummyAgent:
    def __init__(self):
        self.state = _DummyState()
        self.log = _DummyLog()
        self.config = types.SimpleNamespace()
        self.ui = types.SimpleNamespace(print_error=_async_noop)
        self.memory_board_engine = None


async def _async_noop(*args, **kwargs):
    return None


class _PromptBuilder:
    def _current_active_intent_id(self):
        return "intent-x"

    def build_modify_completion_claim_without_proof_prompt(self):
        return "proof-prompt"


class _BoardResult:
    def __init__(self, clean_text, parsed_count=1, accepted_count=1, rejected_count=0):
        self.clean_text = clean_text
        self.parsed_count = parsed_count
        self.accepted_count = accepted_count
        self.rejected_count = rejected_count


class _MemoryBoardEngine:
    def __init__(self, clean_text):
        self.clean_text = clean_text

    def apply_response_text(self, response, active_intent_id=None, current_user_input=None, source=None):
        return _BoardResult(self.clean_text)


class MemoryBoardStageRegressionTests(unittest.IsolatedAsyncioTestCase):
    async def test_memory_checkpoint_and_action_never_becomes_checkpoint_only(self):
        agent = _DummyAgent()
        agent.memory_board_engine = _MemoryBoardEngine(clean_text="")
        handler = MemoryBoardStageHandler(agent, _PromptBuilder())
        ctx = types.SimpleNamespace(user_input="u")
        response = (
            "<progress scope=\"intent\">remember this</progress>\n"
            "<action>{\"type\":\"read_file\",\"path\":\"x\"}</action>"
        )
        decision = await handler.apply(ctx, response)
        self.assertFalse(decision.continue_loop)
        self.assertEqual("memory_checkpoint_and_action", decision.reason)
        self.assertFalse(decision.memory_checkpoint_only)

    async def test_memory_checkpoint_and_text_uses_raw_visible_text_even_if_clean_text_empty(self):
        agent = _DummyAgent()
        agent.memory_board_engine = _MemoryBoardEngine(clean_text="")
        handler = MemoryBoardStageHandler(agent, _PromptBuilder())
        ctx = types.SimpleNamespace(user_input="u")
        response = "<progress scope=\"intent\">remember this</progress>\nNo changes have been applied yet."
        decision = await handler.apply(ctx, response)
        self.assertFalse(decision.continue_loop)
        self.assertEqual("memory_checkpoint_and_text", decision.reason)
        self.assertTrue(decision.memory_checkpoint_and_text)

    async def test_memory_checkpoint_only_still_continues_for_tags_only(self):
        agent = _DummyAgent()
        agent.memory_board_engine = _MemoryBoardEngine(clean_text="")
        handler = MemoryBoardStageHandler(agent, _PromptBuilder())
        ctx = types.SimpleNamespace(user_input="u")
        response = "<progress scope=\"intent\">remember this</progress>"
        decision = await handler.apply(ctx, response)
        self.assertTrue(decision.continue_loop)
        self.assertEqual("memory_checkpoint_only", decision.reason)
        self.assertTrue(decision.memory_checkpoint_only)


class OutputRecoveryRegressionTests(unittest.IsolatedAsyncioTestCase):
    async def test_negated_no_changes_applied_yet_is_not_completion_claim(self):
        agent = _DummyAgent()
        agent.state.active_intent = types.SimpleNamespace(intent_type="MODIFY")
        handler = ModelOutputRecoveryHandler(agent, _PromptBuilder())
        parsed = ParsedModelOutput(
            response="No changes have been applied yet.",
            visible_text="No changes have been applied yet. I still need to read the remaining files.",
            has_action_segment=False,
            invalid_kind="",
        )
        decision = await handler.decide(parsed, malformed_action_retries=0, audit_marker_retries=0)
        self.assertFalse(decision.handled)
        self.assertEqual("no_invalid_kind", decision.reason)

    async def test_real_modify_completion_claim_is_still_blocked_without_proof(self):
        agent = _DummyAgent()
        agent.state.active_intent = types.SimpleNamespace(intent_type="MODIFY")
        handler = ModelOutputRecoveryHandler(agent, _PromptBuilder())
        parsed = ParsedModelOutput(
            response="Готово. Зміни внесено.",
            visible_text="Готово. Зміни внесено.",
            has_action_segment=False,
            invalid_kind="",
        )
        decision = await handler.decide(parsed, malformed_action_retries=0, audit_marker_retries=0)
        self.assertTrue(decision.handled)
        self.assertEqual("modify_completion_claim_without_state_change_proof", decision.reason)
        self.assertTrue(decision.continue_loop)

    async def test_compiler_ir_action_without_legacy_segment_passes_through_as_followup_output(self):
        agent = _DummyAgent()
        handler = ModelOutputRecoveryHandler(agent, _PromptBuilder())
        parsed = ParsedModelOutput(
            response="<think>Need exact chunk.</think>",
            visible_text="",
            has_action_segment=False,
            invalid_kind="",
        )
        parsed.compiler_ir = types.SimpleNamespace(
            action_ops=[types.SimpleNamespace(payload={"type": "read_chunk", "path": "x.py"})]
        )

        decision = await handler.decide(parsed, malformed_action_retries=0, audit_marker_retries=0)

        self.assertFalse(decision.handled)
        self.assertEqual("no_invalid_kind", decision.reason)


class IntentReuseRegressionTests(unittest.TestCase):
    def test_reuse_plaintext_answer_does_not_treat_memory_tags_only_as_plaintext(self):
        agent = _DummyAgent()
        handler = IntentTransitionHandler(agent, _PromptBuilder(), recovery=types.SimpleNamespace())
        payload = {"mode": "reuse"}
        response = (
            "<think>Need refreshed budget.</think>\n"
            "<progress scope=\"intent\">Need refreshed budget to continue.</progress>\n"
            "<intent mode=\"reuse\">{\"intent_id\":\"x\"}</intent>"
        )
        self.assertFalse(handler._reuse_has_inline_plaintext_answer(payload, response))

    def test_reuse_plaintext_answer_accepts_real_plaintext_after_memory_tags(self):
        agent = _DummyAgent()
        handler = IntentTransitionHandler(agent, _PromptBuilder(), recovery=types.SimpleNamespace())
        payload = {"mode": "reuse"}
        response = (
            "<think>Need refreshed budget.</think>\n"
            "<progress scope=\"intent\">checkpoint</progress>\n"
            "<intent mode=\"reuse\">{\"intent_id\":\"x\"}</intent>\n"
            "No changes have been applied yet. I need more steps to continue."
        )
        self.assertTrue(handler._reuse_has_inline_plaintext_answer(payload, response))


if __name__ == "__main__":
    unittest.main()
