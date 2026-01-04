import unittest
from unittest.mock import patch, MagicMock
import os
import shutil
from modules.files import FileModule
from modules.policy import PermissionPolicy
from modules.ui import UI
from modules.processor import ResponseProcessor

class TestFileOperations(unittest.TestCase):
    def setUp(self):
        self.test_dir = "test_temp_files"
        os.makedirs(self.test_dir, exist_ok=True)
        self.ui = UI()
        self.files = FileModule()
        # Mock other dependencies for ResponseProcessor
        self.chat = MagicMock()
        self.policy = PermissionPolicy(self.ui, mode="always") # Always allow for these tests
        self.processor = ResponseProcessor(self.ui, self.files, self.chat, self.policy)
        self.test_file = os.path.join(self.test_dir, "test.txt")

    def tearDown(self):
        if os.path.exists(self.test_dir):
            shutil.rmtree(self.test_dir)

    def test_handle_create_file(self):
        """Test creating a new file."""
        action = {"type": "create_file", "path": self.test_file, "content": "initial content"}
        result = self.processor.process_single_action(action)
        self.assertEqual(result["status"], "success")
        self.assertTrue(os.path.exists(self.test_file))
        with open(self.test_file, "r") as f:
            self.assertEqual(f.read(), "initial content")

    def test_handle_create_existing_file_fails(self):
        """Test that creating a file that already exists fails."""
        # Create the file first
        with open(self.test_file, "w") as f:
            f.write("I exist.")
        action = {"type": "create_file", "path": self.test_file, "content": "new content"}
        result = self.processor.process_single_action(action)
        self.assertEqual(result["status"], "failed")

    def test_handle_write_file_overwrite(self):
        """Test overwriting an existing file."""
        # Create and write initial content
        self.processor.process_single_action(
            {"type": "create_file", "path": self.test_file, "content": "old content"}
        )
        # Now, overwrite it using write_file
        action = {"type": "write_file", "path": self.test_file, "content": "new content"}
        result = self.processor.process_single_action(action)
        self.assertEqual(result["status"], "success")
        with open(self.test_file, "r") as f:
            self.assertEqual(f.read(), "new content")

    def test_handle_write_file_to_new_file(self):
        """Test that write_file creates a file if it doesn't exist."""
        action = {"type": "write_file", "path": self.test_file, "content": "written to new file"}
        result = self.processor.process_single_action(action)
        self.assertEqual(result["status"], "success")
        self.assertTrue(os.path.exists(self.test_file))
        with open(self.test_file, "r") as f:
            self.assertEqual(f.read(), "written to new file")

    def test_handle_edit_file(self):
        """Test editing a file with search and replace."""
        self.processor.process_single_action(
            {"type": "create_file", "path": self.test_file, "content": "line one\nline two\nline three"}
        )
        action = {
            "type": "edit_file",
            "path": self.test_file,
            "edits": [
                {"search": "line two", "replace": "line 2"},
                {"search": "line three", "replace": "line 3"}
            ]
        }
        result = self.processor.process_single_action(action)
        self.assertEqual(result["status"], "success")
        with open(self.test_file, "r") as f:
            self.assertEqual(f.read(), "line one\nline 2\nline 3")

class TestPermissionPolicy(unittest.TestCase):
    def setUp(self):
        self.ui = UI()

    @patch('rich.prompt.Confirm.ask')
    def test_check_ask_mode_allow(self, mock_confirm_ask):
        """Test 'ask' mode where the user allows the action."""
        mock_confirm_ask.return_value = True
        policy = PermissionPolicy(self.ui, mode="ask")
        action = {"type": "run_command", "command": "ls"}
        self.assertTrue(policy.check(action))
        mock_confirm_ask.assert_called_once()

    @patch('rich.prompt.Confirm.ask')
    def test_check_ask_mode_deny(self, mock_confirm_ask):
        """Test 'ask' mode where the user denies the action."""
        mock_confirm_ask.return_value = False
        policy = PermissionPolicy(self.ui, mode="ask")
        action = {"type": "write_file", "path": "test.txt"}
        self.assertFalse(policy.check(action))
        mock_confirm_ask.assert_called_once()

    def test_check_always_mode(self):
        """Test 'always' mode, which should always allow."""
        policy = PermissionPolicy(self.ui, mode="always")
        action = {"type": "run_command", "command": "echo 'hello'"}
        self.assertTrue(policy.check(action))

    def test_check_never_mode(self):
        """Test 'never' mode, which should always deny."""
        policy = PermissionPolicy(self.ui, mode="never")
        action = {"type": "run_command", "command": "rm -rf /"}
        self.assertFalse(policy.check(action))

if __name__ == "__main__":
    unittest.main()