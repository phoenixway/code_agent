from modules.agent.state_manager import AgentState


def test_recovery_visibility_successes_start_empty():
    state = AgentState()

    assert state.recovery_visibility_successes == []


def test_note_recovery_visibility_success_records_successful_action_with_path_target():
    state = AgentState()
    state.current_turn_id = 7

    state.note_recovery_visibility_success(
        {"type": "create_file", "path": "app/build.gradle.kts"},
        {"status": "success", "output": "created"},
    )

    assert state.recovery_visibility_successes == [
        {
            "turn_id": 7,
            "action_type": "create_file",
            "target": "app/build.gradle.kts",
        }
    ]


def test_note_recovery_visibility_success_ignores_failed_error_and_denied_results():
    state = AgentState()
    state.current_turn_id = 8

    state.note_recovery_visibility_success(
        {"type": "create_file", "path": "a.txt"},
        {"status": "failed", "output": "bad"},
    )
    state.note_recovery_visibility_success(
        {"type": "edit_file", "path": "b.txt"},
        {"status": "error", "output": "bad"},
    )
    state.note_recovery_visibility_success(
        {"type": "run_shell", "command": "pytest -q"},
        {"status": "denied", "output": "no"},
    )

    assert state.recovery_visibility_successes == []


def test_note_recovery_visibility_success_uses_command_text_as_shell_target():
    state = AgentState()
    state.current_turn_id = 9

    state.note_recovery_visibility_success(
        {"type": "run_shell", "command": "pytest -q tests"},
        {"status": "success", "output": "green"},
    )

    assert state.recovery_visibility_successes == [
        {
            "turn_id": 9,
            "action_type": "run_shell",
            "target": "pytest -q tests",
        }
    ]


def test_note_recovery_visibility_success_uses_pattern_for_search_content_without_path():
    state = AgentState()
    state.current_turn_id = 10

    state.note_recovery_visibility_success(
        {"type": "search_content", "pattern": "RecoveryDecision"},
        {"status": "success", "output": "2 matches"},
    )

    assert state.recovery_visibility_successes == [
        {
            "turn_id": 10,
            "action_type": "search_content",
            "target": "RecoveryDecision",
        }
    ]


def test_note_recovery_visibility_success_keeps_only_recent_entries():
    state = AgentState()
    state.current_turn_id = 1

    for index in range(25):
        state.current_turn_id = index + 1
        state.note_recovery_visibility_success(
            {"type": "read_file", "path": f"file_{index}.py"},
            {"status": "success", "output": "ok"},
        )

    assert len(state.recovery_visibility_successes) == 20
    assert state.recovery_visibility_successes[0]["target"] == "file_5.py"
    assert state.recovery_visibility_successes[-1]["target"] == "file_24.py"
