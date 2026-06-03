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

    def _write_kotlin_viewmodel_member_duplicate_sample(self) -> str:
        path = Path(self.tmp.name) / "ContextScreenViewModel.kt"
        path.write_text(
            "package sample\n\n"
            "class ContextScreenViewModel @Inject constructor(\n"
            "    private val contextViewActions: ContextViewActions,\n"
            "    private val contextSettingsActions: ContextSettingsActions,\n"
            "    private val ioDispatcher: CoroutineDispatcher,\n"
            ") : ViewModel() {\n"
            "    fun onProjectViewChange(mode: ContextViewMode) {\n"
            "        val resolved = contextViewActions.applyViewChange(mode)\n"
            "        viewModelScope.launch(ioDispatcher) {\n"
            "            contextSettingsActions.persistContextViewMode(contextIdFlow.value, resolved)\n"
            "        }\n"
            "    }\n\n"
            "    private fun helper() {\n"
            "        println(\"helper\")\n"
            "    }\n"
            "}\n\n"
            "fun onProjectViewChange(mode: ContextViewMode) {\n"
            "    println(\"top level\")\n"
            "}\n\n"
            "class OtherViewModel {\n"
            "    fun onProjectViewChange(mode: ContextViewMode) {\n"
            "        println(\"other member\")\n"
            "    }\n"
            "}\n\n"
            "enum class ContextViewMode {\n"
            "    Dashboard,\n"
            "    Backlog\n"
            "}\n",
            encoding="utf-8",
        )
        return str(path)

    async def test_extract_symbol_finds_kotlin_member_function_as_method_with_container(self):
        path = self._write_kotlin_viewmodel_member_duplicate_sample()

        result = await self.processor.process_single_action(
            {
                "type": "extract_symbol",
                "path": path,
                "symbol_name": "onProjectViewChange",
                "symbol_kind": "method",
                "container_name": "ContextScreenViewModel",
                "include_signature": True,
                "include_body": True,
                "include_line_range": True,
            }
        )

        self.assertEqual("success", result["status"])
        self.assertEqual("onProjectViewChange", result["symbol_name"])
        self.assertEqual("method", result["symbol_kind"])
        self.assertEqual("ContextScreenViewModel", result["container_name"])
        self.assertIn("fun onProjectViewChange(mode: ContextViewMode)", result["signature"])
        self.assertIn("val resolved = contextViewActions.applyViewChange(mode)", result["body"])
        self.assertIn("contextSettingsActions.persistContextViewMode", result["file_content"])
        self.assertNotIn('println("top level")', result["file_content"])
        self.assertNotIn('println("other member")', result["file_content"])
        self.assertRegex(result["line_range"], r"\d+-\d+")

    async def test_extract_symbol_method_container_disambiguates_from_top_level_function(self):
        path = self._write_kotlin_viewmodel_member_duplicate_sample()

        result = await self.processor.process_single_action(
            {
                "type": "extract_symbol",
                "path": path,
                "symbol_name": "onProjectViewChange",
                "symbol_kind": "method",
                "container_name": "OtherViewModel",
                "include_signature": True,
                "include_body": True,
                "include_line_range": True,
            }
        )

        self.assertEqual("success", result["status"])
        self.assertEqual("method", result["symbol_kind"])
        self.assertEqual("OtherViewModel", result["container_name"])
        self.assertIn('println("other member")', result["file_content"])
        self.assertNotIn("val resolved = contextViewActions.applyViewChange(mode)", result["file_content"])
        self.assertNotIn('println("top level")', result["file_content"])

    async def test_extract_symbol_method_wrong_container_returns_not_found(self):
        path = self._write_kotlin_viewmodel_member_duplicate_sample()

        result = await self.processor.process_single_action(
            {
                "type": "extract_symbol",
                "path": path,
                "symbol_name": "onProjectViewChange",
                "symbol_kind": "method",
                "container_name": "MissingViewModel",
                "include_signature": True,
                "include_body": True,
                "include_line_range": True,
            }
        )

        self.assertEqual("error", result["status"])
        self.assertEqual("NOT_FOUND", result["error_code"])
        self.assertIn("MissingViewModel", result["output"])

    async def test_extract_symbol_kotlin_member_function_still_extractable_as_function_with_container(self):
        path = self._write_kotlin_viewmodel_member_duplicate_sample()

        result = await self.processor.process_single_action(
            {
                "type": "extract_symbol",
                "path": path,
                "symbol_name": "onProjectViewChange",
                "symbol_kind": "function",
                "container_name": "ContextScreenViewModel",
                "include_signature": True,
                "include_body": True,
                "include_line_range": True,
            }
        )

        self.assertEqual("success", result["status"])
        self.assertEqual("method", result["symbol_kind"])
        self.assertEqual("ContextScreenViewModel", result["container_name"])
        self.assertIn("val resolved = contextViewActions.applyViewChange(mode)", result["file_content"])
        self.assertNotIn('println("top level")', result["file_content"])

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
