import unittest
from unittest.mock import patch, MagicMock, mock_open, AsyncMock
import asyncio
from modules.tools.definitions.files import ReadFileTool, CreateFileTool, EditFileTool
from modules.tools.definitions.shell import ShellTool

class TestFileTools(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.read_tool = ReadFileTool()
        self.create_tool = CreateFileTool()
        self.edit_tool = EditFileTool()

    @patch('pathlib.Path.exists')
    @patch('pathlib.Path.read_text')
    async def test_read_file_success(self, mock_read, mock_exists):
        mock_exists.return_value = True
        mock_read.return_value = "file content"
        
        result = await self.read_tool.execute(path="test.txt")
        self.assertEqual(result["status"], "success")
        self.assertEqual(result["output"], "file content")

    @patch('pathlib.Path.exists')
    async def test_read_file_not_found(self, mock_exists):
        mock_exists.return_value = False
        result = await self.read_tool.execute(path="missing.txt")
        self.assertEqual(result["status"], "error")
        self.assertIn("File not found", result["output"])

    @patch('pathlib.Path.exists')
    async def test_create_file_already_exists(self, mock_exists):
        mock_exists.return_value = True
        result = await self.create_tool.execute(path="existing.txt", content="foo")
        self.assertEqual(result["status"], "error")
        self.assertIn("already exists", result["output"])

    @patch('pathlib.Path.exists')
    @patch('pathlib.Path.write_text')
    @patch('pathlib.Path.parent')
    async def test_create_file_success(self, mock_parent, mock_write, mock_exists):
        mock_exists.return_value = False
        # Setup parent.mkdir
        mock_parent_obj = MagicMock()
        mock_parent.return_value = mock_parent_obj # This fails because parent is a property on Path instance, not class
        
        # Better approach: mock Path object completely
        with patch('modules.tools.definitions.files.Path') as MockPath:
            # Instance mock
            p_mock = MagicMock()
            MockPath.return_value = p_mock
            
            p_mock.exists.return_value = False
            
            result = await self.create_tool.execute(path="new.txt", content="content")
            
            self.assertEqual(result["status"], "success")
            p_mock.write_text.assert_called_with("content", encoding='utf-8')
            p_mock.parent.mkdir.assert_called_with(parents=True, exist_ok=True)

    @patch('modules.tools.definitions.files.Path')
    async def test_create_file_permission_error(self, MockPath):
        p_mock = MagicMock()
        MockPath.return_value = p_mock
        p_mock.exists.return_value = False
        p_mock.write_text.side_effect = PermissionError("Access denied")
        
        result = await self.create_tool.execute(path="root.txt", content="foo")
        self.assertEqual(result["status"], "error")
        self.assertIn("Access denied", result["output"])

    @patch('modules.tools.definitions.files.Path')
    async def test_edit_file_not_found(self, MockPath):
        p_mock = MagicMock()
        MockPath.return_value = p_mock
        p_mock.exists.return_value = False
        
        result = await self.edit_tool.execute(path="missing.txt", search_text="foo", replace_text="bar")
        self.assertEqual(result["status"], "error")
        self.assertIn("File not found", result["output"])

    @patch('modules.tools.definitions.files.Path')
    async def test_edit_file_block_not_found(self, MockPath):
        p_mock = MagicMock()
        MockPath.return_value = p_mock
        p_mock.exists.return_value = True
        p_mock.read_text.return_value = "Line 1\nLine 2\nLine 3"
        
        result = await self.edit_tool.execute(path="test.txt", search_text="Line 4", replace_text="Line 5")
        self.assertEqual(result["status"], "error")
        self.assertIn("Search block not found", result["output"])
        p_mock.write_text.assert_not_called()

    @patch('modules.tools.definitions.files.Path')
    async def test_edit_file_success(self, MockPath):
        p_mock = MagicMock()
        MockPath.return_value = p_mock
        p_mock.exists.return_value = True
        p_mock.read_text.return_value = "Hello World"
        
        result = await self.edit_tool.execute(path="test.txt", search_text="World", replace_text="Universe")
        
        self.assertEqual(result["status"], "success")
        p_mock.write_text.assert_called_with("Hello Universe", encoding='utf-8')


class TestShellTool(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.shell_tool = ShellTool()

    async def test_shell_empty_command(self):
        result = await self.shell_tool.execute(command="")
        self.assertEqual(result["status"], "error")
        self.assertEqual(result["output"], "No command provided.")

    async def test_shell_success_output(self):
        # Mock asyncio.create_subprocess_shell
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
        """Test that unhandled exceptions (e.g. system resource limits) are caught."""
        with patch('asyncio.create_subprocess_shell', side_effect=OSError("System overloaded")):
            result = await self.shell_tool.execute(command="ls")
            self.assertEqual(result["status"], "error")
            self.assertIn("System overloaded", result["output"])

if __name__ == "__main__":
    unittest.main()
