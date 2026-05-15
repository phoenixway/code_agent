from modules.tools.recovery.edit_file_recovery_policy import malformed_edit_file_recovery_actions, search_mismatch_recovery_actions


def test_malformed_modify_edit_file_recovery_includes_replace_line_range():
    actions = malformed_edit_file_recovery_actions(
        active_intent_type="MODIFY",
        active_allowed_actions=("read_chunk", "edit_file"),
    )

    assert "replace_line_range" in actions
    assert actions.index("replace_line_range") < actions.index("edit_file")


def test_modify_search_mismatch_recovery_includes_replace_line_range():
    actions = search_mismatch_recovery_actions(
        path="app/src/main/java/demo/Screen.kt",
        mismatch_type="indentation_or_partial_block_mismatch",
        active_intent_type="MODIFY",
        active_allowed_actions=("read_chunk", "extract_symbol", "replace_symbol", "edit_file", "write_file_block"),
    )

    assert "replace_line_range" in actions
