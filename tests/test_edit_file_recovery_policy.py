from modules.tools.recovery.edit_file_recovery_policy import (
    EditFileRecoveryContext,
    malformed_edit_file_recovery_actions,
    resolve_edit_file_recovery,
    search_mismatch_recovery_actions,
)


def test_modify_kotlin_search_mismatch_prefers_structural_recovery():
    plan = resolve_edit_file_recovery(
        EditFileRecoveryContext(
            reason="edit_file_search_mismatch",
            error_code="VALIDATION_ERROR",
            mismatch_type="indentation_or_partial_block_mismatch",
            path="app/src/main/java/demo/ChecklistScreen.kt",
            active_intent_type="MODIFY",
            active_allowed_actions=("read_chunk", "extract_symbol", "edit_file"),
        )
    )

    assert plan.prefer_structural_recovery is True
    assert plan.is_search_mismatch is True
    assert plan.next_actions == (
        "read_chunk",
        "extract_symbol",
        "replace_symbol",
        "edit_file",
        "write_file_block",
    )
    assert "extract_symbol" in plan.prompt_hint
    assert "replace_symbol" in plan.prompt_hint


def test_repeated_modify_kotlin_search_mismatch_suppresses_edit_file_retry():
    plan = resolve_edit_file_recovery(
        EditFileRecoveryContext(
            reason="repeated_edit_failure_hard_stop",
            error_code="VALIDATION_ERROR",
            mismatch_type="indentation_or_partial_block_mismatch",
            path="app/src/main/java/demo/ChecklistScreen.kt",
            active_intent_type="MODIFY",
            active_allowed_actions=("read_chunk", "extract_symbol", "replace_symbol", "edit_file", "write_file_block"),
        )
    )

    assert plan.prefer_structural_recovery is True
    assert "edit_file" not in plan.next_actions
    assert plan.next_actions == (
        "read_chunk",
        "extract_symbol",
        "replace_symbol",
        "write_file_block",
    )
    assert plan.recommended_actions == plan.next_actions
    assert "do not retry edit_file" in plan.prompt_hint


def test_single_modify_kotlin_search_mismatch_keeps_edit_file_available():
    plan = resolve_edit_file_recovery(
        EditFileRecoveryContext(
            reason="edit_file_search_mismatch",
            error_code="VALIDATION_ERROR",
            mismatch_type="indentation_or_partial_block_mismatch",
            path="app/src/main/java/demo/ChecklistScreen.kt",
            active_intent_type="MODIFY",
            active_allowed_actions=("read_chunk", "extract_symbol", "replace_symbol", "edit_file", "write_file_block"),
        )
    )

    assert "edit_file" in plan.next_actions


def test_repeated_modify_markdown_search_mismatch_suppresses_edit_file_without_replace_symbol():
    plan = resolve_edit_file_recovery(
        EditFileRecoveryContext(
            reason="repeating_failure",
            error_code="VALIDATION_ERROR",
            mismatch_type="no_similar_block_found",
            path="README.md",
            active_intent_type="MODIFY",
            active_allowed_actions=("read_chunk", "extract_symbol", "edit_file", "write_file_block"),
        )
    )

    assert "edit_file" not in plan.next_actions
    assert "replace_symbol" not in plan.next_actions
    assert plan.next_actions == ("read_chunk", "extract_symbol", "write_file_block")


def test_repeated_modify_kotlin_search_mismatch_suppresses_edit_file_retry():
    plan = resolve_edit_file_recovery(
        EditFileRecoveryContext(
            reason="repeated_edit_failure_hard_stop",
            error_code="VALIDATION_ERROR",
            mismatch_type="indentation_or_partial_block_mismatch",
            path="app/src/main/java/demo/ChecklistScreen.kt",
            active_intent_type="MODIFY",
            active_allowed_actions=("read_chunk", "extract_symbol", "replace_symbol", "edit_file", "write_file_block"),
        )
    )

    assert plan.prefer_structural_recovery is True
    assert "edit_file" not in plan.next_actions
    assert plan.next_actions == (
        "read_chunk",
        "extract_symbol",
        "replace_symbol",
        "write_file_block",
    )
    assert plan.recommended_actions == plan.next_actions
    assert "Do not retry edit_file" in plan.prompt_hint


def test_single_modify_kotlin_search_mismatch_keeps_edit_file_available():
    plan = resolve_edit_file_recovery(
        EditFileRecoveryContext(
            reason="edit_file_search_mismatch",
            error_code="VALIDATION_ERROR",
            mismatch_type="indentation_or_partial_block_mismatch",
            path="app/src/main/java/demo/ChecklistScreen.kt",
            active_intent_type="MODIFY",
            active_allowed_actions=("read_chunk", "extract_symbol", "replace_symbol", "edit_file", "write_file_block"),
        )
    )

    assert "edit_file" in plan.next_actions


def test_modify_python_search_mismatch_prefers_structural_recovery():
    actions = search_mismatch_recovery_actions(
        path="modules/example.py",
        mismatch_type="multiple_similar_blocks",
        active_intent_type="MODIFY",
        active_allowed_actions=("read_chunk", "edit_file"),
    )

    assert "replace_symbol" in actions
    assert "write_file_block" in actions


def test_modify_unsupported_suffix_excludes_replace_symbol():
    plan = resolve_edit_file_recovery(
        EditFileRecoveryContext(
            reason="edit_file_search_mismatch",
            error_code="VALIDATION_ERROR",
            mismatch_type="no_similar_block_found",
            path="README.md",
            active_intent_type="MODIFY",
            active_allowed_actions=("read_chunk", "extract_symbol", "edit_file", "write_file_block"),
        )
    )

    assert plan.prefer_structural_recovery is False
    assert "replace_symbol" not in plan.next_actions
    assert plan.next_actions == ("read_chunk", "extract_symbol", "edit_file", "write_file_block")


def test_investigate_recovery_excludes_state_changing_actions():
    plan = resolve_edit_file_recovery(
        EditFileRecoveryContext(
            reason="edit_file_search_mismatch",
            error_code="VALIDATION_ERROR",
            mismatch_type="whitespace_mismatch",
            path="app/src/main/java/demo/ChecklistScreen.kt",
            active_intent_type="INVESTIGATE",
            active_allowed_actions=("read_chunk", "extract_symbol", "search_content", "edit_file", "replace_symbol"),
        )
    )

    assert plan.next_actions == (
        "read_chunk",
        "read_file_skeleton",
        "extract_symbol",
        "search_content",
        "read_file",
    )
    assert "edit_file" not in plan.next_actions
    assert "replace_symbol" not in plan.next_actions
    assert "write_file_block" not in plan.next_actions


def test_malformed_edit_file_recovery_uses_same_modify_policy():
    actions = malformed_edit_file_recovery_actions(
        active_intent_type="MODIFY",
        active_allowed_actions=("read_chunk", "edit_file"),
    )

    assert actions == (
        "read_chunk",
        "extract_symbol",
        "replace_symbol",
        "edit_file",
        "write_file_block",
    )


def test_no_legacy_modify_mismatch_action_set():
    actions = search_mismatch_recovery_actions(
        path="app/src/main/java/demo/ChecklistScreen.kt",
        mismatch_type="indentation_or_partial_block_mismatch",
        active_intent_type="MODIFY",
        active_allowed_actions=("read_file", "search_content", "edit_file", "write_file"),
    )

    assert actions != ("read_file", "search_content", "edit_file", "write_file")
    assert "replace_symbol" in actions
    assert "write_file_block" in actions


def test_modify_kotlin_search_mismatch_with_unique_fuzzy_candidate_recommends_fuzzy_edit_file():
    plan = resolve_edit_file_recovery(
        EditFileRecoveryContext(
            reason="edit_file_search_mismatch",
            error_code="VALIDATION_ERROR",
            mismatch_type="indentation_or_partial_block_mismatch",
            path="app/src/main/java/demo/ChecklistScreen.kt",
            active_intent_type="MODIFY",
            active_allowed_actions=("read_chunk", "extract_symbol", "replace_symbol", "edit_file", "write_file_block"),
            fuzzy_unique_candidate=True,
        )
    )

    assert "fuzzy_edit_file" in plan.next_actions
    assert plan.next_actions.index("fuzzy_edit_file") < plan.next_actions.index("edit_file")
    assert "unique indentation-normalized fuzzy candidate" in plan.prompt_hint


def test_modify_kotlin_search_mismatch_without_unique_fuzzy_candidate_does_not_recommend_fuzzy_edit_file():
    plan = resolve_edit_file_recovery(
        EditFileRecoveryContext(
            reason="edit_file_search_mismatch",
            error_code="VALIDATION_ERROR",
            mismatch_type="indentation_or_partial_block_mismatch",
            path="app/src/main/java/demo/ChecklistScreen.kt",
            active_intent_type="MODIFY",
            active_allowed_actions=("read_chunk", "extract_symbol", "replace_symbol", "edit_file", "write_file_block"),
            fuzzy_unique_candidate=False,
        )
    )

    assert "fuzzy_edit_file" not in plan.next_actions
