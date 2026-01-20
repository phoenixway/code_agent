import unittest
from unittest.mock import MagicMock, AsyncMock
from modules.processor import ResponseProcessor

class TestOutputTruncation(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.ui = AsyncMock()
        self.ui.confirm_truncation.return_value = True
        self.tools = MagicMock()
        self.chat = MagicMock()
        self.policy = MagicMock()
        self.policy.check = AsyncMock(return_value=True)
        
        self.processor = ResponseProcessor(self.ui, self.tools, self.chat, self.policy)
        # For testing, set a small limit
        self.processor.MAX_OUTPUT_LENGTH = 100

    def test_truncate_logic(self):
        text = "A" * 150
        truncated = self.processor._truncate_output(text)
        self.assertEqual(len(truncated), 100 + len("\n... (truncated 50 characters) ..."))
        self.assertTrue(truncated.endswith("... (truncated 50 characters) ..."))

    def test_no_truncate_if_short(self):
        text = "Short text"
        truncated = self.processor._truncate_output(text)
        self.assertEqual(text, truncated)

    async def test_processor_applies_truncation(self):
        # Mock a tool that returns long output
        long_output = "B" * 200
        self.tools.call = AsyncMock(return_value={"status": "success", "output": long_output})
        
        command = {"type": "test_tool", "arg": "val"}
        result = await self.processor.process_single_action(command)
        
        self.assertIn("truncated 100 characters", result["output"])
        self.assertEqual(len(result["output"]), 100 + len("\n... (truncated 100 characters) ..."))

if __name__ == "__main__":
    unittest.main()
