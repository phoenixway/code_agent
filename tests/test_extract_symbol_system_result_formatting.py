from modules.agent.action_dispatcher import ActionDispatcher


def _dispatcher():
    return object.__new__(ActionDispatcher)


def test_extract_symbol_system_result_includes_small_file_content():
    dispatcher = _dispatcher()
    result = {
        "status": "success",
        "output": "Extracted Kotlin property 'label' (8-8) from tests/fixtures/kotlin/SmokeSymbolTarget.kt.",
        "file_content": "const val label: String = \"before\"\n",
        "language": "kotlin",
        "file_path": "tests/fixtures/kotlin/SmokeSymbolTarget.kt",
    }

    text = dispatcher._format_model_facing_tool_result(
        "extract_symbol",
        {"type": "extract_symbol", "path": "tests/fixtures/kotlin/SmokeSymbolTarget.kt"},
        result,
    )

    assert "Extracted Kotlin property 'label'" in text
    assert "Extracted file_content is available below" in text
    assert "do not repeat the same extraction" in text
    assert "```kotlin" in text
    assert "const val label: String = \"before\"" in text


def test_extract_symbol_system_result_does_not_duplicate_existing_content():
    dispatcher = _dispatcher()
    result = {
        "status": "success",
        "output": "fun marker(): String = \"before\"",
        "file_content": "fun marker(): String = \"before\"",
        "language": "kotlin",
    }

    text = dispatcher._format_model_facing_tool_result(
        "extract_symbol",
        {"type": "extract_symbol", "path": "SmokeSymbolTarget.kt"},
        result,
    )

    assert text == "fun marker(): String = \"before\""


def test_extract_symbol_system_result_uses_preview_for_large_content():
    dispatcher = _dispatcher()
    content = "\n".join(f"line {idx} " + ("x" * 80) for idx in range(80))
    result = {
        "status": "success",
        "output": "Extracted Kotlin class 'LargeTarget' (1-80).",
        "file_content": content,
        "language": "kotlin",
    }

    text = dispatcher._format_model_facing_tool_result(
        "extract_symbol",
        {"type": "extract_symbol", "path": "LargeTarget.kt"},
        result,
    )

    assert "Full extracted file_content is too large for inline display" in text
    assert "The full content is preserved as turn working material" in text
    assert "line 0" in text
    assert "line 79" in text
    assert "truncated extracted symbol content" in text


def test_non_extract_tool_result_is_unchanged():
    dispatcher = _dispatcher()
    result = {
        "status": "success",
        "output": "Read file x.py",
        "file_content": "print('hello')",
    }

    text = dispatcher._format_model_facing_tool_result(
        "read_file",
        {"type": "read_file", "path": "x.py"},
        result,
    )

    assert text == "Read file x.py"
