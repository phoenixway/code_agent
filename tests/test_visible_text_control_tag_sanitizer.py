from types import SimpleNamespace

import pytest

from modules.agent.orchestration.decision_models import ActionPolicyDecision, OutputRecoveryDecision
from modules.agent.orchestration.parsing import IntentResponseParser
from modules.agent.orchestration.response_pipeline import ModelResponsePipeline
from modules.agent.orchestration.visible_text import (
    extract_visible_text_for_user,
    terminal_plaintext_completion_status,
    visible_text_has_control_tag_leak,
)


class DummySegment:
    def __init__(self, seg_type, content):
        self.type = seg_type
        self.content = content


class DummyParser:
    def parse(self, response):
        response_text = str(response or "")
        segments = []
        if "<action" in response_text.lower():
            segments.append(DummySegment("action", {"type": "search_content", "pattern": "x"}))
        elif extract_visible_text_for_user(response_text):
            segments.append(DummySegment("text", extract_visible_text_for_user(response_text)))
        return segments


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

    def build_leaked_system_result_recovery_prompt(self):
        return "leaked system result"

    def build_missing_action_or_answer_prompt(self):
        return "missing action or answer"

    def build_multiple_actions_prompt(self):
        return "multiple actions"


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
            parsed_action_count=sum(1 for seg in segments if getattr(seg, "type", "") == "action"),
        )


class RecordingOutputRecovery:
    def __init__(self):
        self.calls = []

    async def decide(self, parsed_output, *, malformed_action_retries, audit_marker_retries):
        self.calls.append(parsed_output.invalid_kind)
        invalid_kind = str(parsed_output.invalid_kind or "").strip()
        if invalid_kind:
            return OutputRecoveryDecision.continue_with(
                f"RECOVER:{invalid_kind}",
                reason=invalid_kind,
                source="output_recovery",
                malformed_action_retries=malformed_action_retries,
                audit_marker_retries=audit_marker_retries,
            )
        return OutputRecoveryDecision.pass_through(
            reason="no_invalid_kind",
            source="output_recovery",
            malformed_action_retries=0,
            audit_marker_retries=0,
        )


def make_pipeline(*, action_policy=None, output_recovery=None):
    state = SimpleNamespace(
        active_intent=SimpleNamespace(intent_id="intent-x", intent_type="OBSERVE", force_plaintext_completion=False),
        intent_required_until_activated=False,
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
        prompt_builder=DummyPromptBuilder(),
        intent_transitions=DummyIntentTransitions(),
        output_recovery=output_recovery or RecordingOutputRecovery(),
        action_policy=action_policy or RecordingActionPolicy(),
        plan_board_stage=DummyPlanBoardStage(),
        memory_board_stage=DummyMemoryBoardStage(),
    )


def test_terminal_completion_strips_think_and_marker():
    response = (
        "<think>\n"
        "Long private draft plan.\n"
        "It can be prose and multiple lines.\n"
        "</think>\n"
        "<memory_update_done />\n"
        "Готово. Зміни внесено в `RecordingService.kt`.\n"
    )
    visible = extract_visible_text_for_user(response)
    assert visible == "Готово. Зміни внесено в `RecordingService.kt`."
    assert "<think" not in visible
    assert "<memory_update_done" not in visible


def test_terminal_completion_strips_intent_and_memory_tags():
    response = (
        "<think>private draft</think>\n"
        "<decision scope=\"intent\">Private decision.</decision>\n"
        "<intent mode=\"complete\">\n"
        '{"intent_id":"x","mode":"complete","completion_reason":"goal_completed"}\n'
        "</intent>\n"
        "<memory_update_done />\n"
        "Фінальна відповідь користувачу.\n"
    )
    assert extract_visible_text_for_user(response) == "Фінальна відповідь користувачу."


def test_raw_control_tags_remaining_after_sanitize_are_rejected():
    response = "Фінал </think> <memory_update_done />"
    ok, reason, visible = terminal_plaintext_completion_status(response)
    assert ok is False
    assert reason == "control_tag_leak_in_visible_text"
    assert visible == "Фінал"
    assert visible_text_has_control_tag_leak(response) is True


def test_long_prose_think_is_accepted_if_structurally_closed():
    response = (
        "<think>\n"
        "Long multi-paragraph draft reasoning with numbered list:\n"
        "1. inspect state\n"
        "2. decide next operation\n"
        "3. answer\n"
        "</think>\n"
        "<memory_update_done />\n"
        "<action>{\"type\":\"read_file\",\"path\":\"x.kt\"}</action>"
    )
    parsed = IntentResponseParser().classify(response, [DummySegment("action", {"type": "read_file", "path": "x.kt"})])
    assert parsed.invalid_kind == ""
    assert parsed.has_action_segment is True


@pytest.mark.asyncio
async def test_action_inside_unclosed_think_remains_invalid_and_recovers_before_action_policy():
    output_recovery = RecordingOutputRecovery()
    action_policy = RecordingActionPolicy()
    pipeline = make_pipeline(action_policy=action_policy, output_recovery=output_recovery)

    step = SimpleNamespace(
        response="<think>\nDraft text\n<action>{\"type\":\"read_file\",\"path\":\"x.kt\"}</action>\n",
        intent_payload=None,
        intent_error=None,
        model_stop_reason="",
    )
    ctx = SimpleNamespace(
        state_machine=None,
        malformed_action_retries=0,
        audit_marker_retries=0,
        user_input="inspect file",
    )

    outcome = await pipeline.run_step(ctx, step)

    assert outcome.continue_loop is False
    assert outcome.reason == "dispatch_ready"
    assert outcome.next_query is None
    assert output_recovery.calls == [""]
    assert action_policy.calls == 1


@pytest.mark.asyncio
async def test_structural_invalid_output_recovery_happens_before_action_policy():
    output_recovery = RecordingOutputRecovery()
    action_policy = RecordingActionPolicy()
    pipeline = make_pipeline(action_policy=action_policy, output_recovery=output_recovery)

    step = SimpleNamespace(
        response="<think>broken\n<action>{\"type\":\"search_content\",\"pattern\":\"x\"}</action>",
        intent_payload=None,
        intent_error=None,
        model_stop_reason="",
    )
    ctx = SimpleNamespace(
        state_machine=None,
        malformed_action_retries=0,
        audit_marker_retries=0,
        user_input="search",
    )

    outcome = await pipeline.run_step(ctx, step)

    assert outcome.continue_loop is False
    assert outcome.reason == "dispatch_ready"
    assert outcome.next_query is None
    assert outcome.reason != "intent_action_not_allowed"
    assert action_policy.calls == 1
