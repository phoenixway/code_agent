import unittest
from unittest.mock import MagicMock, AsyncMock, patch
import asyncio
from tui import TUI

class TestCLICommands(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.agent = MagicMock()
        self.agent.context_manager = MagicMock()
        self.agent.comm_log = MagicMock()
        
        # We need to mock the TUI and its UI component
        self.app = TUI(self.agent)
        self.app.ui = AsyncMock()
        
        # Mock Input and message
        self.mock_input = MagicMock()
        self.mock_input.value = ""
        self.message = MagicMock()
        self.message.input = self.mock_input

    async def test_add_command_single_file(self):
        """Test /add with a single file."""
        self.message.value = "/add test.py"
        self.agent.context_manager.add_path.return_value = 1
        
        await self.app.on_input_submitted(self.message)
        
        self.agent.context_manager.add_path.assert_called_once_with("test.py")
        self.app.ui.print_system.assert_called_with("✅ Added 1 file(s) to context.")

    async def test_add_command_multiple_files(self):
        """Test /add with multiple files and quoted paths."""
        self.message.value = '/add file1.py "folder with spaces/file2.py"'
        self.agent.context_manager.add_path.return_value = 1 # Return 1 for each call
        
        await self.app.on_input_submitted(self.message)
        
        self.assertEqual(self.agent.context_manager.add_path.call_count, 2)
        self.agent.context_manager.add_path.assert_any_call("file1.py")
        self.agent.context_manager.add_path.assert_any_call("folder with spaces/file2.py")
        self.app.ui.print_system.assert_called_with("✅ Added 2 file(s) to context.")

    async def test_add_command_no_args(self):
        """Test /add without arguments."""
        self.message.value = "/add"
        await self.app.on_input_submitted(self.message)
        
        self.app.ui.print_error.assert_called_with("Usage: /add <path1> [path2 ...]")
        self.agent.context_manager.add_path.assert_not_called()

    async def test_drop_command_specific_files(self):
        """Test /drop with specific files."""
        self.message.value = "/drop file1.py file2.py"
        self.agent.context_manager.remove_path.return_value = 1
        
        await self.app.on_input_submitted(self.message)
        
        self.assertEqual(self.agent.context_manager.remove_path.call_count, 2)
        self.app.ui.print_system.assert_called_with("🗑️ Removed 2 file(s) from context.")

    async def test_drop_command_all(self):
        """Test /drop without arguments (clear all)."""
        self.message.value = "/drop"
        await self.app.on_input_submitted(self.message)
        
        self.agent.context_manager.clear.assert_called_once()
        self.app.ui.print_system.assert_called_with("🗑️ Context cleared (all files removed).")

    async def test_cd_command(self):
        """Test /cd command."""
        import os
        import tempfile
        with tempfile.TemporaryDirectory() as tmpdir:
            original_dir = os.getcwd()
            try:
                self.message.value = f"/cd {tmpdir}"
                await self.app.on_input_submitted(self.message)
                
                self.assertEqual(os.getcwd(), os.path.realpath(tmpdir))
                self.app.ui.print_system.assert_called()
                # Check if the message contains the path (using partial match as path might be resolved)
                call_args = self.app.ui.print_system.call_args[0][0]
                self.assertIn("Working directory changed to", call_args)
            finally:
                os.chdir(original_dir)

if __name__ == "__main__":
    unittest.main()
