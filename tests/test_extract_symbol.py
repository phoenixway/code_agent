import tempfile
import unittest
from pathlib import Path

from modules.code_parser import CodeParser
from modules.processor import ResponseProcessor
from modules.tools.manager import ToolManager
from modules.policy import PermissionPolicy


class _DummyUi:
    async def show_diff_preview(self, proposal):
        return True

    async def confirm_truncation(self, action_type, output_length):
        return False

    async def print_error(self, text):
        return None


class ExtractSymbolToolTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.ui = _DummyUi()
        self.tool_manager = ToolManager()
        self.tool_manager.load_tools()
        self.policy = PermissionPolicy(self.ui, mode="always")
        self.processor = ResponseProcessor(self.ui, self.tool_manager, chat=None, policy=self.policy)
        parser = CodeParser()
        if parser._get_language(".kt") is None:
            self.skipTest("Kotlin parser runtime is unavailable in this environment.")

    def tearDown(self):
        self.tmp.cleanup()

    def _write_kotlin_sample(self) -> str:
        path = Path(self.tmp.name) / "Sample.kt"
        path.write_text(
            "package demo\n\n"
            "class Greeter {\n"
            "    fun hi(name: String): String {\n"
            "        return \"Hi, $name\"\n"
            "    }\n"
            "}\n\n"
            "@Composable\n"
            "fun EditRecordDialog(title: String) {\n"
            "    val localState = title.length\n"
            "}\n"
        )
        return str(path)

    async def test_extract_symbol_composable_success(self):
        path = self._write_kotlin_sample()

        result = await self.processor.process_single_action(
            {
                "type": "extract_symbol",
                "path": path,
                "symbol_name": "EditRecordDialog",
                "symbol_kind": "composable",
                "include_signature": True,
                "include_body": True,
                "include_line_range": True,
            }
        )

        self.assertEqual("success", result["status"])
        self.assertEqual("composable", result["symbol_kind"])
        self.assertEqual("EditRecordDialog", result["symbol_name"])
        self.assertIn("@Composable", result["file_content"])
        self.assertIn("val localState", result["file_content"])
        self.assertRegex(result["output"], r"\(\d+-\d+\)")

    async def test_extract_symbol_method_with_container_success(self):
        path = self._write_kotlin_sample()

        result = await self.processor.process_single_action(
            {
                "type": "extract_symbol",
                "path": path,
                "symbol_name": "hi",
                "symbol_kind": "method",
                "container_name": "Greeter",
                "include_signature": True,
                "include_body": True,
                "include_line_range": True,
            }
        )

        self.assertEqual("success", result["status"])
        self.assertEqual("method", result["symbol_kind"])
        self.assertEqual("Greeter", result["container_name"])
        self.assertIn("fun hi(name: String)", result["file_content"])

    async def test_extract_symbol_class_signature_only_success(self):
        path = self._write_kotlin_sample()

        result = await self.processor.process_single_action(
            {
                "type": "extract_symbol",
                "path": path,
                "symbol_name": "Greeter",
                "symbol_kind": "class",
                "include_signature": True,
                "include_body": False,
                "include_line_range": True,
            }
        )

        self.assertEqual("success", result["status"])
        self.assertEqual("class", result["symbol_kind"])
        self.assertEqual("Greeter", result["symbol_name"])
        self.assertIn("class Greeter", result["file_content"])
        self.assertNotIn("return \"Hi, $name\"", result["file_content"])

    async def test_extract_symbol_not_found_returns_clear_error(self):
        path = self._write_kotlin_sample()

        result = await self.processor.process_single_action(
            {
                "type": "extract_symbol",
                "path": path,
                "symbol_name": "MissingThing",
                "symbol_kind": "function",
            }
        )

        self.assertEqual("error", result["status"])
        self.assertEqual("NOT_FOUND", result["error_code"])
        self.assertIn("MissingThing", result["output"])
        self.assertIn("extract_symbol", result.get("next_actions", []))

    async def test_extract_kotlin_function_wrapper_remains_compatible(self):
        path = self._write_kotlin_sample()

        result = await self.processor.process_single_action(
            {
                "type": "extract_kotlin_function",
                "path": path,
                "function_name": "hi",
                "class_name": "Greeter",
            }
        )

        self.assertEqual("success", result["status"])
        self.assertEqual("extract_kotlin_function", result["tool_variant"])
        self.assertEqual("hi", result["function_name"])
        self.assertEqual("Greeter", result["class_name"])
        self.assertIn("fun hi(name: String)", result["file_content"])
