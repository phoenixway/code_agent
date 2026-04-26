import unittest
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

from modules.defaults import DEFAULT_SYSTEM_PROMPT
from modules.agent.intent_runtime import IntentRuntime
from modules.agent.orchestration.decision_models import ParsedModelOutput
from modules.agent.orchestration.output_recovery import ModelOutputRecoveryHandler
from modules.agent.orchestration.parsing import IntentResponseParser
from modules.agent.orchestration.prompting import OrchestratorPromptBuilder
from modules.agent.orchestration.response_semantics import ResponseSemantics
from modules.agent.orchestration.visible_text import extract_visible_text_for_user


class DummyConfig:
    INTENT_RELABEL_GOAL_CORE_OVERLAP_THRESHOLD = 0.45
    INTENT_RELABEL_GOAL_SIMILARITY_THRESHOLD = 0.6
    INTENT_RELABEL_ACTION_OVERLAP_THRESHOLD = 0.6
    INTENT_RELABEL_PRESERVE_STEPS_ON_REFRESH = True
    INTENT_REUSE_EXTENSION_STEPS = 4
    INTENT_MAX_SAFE_STEPS = 8
    INTENT_DEFAULT_SAFE_STEPS = 4
    INTENT_DEFAULT_RETRY_LIMIT = 2
    MALFORMED_ACTION_GRACE_STEPS = 2


class _Segment:
    def __init__(self, seg_type: str, content=None):
        self.type = seg_type
        self.content = content


class IntentModeMergeTests(unittest.TestCase):
    def setUp(self):
        self.parser = IntentResponseParser()

    def test_tag_mode_fills_missing_body_mode(self):
        _clean_text, payload, error = self.parser.extract_intent_update_and_strip(
            '<intent mode="reuse">{"intent_id":"globalsearch_badge_fix","requested_steps":4,"switch_reason":"current_intent_exhausted"}</intent>'
        )

        self.assertIsNone(error)
        self.assertEqual("reuse", payload["mode"])

    def test_matching_tag_and_body_mode_is_accepted(self):
        _clean_text, payload, error = self.parser.extract_intent_update_and_strip(
            '<intent mode="reuse">{"mode":"reuse","intent_id":"globalsearch_badge_fix"}</intent>'
        )

        self.assertIsNone(error)
        self.assertEqual("reuse", payload["mode"])

    def test_conflicting_tag_and_body_mode_is_rejected(self):
        _clean_text, payload, error = self.parser.extract_intent_update_and_strip(
            '<intent mode="reuse">{"mode":"activate","intent_id":"globalsearch_badge_fix"}</intent>'
        )

        self.assertIsNone(payload)
        self.assertEqual("conflicting_intent_mode", error)

    def test_reuse_mode_from_tag_reaches_runtime_as_reuse_not_activate(self):
        runtime = IntentRuntime(DummyConfig())
        ok, msg = runtime.apply_payload(
            {
                "intent_id": "globalsearch_badge_fix",
                "intent_type": "MODIFY",
                "goal": "Move the badge label inside the result card",
                "allowed_actions": ["read_chunk", "search_content", "edit_file"],
                "safe_steps_limit": 4,
                "retry_limit": 2,
                "mode": "activate",
                "switch_reason": "user_requested_new_task",
                "switch_explanation": "initial activation",
            }
        )
        self.assertTrue(ok, msg)
        runtime.active_intent.step_count = runtime.active_intent.safe_steps_limit + 1
        runtime.require_intent("exhausted_intent_requires_reuse_or_completion")

        _clean_text, payload, error = self.parser.extract_intent_update_and_strip(
            '<intent mode="reuse">{"intent_id":"globalsearch_badge_fix","requested_steps":4,"switch_reason":"current_intent_exhausted"}</intent>'
        )

        self.assertIsNone(error)
        ok, msg = runtime.apply_payload(payload)
        self.assertTrue(ok, msg)
        self.assertEqual("intent_reused_with_step_refresh", msg)


class MissingThinkReflectionEscalationTests(unittest.IsolatedAsyncioTestCase):
    def _prompt_builder(self, state):
        return OrchestratorPromptBuilder(
            SimpleNamespace(
                state=state,
                config=DummyConfig(),
                memory_board_store=None,
                log=None,
            )
        )

    def _state(self, intent_type: str = "MODIFY"):
        return SimpleNamespace(
            set_malformed_grace=MagicMock(),
            forbid_next_action_fingerprint=MagicMock(),
            last_completed_fingerprint=None,
            active_intent=SimpleNamespace(intent_id="intent_1", intent_type=intent_type),
            last_completed_intent_type="",
            state_machine=SimpleNamespace(task_kind="MODIFICATION" if intent_type == "MODIFY" else "INSPECTION"),
            current_turn_state_change_count=0,
            missing_think_reflection_warning_count=0,
            missing_think_reflection_warning_intent_id="",
            think_reflection_repair_pending=False,
            think_reflection_repair_kind="",
            orchestration_trace=[],
            orchestration_trace_sequence=0,
        )

    def _handler(self, state):
        agent = SimpleNamespace(
            ui=SimpleNamespace(print_error=AsyncMock()),
            state=state,
            config=DummyConfig(),
            log=None,
        )
        return ModelOutputRecoveryHandler(agent, self._prompt_builder(state))

    async def test_first_missing_reflection_under_modify_is_non_blocking_warning(self):
        state = self._state("MODIFY")
        handler = self._handler(state)

        decision = await handler.decide(
            ParsedModelOutput(
                response="<think>one two three four five six</think><action>{\"type\":\"read_chunk\"}</action>",
                segments=[_Segment("action", {"type": "read_chunk"})],
                has_action_segment=True,
                visible_text="",
            ),
            malformed_action_retries=0,
            audit_marker_retries=0,
        )

        self.assertFalse(decision.handled)
        self.assertEqual("missing_think_reflection_detected_non_blocking", decision.reason)
        self.assertEqual(1, state.missing_think_reflection_warning_count)
        self.assertFalse(state.think_reflection_repair_pending)

    async def test_second_missing_reflection_under_same_modify_escalates_to_repair(self):
        state = self._state("MODIFY")
        handler = self._handler(state)
        parsed = ParsedModelOutput(
            response="<think>one two three four five six</think><action>{\"type\":\"read_chunk\"}</action>",
            segments=[_Segment("action", {"type": "read_chunk"})],
            has_action_segment=True,
            visible_text="",
        )

        first = await handler.decide(parsed, malformed_action_retries=0, audit_marker_retries=0)
        second = await handler.decide(parsed, malformed_action_retries=0, audit_marker_retries=0)

        self.assertFalse(first.handled)
        self.assertTrue(second.handled)
        self.assertEqual("missing_think_reflection", second.reason)
        self.assertTrue(state.think_reflection_repair_pending)
        self.assertEqual("missing_think_reflection", state.think_reflection_repair_kind)

    async def test_state_changing_modify_action_without_review_is_blocked_immediately(self):
        state = self._state("MODIFY")
        handler = self._handler(state)

        decision = await handler.decide(
            ParsedModelOutput(
                response="<think>! Verified target file. ? Missing accepted checkpoint tag. → emit checkpoint.</think><action>{\"type\":\"edit_file\",\"path\":\"a.py\"}</action>",
                segments=[_Segment("action", {"type": "edit_file", "path": "a.py"})],
                has_action_segment=True,
                visible_text="",
            ),
            malformed_action_retries=0,
            audit_marker_retries=0,
        )

        self.assertTrue(decision.handled)
        self.assertEqual("no_accepted_checkpoint_tags", decision.reason)
        self.assertIn("accepted durable tag", decision.next_query)
        self.assertIn("EXACTLY ONE allowed state-changing <action>", decision.next_query)

    async def test_state_changing_modify_action_with_subgoal_progress_and_marker_is_allowed(self):
        state = self._state("MODIFY")
        handler = self._handler(state)

        decision = await handler.decide(
            ParsedModelOutput(
                response=(
                    "<think>! Generator path verified. ? Need one shell run. → execute generator.</think>"
                    "<subgoal action=\"mark_done\" id=\"sg_1\" reason=\"Path verified\" />"
                    "<subgoal action=\"create\" id=\"sg_2\" status=\"in_progress\">Run generator script</subgoal>"
                    "<progress scope=\"intent\">Generator path confirmed; ready to execute scaffold generation.</progress>"
                    "<memory_update_done />"
                    "<action>{\"type\":\"run_shell\",\"command\":\"python generate_bookmarks_app.py\"}</action>"
                ),
                segments=[_Segment("action", {"type": "run_shell", "command": "python generate_bookmarks_app.py"})],
                has_action_segment=True,
                visible_text="",
            ),
            malformed_action_retries=0,
            audit_marker_retries=0,
        )

        self.assertFalse(decision.handled)
        self.assertEqual("no_invalid_kind", decision.reason)

    async def test_canonical_operational_checkpoint_satisfied_suppresses_false_positive(self):
        state = self._state("MODIFY")
        handler = self._handler(state)

        decision = await handler.decide(
            ParsedModelOutput(
                response="<think>! Generator path verified. ? Need one shell run. → execute generator.</think><action>{\"type\":\"run_shell\",\"command\":\"python generate.py\"}</action>",
                segments=[_Segment("action", {"type": "run_shell", "command": "python generate.py"})],
                has_action_segment=True,
                visible_text="",
                operational_checkpoint_satisfied=True,
                operational_checkpoint_has_think=True,
                operational_checkpoint_has_marker=True,
                operational_checkpoint_has_board_commit=True,
            ),
            malformed_action_retries=0,
            audit_marker_retries=0,
        )

        self.assertFalse(decision.handled)
        self.assertEqual("no_invalid_kind", decision.reason)

    async def test_state_changing_modify_action_with_memory_review_is_allowed(self):
        state = self._state("MODIFY")
        handler = self._handler(state)

        decision = await handler.decide(
            ParsedModelOutput(
                response=(
                    "<think>! Target file located. ? No durable change beyond review. → perform edit.</think>"
                    "<memory_review status=\"no_change\" scope=\"intent\" />"
                    "<memory_update_done />"
                    "<action>{\"type\":\"edit_file\",\"path\":\"a.py\"}</action>"
                ),
                segments=[_Segment("action", {"type": "edit_file", "path": "a.py"})],
                has_action_segment=True,
                visible_text="",
            ),
            malformed_action_retries=0,
            audit_marker_retries=0,
        )

        self.assertFalse(decision.handled)
        self.assertEqual("no_invalid_kind", decision.reason)

    async def test_state_changing_modify_action_without_think_is_blocked(self):
        state = self._state("MODIFY")
        handler = self._handler(state)

        decision = await handler.decide(
            ParsedModelOutput(
                response=(
                    "<memory_review status=\"no_change\" scope=\"intent\" />"
                    "<memory_update_done />"
                    "<action>{\"type\":\"edit_file\",\"path\":\"a.py\"}</action>"
                ),
                segments=[_Segment("action", {"type": "edit_file", "path": "a.py"})],
                has_action_segment=True,
                visible_text="",
            ),
            malformed_action_retries=0,
            audit_marker_retries=0,
        )

        self.assertTrue(decision.handled)
        self.assertEqual("missing_think", decision.reason)
        self.assertIn("complete tagged <think>...</think>", decision.next_query)

    async def test_state_changing_modify_action_with_missing_memory_update_done_is_blocked(self):
        state = self._state("MODIFY")
        handler = self._handler(state)

        decision = await handler.decide(
            ParsedModelOutput(
                response=(
                    "<think>! Edit target verified. ? Need checkpoint close. → emit marker.</think>"
                    "<memory_review status=\"no_change\" scope=\"intent\" />"
                    "<action>{\"type\":\"edit_file\",\"path\":\"a.py\"}</action>"
                ),
                segments=[_Segment("action", {"type": "edit_file", "path": "a.py"})],
                has_action_segment=True,
                visible_text="",
            ),
            malformed_action_retries=0,
            audit_marker_retries=0,
        )

        self.assertTrue(decision.handled)
        self.assertEqual("missing_memory_update_done", decision.reason)

    async def test_incomplete_think_before_state_changing_action_stays_malformed(self):
        state = self._state("MODIFY")
        handler = self._handler(state)

        decision = await handler.decide(
            ParsedModelOutput(
                response='<think>unfinished<action>{"type":"edit_file","path":"a.py"}</action>',
                invalid_kind="malformed_incomplete_think",
                segments=[_Segment("action", {"type": "edit_file", "path": "a.py"})],
                has_action_segment=True,
                visible_text="",
            ),
            malformed_action_retries=0,
            audit_marker_retries=0,
        )

        self.assertTrue(decision.handled)
        self.assertEqual("malformed_incomplete_think", decision.reason)

    async def test_plain_think_in_strict_state_changing_recovery_gets_specific_reason(self):
        state = self._state("MODIFY")
        handler = self._handler(state)

        decision = await handler.decide(
            ParsedModelOutput(
                response=(
                    "think\n! verified target\n→ edit file\n"
                    "<subgoal action=\"modify\" id=\"sg_1\" status=\"in_progress\">Add permission</subgoal>"
                    "<memory_update_done />"
                    "<action>{\"type\":\"edit_file\",\"path\":\"AndroidManifest.xml\"}</action>"
                ),
                segments=[_Segment("action", {"type": "edit_file", "path": "AndroidManifest.xml"})],
                has_action_segment=True,
                visible_text="",
            ),
            malformed_action_retries=0,
            audit_marker_retries=0,
        )

        self.assertTrue(decision.handled)
        self.assertEqual("malformed_plain_think_requires_tagged_think", decision.reason)
        self.assertIn("plain `think` text is invalid", decision.next_query)

    async def test_repeated_checkpoint_recovery_triggers_loop_breaker(self):
        state = self._state("MODIFY")
        handler = self._handler(state)
        parsed = ParsedModelOutput(
            response=(
                "<think>! Verified target file. ? Missing accepted checkpoint tag. → emit proper checkpoint.</think>"
                "<action>{\"type\":\"edit_file\",\"path\":\"AndroidManifest.xml\"}</action>"
            ),
            segments=[_Segment("action", {"type": "edit_file", "path": "AndroidManifest.xml"})],
            has_action_segment=True,
            visible_text="",
        )

        first = await handler.decide(parsed, malformed_action_retries=0, audit_marker_retries=0)
        second = await handler.decide(parsed, malformed_action_retries=0, audit_marker_retries=0)
        third = await handler.decide(parsed, malformed_action_retries=0, audit_marker_retries=0)

        self.assertTrue(first.handled)
        self.assertEqual("no_accepted_checkpoint_tags", first.reason)
        self.assertTrue(second.handled)
        self.assertEqual("no_accepted_checkpoint_tags", second.reason)
        self.assertTrue(third.handled)
        self.assertEqual("recovery_loop_detected", third.reason)
        self.assertIn("same checkpoint recovery defect repeated", third.next_query)

    async def test_non_modify_read_only_missing_reflection_stays_non_blocking(self):
        state = self._state("INVESTIGATE")
        handler = self._handler(state)

        decision = await handler.decide(
            ParsedModelOutput(
                response="<think>one two three four five six</think><action>{\"type\":\"read_chunk\"}</action>",
                segments=[_Segment("action", {"type": "read_chunk"})],
                has_action_segment=True,
                visible_text="",
            ),
            malformed_action_retries=0,
            audit_marker_retries=0,
        )

        self.assertFalse(decision.handled)
        self.assertEqual("missing_think_reflection_detected_non_blocking", decision.reason)


class PromptAndSemanticsTests(unittest.TestCase):
    def test_default_system_prompt_contains_modify_final_verification_report_rules(self):
        self.assertIn("FINAL ANSWER VERIFICATION REPORT", DEFAULT_SYSTEM_PROMPT)
        self.assertIn("git diff", DEFAULT_SYSTEM_PROMPT)
        self.assertIn("build/tests", DEFAULT_SYSTEM_PROMPT)
        self.assertIn("unverified", DEFAULT_SYSTEM_PROMPT)

    def test_plaintext_completion_prompt_for_modify_demands_verification_report(self):
        state = SimpleNamespace(
            active_intent=SimpleNamespace(intent_id="x", intent_type="MODIFY"),
            last_resumable_intent_id="x",
            last_completed_intent_type="",
        )
        builder = OrchestratorPromptBuilder(
            SimpleNamespace(state=state, config=DummyConfig(), memory_board_store=None, log=None)
        )

        out = builder.build_plain_text_completion_prompt(
            SimpleNamespace(task_kind="MODIFICATION", target_file="modules/x.py"),
            {"reason": "intent_force_plaintext_completion"},
        )

        self.assertIn("exact file paths changed in this run", out)
        self.assertIn("whether git diff was checked", out)
        self.assertIn("whether build/tests were run", out)
        self.assertIn("any unverified assumption or residual risk", out)

    def test_plaintext_completion_prompt_mentions_missing_gradle_verification_block(self):
        state = SimpleNamespace(
            active_intent=SimpleNamespace(intent_id="x", intent_type="MODIFY"),
            last_resumable_intent_id="x",
            last_completed_intent_type="",
        )
        builder = OrchestratorPromptBuilder(
            SimpleNamespace(state=state, config=DummyConfig(), memory_board_store=None, log=None)
        )

        out = builder.build_plain_text_completion_prompt(
            SimpleNamespace(task_kind="MODIFICATION", target_file="generate_bookmarks_app.py"),
            {
                "reason": "missing_executable",
                "error_code": "MISSING_EXECUTABLE",
                "error_details": {"missing_executable": "gradle"},
            },
        )

        self.assertIn("build/tests were not run because Gradle is unavailable", out)

    def test_memory_review_tag_counts_as_checkpoint_and_is_not_user_visible(self):
        semantics = ResponseSemantics()
        response = (
            "<think>one two three four five six</think>"
            "<memory_review status=\"no_change\" scope=\"intent\" />"
            "<memory_update_done />"
        )

        self.assertTrue(semantics.has_checkpoint_tags(response))
        self.assertFalse(semantics.substantial_think_without_reflection(response + "<action>{}</action>"))
        self.assertEqual("", extract_visible_text_for_user(response))

    def test_create_bookmark_app_write_file_step_with_operational_tags_is_not_dense(self):
        parser = IntentResponseParser()
        response = (
            "<think>! Generator target located. ? Full scaffold should be written in one step. → write_file.</think>\n"
            "<subgoal action=\"modify\" id=\"sg_1\" status=\"in_progress\">Write create_bookmark_app generator scaffold</subgoal>\n"
            "<decision scope=\"intent\">Write the scaffold generator in one file write because the target file is new and self-contained.</decision>\n"
            "<path scope=\"intent\">generate_app.py</path>\n"
            "<memory_update_done />\n"
            "<action>{\"type\":\"write_file\",\"path\":\"generate_app.py\",\"content\":\"Prompt docs may mention <intent mode=\\\"activate\\\"> only as an example.\"}</action>"
        )

        parsed = parser.classify(
            response,
            [SimpleNamespace(type="action", content={"type": "write_file", "path": "generate_app.py"})],
        )

        self.assertEqual("", parsed.invalid_kind)


if __name__ == "__main__":
    unittest.main()
