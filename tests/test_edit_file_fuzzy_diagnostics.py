import pytest

from modules.tools.definitions.files import EditFileTool, FuzzyEditFileTool
from modules.tools.manager import ToolManager


@pytest.mark.asyncio
async def test_edit_file_error_reports_unique_indentation_normalized_fuzzy_candidate(tmp_path):
    path = tmp_path / "Example.kt"
    path.write_text(
        "package demo\n\n"
        "fun screen() {\n"
        "    Column {\n"
        "        Text(\"before\")\n"
        "    }\n"
        "}\n",
        encoding="utf-8",
    )

    result = await EditFileTool().execute(
        path=str(path),
        search_text='Column {\n    Text("before")\n}',
        replace_text='Column {\n    Text("after")\n}',
    )

    assert result["status"] == "error"
    assert result["error_code"] == "VALIDATION_ERROR"
    details = result["error_details"]
    assert details["fuzzy_candidate_count"] == 1
    assert details["fuzzy_unique_candidate"] is True
    candidate = details["fuzzy_candidates"][0]
    assert candidate["mode"] == "indentation_normalized"
    assert candidate["start_line"] == 4
    assert candidate["end_line"] == 6
    assert candidate["base_indent"] == "    "
    assert "Text(\"before\")" in candidate["preview"]
    assert "Indentation-normalized fuzzy candidate found" in result["output"]
    assert path.read_text(encoding="utf-8").endswith("}\n")


@pytest.mark.asyncio
async def test_edit_file_error_reports_ambiguous_indentation_normalized_candidates(tmp_path):
    path = tmp_path / "Example.kt"
    path.write_text(
        "package demo\n\n"
        "fun one() {\n"
        "    Column {\n"
        "        Text(\"same\")\n"
        "    }\n"
        "}\n\n"
        "fun two() {\n"
        "    Column {\n"
        "        Text(\"same\")\n"
        "    }\n"
        "}\n",
        encoding="utf-8",
    )

    result = await EditFileTool().execute(
        path=str(path),
        search_text='Column {\n    Text("same")\n}',
        replace_text='Column {\n    Text("changed")\n}',
    )

    assert result["status"] == "error"
    details = result["error_details"]
    assert details["fuzzy_candidate_count"] == 2
    assert details["fuzzy_unique_candidate"] is False
    assert "candidate is ambiguous" in result["output"]
    assert "changed" not in path.read_text(encoding="utf-8")


@pytest.mark.asyncio
async def test_fuzzy_edit_file_applies_unique_indentation_normalized_candidate(tmp_path):
    path = tmp_path / "Example.kt"
    path.write_text(
        "package demo\n\n"
        "fun screen() {\n"
        "    Column {\n"
        "        Text(\"before\")\n"
        "    }\n"
        "}\n",
        encoding="utf-8",
    )

    result = await FuzzyEditFileTool().execute(
        path=str(path),
        search_text='Column {\n    Text("before")\n}',
        replace_text='Column {\n    Text("after")\n}',
    )

    assert not isinstance(result, dict)
    assert "    Column {\n        Text(\"after\")\n    }" in result.new_content
    assert "Text(\"before\")" in result.original_content
    assert path.read_text(encoding="utf-8").endswith("}\n")


@pytest.mark.asyncio
async def test_fuzzy_edit_file_refuses_ambiguous_candidates(tmp_path):
    path = tmp_path / "Example.kt"
    path.write_text(
        "package demo\n\n"
        "fun one() {\n"
        "    Column {\n"
        "        Text(\"same\")\n"
        "    }\n"
        "}\n\n"
        "fun two() {\n"
        "    Column {\n"
        "        Text(\"same\")\n"
        "    }\n"
        "}\n",
        encoding="utf-8",
    )

    result = await FuzzyEditFileTool().execute(
        path=str(path),
        search_text='Column {\n    Text("same")\n}',
        replace_text='Column {\n    Text("changed")\n}',
    )

    assert result["status"] == "error"
    assert result["error_code"] == "FUZZY_MATCH_AMBIGUOUS"
    assert result["error_details"]["fuzzy_candidate_count"] == 2
    assert "changed" not in path.read_text(encoding="utf-8")


@pytest.mark.asyncio
async def test_fuzzy_edit_file_refuses_missing_candidate(tmp_path):
    path = tmp_path / "Example.kt"
    path.write_text("package demo\n\nfun answer() = 1\n", encoding="utf-8")

    result = await FuzzyEditFileTool().execute(
        path=str(path),
        search_text='Column {\n    Text("missing")\n}',
        replace_text='Column {\n    Text("after")\n}',
    )

    assert result["status"] == "error"
    assert result["error_code"] == "FUZZY_MATCH_NOT_FOUND"
    assert path.read_text(encoding="utf-8") == "package demo\n\nfun answer() = 1\n"


def test_tool_manager_loads_fuzzy_edit_file_tool():
    manager = ToolManager()
    loaded = manager.load_tools()

    assert "fuzzy_edit_file" in loaded
    assert "fuzzy_edit_file" in manager.tools


@pytest.mark.asyncio
async def test_edit_file_exact_match_still_applies_without_fuzzy_path(tmp_path):
    path = tmp_path / "Example.kt"
    path.write_text("package demo\n\nfun answer() = 1\n", encoding="utf-8")

    result = await EditFileTool().execute(
        path=str(path),
        search_text="fun answer() = 1",
        replace_text="fun answer() = 2",
    )

    assert not isinstance(result, dict)
    assert result.new_content.endswith("fun answer() = 2\n")
