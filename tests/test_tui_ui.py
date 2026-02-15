import unittest

from modules.tui_ui import TuiUI


class TestTuiUiSanitizer(unittest.TestCase):
    def test_write_file_large_content_is_sanitized_for_display(self):
        command = {
            "type": "write_file",
            "path": "a.txt",
            "content": "x" * 5000,
        }
        safe = TuiUI.sanitize_tool_call_for_display(command, preview_limit=100)

        self.assertEqual(safe["type"], "write_file")
        self.assertEqual(safe["path"], "a.txt")
        self.assertIn("content omitted in UI", safe["content"])
        self.assertEqual(command["content"], "x" * 5000)  # Original is unchanged.

    def test_write_file_small_content_is_not_sanitized(self):
        command = {
            "type": "write_file",
            "path": "a.txt",
            "content": "short",
        }
        safe = TuiUI.sanitize_tool_call_for_display(command, preview_limit=100)
        self.assertEqual(safe["content"], "short")


if __name__ == "__main__":
    unittest.main()

