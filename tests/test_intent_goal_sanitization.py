from types import SimpleNamespace

from modules.agent.orchestration.prompting import OrchestratorPromptBuilder


def _builder():
    return OrchestratorPromptBuilder(
        SimpleNamespace(
            state=SimpleNamespace(active_intent=None),
            config=SimpleNamespace(),
            planner=None,
            memory_board_store=None,
        )
    )


def test_raw_stack_trace_is_not_used_as_generated_intent_goal():
    raw = """❯ ./gradlew :app:assembleDebug
> Task :app:kspDebugKotlin
e: [ksp] java.util.NoSuchElementException: List is empty.
at kotlin.collections.CollectionsKt___CollectionsKt.single(...)
at androidx.room.processor.DatabaseProcessor.process(...)
..."""
    goal = _builder().sanitize_intent_goal(
        raw,
        fallback="Fix current Android compile errors.",
    )

    assert len(goal) <= 100
    assert "\n" not in goal
    assert "at " not in goal
    assert "Task :app:kspDebugKotlin" not in goal
    assert "java.util.NoSuchElementException" not in goal
    assert goal == "Fix current Android compile errors."


def test_normal_short_user_goal_passes_through():
    goal = _builder().sanitize_intent_goal("Add bookmark import/export UI and file handling.")

    assert goal == "Add bookmark import/export UI and file handling."
    assert len(goal) <= 100


def test_overlong_natural_language_goal_is_truncated_safely():
    raw = (
        "Add bookmark import/export UI and file handling across settings, persistence, "
        "error states, permissions, user flows, and migration details while keeping the "
        "existing build green and preserving current import/export behavior."
    )
    goal = _builder().sanitize_intent_goal(raw)

    assert len(goal) <= 100
    assert "\n" not in goal
    assert goal
