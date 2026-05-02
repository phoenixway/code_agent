import shutil
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

from modules.agent.orchestration.decision_models import ParsedModelOutput
from modules.agent.orchestration.output_recovery import ModelOutputRecoveryHandler
from modules.agent.orchestration.parsing import IntentResponseParser
from modules.agent.orchestration.prompting import OrchestratorPromptBuilder
from modules.agent.orchestration.response_semantics import ResponseSemantics
from modules.agent.orchestration.visible_text import extract_visible_text_for_user
from modules.defaults import DEFAULT_SYSTEM_PROMPT
from modules.parser import ResponseParser
from modules.policy import PermissionPolicy
from modules.processor import ResponseProcessor
from modules.tools.manager import ToolManager


class _DummyConfig:
    MALFORMED_ACTION_GRACE_STEPS = 2


class ResponseParserFileBlockTests(unittest.TestCase):
    def setUp(self):
        self.parser = ResponseParser()

    def test_write_file_block_attaches_raw_file_content_to_action(self):
        response = (
            '<action>{"type":"write_file_block","path":"generate_app.py","overwrite":true}</action>\n'
            "<file_content>#!/usr/bin/env python3\nprint(\"hello\")\n</file_content>"
        )

        segments = self.parser.parse(response)

        self.assertEqual(1, len(segments))
        self.assertEqual("action", segments[0].type)
        self.assertEqual("write_file_block", segments[0].content["type"])
        self.assertEqual("generate_app.py", segments[0].content["path"])
        self.assertEqual('#!/usr/bin/env python3\nprint("hello")\n', segments[0].content["file_content"])

    def test_file_content_without_block_action_is_parsed_as_first_class_segment(self):
        segments = self.parser.parse("<file_content>hello</file_content>")

        self.assertEqual(1, len(segments))
        self.assertEqual("file_content", segments[0].type)
        self.assertEqual("hello", segments[0].content)

    def test_file_content_after_ordinary_action_is_not_attached(self):
        segments = self.parser.parse(
            '<action>{"type":"create_file","path":"a.py","content":"pass"}</action>\n'
            "<file_content>ignored</file_content>"
        )

        self.assertEqual(2, len(segments))
        self.assertEqual("action", segments[0].type)
        self.assertEqual("create_file", segments[0].content["type"])
        self.assertEqual("file_content", segments[1].type)
        self.assertEqual("ignored", segments[1].content)

    def test_write_file_block_keeps_android_xml_action_tags_inside_raw_file_content(self):
        response = (
            '<action>{"type":"write_file_block","path":"AndroidManifest.xml","overwrite":true}</action>\n'
            "<file_content><?xml version=\"1.0\" encoding=\"utf-8\"?>\n"
            "<manifest>\n"
            "  <application>\n"
            "    <activity>\n"
            "      <intent-filter>\n"
            "        <action android:name=\"android.intent.action.MAIN\" />\n"
            "      </intent-filter>\n"
            "    </activity>\n"
            "  </application>\n"
            "</manifest>\n"
            "</file_content>"
        )

        segments = self.parser.parse(response)

        self.assertEqual(1, len(segments))
        self.assertEqual("action", segments[0].type)
        self.assertEqual("write_file_block", segments[0].content["type"])
        self.assertIn("<intent-filter>", segments[0].content["file_content"])
        self.assertIn('<action android:name="android.intent.action.MAIN" />', segments[0].content["file_content"])

    def test_write_file_block_keeps_literal_action_text_inside_raw_file_content(self):
        response = (
            '<action>{"type":"write_file_block","path":"example.txt","overwrite":true}</action>\n'
            "<file_content>literal protocol example:\n"
            "<action>{\"type\":\"read_file\"}</action>\n"
            "</file_content>"
        )

        segments = self.parser.parse(response)

        self.assertEqual(1, len(segments))
        self.assertEqual("action", segments[0].type)
        self.assertEqual("write_file_block", segments[0].content["type"])
        self.assertIn('<action>{"type":"read_file"}</action>', segments[0].content["file_content"])


class FileBlockProcessorTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.tmpdir = tempfile.mkdtemp()
        self.ui = MagicMock()
        self.ui.show_diff_preview = AsyncMock(return_value=True)
        self.tool_manager = ToolManager()
        self.tool_manager.load_tools()
        self.policy = PermissionPolicy(self.ui, mode="always")
        self.processor = ResponseProcessor(
            self.ui,
            self.tool_manager,
            chat=None,
            policy=self.policy,
        )
        self.parser = ResponseParser()

    def tearDown(self):
        shutil.rmtree(self.tmpdir)

    async def test_small_write_file_still_works(self):
        path = Path(self.tmpdir) / "small.py"

        result = await self.processor.process_single_action(
            {"type": "write_file", "path": str(path), "content": "print('ok')\n"}
        )

        self.assertEqual("success", result["status"])
        self.assertEqual("print('ok')\n", path.read_text())

    async def test_huge_write_file_json_is_blocked_with_clear_reason(self):
        path = Path(self.tmpdir) / "huge.py"
        huge_content = "x" * 5001

        result = await self.processor.process_single_action(
            {"type": "write_file", "path": str(path), "content": huge_content}
        )

        self.assertEqual("failed", result["status"])
        self.assertEqual("CONTENT_TOO_LARGE_FOR_JSON_FILE_ACTION", result["error_code"])
        self.assertIn("write_file_block", result["output"])
        self.assertIn("<file_content>", result["output"])
        self.assertFalse(path.exists())

    async def test_write_file_block_writes_raw_python_content(self):
        path = Path(self.tmpdir) / "generate_app.py"
        raw = "#!/usr/bin/env python3\n\ndef main():\n    print(\"hello\")\n"

        result = await self.processor.process_single_action(
            {
                "type": "write_file_block",
                "path": str(path),
                "overwrite": True,
                "file_content": raw,
            }
        )

        self.assertEqual("success", result["status"])
        self.assertEqual(raw, path.read_text())

    async def test_append_file_block_appends_raw_content(self):
        path = Path(self.tmpdir) / "append.txt"
        path.write_text("start\n", encoding="utf-8")

        result = await self.processor.process_single_action(
            {
                "type": "append_file_block",
                "path": str(path),
                "file_content": "line1\n\"quoted\"\n${template}\n",
            }
        )

        self.assertEqual("success", result["status"])
        self.assertEqual('start\nline1\n"quoted"\n${template}\n', path.read_text(encoding="utf-8"))

    async def test_write_file_block_without_file_content_is_rejected(self):
        path = Path(self.tmpdir) / "missing_body.py"

        result = await self.processor.process_single_action(
            {"type": "write_file_block", "path": str(path), "overwrite": True}
        )

        self.assertEqual("failed", result["status"])
        self.assertEqual("MISSING_FILE_CONTENT_BLOCK", result["error_code"])
        self.assertEqual(
            "write_file_block requires a complete <file_content>...</file_content> block immediately after </action>.",
            result["output"],
        )

    def test_file_content_before_action_is_classified_as_wrong_order(self):
        response = (
            "<file_content>body</file_content>\n"
            '<action>{"type":"write_file_block","path":"a.py","overwrite":true}</action>'
        )

        adapter = IntentResponseParser()
        classified = adapter.classify(response, self.parser.parse(response))

        self.assertEqual("file_content_must_follow_action", classified.invalid_kind)

    async def test_generate_app_py_can_be_written_via_block_markup(self):
        path = Path(self.tmpdir) / "generate_app.py"
        response = (
            f'<action>{{"type":"write_file_block","path":"{path}","overwrite":true}}</action>\n'
            "<file_content>from pathlib import Path\n\n"
            "def build():\n"
            "    return Path(\".\")\n"
            "</file_content>"
        )

        segments = self.parser.parse(response)
        self.assertEqual(1, len(segments))
        self.assertEqual("action", segments[0].type)

        result = await self.processor.process_single_action(segments[0].content)

        self.assertEqual("success", result["status"])
        self.assertTrue(path.exists())
        self.assertIn("def build()", path.read_text())


class FileBlockPromptTests(unittest.IsolatedAsyncioTestCase):
    def _handler(self, *, intent_type=None):
        state = SimpleNamespace(
            set_malformed_grace=MagicMock(),
            forbid_next_action_fingerprint=MagicMock(),
            last_completed_fingerprint=None,
            active_intent=SimpleNamespace(intent_id="intent_1", intent_type=intent_type) if intent_type else None,
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
        agent = SimpleNamespace(
            ui=SimpleNamespace(print_error=AsyncMock()),
            state=state,
            config=_DummyConfig(),
            log=None,
        )
        builder = OrchestratorPromptBuilder(
            SimpleNamespace(
                state=state,
                config=_DummyConfig(),
                memory_board_store=None,
                log=None,
            )
        )
        return ModelOutputRecoveryHandler(agent, builder)

    async def test_malformed_action_recovery_mentions_write_file_block(self):
        handler = self._handler()

        decision = await handler.decide(
            ParsedModelOutput(
                response="<action>{bad json</action>",
                invalid_kind="malformed_action",
                has_action_segment=False,
                visible_text="",
            ),
            malformed_action_retries=0,
            audit_marker_retries=0,
        )

        self.assertTrue(decision.handled)
        self.assertEqual("malformed_action", decision.reason)
        self.assertIn("write_file_block", decision.next_query)
        self.assertIn("<file_content>", decision.next_query)

    def test_multiple_actions_prompt_mentions_top_level_actions_only(self):
        builder = OrchestratorPromptBuilder(
            SimpleNamespace(
                state=SimpleNamespace(active_intent=None),
                config=_DummyConfig(),
                memory_board_store=None,
                log=None,
            )
        )

        prompt = builder.build_multiple_actions_prompt()

        self.assertIn("multiple top-level <action> blocks", prompt)
        self.assertIn("inside <file_content> does not", prompt)

    async def test_incomplete_think_uses_special_recovery_prompt(self):
        handler = self._handler()

        decision = await handler.decide(
            ParsedModelOutput(
                response="<think>unfinished",
                invalid_kind="malformed_incomplete_think",
                has_action_segment=False,
                visible_text="unfinished",
            ),
            malformed_action_retries=0,
            audit_marker_retries=0,
        )

        self.assertTrue(decision.handled)
        self.assertEqual("malformed_incomplete_think", decision.reason)
        self.assertIn("closed with </think> before any memory tag", decision.next_query)
        self.assertIn("Do not put protocol tags or actions inside <think>", decision.next_query)
        self.assertIn("Do not continue the previous incomplete sentence", decision.next_query)

    async def test_incomplete_file_content_uses_special_recovery_prompt(self):
        handler = self._handler()

        decision = await handler.decide(
            ParsedModelOutput(
                response='<action>{"type":"write_file_block","path":"a.py","overwrite":true}</action><file_content>abc',
                invalid_kind="malformed_incomplete_file_content",
                has_action_segment=True,
                visible_text="",
            ),
            malformed_action_retries=0,
            audit_marker_retries=0,
        )

        self.assertTrue(decision.handled)
        self.assertEqual("malformed_incomplete_file_content", decision.reason)
        self.assertIn("truncated inside <file_content>", decision.next_query)

    async def test_file_content_wrong_order_recovery_shows_correct_order(self):
        handler = self._handler()

        decision = await handler.decide(
            ParsedModelOutput(
                response="<file_content>body</file_content><action>{\"type\":\"write_file_block\",\"path\":\"a.py\",\"overwrite\":true}</action>",
                invalid_kind="file_content_must_follow_action",
                has_action_segment=True,
                visible_text="",
            ),
            malformed_action_retries=0,
            audit_marker_retries=0,
        )

        self.assertEqual("file_content_must_follow_action", decision.reason)
        self.assertIn('"type": "write_file_block"', decision.next_query)
        self.assertIn("The <file_content> block must appear immediately after </action>", decision.next_query)
        self.assertIn("<file_content>\nraw content\n</file_content>", decision.next_query)

    def test_default_system_prompt_mentions_raw_block_file_writes(self):
        self.assertIn("write_file_block", DEFAULT_SYSTEM_PROMPT)
        self.assertIn("append_file_block", DEFAULT_SYSTEM_PROMPT)
        self.assertIn("<file_content>", DEFAULT_SYSTEM_PROMPT)

    async def test_write_file_block_under_modify_without_think_is_allowed(self):
        handler = self._handler(intent_type="MODIFY")

        decision = await handler.decide(
            ParsedModelOutput(
                response='<action>{"type":"write_file_block","path":"a.py","overwrite":true}</action><file_content>x</file_content>',
                segments=[SimpleNamespace(type="action", content={"type": "write_file_block", "path": "a.py"})],
                has_action_segment=True,
                visible_text="",
            ),
            malformed_action_retries=0,
            audit_marker_retries=0,
        )

        self.assertFalse(decision.handled)
        self.assertEqual("no_invalid_kind", decision.reason)

    async def test_write_file_block_under_modify_with_checkpoint_passes(self):
        handler = self._handler(intent_type="MODIFY")

        decision = await handler.decide(
            ParsedModelOutput(
                response=(
                    "<think>\n! file path chosen\n? need one raw file write\n→ write_file_block a.py\n</think>"
                    "<memory_review status=\"no_change\" scope=\"intent\" />"
                    "<memory_update_done />"
                    '<action>{"type":"write_file_block","path":"a.py","overwrite":true}</action>'
                    "<file_content>x</file_content>"
                ),
                segments=[SimpleNamespace(type="action", content={"type": "write_file_block", "path": "a.py"})],
                has_action_segment=True,
                visible_text="",
            ),
            malformed_action_retries=0,
            audit_marker_retries=0,
        )

        self.assertFalse(decision.handled)
        self.assertEqual("no_invalid_kind", decision.reason)

    def test_file_content_is_not_user_visible_plaintext(self):
        text = '<action>{"type":"write_file_block","path":"a.py","overwrite":true}</action><file_content>hello</file_content>'
        self.assertEqual("", extract_visible_text_for_user(text))


if __name__ == "__main__":
    unittest.main()
