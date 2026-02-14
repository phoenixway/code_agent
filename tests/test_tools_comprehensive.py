import unittest
from unittest.mock import patch, MagicMock, AsyncMock
import asyncio
import tempfile
import shutil
from pathlib import Path
from modules.processor import ResponseProcessor
from modules.tools.manager import ToolManager
from modules.policy import PermissionPolicy
from modules.tools.definitions.shell import ShellTool

class TestFileTools(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.test_dir = tempfile.mkdtemp()
        self.ui = MagicMock()
        self.ui.show_diff_preview = AsyncMock(return_value=True)
        self.tool_manager = ToolManager()
        self.tool_manager.load_tools()
        self.policy = PermissionPolicy(self.ui, mode="always")
        self.processor = ResponseProcessor(self.ui, self.tool_manager, chat=None, policy=self.policy)

    def tearDown(self):
        shutil.rmtree(self.test_dir)

    async def test_read_file_success(self):
        file_path = Path(self.test_dir) / "test.txt"
        file_path.write_text("file content")
        command = {"type": "read_file", "path": str(file_path)}
        result = await self.processor.process_single_action(command)
        self.assertEqual(result["status"], "success")
        self.assertEqual(result["output"], "file content")

    async def test_read_file_not_found(self):
        command = {"type": "read_file", "path": str(Path(self.test_dir) / "missing.txt")}
        result = await self.processor.process_single_action(command)
        self.assertEqual(result["status"], "error")
        self.assertEqual(result.get("error_code"), "NOT_FOUND")
        self.assertTrue(result.get("recoverable"))
        self.assertIn("File not found", result["output"])

    async def test_create_file_already_exists(self):
        file_path = Path(self.test_dir) / "existing.txt"
        file_path.touch()
        command = {"type": "create_file", "path": str(file_path), "content": "foo"}
        result = await self.processor.process_single_action(command)
        self.assertEqual(result["status"], "error")
        self.assertIn("already exists", result["output"])

    async def test_create_file_success(self):
        file_path = Path(self.test_dir) / "new.txt"
        command = {"type": "create_file", "path": str(file_path), "content": "content"}
        result = await self.processor.process_single_action(command)
        self.assertEqual(result["status"], "success")
        self.assertTrue(file_path.exists())
        self.assertEqual(file_path.read_text(), "content")

    async def test_create_file_permission_error(self):
        # This is hard to test reliably without changing file system permissions.
        # We will mock the apply method to simulate the error.
        with patch('modules.types.ChangeProposal.apply', side_effect=PermissionError("Access denied")):
            command = {"type": "create_file", "path": "/root/test.txt", "content": "foo"}
            result = await self.processor.process_single_action(command)
            self.assertEqual(result["status"], "error")
            self.assertIn("Access denied", result["output"])

    async def test_edit_file_not_found(self):
        command = {"type": "edit_file", "path": str(Path(self.test_dir) / "missing.txt"), "search_text": "foo", "replace_text": "bar"}
        result = await self.processor.process_single_action(command)
        self.assertEqual(result["status"], "error")
        self.assertIn("File not found", result["output"])

    async def test_edit_file_block_not_found(self):
        file_path = Path(self.test_dir) / "test.txt"
        file_path.write_text("Line 1\nLine 2\nLine 3")
        command = {"type": "edit_file", "path": str(file_path), "search_text": "Line 4", "replace_text": "Line 5"}
        result = await self.processor.process_single_action(command)
        self.assertEqual(result["status"], "error")
        self.assertIn("Search block not found", result["output"])

    async def test_edit_file_success(self):
        file_path = Path(self.test_dir) / "test.txt"
        file_path.write_text("Hello World")
        command = {"type": "edit_file", "path": str(file_path), "search_text": "World", "replace_text": "Universe"}
        result = await self.processor.process_single_action(command)
        self.assertEqual(result["status"], "success")
        self.assertEqual(file_path.read_text(), "Hello Universe")

    async def test_list_directory_success(self):
        subdir = Path(self.test_dir) / "src"
        subdir.mkdir(parents=True, exist_ok=True)
        file_path = subdir / "main.py"
        file_path.write_text("print('ok')")

        command = {"type": "list_directory", "path": str(self.test_dir)}
        result = await self.processor.process_single_action(command)
        self.assertEqual(result["status"], "success")
        self.assertIn("src/", result["output"])

    async def test_read_file_skeleton_success(self):
        file_path = Path(self.test_dir) / "sample.py"
        file_path.write_text("def foo():\n    return 1\n")
        with patch("modules.tools.definitions.files.CodeParser") as mock_parser_cls:
            parser_inst = mock_parser_cls.return_value
            parser_inst.configs = {".py": {"name": "python"}}
            parser_inst.get_skeleton.return_value = "ƒ def foo() : # ... implementation hidden ..."
            command = {"type": "read_file_skeleton", "path": str(file_path)}
            result = await self.processor.process_single_action(command)
        self.assertEqual(result["status"], "success")
        self.assertEqual(result.get("view"), "skeleton")
        self.assertIn("Skeleton for", result["output"])
        self.assertIn("def foo", result["output"])

    async def test_read_file_skeleton_unsupported_extension(self):
        file_path = Path(self.test_dir) / "sample.txt"
        file_path.write_text("plain text")
        command = {"type": "read_file_skeleton", "path": str(file_path)}
        result = await self.processor.process_single_action(command)
        self.assertEqual(result["status"], "error")
        self.assertEqual(result.get("error_code"), "VALIDATION_ERROR")
        self.assertIn("not supported", result["output"].lower())

class TestShellTool(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.shell_tool = ShellTool()

    async def test_shell_empty_command(self):
        result = await self.shell_tool.execute(command="")
        self.assertEqual(result["status"], "error")
        self.assertEqual(result["output"], "No command provided.")

    async def test_shell_success_output(self):
        with patch('asyncio.create_subprocess_shell') as mock_shell:
            mock_proc = MagicMock()
            mock_proc.communicate = AsyncMock(return_value=(b"hello\n", b""))
            mock_proc.returncode = 0
            mock_shell.return_value = mock_proc
            
            result = await self.shell_tool.execute(command="echo hello")
            
            self.assertEqual(result["status"], "success")
            self.assertEqual(result["output"], "hello")

    async def test_shell_error_stderr(self):
        with patch('asyncio.create_subprocess_shell') as mock_shell:
            mock_proc = MagicMock()
            mock_proc.communicate = AsyncMock(return_value=(b"", b"command not found"))
            mock_proc.returncode = 127
            mock_shell.return_value = mock_proc
            
            result = await self.shell_tool.execute(command="invalid_cmd")
            
            self.assertEqual(result["status"], "error")
            self.assertEqual(result["output"], "command not found")

    async def test_shell_exception_handling(self):
        with patch('asyncio.create_subprocess_shell', side_effect=OSError("System overloaded")):
            result = await self.shell_tool.execute(command="ls")
            self.assertEqual(result["status"], "error")
            self.assertIn("System overloaded", result["output"])

    async def test_shell_timeout_kills_process(self):
        with patch('asyncio.create_subprocess_shell') as mock_shell:
            mock_proc = MagicMock()
            mock_proc.communicate = AsyncMock(side_effect=[asyncio.TimeoutError(), (b"", b"")])
            mock_proc.returncode = None
            mock_proc.kill = MagicMock()
            mock_shell.return_value = mock_proc

            result = await self.shell_tool.execute(command="sleep 60", timeout=1)

            self.assertEqual(result["status"], "error")
            self.assertIn("timed out", result["output"])
            mock_proc.kill.assert_called_once()

    async def test_shell_blocks_too_long_command(self):
        with patch("modules.tools.definitions.shell.load_settings", return_value={"max_shell_command_length": 5}):
            result = await self.shell_tool.execute(command="echo too long")
            self.assertEqual(result["status"], "error")
            self.assertIn("length exceeds 5", result["output"])

    async def test_shell_blocklist_pattern(self):
        with patch(
            "modules.tools.definitions.shell.load_settings",
            return_value={"shell_blocklist": ["danger_cmd"]},
        ):
            result = await self.shell_tool.execute(command="danger_cmd --flag")
            self.assertEqual(result["status"], "error")
            self.assertIn("blocked by policy pattern", result["output"])

    async def test_shell_allowlist_prefixes(self):
        with patch(
            "modules.tools.definitions.shell.load_settings",
            return_value={"shell_allowlist_prefixes": ["echo", "ls"]},
        ):
            blocked = await self.shell_tool.execute(command="cat /etc/hosts")
            self.assertEqual(blocked["status"], "error")
            self.assertIn("allowlist prefixes", blocked["output"])

if __name__ == "__main__":
    unittest.main()
