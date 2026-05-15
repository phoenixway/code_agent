from unittest.mock import MagicMock, patch

import pytest

from modules.tools.definitions.search import ContentSearchTool


@pytest.mark.asyncio
async def test_search_content_literal_mode_uses_fixed_strings():
    mock_result = MagicMock()
    mock_result.returncode = 0
    mock_result.stdout = "Example.kt:10:    AutocompleteSuggestions(\n"
    mock_result.stderr = ""

    with patch("subprocess.run", return_value=mock_result) as mock_run:
        result = await ContentSearchTool().execute(
            pattern="AutocompleteSuggestions(",
            path="Example.kt",
            recursive=False,
            code_only=True,
            limit=5,
            literal=True,
        )

    cmd = mock_run.call_args.args[0]
    assert "--fixed-strings" in cmd
    assert "AutocompleteSuggestions(" in cmd
    assert result["status"] == "success"
    assert "AutocompleteSuggestions" in result["output"]


@pytest.mark.asyncio
async def test_search_content_regex_mode_does_not_use_fixed_strings_by_default():
    mock_result = MagicMock()
    mock_result.returncode = 0
    mock_result.stdout = "Example.kt:10:    AutocompleteSuggestions(\n"
    mock_result.stderr = ""

    with patch("subprocess.run", return_value=mock_result) as mock_run:
        result = await ContentSearchTool().execute(
            pattern="AutocompleteSuggestions",
            path="Example.kt",
            recursive=False,
            code_only=True,
            limit=5,
        )

    cmd = mock_run.call_args.args[0]
    assert "--fixed-strings" not in cmd
    assert result["status"] == "success"


@pytest.mark.asyncio
async def test_search_content_regex_parse_error_recommends_literal_retry():
    mock_result = MagicMock()
    mock_result.returncode = 2
    mock_result.stdout = ""
    mock_result.stderr = (
        "rg: regex parse error:\n"
        "    (?:AutocompleteSuggestions()\n"
        "    ^\n"
        "error: unclosed group\n"
    )

    with patch("subprocess.run", return_value=mock_result):
        result = await ContentSearchTool().execute(
            pattern="AutocompleteSuggestions(",
            path="Example.kt",
            recursive=False,
            code_only=True,
            limit=5,
        )

    assert result["status"] == "failed"
    assert result["error_code"] == "SEARCH_REGEX_PARSE_ERROR"
    assert result["recoverable"] is True
    assert result["next_actions"] == ["search_content", "read_chunk", "extract_symbol"]
    assert "literal=true" in result["output"]
    assert result["error_details"]["suggested_retry"]["literal"] is True
    assert result["error_details"]["suggested_retry"]["pattern"] == "AutocompleteSuggestions("
