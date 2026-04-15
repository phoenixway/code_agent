import unittest
from unittest.mock import MagicMock, AsyncMock, patch
import asyncio
from agent import AngelicaAgent
from modules.tools.manager import ToolManager
from modules.tools.base import BaseTool
from modules.history import HistoryManager

# --- Mock Classes ---

class MockTool(BaseTool):
    name = "mock_tool"
    description = "A mock tool for testing."
    async def execute(self, **kwargs):
        return {"status": "success", "output": f"Executed with {kwargs}"}

class MockChatProvider:
    def __init__(self):
        self.model_name = "mock-model"
    
    async def get_streaming_response(self, prompt, history):
        yield "Summary of conversation"

# --- Tests ---

class TestToolManager(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.manager = ToolManager()
        # Manually inject a mock tool
        self.mock_tool = MockTool()
        self.manager.tools[self.mock_tool.name] = self.mock_tool

    def test_get_tools_prompt(self):
        """Test that prompt generation includes the tool."""
        prompt = self.manager.get_tools_prompt()
        self.assertIn("mock_tool", prompt)
        self.assertIn("A mock tool for testing", prompt)

    async def test_tool_call_success(self):
        """Test calling a tool successfully."""
        result = await self.manager.call("mock_tool", param="test")
        self.assertEqual(result["status"], "success")
        self.assertIn("Executed with {'param': 'test'}", result["output"])

    async def test_tool_call_unknown(self):
        """Test calling a non-existent tool."""
        result = await self.manager.call("unknown_tool")
        self.assertEqual(result["status"], "error")


class TestHistoryManager(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.chat = MockChatProvider()
        self.ui = AsyncMock() # UI methods are async
        self.history = HistoryManager(self.chat, max_tokens=10) # Low limit for testing

    def test_add_message(self):
        """Test adding messages to history."""
        self.history.add_message("user", "Hello")
        self.assertEqual(len(self.history.messages), 1)
        self.assertEqual(self.history.messages[0]["content"], "Hello")

    def test_add_empty_message(self):
        """Test that empty messages are ignored."""
        self.history.add_message("user", "   ")
        self.assertEqual(len(self.history.messages), 0)

    def test_add_file_version_deduplicates_identical_content(self):
        v1 = self.history.add_file_version("a.txt", "same-content")
        v2 = self.history.add_file_version("a.txt", "same-content")
        v3 = self.history.add_file_version("a.txt", "changed-content")

        self.assertEqual(v1, 1)
        self.assertEqual(v2, 1)
        self.assertEqual(v3, 2)
        self.assertEqual(len(self.history.files["a.txt"]), 2)

    async def test_summarize_history(self):
        """Test history summarization when limit is exceeded."""
        # Add messages to exceed 10 tokens (approx)
        self.history.add_message("user", "This is a very long message that should definitely trigger the summarization logic because it is way over the limit.")
        
        await self.history.check_and_summarize(self.ui)
        
        # Check if UI was notified
        self.ui.print_system.assert_called()
        # Check if history was collapsed
        self.assertEqual(len(self.history.messages), 1)
        self.assertEqual(self.history.messages[0]["role"], "system")
        self.assertIn("Previous conversation summary", self.history.messages[0]["content"])

class TestEdgeCases(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.ui = MagicMock()
        self.ui.check = AsyncMock(return_value=True) # Policy check passes
        
        # Files Mock
        self.files_mock = MagicMock()
        self.files_mock.read_file.return_value = "content"
        
        # Tool Manager Mock
        self.tool_manager = MagicMock()
        self.tool_manager.call = AsyncMock(return_value={"status": "success"})
        
        # Chat Mock
        self.chat = MagicMock()
        
        # Policy Mock
        self.policy = MagicMock()
        self.policy.check = AsyncMock(return_value=True)

        # Initialize components
        from modules.context import ContextManager
        from modules.processor import ResponseProcessor
        from modules.files import FileModule
        
        self.context_manager = ContextManager(self.files_mock)
        self.processor = ResponseProcessor(self.ui, self.tool_manager, self.chat, self.policy)
        self.real_files = FileModule() # For file edge cases

    def test_context_get_structure_permission_error(self):
        """Test graceful handling of PermissionError during directory traversal."""
        with patch('pathlib.Path.iterdir', side_effect=PermissionError("Access denied")):
            structure = self.context_manager.get_project_structure(root_dir="/root")
            self.assertIn("Project Structure:", structure)
            # Should just return the header and not crash

    def test_context_add_non_existent_path(self):
        """Test adding a path that does not exist."""
        count = self.context_manager.add_path("/non/existent/path")
        self.assertEqual(count, 0)
        self.assertEqual(len(self.context_manager.basket), 0)

    def test_context_remove_partial_path(self):
        """Test removing multiple files via directory prefix."""
        self.context_manager.basket = {
            "/tmp/project/file1.py": "content",
            "/tmp/project/file2.py": "content",
            "/tmp/other/file3.py": "content"
        }
        count = self.context_manager.remove_path("/tmp/project")
        self.assertEqual(count, 2)
        self.assertEqual(len(self.context_manager.basket), 1)
        self.assertIn("/tmp/other/file3.py", self.context_manager.basket)

    async def test_processor_missing_action(self):
        """Test processor response when action/type is missing."""
        command = {"param": "value"} # No action
        result = await self.processor.process_single_action(command)
        self.assertEqual(result["status"], "failed")
        self.assertIn("Could not identify tool name", result["output"])

    async def test_processor_fallback_command_parsing(self):
        """Test that 'command' key is used as action if type is missing."""
        # Case 1: Simple command -> Tool name
        cmd1 = {"command": "read_file", "path": "test.txt"}
        await self.processor.process_single_action(cmd1)
        # 'command' key is consumed to determine action type and not passed as arg
        self.tool_manager.call.assert_called_with("read_file", ui=self.ui, path="test.txt")
        
        # Case 2: Complex command -> run_shell
        cmd2 = {"command": "ls -la | grep py"}
        await self.processor.process_single_action(cmd2)
        self.tool_manager.call.assert_called_with("run_shell", ui=self.ui, command="ls -la | grep py")

    async def test_processor_argument_flattening(self):
        """Test that nested params/arguments are flattened."""
        cmd = {
            "type": "test_tool",
            "params": {"arg1": "val1"},
            "arguments": {"arg2": "val2"}
        }
        await self.processor.process_single_action(cmd)
        # Check that arg1 and arg2 were passed to call
        # args passed to call should be: arg1='val1', arg2='val2'
        call_kwargs = self.tool_manager.call.call_args.kwargs
        self.assertEqual(call_kwargs["arg1"], "val1")
        self.assertEqual(call_kwargs["arg2"], "val2")

    async def test_processor_rejects_sanitized_write_payload(self):
        cmd = {
            "type": "write_file",
            "path": "structs_methods.go",
            "content": "[content omitted: 5483 chars, sha256:8d69e3d59365, preview:'// structs_methods.go']",
        }
        result = await self.processor.process_single_action(cmd)
        self.assertEqual(result["status"], "failed")
        self.assertEqual(result["error_code"], "VALIDATION_ERROR")
        self.assertIn("sanitized placeholder", result["output"])
        self.tool_manager.call.assert_not_called()

    async def test_processor_normalizes_nested_command_for_file_tool(self):
        cmd = {
            "type": "create_file",
            "command": "{\"path\":\"a.go\",\"content\":\"package main\"}"
        }
        result = await self.processor.process_single_action(cmd)
        self.assertEqual(result["status"], "success")
        self.tool_manager.call.assert_called_with(
            "create_file", ui=self.ui, path="a.go", content="package main"
        )

    def test_file_module_binary_read(self):
        """Test reading a binary file raises error gracefully (or handled)."""
        # Create a temp binary file
        import tempfile
        import os
        with tempfile.NamedTemporaryFile(delete=False) as f:
            f.write(b'\x80\x81\x82') # Invalid UTF-8
            fname = f.name
        
        try:
            with self.assertRaises(UnicodeDecodeError):
                self.real_files.read_file(fname)
        finally:
            os.remove(fname)

if __name__ == "__main__":
    unittest.main()
