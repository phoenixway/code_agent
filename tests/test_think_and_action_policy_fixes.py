import unittest
from types import SimpleNamespace
from unittest.mock import AsyncMock

from modules.agent.orchestration.runtime.action_policy import ActionPolicyHandler
from modules.agent.orchestration.responses import ModelOutputRecoveryHandler
from modules.agent.orchestration.prompts import OrchestratorPromptBuilder
from modules.agent.orchestration.shared.decision_models import ParsedModelOutput
from modules.agent.orchestration.parsers.visible_text import extract_visible_text_for_user
from modules.policy import PermissionPolicy
from modules.agent.orchestration.runtime.policy import IntentGuard


class _Segment:
    def __init__(self, seg_type: str, content=None):
        self.type = seg_type
        self.content = content


class _DummyConfig:
    MALFORMED_ACTION_GRACE_STEPS = 2


class ThinkStrictnessTests(unittest.IsolatedAsyncioTestCase):
    def _handler(self):
        state = SimpleNamespace(
            set_malformed_grace=lambda *args, **kwargs: None,
            forbid_next_action_fingerprint=lambda *args, **kwargs: None,
            last_completed_fingerprint=None,
            active_intent=SimpleNamespace(
                intent_id="intent_modify",
                intent_type="MODIFY",
                goal="Add bookmark tags to existing bookmarks UI",
            ),
            last_completed_intent_type="",
            state_machine=SimpleNamespace(task_kind="MODIFICATION"),
            current_turn_state_change_count=0,
            missing_think_reflection_warning_count=0,
            missing_think_reflection_warning_intent_id="",
            think_reflection_repair_pending=False,
            think_reflection_repair_kind="",
            last_blocked_action_type="",
            last_blocked_action_path="",
            orchestration_trace=[],
            orchestration_trace_sequence=0,
        )
        agent = SimpleNamespace(
            ui=SimpleNamespace(print_error=AsyncMock()),
            state=state,
            config=_DummyConfig(),
            log=None,
        )
        prompt_builder = OrchestratorPromptBuilder(
            SimpleNamespace(state=state, config=_DummyConfig(), memory_board_store=None, log=None)
        )
        return ModelOutputRecoveryHandler(agent, prompt_builder)

    async def test_nested_think_is_rejected(self):
        handler = self._handler()
        response = (
            "<think>! verified state ? gap → search\n"
            "<think>I need to implement more plan prose here.</think>\n"
            "</think>"
            "<subgoal action=\"create\" id=\"sg_1\" status=\"in_progress\">Do edit</subgoal>"
            "<memory_update_done />"
            "<action>{\"type\":\"edit_file\",\"path\":\"a.py\"}</action>"
        )
        decision = await handler.decide(
            ParsedModelOutput(
                response=response,
                invalid_kind="nested_think",
                segments=[_Segment("action", {"type": "edit_file", "path": "a.py"})],
                has_action_segment=True,
                visible_text="",
            ),
            malformed_action_retries=0,
            audit_marker_retries=0,
        )
        self.assertTrue(decision.handled)
        self.assertEqual("nested_think", decision.reason)

    async def test_action_inside_think_is_rejected(self):
        handler = self._handler()
        response = (
            "<think>! verified state ? gap → next\n"
            "<action>{\"type\":\"search_content\",\"pattern\":\"x\"}</action>\n"
            "</think>"
            "<memory_review status=\"no_change\" scope=\"intent\" />"
            "<memory_update_done />"
            "<action>{\"type\":\"edit_file\",\"path\":\"a.py\"}</action>"
        )
        decision = await handler.decide(
            ParsedModelOutput(
                response=response,
                invalid_kind="action_inside_think",
                segments=[_Segment("action", {"type": "edit_file", "path": "a.py"})],
                has_action_segment=True,
                visible_text="",
            ),
            malformed_action_retries=0,
            audit_marker_retries=0,
        )
        self.assertTrue(decision.handled)
        self.assertEqual("action_inside_think", decision.reason)

    async def test_verbose_think_over_threshold_is_accepted(self):
        handler = self._handler()
        long_body = "Here is the plan. " + ("A" * 1700)
        response = (
            f"<think>{long_body}</think>"
            "<memory_review status=\"no_change\" scope=\"intent\" />"
            "<memory_update_done />"
            "<action>{\"type\":\"edit_file\",\"path\":\"a.py\"}</action>"
        )
        decision = await handler.decide(
            ParsedModelOutput(
                response=response,
                segments=[_Segment("action", {"type": "edit_file", "path": "a.py"})],
                has_action_segment=True,
                visible_text="",
            ),
            malformed_action_retries=0,
            audit_marker_retries=0,
        )
        self.assertFalse(decision.handled)
        self.assertEqual("no_invalid_kind", decision.reason)

    async def test_repeated_nested_think_triggers_loop_breaker(self):
        handler = self._handler()
        response = (
            "<think>outer <think>nested</think></think>"
            "<memory_update_done />"
            "<action>{\"type\":\"edit_file\",\"path\":\"a.py\"}</action>"
        )
        parsed = ParsedModelOutput(
            response=response,
            invalid_kind="nested_think",
            segments=[_Segment("action", {"type": "edit_file", "path": "a.py"})],
            has_action_segment=True,
            visible_text="",
        )

        first = await handler.decide(parsed, malformed_action_retries=0, audit_marker_retries=0)
        second = await handler.decide(parsed, malformed_action_retries=0, audit_marker_retries=0)
        third = await handler.decide(parsed, malformed_action_retries=0, audit_marker_retries=0)

        self.assertEqual("nested_think", first.reason)
        self.assertIn("closed with </think> before any memory tag", first.next_query.lower())
        self.assertIn("do not put protocol tags or actions inside <think>", first.next_query.lower())

        self.assertEqual("nested_think", second.reason)
        self.assertIn("return the corrected response from the beginning", second.next_query.lower())

        self.assertEqual("terminal_malformed_think_handoff", third.reason)
        self.assertTrue(third.stop_loop)
        self.assertIsNone(third.next_query)

    async def test_malformed_think_count_accumulates_across_kinds_per_intent(self):
        handler = self._handler()
        nested_first = ParsedModelOutput(
            response="<think>outer <think>nested</think></think><memory_update_done /><action>{\"type\":\"edit_file\",\"path\":\"a.py\"}</action>",
            invalid_kind="nested_think",
            segments=[_Segment("action", {"type": "edit_file", "path": "a.py"})],
            has_action_segment=True,
            visible_text="",
        )
        incomplete = ParsedModelOutput(
            response="<think>! state ? gap → op",
            invalid_kind="malformed_incomplete_think",
            segments=[_Segment("action", {"type": "edit_file", "path": "a.py"})],
            has_action_segment=True,
            visible_text="",
        )
        nested = ParsedModelOutput(
            response="<think>! state\n<think>nested</think></think>",
            invalid_kind="nested_think",
            segments=[_Segment("action", {"type": "edit_file", "path": "a.py"})],
            has_action_segment=True,
            visible_text="",
        )

        first = await handler.decide(nested_first, malformed_action_retries=0, audit_marker_retries=0)
        second = await handler.decide(incomplete, malformed_action_retries=0, audit_marker_retries=0)
        third = await handler.decide(nested, malformed_action_retries=0, audit_marker_retries=0)

        self.assertEqual("nested_think", first.reason)
        self.assertIn("closed with </think> before any memory tag", first.next_query.lower())
        self.assertIn("do not put protocol tags or actions inside <think>", first.next_query.lower())

        self.assertEqual("malformed_incomplete_think", second.reason)
        self.assertIn("return the corrected response from the beginning", second.next_query.lower())

        # Different malformed-think kinds accumulate under the same active intent.
        # The 3rd malformed-think violation stops instead of issuing another retry.
        self.assertEqual("terminal_malformed_think_handoff", third.reason)
        self.assertTrue(third.stop_loop)
        self.assertIsNone(third.next_query)


    async def test_repeated_recovery_loop_detected_escalates_to_terminal_handoff(self):
        handler = self._handler()
        malformed = ParsedModelOutput(
            response="<think>outer <think>nested</think></think><memory_update_done /><action>{\"type\":\"edit_file\",\"path\":\"a.py\"}</action>",
            invalid_kind="nested_think",
            segments=[_Segment("action", {"type": "edit_file", "path": "a.py"})],
            has_action_segment=True,
            visible_text="",
        )

        reasons = []
        decisions = []
        for _ in range(7):
            decision = await handler.decide(malformed, malformed_action_retries=0, audit_marker_retries=0)
            reasons.append(decision.reason)
            decisions.append(decision)
            if decision.stop_loop:
                break

        self.assertIn("terminal_malformed_think_handoff", reasons)
        self.assertLessEqual(reasons.index("terminal_malformed_think_handoff"), 2)
        self.assertEqual("terminal_malformed_think_handoff", reasons[-1])
        self.assertTrue(decisions[-1].stop_loop)

    async def test_large_repeated_malformed_response_triggers_terminal_large_handoff(self):
        handler = self._handler()
        huge = ParsedModelOutput(
            response="<think>" + ("A" * 11050) + "<action>{\"type\":\"write_file_block\",\"path\":\"BookmarksViewModel.kt\"}</action>",
            invalid_kind="action_inside_think",
            segments=[_Segment("action", {"type": "write_file_block", "path": "BookmarksViewModel.kt"})],
            has_action_segment=True,
            visible_text="",
        )
        first = await handler.decide(huge, malformed_action_retries=0, audit_marker_retries=0)
        second = await handler.decide(huge, malformed_action_retries=0, audit_marker_retries=0)
        self.assertEqual("action_inside_think", first.reason)
        self.assertEqual("terminal_large_malformed_response_handoff", second.reason)
        self.assertTrue(handler.state.terminal_plaintext_completion_pending)
        self.assertIn("raw size", handler.state.terminal_plaintext_completion_text)
        self.assertIn("write_file_block", handler.state.terminal_plaintext_completion_text)


    async def test_valid_compact_think_clears_malformed_counter(self):
        handler = self._handler()
        malformed = ParsedModelOutput(
            response="<think>outer <think>nested</think></think><memory_update_done /><action>{\"type\":\"edit_file\",\"path\":\"a.py\"}</action>",
            invalid_kind="nested_think",
            segments=[_Segment("action", {"type": "edit_file", "path": "a.py"})],
            has_action_segment=True,
            visible_text="",
        )
        valid = ParsedModelOutput(
            response=(
                "<think>\n! state verified\n? one gap\n→ edit exact block\n</think>"
                "<decision scope=\"intent\">Use one exact edit.</decision>"
                "<memory_update_done />"
                "<action>{\"type\":\"edit_file\",\"path\":\"a.py\"}</action>"
            ),
            segments=[_Segment("action", {"type": "edit_file", "path": "a.py"})],
            has_action_segment=True,
            visible_text="",
            operational_checkpoint_satisfied=True,
            operational_checkpoint_has_think=True,
            operational_checkpoint_has_tags=True,
            operational_checkpoint_has_marker=True,
        )

        first = await handler.decide(malformed, malformed_action_retries=0, audit_marker_retries=0)
        second = await handler.decide(malformed, malformed_action_retries=0, audit_marker_retries=0)

        assert first.reason == "nested_think"
        assert second.reason == "nested_think"
        assert "return the corrected response from the beginning" in second.next_query.lower()

        ok = await handler.decide(valid, malformed_action_retries=0, audit_marker_retries=0)

        self.assertEqual("no_invalid_kind", ok.reason)
        self.assertEqual(0, getattr(handler.state, "malformed_think_count", 0))

        again = await handler.decide(malformed, malformed_action_retries=0, audit_marker_retries=0)

        self.assertEqual("nested_think", again.reason)
        self.assertFalse(again.stop_loop)

        # Because valid compact think clears the counter, this malformed output is
        # treated as the first malformed-think occurrence again, not as the second
        # strict-skeleton occurrence.
        self.assertIn("closed with </think> before any memory tag", again.next_query.lower())
        self.assertIn("do not put protocol tags or actions inside <think>", again.next_query.lower())
        self.assertIn("return the corrected response from the beginning", again.next_query.lower())

    async def test_valid_compact_operational_think_passes(self):
        handler = self._handler()
        response = (
            "<think>\n! Manifest exists and current permissions were verified.\n? Need one edit to add INTERNET.\n→ edit_file AndroidManifest.xml.\n</think>"
            "<decision scope=\"intent\">Add INTERNET permission via targeted edit.</decision>"
            "<memory_update_done />"
            "<action>{\"type\":\"edit_file\",\"path\":\"AndroidManifest.xml\"}</action>"
        )
        decision = await handler.decide(
            ParsedModelOutput(
                response=response,
                segments=[_Segment("action", {"type": "edit_file", "path": "AndroidManifest.xml"})],
                has_action_segment=True,
                visible_text="",
            ),
            malformed_action_retries=0,
            audit_marker_retries=0,
        )
        self.assertFalse(decision.handled)
        self.assertEqual("no_invalid_kind", decision.reason)

    def test_malformed_think_is_not_forwarded_as_text(self):
        response = (
            "<think>! state ? gap → action\n<think>Nested</think>\n</think>"
            "<action>{\"type\":\"edit_file\",\"path\":\"a.py\"}</action>"
        )
        self.assertEqual("", extract_visible_text_for_user(response))


class DisallowedActionRecoveryTests(unittest.IsolatedAsyncioTestCase):
    def _handler(self, allowed_actions):
        state = SimpleNamespace(
            active_intent=SimpleNamespace(
                intent_id="optimistic_delete",
                intent_type="MODIFY",
                goal="Implement optimistic delete",
                allowed_actions=list(allowed_actions),
            ),
            readonly_steps_this_turn=0,
            intent_required_until_activated=False,
            has_retry_context=lambda: False,
            can_continue_current_intent_after_failure=lambda: True,
            terminal_plaintext_completion_pending=False,
            terminal_plaintext_completion_text="",
            mark_pending_forced_plaintext_completion_close=lambda *args, **kwargs: None,
            orchestration_trace=[],
            orchestration_trace_sequence=0,
        )
        agent = SimpleNamespace(state=state, log=None)
        prompt_builder = OrchestratorPromptBuilder(
            SimpleNamespace(state=state, config=SimpleNamespace(), memory_board_store=None, log=None)
        )
        return ActionPolicyHandler(agent, IntentGuard(), prompt_builder), state

    async def test_disallowed_write_file_recovery_names_write_file_and_allowed_actions(self):
        handler, _state = self._handler(["edit_file", "read_chunk"])
        decision = await handler.decide(
            SimpleNamespace(user_input="Continue delete flow"),
            [_Segment("action", {"type": "write_file", "path": "a.py"})],
            intent_payload=None,
        )
        self.assertTrue(decision.handled)
        self.assertEqual("intent_action_not_allowed", decision.reason)
        self.assertIn("Blocked action type: write_file", decision.next_query)
        self.assertIn("Current allowed_actions: edit_file, read_chunk", decision.next_query)
        self.assertIn("return only a minimal intent transition", decision.next_query)

    async def test_disallowed_write_file_block_recovery_is_specific(self):
        handler, _state = self._handler(["edit_file", "read_chunk"])
        decision = await handler.decide(
            SimpleNamespace(user_input="Continue delete flow"),
            [_Segment("action", {"type": "write_file_block", "path": "a.py"})],
            intent_payload=None,
        )
        self.assertEqual("intent_action_not_allowed", decision.reason)
        self.assertIn("This action is outside the current intent contract", decision.next_query)
        self.assertIn('mode="replace"', decision.next_query)
        self.assertIn('"switch_reason": "save_requested"', decision.next_query)

    async def test_blocked_edit_file_under_investigate_forces_reuse_prompt(self):
        handler, state = self._handler(["read_chunk", "search_content", "read_file_skeleton"])
        state.active_intent.intent_type = "INVESTIGATE"
        decision = await handler.decide(
            SimpleNamespace(user_input="Continue"),
            [_Segment("action", {"type": "edit_file", "path": "BookmarksViewModel.kt"})],
            intent_payload=None,
        )
        self.assertTrue(decision.handled)
        self.assertEqual("intent_action_not_allowed", decision.reason)
        self.assertIn("this action is outside the current intent contract", decision.next_query.lower())
        self.assertIn('mode="reuse"', decision.next_query)
        self.assertIn('"switch_reason": "work_type_changed"', decision.next_query)
        self.assertIn("do not include <think>, <memory_update_done />, <action>, <file_content>, or final answer", decision.next_query.lower())

    async def test_repeated_disallowed_action_triggers_specific_reason(self):
        handler, _state = self._handler(["edit_file", "read_chunk"])
        segs = [_Segment("action", {"type": "write_file", "path": "a.py"})]
        first = await handler.decide(SimpleNamespace(user_input="Continue"), segs, intent_payload=None)
        second = await handler.decide(SimpleNamespace(user_input="Continue"), segs, intent_payload=None)
        self.assertEqual("intent_action_not_allowed", first.reason)
        self.assertEqual("repeated_disallowed_action", second.reason)
        self.assertIn("repeated the same disallowed action", second.next_query)

    async def test_third_repeated_disallowed_action_escalates_to_terminal_handoff(self):
        handler, state = self._handler(["edit_file", "read_chunk"])
        segs = [_Segment("action", {"type": "write_file_block", "path": "a.py"})]
        first = await handler.decide(SimpleNamespace(user_input="Continue"), segs, intent_payload=None)
        second = await handler.decide(SimpleNamespace(user_input="Continue"), segs, intent_payload=None)
        third = await handler.decide(SimpleNamespace(user_input="Continue"), segs, intent_payload=None)
        self.assertEqual("intent_action_not_allowed", first.reason)
        self.assertEqual("repeated_disallowed_action", second.reason)
        self.assertEqual("terminal_repeated_disallowed_action_handoff", third.reason)
        self.assertTrue(state.terminal_plaintext_completion_pending)
        self.assertIn("write_file_block", state.terminal_plaintext_completion_text)
        self.assertIn("optimistic_delete", state.terminal_plaintext_completion_text)
        self.assertIn("edit_file, read_chunk", state.terminal_plaintext_completion_text)

    async def test_repeated_disallowed_edit_under_investigate_forces_reuse_only(self):
        handler, state = self._handler(["read_chunk", "search_content", "read_file_skeleton"])
        state.active_intent.intent_type = "INVESTIGATE"
        segs = [_Segment("action", {"type": "edit_file", "path": "BookmarksViewModel.kt"})]
        first = await handler.decide(SimpleNamespace(user_input="Continue"), segs, intent_payload=None)
        second = await handler.decide(SimpleNamespace(user_input="Continue"), segs, intent_payload=None)
        self.assertEqual("intent_action_not_allowed", first.reason)
        self.assertEqual("repeated_disallowed_action", second.reason)
        self.assertIn('mode="reuse"', second.next_query)
        self.assertNotIn("use an allowed action now", second.next_query.lower())

    async def test_reuse_like_allowed_action_expansion_allows_write_file_after_update(self):
        handler, state = self._handler(["edit_file", "read_chunk"])
        blocked = await handler.decide(
            SimpleNamespace(user_input="Continue"),
            [_Segment("action", {"type": "write_file", "path": "a.py"})],
            intent_payload=None,
        )
        self.assertTrue(blocked.handled)
        state.active_intent.allowed_actions.append("write_file")
        allowed = await handler.decide(
            SimpleNamespace(user_input="Continue"),
            [_Segment("action", {"type": "write_file", "path": "a.py"})],
            intent_payload=None,
        )
        self.assertFalse(allowed.handled)
        self.assertEqual("actions_allowed_to_proceed", allowed.reason)

    async def test_allowed_edit_file_passes_under_current_contract(self):
        handler, _state = self._handler(["edit_file", "read_chunk"])
        decision = await handler.decide(
            SimpleNamespace(user_input="Continue"),
            [_Segment("action", {"type": "edit_file", "path": "a.py"})],
            intent_payload=None,
        )
        self.assertFalse(decision.handled)
        self.assertEqual("actions_allowed_to_proceed", decision.reason)

    async def test_noop_edit_is_blocked_before_dispatch(self):
        handler, _state = self._handler(["edit_file", "read_chunk"])
        decision = await handler.decide(
            SimpleNamespace(user_input="Continue"),
            [_Segment("action", {"type": "edit_file", "path": "a.py", "search_text": "x", "replace_text": "x"})],
            intent_payload=None,
        )
        self.assertTrue(decision.handled)
        self.assertEqual("noop_edit", decision.reason)
        self.assertIn("would not change the file", decision.next_query.lower())

    async def test_edit_retry_requires_fresh_read_after_mismatch(self):
        handler, state = self._handler(["edit_file", "read_chunk", "read_file", "search_content"])
        state.pending_edit_mismatch_path = "a.py"
        state.pending_edit_mismatch_intent_id = "optimistic_delete"
        blocked = await handler.decide(
            SimpleNamespace(user_input="Continue"),
            [_Segment("action", {"type": "edit_file", "path": "a.py", "search_text": "old", "replace_text": "new"})],
            intent_payload=None,
        )
        self.assertTrue(blocked.handled)
        self.assertEqual("edit_retry_requires_fresh_read", blocked.reason)
        self.assertIn("read exact current block first", blocked.next_query.lower())

        state.pending_edit_mismatch_path = ""
        state.pending_edit_mismatch_intent_id = ""
        allowed = await handler.decide(
            SimpleNamespace(user_input="Continue"),
            [_Segment("action", {"type": "edit_file", "path": "a.py", "search_text": "old", "replace_text": "new"})],
            intent_payload=None,
        )
        self.assertFalse(allowed.handled)
        self.assertEqual("actions_allowed_to_proceed", allowed.reason)

    async def test_intent_payload_inside_action_is_rejected(self):
        handler, _state = self._handler(["edit_file", "read_chunk"])
        decision = await handler.decide(
            SimpleNamespace(user_input="Continue"),
            [_Segment("action", {"type": "intent", "mode": "reuse"})],
            intent_payload=None,
        )
        self.assertTrue(decision.handled)
        self.assertEqual("intent_payload_inside_action", decision.reason)
        self.assertIn("intent is not a tool", decision.next_query.lower())

    async def test_top_level_intent_payload_still_passes(self):
        handler, _state = self._handler(["edit_file", "read_chunk"])
        decision = await handler.decide(
            SimpleNamespace(user_input="Continue"),
            [],
            intent_payload={"mode": "reuse", "intent_id": "optimistic_delete"},
        )
        self.assertFalse(decision.handled)
        self.assertEqual("no_action_gate_needed", decision.reason)


if __name__ == "__main__":
    unittest.main()
