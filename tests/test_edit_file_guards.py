import tempfile
import unittest
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock

from modules.policy import PermissionPolicy
from modules.processor import ResponseProcessor
from modules.tools.manager import ToolManager


class EditFileGuardTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.test_dir = tempfile.TemporaryDirectory()
        self.ui = MagicMock()
        self.ui.show_diff_preview = AsyncMock(return_value=True)
        self.tool_manager = ToolManager()
        self.tool_manager.load_tools()
        self.policy = PermissionPolicy(self.ui, mode="always")
        self.processor = ResponseProcessor(self.ui, self.tool_manager, chat=None, policy=self.policy)

    def tearDown(self):
        self.test_dir.cleanup()

    async def test_existing_source_file_full_rewrite_via_edit_file_is_rejected(self):
        file_path = Path(self.test_dir.name) / "BookmarksViewModel.kt"
        original = (
            "package sample\n\n"
            "import sample.A\n\n"
            "class BookmarksViewModel {\n"
            + "".join(f"    fun helper{i}() = println(\"old{i}\")\n" for i in range(60))
            + "}\n"
        )
        file_path.write_text(original)

        result = await self.processor.process_single_action(
            {
                "type": "edit_file",
                "path": str(file_path),
                "search_text": original,
                "replace_text": original.replace("old", "new") + "\n// generated\n" + ("x" * 1600),
            }
        )

        self.assertEqual(result["status"], "error")
        self.assertEqual(result.get("error_code"), "VALIDATION_ERROR")
        self.assertEqual("edit_file_full_rewrite_disallowed", result.get("error_details", {}).get("mismatch_type"))
        self.assertIn("whole-file rewrite", result["output"])
        self.assertEqual(file_path.read_text(), original)

    async def test_import_injection_via_class_anchor_edit_is_rejected(self):
        file_path = Path(self.test_dir.name) / "BookmarksViewModel.kt"
        original = (
            "package sample\n\n"
            "import sample.A\n\n"
            "class BookmarksViewModel {\n"
            "}\n"
        )
        file_path.write_text(original)

        result = await self.processor.process_single_action(
            {
                "type": "edit_file",
                "path": str(file_path),
                "search_text": "class BookmarksViewModel {",
                "replace_text": (
                    "import kotlinx.coroutines.Job\n"
                    "import kotlinx.coroutines.flow.MutableStateFlow\n\n"
                    "class BookmarksViewModel {\n"
                    "    private var deleteJob: Job? = null"
                ),
            }
        )

        self.assertEqual(result["status"], "error")
        self.assertEqual(result.get("error_code"), "VALIDATION_ERROR")
        self.assertEqual("edit_file_crosses_import_boundary", result.get("error_details", {}).get("mismatch_type"))
        self.assertIn("Do not inject import statements", result["output"])
        self.assertEqual(file_path.read_text(), original)


class EditFileMismatchRecoveryPolicyTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.test_dir = tempfile.TemporaryDirectory()
        self.ui = MagicMock()
        self.ui.show_diff_preview = AsyncMock(return_value=True)
        self.tool_manager = ToolManager()
        self.tool_manager.load_tools()
        self.policy = PermissionPolicy(self.ui, mode="always")
        self.processor = ResponseProcessor(self.ui, self.tool_manager, chat=None, policy=self.policy)

    def tearDown(self):
        self.test_dir.cleanup()

    async def test_edit_file_search_mismatch_uses_structural_recovery_actions(self):
        file_path = Path(self.test_dir.name) / "ChecklistScreen.kt"
        file_path.write_text(
            "package demo\n\n"
            "@Composable\n"
            "fun ChecklistContent() {\n"
            "    Text(\"old\")\n"
            "}\n",
            encoding="utf-8",
        )

        result = await self.processor.process_single_action(
            {
                "type": "edit_file",
                "path": str(file_path),
                "search_text": "    fun ChecklistContent() {\n        Text(\"old\")\n    }\n",
                "replace_text": "    fun ChecklistContent() {\n        Text(\"new\")\n    }\n",
            }
        )

        self.assertEqual(result["status"], "error")
        self.assertEqual(result.get("error_code"), "VALIDATION_ERROR")
        self.assertIn(
            result.get("error_details", {}).get("mismatch_type"),
            {
                "whitespace_mismatch",
                "indentation_or_partial_block_mismatch",
                "search_text_stale_or_block_modified",
                "no_similar_block_found",
            },
        )
        self.assertEqual(
            result.get("next_actions"),
            [
                "read_chunk",
                "read_file_skeleton",
                "extract_symbol",
                "replace_symbol",
                "edit_file",
                "write_file_block",
            ],
        )
        self.assertNotEqual(
            result.get("next_actions"),
            ["read_file", "search_content", "edit_file", "write_file"],
        )


if __name__ == "__main__":
    unittest.main()
