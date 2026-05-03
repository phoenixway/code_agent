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
    state.task_board = {
        "goal": "Finish change",
        "intent_id": "intent_1",
        "lineage_id": "lineage_1",
        "steps": [{"id": "sg_1", "status": "in_progress", "title": "Finalize answer"}],
        "active_step_id": "sg_1",
    }
    state.task_board_enabled = True
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
    assert state.task_board is None
    assert state.task_board_enabled is False
    assert state.current_turn_id == 8


def _intent_config():
    return SimpleNamespace(
        INTENT_RELABEL_SUSPICION_ENABLED=False,
        INTENT_REUSE_EXTENSION_STEPS=4,
    )


def test_apply_intent_contract_clears_plan_board_for_new_lineage_activation():
    state = AgentState(_intent_config())
    state.task_board = {
        "goal": "Old lineage board",
        "intent_id": "old_intent",
        "lineage_id": "old_lineage",
        "steps": [{"id": "sg_1", "status": "in_progress", "title": "Stale step"}],
        "active_step_id": "sg_1",
    }
    state.task_board_enabled = True

    ok, msg = state.apply_intent_contract(
        {
            "intent_id": "new_intent",
            "intent_type": "INVESTIGATE",
            "goal": "Determine how plan board ownership should behave across fresh intent lineage activation.",
            "allowed_actions": ["read_file"],
            "safe_steps_limit": 4,
            "retry_limit": 2,
            "mode": "activate",
            "switch_reason": "user_requested_new_task",
        },
        _intent_config(),
    )

    assert ok, msg
    assert state.active_intent is not None
    assert state.active_intent.intent_id == "new_intent"
    assert state.task_board is None
    assert state.task_board_enabled is False


def test_apply_intent_contract_preserves_plan_board_for_same_lineage_reuse():
    state = AgentState(_intent_config())
    assert state.apply_intent_contract(
        {
            "intent_id": "intent_1",
            "intent_type": "INVESTIGATE",
            "goal": "Determine how plan board ownership should behave across same-lineage implementation work.",
            "allowed_actions": ["read_file"],
            "safe_steps_limit": 4,
            "retry_limit": 2,
            "mode": "activate",
            "switch_reason": "user_requested_new_task",
        },
        _intent_config(),
    )[0]
    state.task_board = {
        "goal": "Determine how plan board ownership should behave across same-lineage implementation work.",
        "intent_id": "intent_1",
        "lineage_id": "intent_1",
        "steps": [{"id": "sg_1", "status": "in_progress", "title": "Read key files"}],
        "active_step_id": "sg_1",
    }
    state.task_board_enabled = True

    ok, msg = state.apply_intent_contract(
        {
            "intent_id": "intent_1",
            "intent_type": "MODIFY",
            "goal": "Determine how plan board ownership should behave across same-lineage implementation work.",
            "allowed_actions": ["read_file", "write_file_block"],
            "mode": "reuse",
            "requested_steps": 4,
            "switch_reason": "work_type_changed",
        },
        _intent_config(),
    )

    assert ok, msg
    assert state.active_intent is not None
    assert state.active_intent.intent_id == "intent_1"
    assert state.active_intent.lineage_id == "intent_1"
    assert state.task_board is not None
    assert state.task_board["intent_id"] == "intent_1"
    assert state.task_board["lineage_id"] == "intent_1"
    assert state.task_board_enabled is True
