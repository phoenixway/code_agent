from types import SimpleNamespace

import pytest

from modules.agent.orchestration.parsers import IntentResponseParser
from modules.agent.orchestration.responses import ModelResponsePipeline
from modules.agent.orchestration.responses.response_pipeline_stages import CheckpointStageState
from modules.parser import ResponseParser


@pytest.mark.parametrize(
    ("name", "response", "allow_autorepair", "expect_repair", "expect_blocked_reason", "expect_invalid_kinds", "expect_tag"),
    [
        (
            "action_json_after_unclosed_think",
            '<think>\nDraft reasoning\n<action>{"type":"read_file","path":"x.py"}</action>',
            True,
            True,
            "",
            "",
            "action",
        ),
        (
            "canonical_memory_and_action_sequence",
            (
                "<think>\n"
                "I need one read first.\n"
                '<finding scope="intent">Need the pipeline implementation.</finding>\n'
                "<memory_update_done />\n"
                '<action>{"type":"read_file","path":"modules/agent/orchestration/pipeline.py"}</action>'
            ),
            True,
            True,
            "",
            "",
            "finding",
        ),
        (
            "prose_tag_mention",
            "<think>\nI may use <action> later if reading the file is necessary.",
            True,
            False,
            "",
            {"action_inside_think", "malformed_incomplete_think"},
            "",
        ),
        (
            "backtick_tag_mention",
            "<think>\nI may use `<action>` later if needed.",
            True,
            False,
            "",
            {"action_inside_think", "malformed_incomplete_think"},
            "",
        ),
        (
            "fenced_tag_mention",
            "<think>\n```xml\n<action>{\"type\":\"read_file\",\"path\":\"x.py\"}</action>\n```",
            True,
            False,
            "",
            {"malformed_incomplete_think"},
            "",
        ),
        (
            "textual_subgoal_mention",
            "<think>\nExample only: <subgoal action=\"mark_done\" id=\"sg_1\" /> should not be emitted yet.",
            True,
            False,
            "",
            {"memory_tag_inside_think", "malformed_incomplete_think"},
            "",
        ),
        (
            "incomplete_action_payload",
            '<think>\nDraft reasoning\n<action>{"type":"read_file","path":"x.py"}',
            True,
            False,
            "",
            {"action_inside_think", "malformed_incomplete_think"},
            "",
        ),
        (
            "intent_transition_stays_strict_invalid",
            '<think>\ndraft\n<intent mode="reuse">{"intent_id":"x","mode":"reuse"}</intent>',
            True,
            False,
            "",
            {"intent_inside_think", "malformed_incomplete_think"},
            "",
        ),
        (
            "atomicity_blocks_autorepair",
            '<think>\nDraft reasoning\n<action>{"type":"read_file","path":"x.py"}</action>',
            False,
            False,
            "intent_atomicity_guard",
            {"action_inside_think", "malformed_incomplete_think"},
            "",
        ),
    ],
)
def test_unclosed_think_normalization_matrix(
    name,
    response,
    allow_autorepair,
    expect_repair,
    expect_blocked_reason,
    expect_invalid_kinds,
    expect_tag,
):
    parser = IntentResponseParser()
    normalized = parser.normalize_model_response(
        response,
        allow_think_autorepair=allow_autorepair,
    )
    parsed = parser.classify(
        response,
        ResponseParser().parse(response) if expect_repair else [],
        allow_think_autorepair=allow_autorepair,
    )

    assert normalized.raw_response == response, name
    assert normalized.think_repair_applied is expect_repair, name
    assert normalized.repair_blocked_reason == expect_blocked_reason, name
    if isinstance(expect_invalid_kinds, set):
        assert parsed.invalid_kind in expect_invalid_kinds, name
    else:
        assert parsed.invalid_kind == expect_invalid_kinds, name
    assert parsed.auto_closed_think is expect_repair, name
    assert parsed.auto_closed_think_tag == expect_tag, name
    if expect_repair:
        assert normalized.normalized_response != response, name
        assert "</think>\n<" in normalized.normalized_response, name
        assert normalized.repairs_applied == ("auto_close_think",), name
        assert normalized.think_repair_confidence == "high", name
    else:
        assert normalized.repairs_applied == (), name


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


class DummyOutputRecovery:
    async def decide(self, parsed_output, *, malformed_action_retries, audit_marker_retries):
        return SimpleNamespace(
            handled=False,
            continue_loop=False,
            stop_loop=False,
            next_query=None,
            malformed_action_retries=0,
            audit_marker_retries=0,
            reason="",
            source="",
        )


class DummyActionPolicy:
    async def decide(self, ctx, segments, *, intent_payload):
        return SimpleNamespace(
            handled=False,
            continue_loop=False,
            next_query=None,
            parsed_action_count=sum(1 for seg in segments if getattr(seg, "type", "") == "action"),
            reason="",
            source="action_policy",
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


def _pipeline_state():
    return SimpleNamespace(
        active_intent=None,
        intent_required_until_activated=False,
        last_memory_update_done=False,
        orchestration_trace_sequence=0,
        orchestration_trace=[],
    )


def _make_pipeline():
    state = _pipeline_state()
    agent = SimpleNamespace(
        state=state,
        log=None,
        ui=SimpleNamespace(print_error=None),
        config=SimpleNamespace(
            MEMORY_CHECKPOINT_ONLY_HARD_STOP_STREAK=4,
            REPEATED_THINKING_WITHOUT_VALID_OUTPUT_STREAK=2,
        ),
    )
    return ModelResponsePipeline(
        agent,
        ResponseParser(),
        IntentResponseParser(),
        DummyPromptBuilder(),
        DummyIntentTransitions(),
        DummyOutputRecovery(),
        DummyActionPolicy(),
        DummyPlanBoardStage(),
        DummyMemoryBoardStage(),
    ), state


@pytest.mark.asyncio
async def test_normalization_stage_logs_think_repair_trace_fields():
    pipeline, state = _make_pipeline()
    ctx = SimpleNamespace(
        state_machine=None,
        malformed_action_retries=0,
        audit_marker_retries=0,
    )
    step = SimpleNamespace(
        response='<think>\nDraft reasoning\n<action>{"type":"read_file","path":"x.py"}</action>',
        intent_payload=None,
        intent_error=None,
        model_stop_reason="",
    )

    outcome = await pipeline.run_step(ctx, step)

    assert outcome.reason == "dispatch_ready"
    normalization_entries = [
        entry for entry in list(getattr(state, "orchestration_trace", []) or [])
        if getattr(entry, "stage", "") == "response_normalization"
    ]
    assert normalization_entries
    fields = next(
        entry.fields
        for entry in normalization_entries
        if entry.fields.get("source") == "run_step"
    )
    assert fields["think_repair_applied"] is True
    assert fields["think_repair_confidence"] == "high"
    assert fields["think_repair_tag"] == "action"
    assert fields["source"] == "run_step"


def test_classification_stage_repairs_unclosed_think_before_checkpoint_tail():
    pipeline, _state = _make_pipeline()
    response = (
        "<think>\n"
        "Goal: inspect files\n"
        "Evidence: need file list\n"
        "Next: run listing\n"
        "<memory_update_done />\n"
        '<action>{"type":"run_shell","command":"ls"}</action>'
    )
    step = SimpleNamespace(response=response, model_stop_reason="")
    checkpoint_state = CheckpointStageState(
        response=response,
        reflection_repair_pending=False,
        reflection_repair_kind="",
        plan_checkpoint_only=False,
        plan_checkpoint_and_text=False,
        plan_checkpoint_and_action=False,
        memory_checkpoint_only=False,
        memory_checkpoint_and_text=False,
        memory_checkpoint_and_action=False,
        memory_board_decision=None,
    )

    classified = pipeline._run_classification_stage(step, response, checkpoint_state)

    assert classified.response != response
    assert "</think>\n<memory_update_done />" in classified.response
    assert classified.parsed_output.auto_closed_think is True
    assert classified.parsed_output.compiler_error_code == ""
    assert classified.parsed_output.compiler_shape != "INVALID"
    assert classified.parsed_action_count == 1


def test_classification_stage_repairs_unclosed_think_before_board_tags_and_action():
    pipeline, _state = _make_pipeline()
    response = (
        "<think>\n"
        "Need to checkpoint and inspect.\n"
        '<subgoal action="mark_in_progress" id="sg_1" />\n'
        '<memory_review status="no_change" scope="intent" />\n'
        "<memory_update_done />\n"
        '<action>{"type":"read_file","path":"README.md"}</action>'
    )
    step = SimpleNamespace(response=response, model_stop_reason="")
    checkpoint_state = CheckpointStageState(
        response=response,
        reflection_repair_pending=False,
        reflection_repair_kind="",
        plan_checkpoint_only=False,
        plan_checkpoint_and_text=False,
        plan_checkpoint_and_action=False,
        memory_checkpoint_only=False,
        memory_checkpoint_and_text=False,
        memory_checkpoint_and_action=False,
        memory_board_decision=None,
    )

    classified = pipeline._run_classification_stage(step, response, checkpoint_state)

    assert classified.response != response
    assert '</think>\n<subgoal action="mark_in_progress" id="sg_1" />' in classified.response
    assert classified.parsed_output.auto_closed_think is True
    assert classified.parsed_output.compiler_error_code == ""
    assert classified.parsed_output.compiler_shape != "INVALID"
    assert classified.parsed_action_count == 1
