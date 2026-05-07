from types import SimpleNamespace

import pytest

from modules.agent.orchestration.responses import ModelOutputRecoveryHandler
from modules.agent.orchestration.parsers import IntentResponseParser
from modules.agent.orchestration.prompts import OrchestratorPromptBuilder
from modules.agent.orchestration.responses import ModelResponsePipeline
from modules.agent.orchestration.shared.decision_models import ActionPolicyDecision, OutputRecoveryDecision
from modules.parser import ResponseParser


def test_visible_answer_before_action_is_classified_as_mixed_protocol():
    response = (
        "Для початку реалізації цього плану я б детально вивчив код.\n\n"
        '<action>{"type":"read_file_skeleton","path":"modules/agent/orchestration/response_pipeline.py"}</action>'
    )
    parser = IntentResponseParser()
    parsed = parser.classify(response, ResponseParser().parse(response))

    assert parsed.invalid_kind == "mixed_visible_text_and_control_protocol"


def test_visible_answer_before_think_and_action_is_classified_as_mixed_protocol():
    response = (
        "Рефактор я б почав із виділення фаз pipeline.\n\n"
        "<think>\nNeed exact file shape first.\n</think>\n"
        '<action>{"type":"read_file_skeleton","path":"modules/agent/orchestration/response_pipeline.py"}</action>'
    )
    parser = IntentResponseParser()
    parsed = parser.classify(response, ResponseParser().parse(response))

    assert parsed.invalid_kind == "mixed_visible_text_and_control_protocol"


def test_visible_answer_before_intent_is_classified_as_mixed_protocol():
    response = (
        "Ось план переходу.\n\n"
        '<intent mode="activate">{"intent_id":"x","intent_type":"MODIFY","goal":"Inspect pipeline.","allowed_actions":["read_file"],"mode":"activate"}</intent>'
    )
    parser = IntentResponseParser()
    parsed = parser.classify(response, [])

    assert parsed.invalid_kind == "mixed_visible_text_and_control_protocol"


def test_pure_plaintext_answer_is_not_mixed_protocol():
    response = "Ось як би я зробив цей рефактор без додаткових дій."
    parser = IntentResponseParser()
    parsed = parser.classify(response, ResponseParser().parse(response))

    assert parsed.invalid_kind == ""
    assert parsed.visible_text


@pytest.mark.asyncio
async def test_recovery_prompt_for_mixed_visible_text_and_control_protocol():
    agent = SimpleNamespace(
        state=SimpleNamespace(
            active_intent=None,
            malformed_think_intent_id="",
            malformed_think_count=0,
            missing_think_reflection_warning_count=0,
            missing_think_reflection_warning_intent_id="",
            architecture_defect_repeat_kind="",
            architecture_defect_repeat_count=0,
        ),
        config=SimpleNamespace(MALFORMED_ACTION_GRACE_STEPS=2),
        log=None,
    )
    builder = OrchestratorPromptBuilder(
        SimpleNamespace(state=agent.state, config=agent.config, planner=None, memory_board_store=None)
    )
    recovery = ModelOutputRecoveryHandler(agent, builder)
    parsed = SimpleNamespace(
        response="Answer\n<action>{}</action>",
        segments=[],
        has_action_segment=True,
        has_intent_segment=False,
        visible_text="Answer",
        invalid_kind="mixed_visible_text_and_control_protocol",
        operational_checkpoint_satisfied=False,
    )

    decision = await recovery.decide(parsed, malformed_action_retries=0, audit_marker_retries=0)

    assert decision.reason == "mixed_visible_text_and_control_protocol"
    assert "mixed a user-visible answer with internal protocol/tool use" in (decision.next_query or "")
    assert "Choose exactly one" in (decision.next_query or "")


class DummyIntentTransitions:
    async def handle_model_step(self, **kwargs):
        return SimpleNamespace(handled=False)


class DummyPlanBoardStage:
    async def apply(self, ctx, response):
        return SimpleNamespace(
            handled=False,
            response_text=response,
            plan_checkpoint_only=False,
            plan_checkpoint_and_text=False,
            plan_checkpoint_and_action=False,
        )


class DummyMemoryBoardStage:
    async def apply(self, ctx, response):
        return SimpleNamespace(
            handled=False,
            response_text=response,
            memory_checkpoint_only=False,
            memory_checkpoint_and_text=False,
            memory_checkpoint_and_action=False,
        )


class RecordingActionPolicy:
    def __init__(self):
        self.calls = 0

    async def decide(self, ctx, segments, *, intent_payload):
        self.calls += 1
        return ActionPolicyDecision.pass_through(
            reason="no_action_gate_needed",
            source="action_policy",
            parsed_action_count=0,
        )


class RecordingOutputRecovery:
    def __init__(self):
        self.calls = []

    async def decide(self, parsed_output, *, malformed_action_retries, audit_marker_retries):
        self.calls.append(parsed_output.invalid_kind)
        if parsed_output.invalid_kind:
            return OutputRecoveryDecision.continue_with(
                "recover mixed protocol",
                reason=parsed_output.invalid_kind,
                source="output_recovery",
                malformed_action_retries=0,
                audit_marker_retries=0,
            )
        return OutputRecoveryDecision.pass_through(
            reason="no_invalid_kind",
            source="output_recovery",
            malformed_action_retries=0,
            audit_marker_retries=0,
        )


class DummyPromptBuilder:
    def build_plain_text_completion_prompt(self, *args, **kwargs):
        return "plain text completion"

    def build_control_tag_leak_recovery_prompt(self):
        return "control tag leak recovery"

    def build_intent_required_prompt(self, reason):
        return reason

    def build_reflection_repair_accepted_prompt(self):
        return "reflection accepted"

    def build_durable_state_repair_prompt(self, *args, **kwargs):
        return "durable repair"

    def build_repeated_thinking_without_valid_output_prompt(self, *args, **kwargs):
        return "repeated thinking"

    def build_mixed_visible_text_and_control_protocol_prompt(self):
        return "mixed visible text and control protocol"

    def build_mixed_intent_transition_and_visible_answer_prompt(self):
        return "mixed intent transition and visible answer"


@pytest.mark.asyncio
async def test_mixed_visible_text_recovery_happens_before_action_policy():
    state = SimpleNamespace(
        active_intent=None,
        intent_required_until_activated=False,
        last_memory_update_done=False,
        orchestration_trace_sequence=0,
        orchestration_trace=[],
    )
    agent = SimpleNamespace(
        state=state,
        log=None,
        ui=SimpleNamespace(print_error=None),
        config=SimpleNamespace(
            MEMORY_CHECKPOINT_ONLY_HARD_STOP_STREAK=4,
            REPEATED_THINKING_WITHOUT_VALID_OUTPUT_STREAK=2,
        ),
    )
    output_recovery = RecordingOutputRecovery()
    action_policy = RecordingActionPolicy()
    pipeline = ModelResponsePipeline(
        agent,
        ResponseParser(),
        IntentResponseParser(),
        DummyPromptBuilder(),
        DummyIntentTransitions(),
        output_recovery,
        action_policy,
        DummyPlanBoardStage(),
        DummyMemoryBoardStage(),
    )
    ctx = SimpleNamespace(state_machine=None, malformed_action_retries=0, audit_marker_retries=0)
    step = SimpleNamespace(
        response=(
            "Ось як би я зробив цей рефактор.\n\n"
            "<think>\nNeed exact file first.\n</think>\n"
            '<action>{"type":"read_file_skeleton","path":"modules/agent/orchestration/response_pipeline.py"}</action>'
        ),
        intent_payload=None,
        intent_error=None,
        model_stop_reason="",
    )

    outcome = await pipeline.run_step(ctx, step)

    assert outcome.continue_loop is True
    assert outcome.reason == "mixed_visible_text_and_control_protocol"
    assert output_recovery.calls == ["mixed_visible_text_and_control_protocol"]
    assert action_policy.calls == 0


@pytest.mark.asyncio
async def test_visible_text_after_action_is_recovered():
    state = SimpleNamespace(
        active_intent=None,
        intent_required_until_activated=False,
        last_memory_update_done=False,
        orchestration_trace_sequence=0,
        orchestration_trace=[],
    )
    agent = SimpleNamespace(
        state=state,
        log=None,
        ui=SimpleNamespace(print_error=None),
        config=SimpleNamespace(
            MEMORY_CHECKPOINT_ONLY_HARD_STOP_STREAK=4,
            REPEATED_THINKING_WITHOUT_VALID_OUTPUT_STREAK=2,
        ),
    )
    output_recovery = RecordingOutputRecovery()
    action_policy = RecordingActionPolicy()
    pipeline = ModelResponsePipeline(
        agent,
        ResponseParser(),
        IntentResponseParser(),
        DummyPromptBuilder(),
        DummyIntentTransitions(),
        output_recovery,
        action_policy,
        DummyPlanBoardStage(),
        DummyMemoryBoardStage(),
    )
    ctx = SimpleNamespace(state_machine=None, malformed_action_retries=0, audit_marker_retries=0)
    step = SimpleNamespace(
        response='<action>{"type":"read_file_skeleton","path":"x.py"}</action>\nDone.',
        intent_payload=None,
        intent_error=None,
        model_stop_reason="",
    )

    outcome = await pipeline.run_step(ctx, step)

    assert outcome.continue_loop is True
    assert outcome.reason == "mixed_visible_text_and_control_protocol"
    assert output_recovery.calls == ["mixed_visible_text_and_control_protocol"]
    assert action_policy.calls == 0


@pytest.mark.asyncio
async def test_intent_followup_visible_text_is_not_treated_as_malformed_action():
    state = SimpleNamespace(
        active_intent=None,
        intent_required_until_activated=True,
        reuse_only_intent_required=False,
        transition_only_intent_required=False,
        last_memory_update_done=False,
        orchestration_trace_sequence=0,
        orchestration_trace=[],
    )
    agent = SimpleNamespace(
        state=state,
        log=None,
        ui=SimpleNamespace(print_error=None),
        config=SimpleNamespace(
            MEMORY_CHECKPOINT_ONLY_HARD_STOP_STREAK=4,
            REPEATED_THINKING_WITHOUT_VALID_OUTPUT_STREAK=2,
        ),
    )
    output_recovery = RecordingOutputRecovery()
    action_policy = RecordingActionPolicy()
    pipeline = ModelResponsePipeline(
        agent,
        ResponseParser(),
        IntentResponseParser(),
        DummyPromptBuilder(),
        DummyIntentTransitions(),
        output_recovery,
        action_policy,
        DummyPlanBoardStage(),
        DummyMemoryBoardStage(),
    )
    ctx = SimpleNamespace(state_machine=None, malformed_action_retries=0, audit_marker_retries=0)
    response = (
        "<think>\nReady to inspect the codebase.\n</think>\n"
        '<intent mode="activate">{"intent_id":"save_run_step_refactor_plan","intent_type":"MODIFY","goal":"Save run_step refactoring plan to docs.","allowed_actions":["write_file_block"],"mode":"activate"}</intent>\n'
        "Гаразд, я готовий розпочати аналіз і спочатку зберу правила.\n"
        "### 1. Поточний protocol\n"
    )
    step = SimpleNamespace(
        response=response,
        intent_payload={
            "intent_id": "save_run_step_refactor_plan",
            "intent_type": "MODIFY",
            "goal": "Save run_step refactoring plan to docs.",
            "allowed_actions": ["write_file_block"],
            "mode": "activate",
        },
        intent_error=None,
        model_stop_reason="",
    )

    outcome = await pipeline.run_step(ctx, step)

    assert outcome.continue_loop is True
    assert outcome.reason == "mixed_visible_text_and_control_protocol"
    assert output_recovery.calls == ["mixed_visible_text_and_control_protocol"]
    assert action_policy.calls == 0
    assert "malformed <action>" not in (outcome.next_query or "")
