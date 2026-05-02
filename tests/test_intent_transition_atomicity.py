from types import SimpleNamespace

import pytest

from modules.agent.orchestration.shared.decision_models import (
    ActionPolicyDecision,
    MemoryBoardDecision,
    PlanBoardDecision,
)
from modules.agent.orchestration.transitions import IntentTransitionHandler
from modules.agent.orchestration.parsers import IntentResponseParser
from modules.agent.orchestration.responses import ModelResponsePipeline
from modules.agent.state_manager import AgentState


class _Parser:
    def parse(self, response):
        return []


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
        self.reasons = []

    async def decide(self, parsed_output, *, malformed_action_retries, audit_marker_retries):
        self.calls += 1
        self.reasons.append(parsed_output.invalid_kind)
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


class _ActionPolicy:
    async def decide(self, ctx, segments, *, intent_payload):
        return ActionPolicyDecision.pass_through(
            reason="actions_allowed_to_proceed",
            source="action_policy",
            parsed_action_count=0,
        )


def _config():
    return SimpleNamespace(
        INTENT_RELABEL_SUSPICION_ENABLED=False,
        MEMORY_CHECKPOINT_ONLY_HARD_STOP_STREAK=4,
        REPEATED_THINKING_WITHOUT_VALID_OUTPUT_STREAK=2,
        INTENT_REUSE_EXTENSION_STEPS=4,
    )


def _activate_investigate(state):
    ok, msg = state.apply_intent_contract(
        {
            "intent_id": "improve_orchestration",
            "intent_type": "INVESTIGATE",
            "goal": "Determine how blocked intent transitions should work in orchestration runtime.",
            "allowed_actions": ["list_directory", "read_file_skeleton", "read_chunk", "search_content"],
            "safe_steps_limit": 4,
            "retry_limit": 2,
            "mode": "activate",
            "switch_reason": "user_requested_new_task",
        },
        _config(),
    )
    assert ok, msg


def _pipeline(state, *, output_recovery):
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
        prompt_builder=SimpleNamespace(
            build_plain_text_completion_prompt=lambda *args, **kwargs: "plain text completion",
            build_control_tag_leak_recovery_prompt=lambda: "control tag leak recovery",
            build_intent_required_prompt=lambda reason, *args, **kwargs: f"intent required: {reason}",
            build_reflection_repair_accepted_prompt=lambda: "reflection accepted",
            build_durable_state_repair_prompt=lambda *args, **kwargs: "durable repair",
            build_repeated_thinking_without_valid_output_prompt=lambda *args, **kwargs: "repeated thinking",
            build_leaked_system_result_recovery_prompt=lambda: "leaked system result",
            build_missing_action_or_answer_prompt=lambda: "missing action",
            build_multiple_actions_prompt=lambda: "multiple actions",
            build_conflicting_intent_transitions_prompt=lambda: "conflicting transitions",
        ),
        intent_transitions=IntentTransitionHandler(
            agent,
            SimpleNamespace(
                build_intent_transition_rejected_prompt=lambda reason, *args, **kwargs: f"rejected: {reason}",
                build_intent_accepted_without_followup_prompt=lambda active_goal="": f"accepted: {active_goal}",
                build_intent_completed_prompt=lambda: "intent completed",
                build_completion_with_action_not_allowed_prompt=lambda: "completion with action not allowed",
                build_followup_conflict_prompt=lambda reason: f"followup conflict: {reason}",
                build_reuse_only_transition_cannot_bundle_action_prompt=lambda blocked_action="": f"reuse only: {blocked_action}",
                build_transition_only_intent_cannot_bundle_action_prompt=lambda blocked_action="": f"transition only: {blocked_action}",
                build_intent_body_contains_action_prompt=lambda: "intent body contains action",
                build_invalid_intent_contract_prompt=lambda reason: f"invalid: {reason}",
                build_invalid_intent_resumable_available_prompt=lambda *args, **kwargs: "invalid resumable",
            ),
            SimpleNamespace(handle_defect_detector_stop=lambda stop_info: None),
        ),
        output_recovery=output_recovery,
        action_policy=_ActionPolicy(),
        plan_board_stage=_PlanBoardStage(),
        memory_board_stage=_MemoryBoardStage(),
    )


@pytest.mark.asyncio
async def test_conflicting_transition_does_not_mutate_active_intent():
    state = AgentState(_config())
    _activate_investigate(state)
    before_allowed = list(state.active_intent.allowed_actions)
    output_recovery = _OutputRecovery()
    pipeline = _pipeline(state, output_recovery=output_recovery)
    payload = {
        "intent_id": "save_analysis_doc",
        "intent_type": "MODIFY",
        "goal": "Save the analysis as a markdown file.",
        "allowed_actions": ["write_file_block"],
        "mode": "replace",
        "switch_reason": "save_requested",
    }
    response = (
        '<intent mode="replace">{"intent_id":"save_analysis_doc","intent_type":"MODIFY","goal":"Save the analysis as a markdown file.","allowed_actions":["write_file_block"],"mode":"replace","switch_reason":"save_requested"}</intent>\n'
        '<intent mode="replace">{"intent_id":"save_analysis_doc_2","intent_type":"MODIFY","goal":"Save a second file.","allowed_actions":["write_file_block"],"mode":"replace","switch_reason":"save_requested"}</intent>'
    )

    outcome = await pipeline.run_step(
        SimpleNamespace(state_machine=None, malformed_action_retries=0, audit_marker_retries=0, user_input="continue"),
        SimpleNamespace(response=response, intent_payload=payload, intent_error=None, model_stop_reason=""),
    )

    assert outcome.reason == "conflicting_intent_transitions"
    assert output_recovery.calls == 1
    assert state.active_intent.intent_id == "improve_orchestration"
    assert state.active_intent.intent_type == "INVESTIGATE"
    assert state.active_intent.allowed_actions == before_allowed


def test_rejected_transition_leaves_allowed_actions_unchanged():
    state = AgentState(_config())
    _activate_investigate(state)
    before_allowed = list(state.active_intent.allowed_actions)
    handler = IntentTransitionHandler(
        SimpleNamespace(state=state, config=_config(), log=None),
        SimpleNamespace(
            build_intent_transition_rejected_prompt=lambda reason, *args, **kwargs: f"rejected: {reason}",
            build_intent_accepted_without_followup_prompt=lambda active_goal="": f"accepted: {active_goal}",
            build_intent_completed_prompt=lambda: "intent completed",
            build_completion_with_action_not_allowed_prompt=lambda: "completion with action not allowed",
            build_followup_conflict_prompt=lambda reason: f"followup conflict: {reason}",
            build_reuse_only_transition_cannot_bundle_action_prompt=lambda blocked_action="": f"reuse only: {blocked_action}",
            build_transition_only_intent_cannot_bundle_action_prompt=lambda blocked_action="": f"transition only: {blocked_action}",
            build_intent_body_contains_action_prompt=lambda: "intent body contains action",
            build_invalid_intent_contract_prompt=lambda reason: f"invalid: {reason}",
            build_invalid_intent_resumable_available_prompt=lambda *args, **kwargs: "invalid resumable",
        ),
        SimpleNamespace(handle_defect_detector_stop=lambda stop_info: None),
    )

    decision = handler.apply_payload_decision(
        {
            "intent_id": "save_analysis_doc",
            "intent_type": "MODIFY",
            "goal": "Save the analysis as a markdown file.",
            "allowed_actions": ["write_file_block"],
            "mode": "replace",
        }
    )

    assert decision.applied is False
    assert decision.message == "intent_switch_reason_required"
    assert state.active_intent.allowed_actions == before_allowed
    assert decision.transition_info["transition"] == "rejected"
    assert decision.transition_info["transition_applied"] is False
    assert decision.transition_info["after_active_intent_id"] == "improve_orchestration"
