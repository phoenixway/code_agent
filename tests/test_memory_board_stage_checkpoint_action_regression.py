import unittest
from types import SimpleNamespace

from modules.agent.orchestration.runtime.memory_board_stage import MemoryBoardStageHandler


class _DummyLogger:
    def debug(self, *args, **kwargs):
        pass
    def info(self, *args, **kwargs):
        pass
    def warning(self, *args, **kwargs):
        pass


class _DummyPromptBuilder:
    def _current_active_intent_id(self):
        return "per_link_vault_e2e"


class _DummyBoardResult:
    def __init__(self, *, parsed_count=0, accepted_count=0, rejected_count=0, clean_text=""):
        self.parsed_count = parsed_count
        self.accepted_count = accepted_count
        self.rejected_count = rejected_count
        self.clean_text = clean_text


class _DummyMemoryBoardEngine:
    def __init__(self, board_result):
        self.board_result = board_result

    def apply_response_text(self, response, active_intent_id, current_user_input, source):
        return self.board_result


class MemoryBoardStageRegressionTests(unittest.IsolatedAsyncioTestCase):
    def _make_handler(self, board_result):
        state = SimpleNamespace(
            consecutive_memory_checkpoint_only_count=0,
            last_memory_checkpoint_only=False,
            last_memory_board_parsed_count=0,
            last_memory_board_accepted_count=0,
            last_memory_board_rejected_count=0,
            memory_tag_expected_next_step=False,
            memory_tag_reason="",
            memory_tag_expected_intent_id="",
        )
        agent = SimpleNamespace(
            state=state,
            memory_board_engine=_DummyMemoryBoardEngine(board_result),
            log=_DummyLogger(),
        )
        handler = MemoryBoardStageHandler(agent, _DummyPromptBuilder())
        ctx = SimpleNamespace(user_input="Implement per-link vault support")
        return handler, ctx, state

    async def test_memory_tags_plus_action_do_not_become_checkpoint_only_even_if_clean_text_is_empty(self):
        board_result = _DummyBoardResult(
            parsed_count=1,
            accepted_count=1,
            rejected_count=0,
            clean_text="",  # simulate the problematic case from the dump
        )
        handler, ctx, state = self._make_handler(board_result)

        raw_response = '''
<decision scope="intent">Need to read the snapshot file first.</decision>
<action>
{"type":"read_file_skeleton","path":"core-data-models/.../RelatedLinkSnapshot.kt"}
</action>
'''

        decision = await handler.apply(ctx, raw_response)

        self.assertFalse(decision.handled, "memory_board must not swallow a valid action as checkpoint-only")
        self.assertEqual("memory_checkpoint_and_action", decision.reason)
        self.assertEqual("memory_board", decision.source)
        self.assertFalse(decision.memory_checkpoint_only)
        self.assertEqual(0, getattr(state, "consecutive_memory_checkpoint_only_count", 0))

    async def test_memory_tags_only_still_continue_as_checkpoint_only(self):
        board_result = _DummyBoardResult(
            parsed_count=2,
            accepted_count=2,
            rejected_count=0,
            clean_text="",
        )
        handler, ctx, state = self._make_handler(board_result)

        raw_response = '''
<finding scope="intent">Need to inspect sync layer first.</finding>
<decision scope="intent">Read snapshot and mapper files.</decision>
'''

        decision = await handler.apply(ctx, raw_response)

        self.assertTrue(decision.handled)
        self.assertEqual("memory_checkpoint_only", decision.reason)
        self.assertTrue(decision.memory_checkpoint_only)
        self.assertEqual(1, getattr(state, "consecutive_memory_checkpoint_only_count", 0))

    async def test_memory_tags_plus_plain_text_continue_to_pass_through(self):
        board_result = _DummyBoardResult(
            parsed_count=1,
            accepted_count=1,
            rejected_count=0,
            clean_text="I still need to update the snapshot mapper next.",
        )
        handler, ctx, state = self._make_handler(board_result)

        raw_response = '''
<progress scope="intent">Sync layer analysis complete.</progress>
I still need to update the snapshot mapper next.
'''

        decision = await handler.apply(ctx, raw_response)

        self.assertFalse(decision.handled)
        self.assertEqual("memory_checkpoint_and_text", decision.reason)
        self.assertFalse(decision.memory_checkpoint_only)
        self.assertEqual(0, getattr(state, "consecutive_memory_checkpoint_only_count", 0))


if __name__ == "__main__":
    unittest.main()
