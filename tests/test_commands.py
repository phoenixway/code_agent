import unittest
from unittest.mock import MagicMock, AsyncMock, patch
import asyncio
import os
import tempfile
import shutil
from modules.command_handler import CommandHandler

class TestCLICommands(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.app = MagicMock()
        self.app.agent = MagicMock()
        self.app.agent.context_manager = MagicMock()
        self.app.ui = AsyncMock()
        self.command_handler = CommandHandler(self.app)

    async def test_add_command_single_file(self):
        """Test /add with a single file."""
        self.app.agent.context_manager.add_path.return_value = 1
        await self.command_handler.handle("/add test.py")
        self.app.agent.context_manager.add_path.assert_called_once_with("test.py")
        self.app.ui.print_system.assert_called_with("✅ Added 1 file(s) to context.")

    async def test_add_command_multiple_files(self):
        """Test /add with multiple files and quoted paths."""
        self.app.agent.context_manager.add_path.return_value = 1 # Return 1 for each call
        await self.command_handler.handle('/add file1.py "folder with spaces/file2.py"')
        self.assertEqual(self.app.agent.context_manager.add_path.call_count, 2)
        self.app.agent.context_manager.add_path.assert_any_call("file1.py")
        self.app.agent.context_manager.add_path.assert_any_call("folder with spaces/file2.py")
        self.app.ui.print_system.assert_called_with("✅ Added 2 file(s) to context.")

    async def test_add_command_no_args(self):
        """Test /add without arguments."""
        await self.command_handler.handle("/add")
        self.app.ui.print_error.assert_called_with("Usage: /add <path1> [path2 ...]")
        self.app.agent.context_manager.add_path.assert_not_called()

    async def test_drop_command_specific_files(self):
        """Test /drop with specific files."""
        self.app.agent.context_manager.remove_path.return_value = 1
        await self.command_handler.handle("/drop file1.py file2.py")
        self.assertEqual(self.app.agent.context_manager.remove_path.call_count, 2)
        self.app.ui.print_system.assert_called_with("🗑️ Removed 2 file(s) from context.")

    async def test_drop_command_all(self):
        """Test /drop without arguments (clear all)."""
        await self.command_handler.handle("/drop")
        self.app.agent.context_manager.clear.assert_called_once()
        self.app.ui.print_system.assert_called_with("🗑️ Context cleared (all files removed).")

    async def test_cd_command(self):
        """Test /cd command."""
        with tempfile.TemporaryDirectory() as tmpdir:
            original_dir = os.getcwd()
            try:
                await self.command_handler.handle(f"/cd {tmpdir}")
                self.assertEqual(os.getcwd(), os.path.realpath(tmpdir))
                self.app.ui.print_system.assert_called()
                call_args = self.app.ui.print_system.call_args[0][0]
                self.assertIn("Working directory changed to", call_args)
            finally:
                os.chdir(original_dir)

if __name__ == "__main__":
    unittest.main()