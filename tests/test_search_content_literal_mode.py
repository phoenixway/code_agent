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


@pytest.mark.asyncio
async def test_search_content_regex_parse_error_on_kotlin_brace_pattern_recommends_literal_retry(tmp_path):
    source = tmp_path / "ContextViewMode.kt"
    source.write_text(
        "package sample\n\n"
        "enum class ContextViewMode {\n"
        "    Dashboard,\n"
        "    Backlog\n"
        "}\n",
        encoding="utf-8",
    )

    result = await ContentSearchTool().execute(
        pattern="(?:enum class ContextViewMode|sealed class ContextViewMode|ContextViewMode {)",
        path=str(tmp_path),
        recursive=True,
        code_only=True,
        include_extensions=["kt"],
        limit=10,
    )

    assert result["status"] == "failed"
    assert result["error_code"] == "SEARCH_REGEX_PARSE_ERROR"
    assert result["recoverable"] is True
    assert result["next_actions"][0] == "search_content"
    assert "regex parse error" in result["output"].lower()
    assert "literal=true" in result["output"]
    assert result["error_details"]["pattern"] == (
        "(?:enum class ContextViewMode|sealed class ContextViewMode|ContextViewMode {)"
    )
    assert result["error_details"]["path"] == str(tmp_path)
    assert result["error_details"]["literal"] is False
    assert result["error_details"]["suggested_retry"]["type"] == "search_content"
    assert result["error_details"]["suggested_retry"]["literal"] is True
    assert result["error_details"]["suggested_retry"]["pattern"] == (
        "(?:enum class ContextViewMode|sealed class ContextViewMode|ContextViewMode {)"
    )


@pytest.mark.asyncio
async def test_search_content_literal_true_finds_kotlin_brace_code_text(tmp_path):
    source = tmp_path / "ContextViewMode.kt"
    source.write_text(
        "package sample\n\n"
        "enum class ContextViewMode {\n"
        "    Dashboard,\n"
        "    Backlog\n"
        "}\n",
        encoding="utf-8",
    )

    result = await ContentSearchTool().execute(
        pattern="ContextViewMode {",
        path=str(tmp_path),
        recursive=True,
        code_only=True,
        include_extensions=["kt"],
        literal=True,
        limit=10,
    )

    assert result["status"] == "success"
    assert "ContextViewMode" in result["output"]
    assert "enum class ContextViewMode {" in result["output"]
    assert "regex parse error" not in result["output"].lower()


@pytest.mark.asyncio
async def test_search_content_regex_mode_still_finds_escaped_kotlin_brace_pattern(tmp_path):
    source = tmp_path / "ContextViewMode.kt"
    source.write_text(
        "package sample\n\n"
        "enum class ContextViewMode {\n"
        "    Dashboard,\n"
        "    Backlog\n"
        "}\n",
        encoding="utf-8",
    )

    result = await ContentSearchTool().execute(
        pattern=r"enum class ContextViewMode\s*\{",
        path=str(tmp_path),
        recursive=True,
        code_only=True,
        include_extensions=["kt"],
        literal=False,
        limit=10,
    )

    assert result["status"] == "success"
    assert "enum class ContextViewMode {" in result["output"]
    assert "regex parse error" not in result["output"].lower()


@pytest.mark.asyncio
async def test_search_content_literal_true_treats_regex_metacharacters_as_text(tmp_path):
    source = tmp_path / "Operators.kt"
    source.write_text(
        "package sample\n\n"
        "val marker = \"foo(bar)|baz+qux? [x] *literal*\"\n",
        encoding="utf-8",
    )

    result = await ContentSearchTool().execute(
        pattern="foo(bar)|baz+qux? [x] *literal*",
        path=str(tmp_path),
        recursive=True,
        code_only=True,
        include_extensions=["kt"],
        literal=True,
        limit=10,
    )

    assert result["status"] == "success"
    assert "foo(bar)|baz+qux? [x] *literal*" in result["output"]
    assert "regex parse error" not in result["output"].lower()
