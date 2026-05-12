from types import SimpleNamespace

import pytest

from modules.agent.orchestration.parsers import IntentResponseParser
from modules.agent.orchestration.responses import ModelResponsePipeline
from modules.agent.orchestration.responses.response_pipeline_stages import CheckpointStageState
from modules.parser import ResponseParser


@pytest.mark.parametrize(
    ("name", "response", "allow_autorepair", "expect_repair", "expect_blocked_reason", "expect_invalid_kind"),
    [
        (
            "action_json_after_unclosed_think_is_repaired_and_valid",
            '<think>\nDraft reasoning\n<action>{"type":"read_file","path":"x.py"}</action>',
            True,
            True,
            "",
            "",
        ),
        (
            "canonical_memory_and_action_sequence_is_repaired_and_valid",
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
        ),
        (
            "prose_tag_mention_is_repaired_at_eof_and_still_invalid",
            "<think>\nI may use <action> later if reading the file is necessary.",
            True,
            True,
            "",
            "malformed_incomplete_action",
        ),
        (
            "backtick_tag_mention_is_repaired_at_eof_and_valid",
            "<think>\nI may use `<action>` later if needed.",
            True,
            True,
            "",
            "malformed_action",
        ),
        (
            "fenced_tag_mention_is_repaired_at_eof_and_valid",
            "<think>\n```xml\n<action>{\"type\":\"read_file\",\"path\":\"x.py\"}</action>\n```",
            True,
            True,
            "",
            "malformed_action",
        ),
        (
            "textual_subgoal_mention_is_repaired_at_eof_and_valid",
            "<think>\nExample only: <subgoal action=\"mark_done\" id=\"sg_1\" /> should not be emitted yet.",
            True,
            True,
            "",
            "",
        ),
        (
            "incomplete_action_payload_is_repaired_and_then_malformed",
            '<think>\nDraft reasoning\n<action>{"type":"read_file","path":"x.py"}',
            True,
            True,
            "",
            "malformed_incomplete_action",
        ),
        (
            "intent_transition_is_repaired_and_valid",
            '<think>\ndraft\n<intent mode="reuse">{"intent_id":"x","mode":"reuse"}</intent>',
            True,
            True,
            "",
            "",
        ),
        (
            "atomicity_blocks_autorepair",
            '<think>\nDraft reasoning\n<action>{"type":"read_file","path":"x.py"}</action>',
            False,
            True,
            "intent_atomicity_guard",
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
    expect_invalid_kind,
):
    pipeline, _ = _make_pipeline()
    normalized = pipeline._normalize_response_stage(response, allow_autorepair=allow_autorepair, source="test")
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
    parsed = classified.parsed_output

    assert normalized.raw_response == response, name
    assert normalized.think_repair_applied is expect_repair, name
    assert normalized.repair_blocked_reason == expect_blocked_reason, name
    if name == "atomicity_blocks_autorepair":
        assert normalized.think_repair_blocked_by_atomicity is True
    assert parsed.invalid_kind == expect_invalid_kind, name

    if expect_repair:
        assert normalized.normalized_response != response, name
        assert "auto_close_think_boundary" in normalized.repairs_applied, name
    else:
        assert not any(r.startswith("auto_close_think") for r in normalized.repairs_applied), name


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
    assert fields["think_repair_reason"] == "auto_close_think_boundary"
    assert "auto_close_think_boundary" in fields["repairs_applied"]
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
    assert "</think><memory_update_done />" in classified.response
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
    assert '</think><subgoal action="mark_in_progress" id="sg_1" />' in classified.response
    assert classified.parsed_output.auto_closed_think is True
    assert classified.parsed_output.compiler_error_code == ""
    assert classified.parsed_output.compiler_shape != "INVALID"
    assert classified.parsed_action_count == 1
