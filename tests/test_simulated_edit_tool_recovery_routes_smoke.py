from types import SimpleNamespace


from modules.agent.policy_engine import PolicyEngine, PreActionPolicyInput
from modules.tools.recovery.edit_file_recovery_policy import (
    EditFileRecoveryContext,
    malformed_edit_file_recovery_actions,
    resolve_edit_file_recovery,
    search_mismatch_recovery_actions,
)


def test_p3_edit_file_exact_miss_with_unique_fuzzy_candidate_recommends_fuzzy_edit_file_first():
    plan = resolve_edit_file_recovery(
        EditFileRecoveryContext(
            reason="edit_file_search_mismatch",
            error_code="VALIDATION_ERROR",
            mismatch_type="indentation_or_partial_block_mismatch",
            path="app/src/main/java/demo/ChecklistScreen.kt",
            active_intent_type="MODIFY",
            active_allowed_actions=(
                "read_chunk",
                "extract_symbol",
                "replace_symbol",
                "edit_file",
                "write_file_block",
            ),
            fuzzy_unique_candidate=True,
        )
    )

    assert "fuzzy_edit_file" in plan.next_actions
    assert "edit_file" in plan.next_actions
    assert plan.next_actions.index("fuzzy_edit_file") < plan.next_actions.index("edit_file")
    assert "unique indentation-normalized fuzzy candidate" in plan.prompt_hint
    assert "use fuzzy_edit_file only with the same path, search_text, and replace_text" in plan.prompt_hint


def test_p3_repeated_edit_file_exact_miss_suppresses_blind_edit_file_retry_but_keeps_safer_routes():
    actions = search_mismatch_recovery_actions(
        path="app/src/main/java/demo/ChecklistScreen.kt",
        mismatch_type="indentation_or_partial_block_mismatch",
        active_intent_type="MODIFY",
        active_allowed_actions=(
            "read_chunk",
            "extract_symbol",
            "replace_symbol",
            "fuzzy_edit_file",
            "replace_line_range",
            "edit_file",
            "write_file_block",
        ),
        reason="repeating_failure",
        fuzzy_unique_candidate=True,
    )

    assert "edit_file" not in actions
    assert "fuzzy_edit_file" in actions
    assert "replace_line_range" in actions
    assert "replace_symbol" in actions
    assert "write_file_block" in actions


def test_p3_malformed_edit_file_line_range_payload_points_to_replace_line_range_route():
    actions = malformed_edit_file_recovery_actions(
        active_intent_type="MODIFY",
        active_allowed_actions=(
            "read_chunk",
            "edit_file",
        ),
    )

    assert "replace_line_range" in actions
    assert "extract_symbol" in actions
    assert "replace_symbol" in actions
    assert "write_file_block" in actions

def test_p3_repeated_read_file_already_available_returns_use_existing_content_route():
    engine = PolicyEngine()

    first_decision = engine.evaluate_pre_action(
        PreActionPolicyInput(
            cmd_type="read_file",
            path="src/example.py",
            fingerprint="read_file:src/example.py",
            target_file=None,
            forbidden_recover_fingerprint=None,
            has_cross_target_reason=False,
            already_read_current_version=True,
            reread_reason_ok=False,
            reread_after_summary=False,
            history_version=4,
            reread_repeat_count=0,
        )
    )

    assert first_decision.allow is False
    assert first_decision.stop_reason == "reread_already_in_history"
    assert "File content is already available as history" in first_decision.recovery_prompt
    assert "version v4" in first_decision.recovery_prompt
    assert "Use that content now. Do not call read_file again." in first_decision.recovery_prompt
    assert first_decision.required_next_action_types == ["search_content", "edit_file", "write_file"]

    repeated_decision = engine.evaluate_pre_action(
        PreActionPolicyInput(
            cmd_type="read_file",
            path="src/example.py",
            fingerprint="read_file:src/example.py",
            target_file=None,
            forbidden_recover_fingerprint=None,
            has_cross_target_reason=False,
            already_read_current_version=True,
            reread_reason_ok=False,
            reread_after_summary=False,
            history_version=4,
            reread_repeat_count=2,
        )
    )

    assert repeated_decision.allow is False
    assert repeated_decision.stop_reason == "reread_already_in_history_use_existing_content"
    assert "File content is already available as history" in repeated_decision.recovery_prompt
    assert "version v4" in repeated_decision.recovery_prompt
    assert "Use that content now. Do not call read_file again." in repeated_decision.recovery_prompt
    assert repeated_decision.required_next_action_types == ["search_content", "edit_file", "write_file"]
