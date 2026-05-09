from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest

from modules.agent.orchestration.runtime.memory_board_stage import MemoryBoardStageHandler
from modules.agent.orchestration.runtime.plan_board_stage import PlanBoardStageHandler


def _memory_agent(*, board_engine=None, state_overrides=None):
    state = SimpleNamespace(
        last_memory_board_parsed_count=0,
        last_memory_board_accepted_count=0,
        last_memory_board_rejected_count=0,
        last_memory_update_done=False,
        last_memory_checkpoint_only=False,
        consecutive_memory_checkpoint_only_count=0,
        memory_tag_expected_next_step=False,
        memory_tag_reason="",
        memory_tag_expected_intent_id="",
    )
    for key, value in dict(state_overrides or {}).items():
        setattr(state, key, value)
    return SimpleNamespace(
        state=state,
        memory_board_engine=board_engine,
        log=None,
        ui=SimpleNamespace(),
    )


def _plan_agent(*, planner=None, state_overrides=None):
    state = SimpleNamespace(
        last_plan_subgoal_create_count=99,
    )
    for key, value in dict(state_overrides or {}).items():
        setattr(state, key, value)
    return SimpleNamespace(
        state=state,
        planner=planner,
        log=None,
        ui=SimpleNamespace(print_plan=AsyncMock()),
    )


@pytest.mark.asyncio
async def test_memory_board_handler_uses_clean_text_for_checkpoint_with_text():
    board_engine = SimpleNamespace(
        apply_response_text=MagicMock(
            return_value=SimpleNamespace(
                parsed_count=1,
                accepted_count=1,
                rejected_count=0,
                clean_text="Need one more read.",
            )
        )
    )
    handler = MemoryBoardStageHandler(
        _memory_agent(board_engine=board_engine),
        SimpleNamespace(_current_active_intent_id=MagicMock(return_value="intent_1")),
    )

    decision = await handler.apply(SimpleNamespace(user_input="inspect"), "<finding scope=\"intent\">Found X</finding>")

    assert decision.handled is False
    assert decision.reason == "memory_checkpoint_and_text"
    assert decision.memory_checkpoint_and_text is True
    assert decision.response_text == "Need one more read."


@pytest.mark.asyncio
async def test_memory_board_handler_raw_visible_text_fallback_wins_when_clean_text_is_empty():
    board_engine = SimpleNamespace(
        apply_response_text=MagicMock(
            return_value=SimpleNamespace(
                parsed_count=1,
                accepted_count=1,
                rejected_count=0,
                clean_text="",
            )
        )
    )
    handler = MemoryBoardStageHandler(
        _memory_agent(board_engine=board_engine),
        SimpleNamespace(_current_active_intent_id=MagicMock(return_value="intent_1")),
    )
    response = '<finding scope="intent">Found X</finding>\nNeed one more read.'

    decision = await handler.apply(SimpleNamespace(user_input="inspect"), response)

    assert decision.handled is False
    assert decision.reason == "memory_checkpoint_and_text"
    assert decision.memory_checkpoint_and_text is True
    assert decision.response_text == response


@pytest.mark.asyncio
async def test_memory_board_handler_marker_only_becomes_checkpoint_only_and_increments_streak():
    board_engine = SimpleNamespace(
        apply_response_text=MagicMock(
            return_value=SimpleNamespace(
                parsed_count=0,
                accepted_count=0,
                rejected_count=0,
                clean_text="<think>Reviewed memory.</think>\n<memory_update_done />",
            )
        )
    )
    agent = _memory_agent(board_engine=board_engine)
    handler = MemoryBoardStageHandler(
        agent,
        SimpleNamespace(_current_active_intent_id=MagicMock(return_value="intent_1")),
    )

    decision = await handler.apply(SimpleNamespace(user_input="inspect"), "<think>Reviewed memory.</think>\n<memory_update_done />")

    assert decision.handled is True
    assert decision.reason == "memory_checkpoint_only"
    assert decision.memory_checkpoint_only is True
    assert agent.state.last_memory_update_done is True
    assert agent.state.last_memory_checkpoint_only is True
    assert agent.state.consecutive_memory_checkpoint_only_count == 1
    assert "<memory_update_done" not in decision.response_text


@pytest.mark.asyncio
async def test_memory_board_handler_checkpoint_only_resets_local_streak_before_incrementing():
    board_engine = SimpleNamespace(
        apply_response_text=MagicMock(
            return_value=SimpleNamespace(
                parsed_count=1,
                accepted_count=1,
                rejected_count=0,
                clean_text="",
            )
        )
    )
    agent = _memory_agent(
        board_engine=board_engine,
        state_overrides={"consecutive_memory_checkpoint_only_count": 1},
    )
    handler = MemoryBoardStageHandler(
        agent,
        SimpleNamespace(_current_active_intent_id=MagicMock(return_value="intent_1")),
    )

    decision = await handler.apply(SimpleNamespace(user_input="inspect"), '<finding scope="intent">Found X</finding>')

    assert decision.reason == "memory_checkpoint_only"
    assert decision.memory_checkpoint_only is True
    assert agent.state.consecutive_memory_checkpoint_only_count == 1
    assert "Now continue the current task." in (decision.next_query or "")


@pytest.mark.asyncio
async def test_memory_board_handler_keeps_action_paths_as_checkpoint_and_action():
    board_engine = SimpleNamespace(
        apply_response_text=MagicMock(
            return_value=SimpleNamespace(
                parsed_count=1,
                accepted_count=1,
                rejected_count=0,
                clean_text='<action>{"type":"read_file","path":"x.py"}</action>',
            )
        )
    )
    agent = _memory_agent(board_engine=board_engine)
    handler = MemoryBoardStageHandler(
        agent,
        SimpleNamespace(_current_active_intent_id=MagicMock(return_value="intent_1")),
    )

    decision = await handler.apply(
        SimpleNamespace(user_input="inspect"),
        '<finding scope="intent">Found X</finding>\n<action>{"type":"read_file","path":"x.py"}</action>',
    )

    assert decision.handled is False
    assert decision.reason == "memory_checkpoint_and_action"
    assert decision.memory_checkpoint_and_action is True
    assert agent.state.consecutive_memory_checkpoint_only_count == 0


@pytest.mark.asyncio
async def test_memory_board_handler_engine_failure_falls_back_to_memory_board_pass():
    board_engine = SimpleNamespace(
        apply_response_text=MagicMock(side_effect=RuntimeError("engine failed"))
    )
    agent = _memory_agent(board_engine=board_engine)
    handler = MemoryBoardStageHandler(
        agent,
        SimpleNamespace(_current_active_intent_id=MagicMock(return_value="intent_1")),
    )

    decision = await handler.apply(SimpleNamespace(user_input="inspect"), "plain text only")

    assert decision.handled is False
    assert decision.reason == "memory_board_pass"
    assert decision.response_text == "plain text only"
    assert agent.state.last_memory_board_parsed_count == 0
    assert agent.state.last_memory_board_accepted_count == 0


@pytest.mark.asyncio
async def test_memory_board_handler_rejected_or_noop_result_without_marker_passes_through():
    board_engine = SimpleNamespace(
        apply_response_text=MagicMock(
            return_value=SimpleNamespace(
                parsed_count=1,
                accepted_count=0,
                rejected_count=1,
                clean_text="plain text only",
            )
        )
    )
    agent = _memory_agent(board_engine=board_engine)
    handler = MemoryBoardStageHandler(
        agent,
        SimpleNamespace(_current_active_intent_id=MagicMock(return_value="intent_1")),
    )

    decision = await handler.apply(SimpleNamespace(user_input="inspect"), "plain text only")

    assert decision.handled is False
    assert decision.reason == "memory_board_pass"
    assert decision.response_text == "plain text only"
    assert agent.state.last_memory_board_parsed_count == 1
    assert agent.state.last_memory_board_accepted_count == 0
    assert agent.state.last_memory_board_rejected_count == 1


@pytest.mark.asyncio
async def test_plan_board_handler_planner_unavailable_passes_through():
    handler = PlanBoardStageHandler(
        _plan_agent(planner=None),
        SimpleNamespace(),
    )

    decision = await handler.apply(SimpleNamespace(), "response")

    assert decision.handled is False
    assert decision.reason == "planner_unavailable"
    assert decision.response_text == "response"


@pytest.mark.asyncio
async def test_plan_board_handler_extract_error_requests_correction():
    planner = SimpleNamespace(
        extract_update_and_strip=MagicMock(return_value=("clean_response", None, "invalid_subgoal_xml"))
    )
    handler = PlanBoardStageHandler(
        _plan_agent(planner=planner),
        SimpleNamespace(),
    )

    decision = await handler.apply(SimpleNamespace(), "<subgoal>broken")

    assert decision.handled is True
    assert decision.continue_loop is True
    assert decision.reason == "invalid_subgoal_xml"
    assert "corrected flat <subgoal ...> tags" in (decision.next_query or "")
    assert decision.response_text == "clean_response"


@pytest.mark.asyncio
async def test_plan_board_handler_no_updates_resets_create_count_and_passes_through():
    planner = SimpleNamespace(
        extract_update_and_strip=MagicMock(return_value=("clean_response", [], None))
    )
    agent = _plan_agent(planner=planner)
    handler = PlanBoardStageHandler(agent, SimpleNamespace())

    decision = await handler.apply(SimpleNamespace(), "response")

    assert decision.handled is False
    assert decision.reason == "no_plan_updates"
    assert decision.response_text == "clean_response"
    assert agent.state.last_plan_subgoal_create_count == 0


@pytest.mark.asyncio
async def test_plan_board_handler_checkpoint_with_text_uses_clean_response():
    update_ops = [{"op": "modify", "id": "sg_1"}]
    planner = SimpleNamespace(
        extract_update_and_strip=MagicMock(return_value=("Need one more read.", update_ops, None)),
        apply_update=MagicMock(return_value=(False, "")),
    )
    agent = _plan_agent(planner=planner)
    handler = PlanBoardStageHandler(agent, SimpleNamespace())

    decision = await handler.apply(SimpleNamespace(), '<subgoal action="modify" id="sg_1">Inspect</subgoal>\nNeed one more read.')

    assert decision.handled is False
    assert decision.reason == "plan_checkpoint_and_text"
    assert decision.plan_checkpoint_and_text is True
    assert decision.response_text == "Need one more read."


@pytest.mark.asyncio
async def test_plan_board_handler_checkpoint_with_action_uses_raw_or_clean_action_detection():
    update_ops = [{"op": "create", "id": "sg_1"}]
    planner = SimpleNamespace(
        extract_update_and_strip=MagicMock(return_value=('<action>{"type":"read_file","path":"x.py"}</action>', update_ops, None)),
        apply_update=MagicMock(return_value=(False, "")),
    )
    agent = _plan_agent(planner=planner)
    handler = PlanBoardStageHandler(agent, SimpleNamespace())

    decision = await handler.apply(SimpleNamespace(), '<subgoal action="create" id="sg_1">Inspect</subgoal>')

    assert decision.handled is False
    assert decision.reason == "plan_checkpoint_and_action"
    assert decision.plan_checkpoint_and_action is True


@pytest.mark.asyncio
async def test_plan_board_handler_checkpoint_only_and_summary_print_side_effects():
    update_ops = [{"op": "create", "id": "sg_1"}]
    planner = SimpleNamespace(
        extract_update_and_strip=MagicMock(return_value=("", update_ops, None)),
        apply_update=MagicMock(return_value=(True, "summary")),
    )
    agent = _plan_agent(planner=planner)
    handler = PlanBoardStageHandler(agent, SimpleNamespace())

    decision = await handler.apply(SimpleNamespace(), '<subgoal action="create" id="sg_1">Inspect</subgoal>')

    assert decision.handled is True
    assert decision.continue_loop is True
    assert decision.reason == "plan_checkpoint_only"
    assert decision.plan_checkpoint_only is True
    assert "Plan updates were recorded" in (decision.next_query or "")
    assert agent.state.last_plan_subgoal_create_count == 1
    agent.ui.print_plan.assert_awaited_once_with("summary")
