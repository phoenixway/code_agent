import tempfile
import unittest
from pathlib import Path

from modules.history import HistoryManager


class MockChatProvider:
    async def get_streaming_response(self, prompt, history):
        yield "summary"


class _CodeParserStub:
    def get_skeleton(self, filename, content):
        return f"SKELETON::{filename}::{len(content)}"


class TestHistoryContext(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.history = HistoryManager(
            chat_provider=MockChatProvider(),
            max_tokens=100,
            storage_dir=self.tmp.name,
        )
        self.history.code_parser = _CodeParserStub()

    def tearDown(self):
        self.tmp.cleanup()

    def test_last_transient_read_file_is_visible_in_api_history(self):
        self.history.add_file_version("a.txt", "line1\nline2")
        self.history.add_transient_file_content("a.txt", 1, "line1\nline2")

        api_history = self.history.get_history_for_api()
        joined = "\n".join(m["content"] for m in api_history if isinstance(m.get("content"), str))
        self.assertIn("SYSTEM RESULT (read_file):", joined)
        self.assertIn("<file_content path='a.txt' version='1'>", joined)

    def test_non_last_transient_read_file_is_skipped(self):
        self.history.add_file_version("a.txt", "line1\nline2")
        self.history.add_transient_file_content("a.txt", 1, "line1\nline2")
        self.history.add_message("user", "next step")

        api_history = self.history.get_history_for_api()
        joined = "\n".join(m["content"] for m in api_history if isinstance(m.get("content"), str))
        self.assertNotIn("SYSTEM RESULT (read_file):", joined)
        self.assertIn("next step", joined)

    def test_large_inactive_file_uses_skeleton(self):
        self.history.SKELETON_THRESHOLD = 20
        self.history.add_file_version("big.kt", "x" * 500)
        self.history.active_files.discard("big.kt")  # force inactive file behavior

        api_history = self.history.get_history_for_api()
        joined = "\n".join(m["content"] for m in api_history if isinstance(m.get("content"), str))
        self.assertIn("<file_skeleton path='big.kt' version='1'>", joined)
        self.assertIn("SKELETON::big.kt::500", joined)

    def test_active_file_limit_shrinks_under_token_pressure(self):
        self.history.SKELETON_THRESHOLD = 20
        self.history.max_tokens = 20
        for i in range(3):
            name = f"f{i}.py"
            self.history.add_file_version(name, "z" * 300)
            # Stable recency ranking: f2 is most recent.
            self.history.files[name][-1]["timestamp"] = i
        self.history.add_message("user", "u " * 400)  # push current_token_count above 1.5x

        api_history = self.history.get_history_for_api()
        joined = "\n".join(m["content"] for m in api_history if isinstance(m.get("content"), str))
        self.assertIn("<file_content path='f2.py' version='1'>", joined)
        self.assertIn("<file_skeleton path='f0.py' version='1'>", joined)
        self.assertIn("<file_skeleton path='f1.py' version='1'>", joined)

    def test_version_storage_deduplicates_identical_content_blob(self):
        v1 = self.history.add_file_version("a.txt", "same")
        v2 = self.history.add_file_version("a.txt", "same")
        self.assertEqual(v1, 1)
        self.assertEqual(v2, 1)
        self.assertEqual(len(self.history.files["a.txt"]), 1)

        blob_hash = self.history.files["a.txt"][0]["blob_hash"]
        blob_file = Path(self.history.blobs_dir) / blob_hash
        self.assertTrue(blob_file.exists())


if __name__ == "__main__":
    unittest.main()

