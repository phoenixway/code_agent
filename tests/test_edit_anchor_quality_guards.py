from modules.tools.definitions.files import _validate_edit_file_scope


def test_generic_spacer_anchor_with_large_replace_is_blocked():
    result = _validate_edit_file_scope(
        "app/src/main/java/com/example/bookmarks/ui/BookmarksScreen.kt",
        "fun x() {\n    Spacer(modifier = Modifier.height(14.dp))\n}\n",
        "                Spacer(modifier = Modifier.height(14.dp))",
        "A" * 900,
    )
    assert result is not None
    assert result["error_details"]["mismatch_type"] == "bad_edit_anchor_too_generic"


def test_multiline_specific_bookmark_block_is_allowed():
    result = _validate_edit_file_scope(
        "app/src/main/java/com/example/bookmarks/ui/BookmarksScreen.kt",
        "BookmarkCard(\n    title = item.title,\n    tags = item.tags,\n)\n",
        "BookmarkCard(\n    title = item.title,\n    tags = item.tags,\n)",
        "BookmarkCard(\n    title = item.title,\n    tags = item.tags,\n    subtitle = item.url,\n)",
    )
    assert result is None


def test_small_one_line_replacement_is_allowed():
    result = _validate_edit_file_scope(
        "app/src/main/java/com/example/bookmarks/ui/BookmarksScreen.kt",
        "Spacer(modifier = Modifier.height(14.dp))\n",
        "Spacer(modifier = Modifier.height(14.dp))",
        "Spacer(modifier = Modifier.height(16.dp))",
    )
    assert result is None
