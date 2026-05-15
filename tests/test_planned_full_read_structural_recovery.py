from pathlib import Path
from types import SimpleNamespace

from modules.agent.action_dispatcher import ActionDispatcher
from modules.agent.state_manager import AgentState


class DummyLog:
    def debug(self, *_args, **_kwargs):
        pass


class DummyHistory:
    max_tokens = 256
    TURN_WORKING_MATERIAL_SAFE_RATIO = 0.5

    def current_turn_working_material_token_count(self, _turn_id):
        return 0


def test_planned_full_read_too_large_recommends_extract_symbol_for_source_file(tmp_path):
    target = tmp_path / "ChecklistScreen.kt"
    target.write_text("fun x() = Unit\n" * 2000, encoding="utf-8")

    agent = SimpleNamespace(
        ui=None,
        processor=None,
        config=SimpleNamespace(),
        log=DummyLog(),
        history=DummyHistory(),
    )
    dispatcher = ActionDispatcher(agent)
    state = AgentState(agent.config)

    command = {"type": "read_file", "path": str(target)}
    stop = dispatcher._preflight_turn_working_material_budget([command], [0], state)

    assert stop is not None
    assert stop["reason"] == "planned_full_read_too_large"
    assert "extract_symbol" in stop["next_actions"]
    assert "extract_symbol" in stop["message"]
    assert "prefer extract_symbol over large read_chunk ranges" in stop["message"]
    assert "Return EXACTLY ONE" not in stop["message"]
    assert "[RECOVERY_SCOPE]" in stop["message"]
    assert "[NEXT_STEP_RULE]" in stop["message"]
    assert "[EXIT_CONDITION]" in stop["message"]


def test_planned_turn_working_material_too_large_uses_scoped_recovery_text(tmp_path):
    first = tmp_path / "A.py"
    second = tmp_path / "B.py"
    first.write_text("print('a')\n" * 1200, encoding="utf-8")
    second.write_text("print('b')\n" * 1200, encoding="utf-8")

    agent = SimpleNamespace(
        ui=None,
        processor=None,
        config=SimpleNamespace(),
        log=DummyLog(),
        history=DummyHistory(),
    )
    dispatcher = ActionDispatcher(agent)
    state = AgentState(agent.config)

    commands = [
        {"type": "read_file", "path": str(first), "start_byte": 0, "end_byte": 5000},
        {"type": "read_file", "path": str(second), "start_byte": 0, "end_byte": 5000},
    ]
    stop = dispatcher._preflight_turn_working_material_budget(commands, [0, 1], state)

    assert stop is not None
    assert stop["reason"] == "planned_turn_working_material_too_large"
    assert stop["error_code"] == "PLANNED_TURN_WORKING_MATERIAL_TOO_LARGE"
    assert stop["next_actions"] == [
        "read_file",
        "read_chunk",
        "read_file_skeleton",
        "search_content",
        "search_files",
        "run_shell",
    ]
    assert "Return EXACTLY ONE" not in stop["message"]
    assert "[RECOVERY_SCOPE]" in stop["message"]
    assert "[NEXT_STEP_RULE]" in stop["message"]
    assert "[EXIT_CONDITION]" in stop["message"]
