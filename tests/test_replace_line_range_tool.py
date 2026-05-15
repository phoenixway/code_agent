import pytest

from modules.tools.definitions.files import ReplaceLineRangeTool
from modules.tools.manager import ToolManager


@pytest.mark.asyncio
async def test_replace_line_range_replaces_inclusive_range(tmp_path):
    path = tmp_path / "Example.kt"
    path.write_text("one\ntwo\nthree\nfour\n", encoding="utf-8")

    result = await ReplaceLineRangeTool().execute(
        path=str(path),
        start_line=2,
        end_line=3,
        replace_text="TWO\nTHREE\n",
    )

    assert not isinstance(result, dict)
    assert result.new_content == "one\nTWO\nTHREE\nfour\n"


@pytest.mark.asyncio
async def test_replace_line_range_allows_empty_replace_text_for_deletion(tmp_path):
    path = tmp_path / "Example.kt"
    path.write_text("one\ntwo\nthree\n", encoding="utf-8")

    result = await ReplaceLineRangeTool().execute(
        path=str(path),
        start_line=2,
        end_line=2,
        replace_text="",
    )

    assert not isinstance(result, dict)
    assert result.new_content == "one\nthree\n"


@pytest.mark.asyncio
async def test_replace_line_range_rejects_stale_expected_excerpt(tmp_path):
    path = tmp_path / "Example.kt"
    path.write_text("one\ncurrent\nthree\n", encoding="utf-8")

    result = await ReplaceLineRangeTool().execute(
        path=str(path),
        start_line=2,
        end_line=2,
        replace_text="changed\n",
        expected_excerpt="old\n",
    )

    assert result["status"] == "error"
    assert result["error_code"] == "RANGE_STALE"
    assert "changed" not in path.read_text(encoding="utf-8")


@pytest.mark.asyncio
async def test_replace_line_range_rejects_large_range(tmp_path):
    path = tmp_path / "Example.kt"
    path.write_text("".join(f"line {i}\n" for i in range(150)), encoding="utf-8")

    result = await ReplaceLineRangeTool().execute(
        path=str(path),
        start_line=1,
        end_line=121,
        replace_text="changed\n",
    )

    assert result["status"] == "error"
    assert result["error_code"] == "VALIDATION_ERROR"
    assert "larger than 120 lines" in result["output"]


def test_tool_manager_loads_replace_line_range_tool():
    manager = ToolManager()
    loaded = manager.load_tools()

    assert "replace_line_range" in loaded
    assert "replace_line_range" in manager.tools
