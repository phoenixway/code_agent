from types import SimpleNamespace

from modules.agent.state_machine import AgentStateMachine, TaskKind


def test_no_progress_diagnostic_prompt_uses_scoped_recovery_text():
    sm = AgentStateMachine.__new__(AgentStateMachine)
    sm.config = SimpleNamespace(
        RESEARCH_STAGNATION_LIMIT=4,
        IMPLEMENT_STAGNATION_LIMIT=2,
        STAGNATION_MAX_DIAGNOSTICS=1,
    )
    sm.task_kind = TaskKind.INSPECTION

    prompt = sm.build_diagnostic_prompt()

    assert "SYSTEM_DIAGNOSTIC: You are in a no-progress loop." in prompt
    assert "Allowed next actions now:" in prompt
    assert "Return EXACTLY ONE" not in prompt
    assert "[RECOVERY_SCOPE]" in prompt
    assert "[NEXT_STEP_RULE]" in prompt
    assert "[EXIT_CONDITION]" in prompt
    assert "Choose a materially different next action" in prompt
