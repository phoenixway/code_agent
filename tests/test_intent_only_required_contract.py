from types import SimpleNamespace

import pytest

from modules.agent.orchestration.decision_models import (
    ActionPolicyDecision,
    IntentHandlingDecision,
    MemoryBoardDecision,
    PlanBoardDecision,
)
from modules.agent.orchestration.intent_transitions import IntentTransitionHandler
from modules.agent.orchestration.prompting import OrchestratorPromptBuilder
from modules.agent.orchestration.response_pipeline import ModelResponsePipeline
from modules.agent.orchestration.parsing import IntentResponseParser


class DummyParser:
    def parse(self, response):
        text = str(response or "")
        segments = []
        if "<action" in text.lower():
            segments.append(SimpleNamespace(type="action", content={"type": "read_file", "path": "x.kt"}))
        return segments


class DummyPlanBoardStage:
    async def apply(self, ctx, response):
        return PlanBoardDecision.pass_through(
            reason="no_plan_updates",
            source="plan_board",
            response_text=response,
        )


class DummyMemoryBoardStage:
    async def apply(self, ctx, response):
        return MemoryBoardDecision.pass_through(
            reason="no_memory_updates",
            source="memory_board",
            response_text=response,
        )


class RecordingOutputRecovery:
    def __init__(self):
        self.calls = 0
        self.invalid_kinds = []

    async def decide(self, parsed_output, *, malformed_action_retries, audit_marker_retries):
        self.calls += 1
        self.invalid_kinds.append(parsed_output.invalid_kind)
        return SimpleNamespace(
            handled=True,
            continue_loop=True,
            next_query=f"recovery::{parsed_output.invalid_kind}",
            stop_loop=False,
            malformed_action_retries=malformed_action_retries,
            audit_marker_retries=audit_marker_retries,
            reason=parsed_output.invalid_kind,
            source="output_recovery",
        )


class RecordingActionPolicy:
    def __init__(self):
        self.calls = 0

    async def decide(self, ctx, segments, *, intent_payload):
        self.calls += 1
        return ActionPolicyDecision.pass_through(
            reason="actions_allowed_to_proceed",
            source="action_policy",
            parsed_action_count=sum(1 for seg in segments if getattr(seg, "type", "") == "action"),
        )


class RecordingIntentTransitions:
    def __init__(self, state):
        self.state = state
        self.calls = 0

    async def handle_model_step(self, *, intent_payload, intent_error, response_text, state_machine=None):
        self.calls += 1
        if isinstance(intent_payload, dict):
            self.state.active_intent = SimpleNamespace(
                intent_id=intent_payload.get("intent_id"),
                intent_type=intent_payload.get("intent_type"),
                goal=intent_payload.get("goal"),
                allowed_actions=list(intent_payload.get("allowed_actions") or []),
            )
            return IntentHandlingDecision(
                handled=True,
                next_query="intent accepted without followup",
                reason="intent_accepted_without_followup",
            )
        return IntentHandlingDecision(handled=False)


def _pipeline(state, *, output_recovery=None, action_policy=None, intent_transitions=None):
    agent = SimpleNamespace(
        state=state,
        config=SimpleNamespace(
            MEMORY_CHECKPOINT_ONLY_HARD_STOP_STREAK=4,
            REPEATED_THINKING_WITHOUT_VALID_OUTPUT_STREAK=2,
        ),
        memory_board_engine=None,
        log=None,
        ui=SimpleNamespace(),
    )
    return ModelResponsePipeline(
        agent=agent,
        parser=DummyParser(),
        intent_response_parser=IntentResponseParser(),
        prompt_builder=OrchestratorPromptBuilder(
            SimpleNamespace(
                state=state,
                config=agent.config,
                planner=None,
                memory_board_store=None,
                log=None,
            )
        ),
        intent_transitions=intent_transitions or RecordingIntentTransitions(state),
        output_recovery=output_recovery or RecordingOutputRecovery(),
        action_policy=action_policy or RecordingActionPolicy(),
        plan_board_stage=DummyPlanBoardStage(),
        memory_board_stage=DummyMemoryBoardStage(),
    )


def _ctx():
    return SimpleNamespace(state_machine=None, malformed_action_retries=0, audit_marker_retries=0, user_input="continue")


@pytest.mark.asyncio
async def test_activate_intent_only_is_valid_when_formal_intent_required():
    state = SimpleNamespace(
        active_intent=None,
        intent_required_until_activated=True,
        reuse_only_intent_required=False,
        intent_required_reason="formal_intent_required_for_multi_step_state_change",
        last_memory_update_done=False,
        consecutive_memory_checkpoint_only_count=0,
        consecutive_nonproductive_thinking_count=0,
        think_reflection_repair_pending=False,
        think_reflection_repair_kind="",
        orchestration_trace_sequence=0,
        orchestration_trace=[],
        terminal_plaintext_completion_pending=False,
        terminal_plaintext_completion_text="",
    )
    output_recovery = RecordingOutputRecovery()
    action_policy = RecordingActionPolicy()
    transitions = RecordingIntentTransitions(state)
    pipeline = _pipeline(
        state,
        output_recovery=output_recovery,
        action_policy=action_policy,
        intent_transitions=transitions,
    )
    payload = {
        "intent_id": "fix_ksp_build_error",
        "intent_type": "MODIFY",
        "goal": "Fix KSP/Room build failure after bookmark import/export changes.",
        "allowed_actions": ["read_file", "edit_file", "write_file_block"],
        "safe_steps_limit": 10,
        "retry_limit": 2,
        "mode": "activate",
    }
    response = (
        '<intent mode="activate">\n'
        "{\n"
        '  "intent_id": "fix_ksp_build_error",\n'
        '  "intent_type": "MODIFY",\n'
        '  "goal": "Fix KSP/Room build failure after bookmark import/export changes.",\n'
        '  "allowed_actions": ["read_file", "edit_file", "write_file_block"],\n'
        '  "safe_steps_limit": 10,\n'
        '  "retry_limit": 2,\n'
        '  "mode": "activate"\n'
        "}\n"
        "</intent>"
    )

    outcome = await pipeline.run_step(
        _ctx(),
        SimpleNamespace(response=response, intent_payload=payload, intent_error=None, model_stop_reason=""),
    )

    assert outcome.reason == "intent_accepted_without_followup"
    assert output_recovery.calls == 0
    assert transitions.calls == 1
    assert action_policy.calls == 0
    assert state.active_intent.intent_id == "fix_ksp_build_error"


@pytest.mark.asyncio
async def test_reuse_intent_only_is_valid_when_reuse_only_recovery_requested():
    state = SimpleNamespace(
        active_intent=SimpleNamespace(
            intent_id="bookmark_import_export",
            intent_type="MODIFY",
            goal="Add bookmark import/export UI and file handling.",
            allowed_actions=["read_file"],
        ),
        intent_required_until_activated=False,
        reuse_only_intent_required=True,
        intent_required_reason="",
        last_memory_update_done=False,
        consecutive_memory_checkpoint_only_count=0,
        consecutive_nonproductive_thinking_count=0,
        think_reflection_repair_pending=False,
        think_reflection_repair_kind="",
        orchestration_trace_sequence=0,
        orchestration_trace=[],
        terminal_plaintext_completion_pending=False,
        terminal_plaintext_completion_text="",
    )
    output_recovery = RecordingOutputRecovery()
    action_policy = RecordingActionPolicy()
    transitions = RecordingIntentTransitions(state)
    pipeline = _pipeline(
        state,
        output_recovery=output_recovery,
        action_policy=action_policy,
        intent_transitions=transitions,
    )
    payload = {
        "intent_id": "bookmark_import_export",
        "intent_type": "MODIFY",
        "goal": "Add bookmark import/export UI and file handling.",
        "allowed_actions": ["read_file", "edit_file", "write_file_block"],
        "requested_steps": 5,
        "mode": "reuse",
        "switch_reason": "work_type_changed",
        "switch_explanation": "Need write_file_block.",
    }
    response = (
        '<intent mode="reuse">\n'
        "{\n"
        '  "intent_id": "bookmark_import_export",\n'
        '  "intent_type": "MODIFY",\n'
        '  "goal": "Add bookmark import/export UI and file handling.",\n'
        '  "allowed_actions": ["read_file", "edit_file", "write_file_block"],\n'
        '  "requested_steps": 5,\n'
        '  "mode": "reuse",\n'
        '  "switch_reason": "work_type_changed",\n'
        '  "switch_explanation": "Need write_file_block."\n'
        "}\n"
        "</intent>"
    )

    outcome = await pipeline.run_step(
        _ctx(),
        SimpleNamespace(response=response, intent_payload=payload, intent_error=None, model_stop_reason=""),
    )

    assert outcome.reason == "intent_accepted_without_followup"
    assert output_recovery.calls == 0
    assert transitions.calls == 1
    assert action_policy.calls == 0


def test_intent_only_with_unclosed_think_remains_invalid():
    parsed = IntentResponseParser().classify(
        '<think>\nDraft text\n<intent mode="activate">\n{"intent_id":"x","intent_type":"MODIFY","goal":"Fix build","mode":"activate"}\n</intent>',
        [],
    )
    assert parsed.invalid_kind in {"malformed_incomplete_think", "intent_inside_think"}


@pytest.mark.asyncio
async def test_intent_activate_plus_action_still_works_for_ordinary_valid_bundle():
    state = SimpleNamespace(
        active_intent=None,
        intent_required_until_activated=False,
        reuse_only_intent_required=False,
        intent_required_reason="",
        last_memory_update_done=False,
        consecutive_memory_checkpoint_only_count=0,
        consecutive_nonproductive_thinking_count=0,
        think_reflection_repair_pending=False,
        think_reflection_repair_kind="",
        orchestration_trace_sequence=0,
        orchestration_trace=[],
        terminal_plaintext_completion_pending=False,
        terminal_plaintext_completion_text="",
    )
    output_recovery = RecordingOutputRecovery()
    transitions = RecordingIntentTransitions(state)
    pipeline = _pipeline(state, output_recovery=output_recovery, intent_transitions=transitions)
    payload = {
        "intent_id": "x",
        "intent_type": "MODIFY",
        "goal": "Inspect file.",
        "allowed_actions": ["read_file"],
        "mode": "activate",
    }
    response = (
        '<intent mode="activate">\n'
        '{\n  "intent_id": "x",\n  "intent_type": "MODIFY",\n  "goal": "Inspect file.",\n'
        '  "allowed_actions": ["read_file"],\n  "mode": "activate"\n}\n'
        "</intent>\n"
        "<memory_update_done />\n"
        '<action>{"type":"read_file","path":"x.kt"}</action>'
    )

    outcome = await pipeline._reject_invalid_intent_followup_before_transition(  # noqa: SLF001
        _ctx(),
        response,
        SimpleNamespace(response=response, intent_payload=payload, intent_error=None, model_stop_reason=""),
    )

    assert outcome is None
    assert output_recovery.calls == 0


@pytest.mark.asyncio
async def test_intent_only_activate_without_requirement_keeps_existing_policy():
    state = SimpleNamespace(
        active_intent=None,
        intent_required_until_activated=False,
        reuse_only_intent_required=False,
        intent_required_reason="",
        last_memory_update_done=False,
        consecutive_memory_checkpoint_only_count=0,
        consecutive_nonproductive_thinking_count=0,
        think_reflection_repair_pending=False,
        think_reflection_repair_kind="",
        orchestration_trace_sequence=0,
        orchestration_trace=[],
        terminal_plaintext_completion_pending=False,
        terminal_plaintext_completion_text="",
    )
    output_recovery = RecordingOutputRecovery()
    pipeline = _pipeline(state, output_recovery=output_recovery)
    payload = {
        "intent_id": "x",
        "intent_type": "MODIFY",
        "goal": "Inspect file.",
        "allowed_actions": ["read_file"],
        "mode": "activate",
    }
    response = '<intent mode="activate">{"intent_id":"x","intent_type":"MODIFY","goal":"Inspect file.","allowed_actions":["read_file"],"mode":"activate"}</intent>'

    outcome = await pipeline.run_step(
        _ctx(),
        SimpleNamespace(response=response, intent_payload=payload, intent_error=None, model_stop_reason=""),
    )

    assert outcome.reason == "intent_only_without_next_step"
    assert output_recovery.calls == 1
