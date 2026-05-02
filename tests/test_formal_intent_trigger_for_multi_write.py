from types import SimpleNamespace

import pytest

from modules.agent.orchestration.action_policy import ActionPolicyHandler
from modules.agent.orchestration.decision_models import ActionPolicyDecision
from modules.agent.orchestration.prompting import OrchestratorPromptBuilder
from modules.agent.orchestration.policy import IntentGuard


class _Segment:
    def __init__(self, seg_type, content):
        self.type = seg_type
        self.content = content


class _Config:
    INTENTLESS_SHORT_MODE_MAX_STEPS = 2


def _state():
    state = SimpleNamespace(
        active_intent=None,
        intent_runtime=SimpleNamespace(
            intent_required_until_activated=False,
            intent_required_reason="",
            require_intent=lambda reason: setattr(state, "_intent_required_reason", reason),
        ),
        _intent_required_reason="",
        last_error_code="",
        last_error_recoverable=False,
        last_turn_had_failure=False,
        consecutive_same_error_count=0,
        readonly_steps_this_turn=0,
        intentless_state_changing_file_write_count=0,
        last_plan_subgoal_create_count=0,
        task_board=None,
        orchestration_trace=[],
        orchestration_trace_sequence=0,
        disallowed_action_repeat_type="",
        disallowed_action_repeat_intent_id="",
        disallowed_action_repeat_count=0,
        last_blocked_action_type="",
        last_blocked_action_path="",
        pending_edit_mismatch_path="",
        pending_edit_mismatch_intent_id="",
    )
    state.require_intent = lambda reason: setattr(state, "_intent_required_reason", reason)
    state.has_retry_context = lambda: False
    state.can_continue_current_intent_after_failure = lambda: False
    state.has_hard_exhausted_active_intent = lambda: False
    return state


def _handler(state):
    agent = SimpleNamespace(state=state, config=_Config(), log=None)
    prompt_builder = OrchestratorPromptBuilder(
        SimpleNamespace(state=state, config=_Config(), memory_board_store=None, log=None)
    )
    return ActionPolicyHandler(agent, IntentGuard(), prompt_builder)


@pytest.mark.asyncio
async def test_third_write_in_intentless_lineage_requires_formal_intent():
    state = _state()
    state.intentless_state_changing_file_write_count = 2
    handler = _handler(state)

    decision = await handler.decide(
        SimpleNamespace(user_input="Create a structured Kotlin lessons set as commented code examples."),
        [_Segment("action", {"type": "write_file_block", "path": "kotlin-lessons/src/L03.kt"})],
        intent_payload=None,
    )

    assert decision.handled is True
    assert decision.reason == "formal_intent_required_for_multi_step_state_change"
    assert '<intent mode="activate">' in (decision.next_query or "")
    assert '<action>{"type":' not in (decision.next_query or "")
    assert "Do not include <think>, <memory_update_done />, <action>, <file_content>, or final answer." in (
        decision.next_query or ""
    )


@pytest.mark.asyncio
async def test_many_subgoal_creates_plus_write_requires_formal_intent():
    state = _state()
    state.last_plan_subgoal_create_count = 3
    state.task_board = {
        "steps": [
            {"id": "sg_1", "title": "Lesson 1", "status": "in_progress"},
            {"id": "sg_2", "title": "Lesson 2", "status": "todo"},
            {"id": "sg_3", "title": "Lesson 3", "status": "todo"},
        ]
    }
    handler = _handler(state)

    decision = await handler.decide(
        SimpleNamespace(user_input="Generate Kotlin lessons."),
        [_Segment("action", {"type": "write_file_block", "path": "kotlin-lessons/src/L01.kt", "overwrite": True})],
        intent_payload=None,
    )

    assert decision.handled is True
    assert decision.reason == "formal_intent_required_for_multi_step_state_change"
    assert '<intent mode="activate">' in (decision.next_query or "")


@pytest.mark.asyncio
async def test_one_off_markdown_save_remains_intentless_valid():
    state = _state()
    handler = _handler(state)

    decision = await handler.decide(
        SimpleNamespace(user_input="Save these notes to a markdown file."),
        [_Segment("action", {"type": "write_file_block", "path": "notes.md", "overwrite": True})],
        intent_payload=None,
    )

    assert decision.handled is False
    assert decision.reason == "actions_allowed_to_proceed"


@pytest.mark.asyncio
async def test_read_only_batch_does_not_require_formal_intent():
    state = _state()
    handler = _handler(state)

    decision = await handler.decide(
        SimpleNamespace(user_input="Inspect two files."),
        [
            _Segment("action", {"type": "read_file", "path": "A.kt"}),
            _Segment("action", {"type": "read_file", "path": "B.kt"}),
        ],
        intent_payload=None,
    )

    assert decision.reason != "formal_intent_required_for_multi_step_state_change"


@pytest.mark.asyncio
async def test_plain_answer_does_not_require_formal_intent():
    state = _state()
    handler = _handler(state)

    decision = await handler.decide(
        SimpleNamespace(user_input="Outline the lesson plan."),
        [],
        intent_payload=None,
    )

    assert decision.handled is False
    assert decision.reason == "no_action_gate_needed"
