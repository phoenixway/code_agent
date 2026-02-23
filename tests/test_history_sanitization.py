import json
import re
import tempfile
import unittest

from modules.history import HistoryManager


class _DummyChatProvider:
    def count_tokens(self, text):
        return len(str(text))


class TestHistorySanitization(unittest.TestCase):
    def setUp(self):
        self.tmpdir = tempfile.TemporaryDirectory()
        self.history = HistoryManager(
            chat_provider=_DummyChatProvider(),
            storage_dir=self.tmpdir.name,
        )

    def tearDown(self):
        self.tmpdir.cleanup()

    def test_action_block_redacts_large_write_content_without_preview(self):
        large_content = "A" * 512
        assistant_message = (
            "<think>ok</think>\n"
            '<action type="write_file">\n'
            + json.dumps({"path": "a.txt", "content": large_content}, ensure_ascii=False)
            + "\n</action>"
        )
        self.history.add_message("assistant", assistant_message)

        stored = self.history.messages[-1]["content"]
        self.assertNotIn(large_content, stored)
        self.assertNotIn("preview", stored)

        match = re.search(r"<action type=\"write_file\">(.*?)</action>", stored, re.DOTALL)
        self.assertIsNotNone(match)
        payload = json.loads(match.group(1).strip())
        self.assertNotIn("content", payload)
        self.assertTrue(payload.get("content_redacted"))
        self.assertEqual(payload.get("content_size"), 512)
        self.assertTrue(payload.get("content_blob_hash"))

    def test_json_tool_call_redacts_large_write_content_without_preview(self):
        large_content = "B" * 700
        raw_json = json.dumps(
            {"type": "write_file", "path": "b.txt", "content": large_content},
            ensure_ascii=False,
        )

        redacted = self.history._compress_assistant_tool_call(raw_json)
        payload = json.loads(redacted)
        self.assertNotIn("content", payload)
        self.assertTrue(payload.get("content_redacted"))
        self.assertEqual(payload.get("content_size"), 700)
        self.assertTrue(payload.get("content_blob_hash"))


if __name__ == "__main__":
    unittest.main()
