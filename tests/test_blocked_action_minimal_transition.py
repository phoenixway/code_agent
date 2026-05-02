from types import SimpleNamespace

import pytest

from modules.agent.orchestration.action_policy import ActionPolicyHandler
from modules.agent.orchestration.decision_models import (
    ActionPolicyDecision,
    MemoryBoardDecision,
    PlanBoardDecision,
)
from modules.agent.orchestration.intent_transitions import IntentTransitionHandler
from modules.agent.orchestration.parsing import IntentResponseParser
from modules.agent.orchestration.prompting import OrchestratorPromptBuilder
from modules.agent.orchestration.response_pipeline import ModelResponsePipeline


class _IntentGuard:
    def action_requires_intent(self, command, state, *, batch_size, current_user_input):
        return True, "intent_action_not_allowed"


class _PlanBoardStage:
    async def apply(self, ctx, response):
        return PlanBoardDecision.pass_through(
            reason="no_plan_updates",
            source="plan_board",
            response_text=response,
        )


class _MemoryBoardStage:
    async def apply(self, ctx, response):
        return MemoryBoardDecision.pass_through(
            reason="no_memory_updates",
            source="memory_board",
            response_text=response,
        )


class _OutputRecovery:
    def __init__(self):
        self.calls = 0

    async def decide(self, parsed_output, *, malformed_action_retries, audit_marker_retries):
        self.calls += 1
        return SimpleNamespace(
            handled=True,
            continue_loop=True,
            next_query=f"recovery::{parsed_output.invalid_kind}",
            stop_loop=False,
            malformed_action_retries=0,
            audit_marker_retries=0,
            reason=parsed_output.invalid_kind,
            source="output_recovery",
        )


class _ActionPolicyPass:
    def __init__(self):
        self.calls = 0

    async def decide(self, ctx, segments, *, intent_payload):
        self.calls += 1
        return ActionPolicyDecision.pass_through(
            reason="actions_allowed_to_proceed",
            source="action_policy",
            parsed_action_count=sum(1 for seg in segments if getattr(seg, "type", "") == "action"),
        )


class _Parser:
    def parse(self, response):
        text = str(response or "")
        segments = []
        if "<action" in text.lower():
            segments.append(SimpleNamespace(type="action", content={"type": "write_file_block", "path": "analysis.md"}))
        return segments


class _Transitions:
    def __init__(self, state):
        self.state = state
        self.calls = 0

    async def handle_model_step(self, *, intent_payload, intent_error, response_text, state_machine=None):
        self.calls += 1
        if not isinstance(intent_payload, dict):
            return SimpleNamespace(handled=False)
        self.state.active_intent = SimpleNamespace(
            intent_id=intent_payload.get("intent_id"),
            intent_type=intent_payload.get("intent_type"),
            goal=intent_payload.get("goal") or getattr(self.state.active_intent, "goal", ""),
            allowed_actions=list(intent_payload.get("allowed_actions") or []),
        )
        self.state.transition_only_intent_required = False
        self.state.transition_only_blocked_action = ""
        return SimpleNamespace(
            handled=True,
            next_query="accepted",
            reason="intent_accepted_without_followup",
        )


def _state():
    return SimpleNamespace(
        active_intent=SimpleNamespace(
            intent_id="improve_orchestration",
            intent_type="INVESTIGATE",
            goal="Investigate orchestration problems.",
            allowed_actions=["list_directory", "read_file_skeleton", "read_chunk", "search_content"],
        ),
        intent_required_until_activated=False,
        intent_required_reason="",
        reuse_only_intent_required=False,
        reuse_only_blocked_action="",
        transition_only_intent_required=False,
        transition_only_blocked_action="",
        disallowed_action_repeat_type="",
        disallowed_action_repeat_intent_id="",
        disallowed_action_repeat_count=0,
        last_blocked_action_type="",
        last_blocked_action_path="",
        last_memory_update_done=False,
        consecutive_memory_checkpoint_only_count=0,
        consecutive_nonproductive_thinking_count=0,
        think_reflection_repair_pending=False,
        think_reflection_repair_kind="",
        orchestration_trace_sequence=0,
        orchestration_trace=[],
        terminal_plaintext_completion_pending=False,
        terminal_plaintext_completion_text="",
        require_intent=lambda reason: None,
        has_hard_exhausted_active_intent=lambda: False,
        build_fix_mode_requires_intent=lambda: False,
    )


def _config():
    return SimpleNamespace(
        MEMORY_CHECKPOINT_ONLY_HARD_STOP_STREAK=4,
        REPEATED_THINKING_WITHOUT_VALID_OUTPUT_STREAK=2,
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


def _pipeline(state, *, transitions, output_recovery=None, action_policy=None):
    agent = SimpleNamespace(
        state=state,
        config=_config(),
        memory_board_engine=None,
        log=None,
        ui=SimpleNamespace(),
    )
    return ModelResponsePipeline(
        agent=agent,
        parser=_Parser(),
        intent_response_parser=IntentResponseParser(),
        prompt_builder=_builder(state),
        intent_transitions=transitions,
        output_recovery=output_recovery or _OutputRecovery(),
        action_policy=action_policy or _ActionPolicyPass(),
        plan_board_stage=_PlanBoardStage(),
        memory_board_stage=_MemoryBoardStage(),
    )


@pytest.mark.asyncio
async def test_blocked_write_file_block_prompts_minimal_transition():
    state = _state()
    handler = ActionPolicyHandler(
        SimpleNamespace(state=state, log=None),
        _IntentGuard(),
        _builder(state),
    )

    decision = await handler.decide(
        SimpleNamespace(user_input="save the analysis"),
        [SimpleNamespace(type="action", content={"type": "write_file_block", "path": "analysis.md"})],
        intent_payload=None,
    )

    assert decision.handled is True
    assert decision.reason == "intent_action_not_allowed"
    assert "This action is outside the current intent contract." in (decision.next_query or "")
    assert "return only a minimal intent transition" in (decision.next_query or "")
    assert "Do not include <think>" in (decision.next_query or "")
    assert 'mode="reuse"' in (decision.next_query or "")
    assert 'mode="replace"' in (decision.next_query or "")
    assert "retry `write_file_block`" not in (decision.next_query or "")


@pytest.mark.asyncio
async def test_valid_reuse_transition_after_blocked_action_is_accepted():
    state = _state()
    state.transition_only_intent_required = True
    state.transition_only_blocked_action = "write_file_block"
    transitions = _Transitions(state)
    output_recovery = _OutputRecovery()
    action_policy = _ActionPolicyPass()
    pipeline = _pipeline(state, transitions=transitions, output_recovery=output_recovery, action_policy=action_policy)

    payload = {
        "intent_id": "improve_orchestration",
        "intent_type": "MODIFY",
        "allowed_actions": ["list_directory", "read_file_skeleton", "read_chunk", "search_content", "write_file_block"],
        "mode": "reuse",
        "switch_reason": "save_requested",
    }

    outcome = await pipeline.run_step(
        SimpleNamespace(state_machine=None, malformed_action_retries=0, audit_marker_retries=0, user_input="continue"),
        SimpleNamespace(
            response='<intent mode="reuse">{"intent_id":"improve_orchestration","intent_type":"MODIFY","allowed_actions":["list_directory","read_file_skeleton","read_chunk","search_content","write_file_block"],"mode":"reuse","switch_reason":"save_requested"}</intent>',
            intent_payload=payload,
            intent_error=None,
            model_stop_reason="",
        ),
    )

    assert output_recovery.calls == 0
    assert action_policy.calls == 0
    assert outcome.reason == "intent_accepted_without_followup"
    assert state.active_intent.intent_id == "improve_orchestration"
    assert state.active_intent.intent_type == "MODIFY"
    assert "write_file_block" in state.active_intent.allowed_actions


@pytest.mark.asyncio
async def test_valid_replace_transition_after_blocked_action_is_accepted():
    state = _state()
    state.transition_only_intent_required = True
    state.transition_only_blocked_action = "write_file_block"
    transitions = _Transitions(state)
    output_recovery = _OutputRecovery()
    action_policy = _ActionPolicyPass()
    pipeline = _pipeline(state, transitions=transitions, output_recovery=output_recovery, action_policy=action_policy)
    payload = {
        "intent_id": "save_analysis_doc",
        "intent_type": "MODIFY",
        "goal": "Save orchestration analysis as markdown.",
        "allowed_actions": ["write_file_block"],
        "mode": "replace",
        "switch_reason": "save_requested",
    }

    outcome = await pipeline.run_step(
        SimpleNamespace(state_machine=None, malformed_action_retries=0, audit_marker_retries=0, user_input="continue"),
        SimpleNamespace(
            response='<intent mode="replace">{"intent_id":"save_analysis_doc","intent_type":"MODIFY","goal":"Save orchestration analysis as markdown.","allowed_actions":["write_file_block"],"mode":"replace","switch_reason":"save_requested"}</intent>',
            intent_payload=payload,
            intent_error=None,
            model_stop_reason="",
        ),
    )

    assert output_recovery.calls == 0
    assert action_policy.calls == 0
    assert outcome.reason == "intent_accepted_without_followup"
    assert state.active_intent.intent_id == "save_analysis_doc"
    assert state.active_intent.intent_type == "MODIFY"


@pytest.mark.asyncio
async def test_reuse_without_switch_reason_is_rejected_but_atomic():
    state = _state()
    before_id = state.active_intent.intent_id
    before_type = state.active_intent.intent_type
    state.intent_runtime = SimpleNamespace(
        last_apply_warning="",
        last_transition_info={"transition": "rejected", "transition_applied": False, "reason": "intent_switch_reason_required"},
    )
    state.apply_intent_contract = lambda payload, config: (False, "intent_switch_reason_required")

    class _Recovery:
        async def handle_defect_detector_stop(self, stop_info):
            return SimpleNamespace(handled=True, next_query=f"recovery::{stop_info['reason']}")

    handler = IntentTransitionHandler(
        SimpleNamespace(state=state, config=_config(), log=None),
        _builder(state),
        _Recovery(),
    )

    decision = await handler.handle_model_step(
        intent_payload={
            "intent_id": "improve_orchestration",
            "intent_type": "MODIFY",
            "allowed_actions": ["list_directory", "read_chunk", "write_file_block"],
            "mode": "reuse",
        },
        intent_error=None,
        response_text='<intent mode="reuse">{"intent_id":"improve_orchestration","intent_type":"MODIFY","allowed_actions":["list_directory","read_chunk","write_file_block"],"mode":"reuse"}</intent>',
        state_machine=None,
    )

    assert decision.handled is True
    assert decision.reason == "intent_switch_reason_required"
    assert state.active_intent.intent_id == before_id
    assert state.active_intent.intent_type == before_type


@pytest.mark.asyncio
async def test_transition_with_action_during_transition_only_recovery_is_rejected():
    state = _state()
    state.transition_only_intent_required = True
    state.transition_only_blocked_action = "write_file_block"
    handler = IntentTransitionHandler(
        SimpleNamespace(state=state, config=_config(), log=None),
        _builder(state),
        SimpleNamespace(handle_defect_detector_stop=lambda stop_info: None),
    )

    def _apply(payload, config):
        state.active_intent = SimpleNamespace(
            intent_id=payload.get("intent_id"),
            intent_type=payload.get("intent_type"),
            goal=payload.get("goal", state.active_intent.goal),
            allowed_actions=list(payload.get("allowed_actions") or []),
        )
        state.intent_runtime = SimpleNamespace(
            last_apply_warning="",
            last_transition_info={
                "transition": "intent_reused_with_step_refresh",
                "transition_applied": True,
            },
        )
        return True, "intent_reused_with_step_refresh"

    state.apply_intent_contract = _apply
    state.intent_runtime = SimpleNamespace(last_apply_warning="", last_transition_info={})

    decision = await handler.handle_model_step(
        intent_payload={
            "intent_id": "improve_orchestration",
            "intent_type": "MODIFY",
            "allowed_actions": ["list_directory", "read_file_skeleton", "read_chunk", "search_content", "write_file_block"],
            "mode": "reuse",
            "switch_reason": "save_requested",
        },
        intent_error=None,
        response_text=(
            '<intent mode="reuse">{"intent_id":"improve_orchestration","intent_type":"MODIFY","allowed_actions":["list_directory","read_file_skeleton","read_chunk","search_content","write_file_block"],"mode":"reuse","switch_reason":"save_requested"}</intent>\n'
            '<action>{"type":"write_file_block","path":"analysis.md"}</action>\n'
            "<file_content>hello</file_content>"
        ),
        state_machine=None,
    )

    assert decision.handled is True
    assert decision.reason == "transition_only_recovery_cannot_bundle_action"
