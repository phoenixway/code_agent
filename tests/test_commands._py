import unittest
from unittest.mock import MagicMock, AsyncMock, patch
import asyncio
import os
import tempfile
import shutil
from pathlib import Path
from types import SimpleNamespace
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

    async def test_dump_command_creates_dump_file(self):
        """Test /dump creates a diagnostics dump file."""
        with tempfile.TemporaryDirectory() as tmpdir:
            original_dir = os.getcwd()
            os.chdir(tmpdir)
            try:
                with patch("modules.command_handler.get_log_files", return_value=[]):
                    handled = await self.command_handler.handle("/dump")
                    self.assertTrue(handled)

                dumps_dir = os.path.join(tmpdir, "dumps")
                self.assertTrue(os.path.isdir(dumps_dir))
                files = os.listdir(dumps_dir)
                self.assertTrue(any(name.startswith("agent_dump_") and name.endswith(".txt") for name in files))
                self.app.ui.print_system.assert_called()
            finally:
                os.chdir(original_dir)

    async def test_dump_full_with_custom_filename(self):
        """Test /dump --full writes to provided filename."""
        with tempfile.TemporaryDirectory() as tmpdir:
            original_dir = os.getcwd()
            os.chdir(tmpdir)
            try:
                target = "custom_dump.txt"
                with patch("modules.command_handler.get_log_files", return_value=[]):
                    handled = await self.command_handler.handle(f"/dump --full {target}")
                    self.assertTrue(handled)
                self.assertTrue(os.path.exists(target))
                with open(target, "r", encoding="utf-8") as f:
                    content = f.read()
                self.assertIn("Dump mode: full", content)
                self.assertIn("RUNTIME DIAGNOSTICS", content)
            finally:
                os.chdir(original_dir)

    async def test_dump_full_includes_failed_action_and_file_snapshot(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            original_dir = os.getcwd()
            os.chdir(tmpdir)
            try:
                target_file = Path(tmpdir) / "target.txt"
                target_file.write_text("alpha\nbeta\n", encoding="utf-8")
                self.app.agent.state = SimpleNamespace(
                    last_error_code="VALIDATION_ERROR",
                    last_error_recoverable=True,
                    consecutive_same_error_count=2,
                    last_failed_action_command={
                        "type": "edit_file",
                        "path": str(target_file),
                        "search_text": "gamma",
                        "replace_text": "delta",
                    },
                    last_failed_action_result={
                        "status": "error",
                        "error_code": "VALIDATION_ERROR",
                        "output": "Search block not found",
                    },
                )
                target = "full_dump_with_failed_action.txt"
                with patch("modules.command_handler.get_log_files", return_value=[]):
                    await self.command_handler.handle(f"/dump --full {target}")
                content = Path(target).read_text(encoding="utf-8")
                self.assertIn("LAST FAILED ACTION COMMAND:", content)
                self.assertIn("\"search_text\": \"gamma\"", content)
                self.assertIn("FAILED ACTION FILE SNAPSHOT:", content)
                self.assertIn("alpha", content)
            finally:
                os.chdir(original_dir)

    async def test_dump_skips_empty_logs(self):
        """Test empty log files are reported as skipped."""
        with tempfile.TemporaryDirectory() as tmpdir:
            original_dir = os.getcwd()
            os.chdir(tmpdir)
            try:
                empty_log = os.path.join(tmpdir, "debug.log")
                with open(empty_log, "w", encoding="utf-8") as f:
                    f.write("")
                with patch("modules.command_handler.get_log_files", return_value=[Path(empty_log)]):
                    await self.command_handler.handle("/dump")
                dumps_dir = os.path.join(tmpdir, "dumps")
                dump_name = sorted(os.listdir(dumps_dir))[-1]
                with open(os.path.join(dumps_dir, dump_name), "r", encoding="utf-8") as f:
                    content = f.read()
                self.assertIn("Skipped empty log files:", content)
            finally:
                os.chdir(original_dir)

    async def test_filter_log_for_session_handles_multiline_records(self):
        """Session filter should keep full multiline records for current session only."""
        log_text = (
            "2026-02-14 09:00:00,000 - --- OUTGOING ---\n"
            "old line 1\n"
            "old line 2\n"
            "2026-02-14 10:30:00,000 - --- OUTGOING ---\n"
            "new line 1\n"
            "new line 2\n"
        )
        self.command_handler.session_started_at = self.command_handler.session_started_at.replace(
            hour=10, minute=0, second=0, microsecond=0
        )
        filtered = self.command_handler._filter_log_for_session(Path("communication.log"), log_text)
        self.assertIn("2026-02-14 10:30:00,000 - --- OUTGOING ---", filtered)
        self.assertIn("new line 1", filtered)
        self.assertNotIn("old line 1", filtered)

    async def test_clearsession_resets_runtime_state(self):
        """Test /clearsession clears runtime memory, not only session file."""
        self.app.agent.session_manager = MagicMock()
        self.app.agent.session_manager.clear_session.return_value = True
        self.app.agent.history = MagicMock()
        self.app.agent.context_manager = MagicMock()
        self.app.agent.state = MagicMock()
        self.app.agent.state.session_tokens = 123
        self.app.agent.state.confirmation_count = 7

        handled = await self.command_handler.handle("/clearsession")
        self.assertTrue(handled)
        self.app.agent.session_manager.clear_session.assert_called_once()
        self.app.agent.history.clear_history.assert_called_once()
        self.app.agent.context_manager.clear.assert_called_once()
        self.assertEqual(self.app.agent.state.session_tokens, 0)
        self.assertEqual(self.app.agent.state.confirmation_count, 0)
        self.app.ui.update_token_status.assert_called_once()

if __name__ == "__main__":
    unittest.main()
