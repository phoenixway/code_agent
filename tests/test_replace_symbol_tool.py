from pathlib import Path

import pytest

from modules.tools.definitions.replace_symbol import ReplaceSymbolTool
from modules.types import ChangeProposal


@pytest.mark.asyncio
async def test_replace_symbol_replaces_unique_kotlin_function(tmp_path):
    path = tmp_path / "Example.kt"
    path.write_text(
        "package demo\n\n"
        "fun keep(): String = \"keep\"\n\n"
        "fun target(): String {\n"
        "    return \"old\"\n"
        "}\n",
        encoding="utf-8",
    )

    tool = ReplaceSymbolTool()
    result = await tool.execute(
        path=str(path),
        symbol_name="target",
        symbol_kind="function",
        new_content="fun target(): String {\n    return \"new\"\n}\n",
    )

    assert isinstance(result, ChangeProposal)
    assert "return \"old\"" in result.original_content
    assert "return \"new\"" in result.new_content
    assert "fun keep" in result.new_content


@pytest.mark.asyncio
async def test_replace_symbol_accepts_name_and_newcontent_aliases(tmp_path):
    path = tmp_path / "Example.kt"
    path.write_text(
        "package demo\n\n"
        "class Target {\n"
        "    fun run(): String = \"old\"\n"
        "}\n",
        encoding="utf-8",
    )

    tool = ReplaceSymbolTool()
    result = await tool.execute(
        path=str(path),
        name="Target",
        symbol_type="class",
        newcontent="class Target {\n    fun run(): String = \"new\"\n}\n",
    )

    assert isinstance(result, ChangeProposal)
    assert "\"new\"" in result.new_content


@pytest.mark.asyncio
async def test_replace_symbol_rejects_replacement_that_renames_symbol(tmp_path):
    path = tmp_path / "Example.kt"
    path.write_text(
        "package demo\n\n"
        "fun target(): String = \"old\"\n",
        encoding="utf-8",
    )

    tool = ReplaceSymbolTool()
    result = await tool.execute(
        path=str(path),
        symbol_name="target",
        symbol_kind="function",
        new_content="fun renamed(): String = \"new\"\n",
    )

    assert result["status"] == "error"
    assert result["error_code"] == "VALIDATION_ERROR"
    assert "same symbol" in result["output"]


@pytest.mark.asyncio
async def test_replace_symbol_replaces_unique_python_function(tmp_path):
    path = tmp_path / "example.py"
    path.write_text(
        "def keep():\n"
        "    return 'keep'\n\n"
        "def target():\n"
        "    return 'old'\n",
        encoding="utf-8",
    )

    tool = ReplaceSymbolTool()
    result = await tool.execute(
        path=str(path),
        symbol_name="target",
        symbol_kind="function",
        new_content="def target():\n    return 'new'\n",
    )

    assert isinstance(result, ChangeProposal)
    assert "return 'old'" in result.original_content
    assert "return 'new'" in result.new_content
    assert "def keep" in result.new_content


@pytest.mark.asyncio
async def test_replace_symbol_replaces_python_method_with_container_name(tmp_path):
    path = tmp_path / "example.py"
    path.write_text(
        "class One:\n"
        "    def target(self):\n"
        "        return 'one'\n\n"
        "class Two:\n"
        "    def target(self):\n"
        "        return 'two'\n",
        encoding="utf-8",
    )

    tool = ReplaceSymbolTool()
    result = await tool.execute(
        path=str(path),
        symbol_name="target",
        symbol_kind="method",
        container_name="Two",
        new_content="    def target(self):\n        return 'changed'\n",
    )

    assert isinstance(result, ChangeProposal)
    assert "return 'one'" in result.new_content
    assert "return 'changed'" in result.new_content
    assert "return 'two'" not in result.new_content


@pytest.mark.asyncio
async def test_replace_symbol_rejects_ambiguous_python_method_without_container(tmp_path):
    path = tmp_path / "example.py"
    path.write_text(
        "class One:\n"
        "    def target(self):\n"
        "        return 'one'\n\n"
        "class Two:\n"
        "    def target(self):\n"
        "        return 'two'\n",
        encoding="utf-8",
    )

    tool = ReplaceSymbolTool()
    result = await tool.execute(
        path=str(path),
        symbol_name="target",
        symbol_kind="method",
        new_content="    def target(self):\n        return 'changed'\n",
    )

    assert result["status"] == "error"
    assert result["error_code"] == "AMBIGUOUS_MATCH"


@pytest.mark.asyncio
async def test_replace_symbol_rejects_invalid_python_function_new_content(tmp_path):
    path = tmp_path / "example.py"
    path.write_text(
        "def target():\n"
        "    return 'old'\n",
        encoding="utf-8",
    )

    tool = ReplaceSymbolTool()
    result = await tool.execute(
        path=str(path),
        symbol_name="target",
        symbol_kind="function",
        new_content="def target(:\n    return 'new'\n",
    )

    assert result["status"] == "error"
    assert result["error_code"] == "VALIDATION_ERROR"
    assert "not syntactically valid" in result["output"]
    assert result["error_details"]["language"] == "python"


@pytest.mark.asyncio
async def test_replace_symbol_rejects_invalid_python_method_new_content(tmp_path):
    path = tmp_path / "example.py"
    path.write_text(
        "class Target:\n"
        "    def run(self):\n"
        "        return 'old'\n",
        encoding="utf-8",
    )

    tool = ReplaceSymbolTool()
    result = await tool.execute(
        path=str(path),
        symbol_name="run",
        symbol_kind="method",
        container_name="Target",
        new_content="    def run(self):\n        return (\n",
    )

    assert result["status"] == "error"
    assert result["error_code"] == "VALIDATION_ERROR"
    assert "not syntactically valid" in result["output"]
    assert result["error_details"]["symbol_kind"] == "method"


@pytest.mark.asyncio
async def test_replace_symbol_rejects_unsupported_language_with_supported_language_list(tmp_path):
    path = tmp_path / "example.txt"
    path.write_text("target\n", encoding="utf-8")

    tool = ReplaceSymbolTool()
    result = await tool.execute(
        path=str(path),
        symbol_name="target",
        symbol_kind="function",
        new_content="target\n",
    )

    assert result["status"] == "error"
    assert result["error_code"] == "VALIDATION_ERROR"
    assert "does not yet support" in result["output"]
    assert result["error_details"]["supported_languages"] == {".kt": "kotlin", ".py": "python"}
