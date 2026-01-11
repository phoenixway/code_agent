import unittest
from unittest.mock import patch, MagicMock
from modules.tools.definitions.search import FileSearchTool, ContentSearchTool

class TestSearchTools(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.file_tool = FileSearchTool()
        self.content_tool = ContentSearchTool()

    @patch('subprocess.run')
    async def test_file_search_success(self, mock_run):
        # Setup mock for successful found
        mock_result = MagicMock()
        mock_result.returncode = 0
        mock_result.stdout = "file1.py\nfile2.py"
        mock_run.return_value = mock_result

        result = await self.file_tool.execute(pattern="*.py")
        
        self.assertEqual(result["status"], "success")
        self.assertIn("file1.py", result["output"])
        self.assertIn("file2.py", result["output"])
        
        # Check command args
        args = mock_run.call_args[0][0]
        self.assertIn("fd", args)
        self.assertIn("*.py", args)

    @patch('subprocess.run')
    async def test_file_search_limit_output(self, mock_run):
        # Setup mock for many results
        mock_result = MagicMock()
        mock_result.returncode = 0
        # Create 60 lines
        mock_result.stdout = "\n".join([f"file{i}.txt" for i in range(60)])
        mock_run.return_value = mock_result

        result = await self.file_tool.execute(pattern="*.txt")
        
        self.assertEqual(result["status"], "success")
        self.assertIn("Found 60 files", result["output"])
        self.assertIn("Showing first 50", result["output"])

    @patch('subprocess.run')
    async def test_content_search_success(self, mock_run):
        mock_result = MagicMock()
        mock_result.returncode = 0
        mock_result.stdout = "file.py:10:def main():"
        mock_run.return_value = mock_result

        result = await self.content_tool.execute(pattern="def main")
        
        self.assertEqual(result["status"], "success")
        self.assertEqual(result["output"], "file.py:10:def main():")

    @patch('subprocess.run')
    async def test_content_search_no_matches(self, mock_run):
        # rg returns 1 for no matches
        mock_result = MagicMock()
        mock_result.returncode = 1
        mock_result.stdout = ""
        mock_result.stderr = ""
        mock_run.return_value = mock_result

        result = await self.content_tool.execute(pattern="missing")
        
        self.assertEqual(result["status"], "success")
        self.assertEqual(result["output"], "No matches found.")

if __name__ == "__main__":
    unittest.main()
