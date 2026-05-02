from types import SimpleNamespace

import pytest

from modules.agent.orchestration.intent_transitions import IntentTransitionHandler
from modules.agent.orchestration.prompting import OrchestratorPromptBuilder
from modules.agent.state_manager import AgentState


def _config():
    return SimpleNamespace(
        INTENT_RELABEL_SUSPICION_ENABLED=False,
        INTENT_DEFAULT_SAFE_STEPS=4,
        INTENT_DEFAULT_RETRY_LIMIT=2,
        INTENT_MAX_SAFE_STEPS=8,
        INTENT_MAX_RETRY_LIMIT=4,
        INTENT_REUSE_EXTENSION_STEPS=4,
    )


class _Recovery:
    async def handle_defect_detector_stop(self, stop_info):
        return SimpleNamespace(handled=False, next_query=None)


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


def _handler(state):
    return IntentTransitionHandler(
        SimpleNamespace(state=state, config=_config(), log=None),
        _builder(state),
        _Recovery(),
    )


def _reuse_payload():
    return {
        "intent_id": "save_analysis_to_docs",
        "intent_type": "MODIFY",
        "goal": "Save orchestration analysis to a docs markdown file.",
        "allowed_actions": ["write_file_block"],
        "mode": "reuse",
        "switch_reason": "save_requested",
    }


@pytest.mark.asyncio
async def test_reuse_without_active_intent_returns_activate_only_recovery():
    state = AgentState(_config())
    handler = _handler(state)

    decision = await handler.handle_model_step(
        intent_payload=_reuse_payload(),
        intent_error=None,
        response_text='<intent mode="reuse">{"intent_id":"save_analysis_to_docs","intent_type":"MODIFY","goal":"Save orchestration analysis to a docs markdown file.","allowed_actions":["write_file_block"],"mode":"reuse","switch_reason":"save_requested"}</intent>',
        state_machine=None,
    )

    assert decision.handled is True
    assert decision.reason == "intent_reuse_without_active_intent"
    assert state.active_intent is None
    assert state.intent_runtime.last_transition_info.get("transition") == "rejected"
    assert '<intent mode="activate">' in (decision.next_query or "")
    assert '<intent mode="reuse">' not in (decision.next_query or "")
    assert "Do not use mode=\"reuse\"" in (decision.next_query or "")


@pytest.mark.asyncio
async def test_repeated_reuse_without_active_intent_escalates():
    state = AgentState(_config())
    handler = _handler(state)
    response = '<intent mode="reuse">{"intent_id":"save_analysis_to_docs","intent_type":"MODIFY","goal":"Save analysis to docs.","allowed_actions":["write_file_block"],"mode":"reuse","switch_reason":"save_requested"}</intent>'

    first = await handler.handle_model_step(
        intent_payload=_reuse_payload(),
        intent_error=None,
        response_text=response,
        state_machine=None,
    )
    second = await handler.handle_model_step(
        intent_payload=_reuse_payload(),
        intent_error=None,
        response_text=response,
        state_machine=None,
    )
    third = await handler.handle_model_step(
        intent_payload=_reuse_payload(),
        intent_error=None,
        response_text=response,
        state_machine=None,
    )

    assert first.handled is True
    assert second.handled is True
    assert first.reason == "intent_reuse_without_active_intent"
    assert second.reason == "intent_reuse_without_active_intent"
    assert third.stop_loop is True
    assert third.reason == "terminal_repeated_intent_transition_defect"


@pytest.mark.asyncio
async def test_valid_activate_after_reuse_without_active_intent_is_accepted():
    state = AgentState(_config())
    handler = _handler(state)

    await handler.handle_model_step(
        intent_payload=_reuse_payload(),
        intent_error=None,
        response_text='<intent mode="reuse">{"intent_id":"save_analysis_to_docs","intent_type":"MODIFY","goal":"Save analysis to docs.","allowed_actions":["write_file_block"],"mode":"reuse","switch_reason":"save_requested"}</intent>',
        state_machine=None,
    )

    activate_payload = {
        "intent_id": "save_analysis_to_docs",
        "intent_type": "MODIFY",
        "goal": "Save orchestration analysis to a docs markdown file.",
        "allowed_actions": ["write_file_block"],
        "mode": "activate",
    }
    decision = await handler.handle_model_step(
        intent_payload=activate_payload,
        intent_error=None,
        response_text='<intent mode="activate">{"intent_id":"save_analysis_to_docs","intent_type":"MODIFY","goal":"Save orchestration analysis to a docs markdown file.","allowed_actions":["write_file_block"],"mode":"activate"}</intent>',
        state_machine=None,
    )

    assert decision.handled is True
    assert decision.reason == "intent_accepted_without_followup"
    assert state.active_intent is not None
    assert state.active_intent.intent_id == "save_analysis_to_docs"
