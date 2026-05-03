from types import SimpleNamespace

from modules.agent.state_manager import AgentState


def test_orchestration_state_field_groups_expose_expected_categories():
    groups = AgentState.orchestration_state_field_groups()

    assert set(groups) == {"turn_local", "cross_turn", "resumable", "technical_interruption"}
    assert "orchestration_trace" in groups["turn_local"]
    assert "terminal_plaintext_completion_pending" in groups["cross_turn"]
    assert "last_resumable_intent_id" in groups["resumable"]
    assert "last_technical_interruption" in groups["technical_interruption"]


def test_start_turn_runtime_resets_turn_local_orchestration_fields_but_preserves_resumable_metadata():
    state = AgentState()
    state.pending_suspect_intent_payload = {"intent_id": "x"}
    state.memory_tag_expected_next_step = True
    state.memory_tag_reason = "meaningful_evidence_gain"
    state.reuse_only_intent_required = True
    state.transition_only_intent_required = True
    state.intent_transition_defect_reason = "conflict"
    state.orchestration_trace = ["entry"]
    state.orchestration_trace_sequence = 3
    state.build_fix_last_build_ran = True
    state.build_fix_last_build_passed = True
    state.build_fix_last_build_command = "./gradlew :app:assembleDebug"

    state.last_resumable_intent_id = "resume_1"
    state.last_resumable_intent_goal = "Continue work"
    state.last_technical_interruption = {"message": "provider failed"}
    state.pending_resume_query = "resume query"
    state.build_fix_mode_active = True
    state.build_fix_error_summary = "Fix current Android compile errors."

    state.start_turn_runtime()

    assert state.pending_suspect_intent_payload is None
    assert state.memory_tag_expected_next_step is False
    assert state.memory_tag_reason == ""
    assert state.reuse_only_intent_required is False
    assert state.transition_only_intent_required is False
    assert state.intent_transition_defect_reason == ""
    assert state.orchestration_trace == []
    assert state.orchestration_trace_sequence == 0
    assert state.build_fix_last_build_ran is False
    assert state.build_fix_last_build_passed is False
    assert state.build_fix_last_build_command == ""

    assert state.last_resumable_intent_id == "resume_1"
    assert state.last_resumable_intent_goal == "Continue work"
    assert state.last_technical_interruption == {"message": "provider failed"}
    assert state.pending_resume_query == "resume query"
    assert state.build_fix_mode_active is True
    assert state.build_fix_error_summary == "Fix current Android compile errors."


def test_start_turn_runtime_finalizes_pending_forced_plaintext_completion_before_new_turn():
    state = AgentState()
    active_intent = SimpleNamespace(
        intent_id="intent_1",
        intent_type="MODIFY",
        goal="Finish change",
        allowed_actions=["edit_file"],
        lineage_id="lineage_1",
        safe_steps_limit=5,
        retry_limit=2,
        force_plaintext_completion=True,
        hard_limit_hit_count=4,
    )
    state.intent_runtime = SimpleNamespace(
        active_intent=active_intent,
        finalize_current_intent_completion=lambda: setattr(state.intent_runtime, "active_intent", None) or True,
        clear_requirement=lambda: None,
    )
    state.mark_pending_forced_plaintext_completion_close("forced_plaintext_completion", "test")
    state.current_turn_id = 7

    finalized = state.start_turn_runtime()

    assert finalized is None
    assert state.active_intent is None
    assert state.pending_finalize_after_terminal_plaintext_completion is False
    assert state.last_resumable_intent_id == "intent_1"
    assert state.last_resumable_intent_type == "MODIFY"
    assert state.last_resumable_intent_lineage_id == "lineage_1"
    assert state.last_resumable_intent_completion_reason == "forced_plaintext_completion"
    assert state.current_turn_id == 8
