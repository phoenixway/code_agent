from types import SimpleNamespace

import pytest

from modules.agent.orchestration.action_policy import ActionPolicyHandler
from modules.agent.orchestration.decision_models import ParsedModelOutput
from modules.agent.orchestration.output_recovery import ModelOutputRecoveryHandler
from modules.agent.orchestration.prompting import OrchestratorPromptBuilder
from modules.agent.state_manager import AgentState


class _IntentGuard:
    def action_requires_intent(self, *args, **kwargs):
        return False, ""


def _config():
    return SimpleNamespace(
        INTENT_RELABEL_SUSPICION_ENABLED=False,
        INTENT_REUSE_EXTENSION_STEPS=4,
    )


def _builder(state):
    return OrchestratorPromptBuilder(
        SimpleNamespace(
            state=state,
            config=_config(),
            planner=None,
            memory_board_store=None,
            log=None,
        )
    )


def _active_build_fix_state():
    state = AgentState(_config())
    state.note_build_failure_from_text(
        "> Task :app:compileDebugKotlin FAILED\n"
        "e: file:///tmp/app/src/main/java/com/example/localbookmarks/MainActivity.kt:45:21 "
        "Unresolved reference: AppScaffold"
    )
    state.intent_runtime.active_intent = SimpleNamespace(
        intent_id="fix_build_errors",
        intent_type="MODIFY",
        goal="Fix current Android compile errors.",
        allowed_actions=["read_file", "edit_file", "create_file", "run_shell"],
    )
    return state


def test_build_failure_triggers_build_fix_intent_requirement():
    state = AgentState(_config())
    detected = state.note_build_failure_from_text(
        "> Task :app:compileDebugKotlin FAILED\n"
        "e: file:///tmp/app/src/main/java/com/example/localbookmarks/MainActivity.kt:45:21 "
        "Unresolved reference: AppScaffold"
    )

    prompt = _builder(state).build_intent_required_prompt("build_failure_requires_formal_intent")

    assert detected is True
    assert state.build_fix_mode_requires_intent() is True
    assert state.build_fix_mode_reason == "build_failure_requires_formal_intent"
    assert 'Return only one top-level <intent mode="activate">...</intent>.' in prompt
    assert "Do not include <think>, <memory_update_done />, <action>" in prompt
    assert '"goal": "Fix current Android compile errors."' in prompt


def test_build_fix_prompt_does_not_include_raw_stack_trace_as_goal():
    state = AgentState(_config())
    state.note_build_failure_from_text(
        "❯ ./gradlew :app:assembleDebug\n"
        "> Task :app:kspDebugKotlin\n"
        "e: [ksp] java.util.NoSuchElementException: List is empty.\n"
        "at androidx.room.processor.DatabaseProcessor.process(...)"
    )

    prompt = _builder(state).build_build_fix_intent_required_prompt(
        goal="❯ ./gradlew :app:assembleDebug\n> Task :app:kspDebugKotlin\ne: [ksp] java.util.NoSuchElementException"
    )

    assert '"goal": "Fix current Android compile errors."' in prompt
    assert "java.util.NoSuchElementException" not in prompt
    assert "at androidx.room.processor" not in prompt
    assert "> Task :app:kspDebugKotlin" not in prompt


@pytest.mark.asyncio
async def test_build_fix_mode_blocks_feature_expansion_action():
    state = _active_build_fix_state()
    builder = _builder(state)
    handler = ActionPolicyHandler(
        SimpleNamespace(state=state, log=None),
        _IntentGuard(),
        builder,
    )

    decision = await handler.decide(
        SimpleNamespace(user_input="continue"),
        [SimpleNamespace(type="action", content={"type": "create_file", "path": "app/src/main/java/com/example/NewFeature.kt"})],
        intent_payload=None,
    )

    assert decision.handled is True
    assert decision.reason == "build_fix_mode_blocks_feature_expansion"


@pytest.mark.asyncio
async def test_build_fix_mode_allows_reading_compiler_mentioned_files():
    state = _active_build_fix_state()
    builder = _builder(state)
    handler = ActionPolicyHandler(
        SimpleNamespace(state=state, log=None),
        _IntentGuard(),
        builder,
    )

    decision = await handler.decide(
        SimpleNamespace(user_input="continue"),
        [SimpleNamespace(type="action", content={"type": "read_file", "path": "app/src/main/java/com/example/localbookmarks/MainActivity.kt"})],
        intent_payload=None,
    )

    assert decision.handled is False
    assert decision.reason == "actions_allowed_to_proceed"


@pytest.mark.asyncio
async def test_build_fix_mode_final_answer_must_mention_build_status():
    state = _active_build_fix_state()
    builder = _builder(state)
    recovery = ModelOutputRecoveryHandler(
        SimpleNamespace(state=state, config=_config(), log=None, ui=SimpleNamespace()),
        builder,
    )

    decision = await recovery.decide(
        ParsedModelOutput(
            response="Done, fixed imports and coroutine usage.",
            segments=[],
            has_action_tag=False,
            has_action_segment=False,
            has_intent_segment=False,
            visible_text="Done, fixed imports and coroutine usage.",
            invalid_kind="",
            model_stop_reason="",
        ),
        malformed_action_retries=0,
        audit_marker_retries=0,
    )

    assert decision.handled is True
    assert decision.reason == "build_fix_final_answer_missing_build_status"
