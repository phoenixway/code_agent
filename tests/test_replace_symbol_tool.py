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
async def test_replace_symbol_rejects_non_kotlin_file(tmp_path):
    path = tmp_path / "example.py"
    path.write_text("def target():\n    return 'old'\n", encoding="utf-8")

    tool = ReplaceSymbolTool()
    result = await tool.execute(
        path=str(path),
        symbol_name="target",
        symbol_kind="function",
        new_content="def target():\n    return 'new'\n",
    )

    assert result["status"] == "error"
    assert result["error_code"] == "VALIDATION_ERROR"
    assert "Kotlin .kt" in result["output"]
