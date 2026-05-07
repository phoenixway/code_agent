from __future__ import annotations

from types import SimpleNamespace

import pytest

from modules.agent.orchestration.responses import ModelResponsePipeline


class DummyParsedOutput:
    def __init__(self, **kwargs):
        self.has_action_segment = False
        self.invalid_kind = ""
        self.visible_text = ""
        self.compiler_shape = ""
        self.compiler_error_code = ""
        self.compiler_ir = None
        self.response = ""
        self.__dict__.update(kwargs)


class LegacyPermissiveIntentResponseParser:
    def classify(self, response, segments, allow_think_autorepair=True):
        response_str = str(response or "")
        lower_response = response_str.lower()
        has_action = "<action" in lower_response

        if "unclosed_think_with_legacy_action" in lower_response:
            return DummyParsedOutput(
                response=response_str,
                has_action_segment=True,
                invalid_kind="",
            )

        if "i will now read the file" in lower_response and has_action:
            return DummyParsedOutput(
                response=response_str,
                has_action_segment=True,
                invalid_kind="mixed_visible_text_and_control_protocol",
                visible_text="I will now read the file.",
                compiler_shape="PRE_ACTION_TEXT_AND_ACTION",
                compiler_error_code="",
                compiler_ir=SimpleNamespace(
                    action_count=1,
                    has_action=True,
                    has_think=False,
                    has_checkpoint=False,
                    has_pre_action_text=True,
                    pre_action_text="I will now read the file.",
                    has_visible_answer=False,
                    action_ops=[SimpleNamespace(action_type="read_file", payload={"path": "x.py"})],
                ),
            )

        if '"type":"read_file","path":"a.py"' in lower_response and '"type":"read_file","path":"b.py"' in lower_response:
            return DummyParsedOutput(
                response=response_str,
                has_action_segment=True,
                invalid_kind="",
                compiler_shape="INVALID",
                compiler_error_code="E_ACTION_PAYLOAD_ARRAY",
            )

        if '<intent mode="complete">' in lower_response and "<action" in lower_response:
            return DummyParsedOutput(
                response=response_str,
                has_action_segment=True,
                invalid_kind="",
                compiler_shape="INVALID",
                compiler_error_code="E_INTENT_COMPLETE_WITH_ACTION",
            )

        if '"type":"write_file_block"' in lower_response and "file_content" not in lower_response:
            return DummyParsedOutput(
                response=response_str,
                has_action_segment=True,
                invalid_kind="",
                compiler_shape="INVALID",
                compiler_error_code="E_FILE_CONTENT_REQUIRES_ACTION",
            )

        if '"type":"read_file"' in lower_response and "file_content" in lower_response:
            return DummyParsedOutput(
                response=response_str,
                has_action_segment=True,
                invalid_kind="",
                compiler_shape="INVALID",
                compiler_error_code="E_FILE_CONTENT_ACTION_MISMATCH",
            )

        if "action_only_missing_checkpoint" in lower_response:
            return DummyParsedOutput(
                response=response_str,
                has_action_segment=True,
                invalid_kind="missing_memory_update_done",
                compiler_shape="ACTION_ONLY",
                compiler_error_code="",
                compiler_ir=SimpleNamespace(
                    action_count=1,
                    has_action=True,
                    has_think=False,
                    has_checkpoint=False,
                    has_pre_action_text=False,
                    pre_action_text="",
                    has_visible_answer=False,
                    action_ops=[SimpleNamespace(action_type="edit_file", payload={"path": "x.py"})],
                ),
            )

        return DummyParsedOutput(
            response=response_str,
            has_action_segment=has_action,
            invalid_kind="",
            visible_text="",
        )


class DummyParser:
    def parse(self, response):
        return [response] if response else []


class DummyIntentTransitions:
    async def handle_model_step(self, **kwargs):
        return SimpleNamespace(handled=False)


class CapturingOutputRecovery:
    def __init__(self):
        self.calls = []

    async def decide(self, parsed_output, *, malformed_action_retries, audit_marker_retries):
        self.calls.append(parsed_output)
        invalid_kind = getattr(parsed_output, "invalid_kind", "")

        if invalid_kind == "mixed_visible_text_and_control_protocol":
            compiler_shape = str(getattr(parsed_output, "compiler_shape", "") or "").strip()
            compiler_error_code = str(getattr(parsed_output, "compiler_error_code", "") or "").strip()
            ir = getattr(parsed_output, "compiler_ir", None)
            has_action = (ir and ir.action_count > 0) or getattr(parsed_output, "has_action_segment", False)
            if compiler_shape == "PRE_ACTION_TEXT_AND_ACTION" and not compiler_error_code and has_action:
                return SimpleNamespace(
                    handled=False,
                    continue_loop=False,
                    next_query=None,
                    stop_loop=False,
                    malformed_action_retries=0,
                    audit_marker_retries=0,
                    reason="",
                    source="",
                )

        if not invalid_kind:
            # Mimic real recovery logic by checking compiler error codes
            compiler_code = getattr(parsed_output, "compiler_error_code", "")
            if compiler_code == "E_ACTION_PAYLOAD_ARRAY":
                invalid_kind = "action_payload_array"
            elif compiler_code == "E_MIXED_VISIBLE_TEXT_AND_CONTROL":
                invalid_kind = "mixed_visible_text_and_control_protocol"
            elif compiler_code == "E_FILE_CONTENT_REQUIRES_ACTION":
                invalid_kind = "file_content_must_follow_action"

        if invalid_kind:
            return SimpleNamespace(
                handled=True,
                continue_loop=True,
                next_query=f"recover::{invalid_kind}",
                stop_loop=False,
                malformed_action_retries=0,
                audit_marker_retries=0,
                reason=invalid_kind,
                source="output_recovery",
            )
        return SimpleNamespace(
            handled=False,
            continue_loop=False,
            next_query=None,
            stop_loop=False,
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
            stop_loop=False,
            parsed_action_count=0,
            reason="",
            source="",
        )


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


def _pipeline(output_recovery):
    state = SimpleNamespace(
        active_intent=None,
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
        intent_response_parser=LegacyPermissiveIntentResponseParser(),
        prompt_builder=SimpleNamespace(
            build_intent_required_prompt=lambda reason: reason,
            build_plain_text_completion_prompt=lambda *args, **kwargs: "plain",
            build_reflection_repair_accepted_prompt=lambda: "accepted",
            build_durable_state_repair_prompt=lambda *args, **kwargs: "repair",
            build_repeated_thinking_without_valid_output_prompt=lambda *args, **kwargs: "thinking",
            build_missing_action_or_answer_prompt=lambda: "missing_action_or_answer",
            build_multiple_actions_prompt=lambda: "multiple_actions",
        ),
        intent_transitions=DummyIntentTransitions(),
        output_recovery=output_recovery,
        action_policy=DummyActionPolicy(),
        plan_board_stage=DummyPlanBoardStage(),
        memory_board_stage=DummyMemoryBoardStage(),
    )


@pytest.mark.asyncio
async def test_compiler_validates_pre_action_text_and_action_flow():
    """
    Tests that a response with text before an action is correctly identified
    as PRE_ACTION_TEXT_AND_ACTION and, despite legacy classification as an
    error, is allowed to proceed to dispatch due to compiler override.
    """
    recovery = CapturingOutputRecovery()
    pipeline = _pipeline(recovery)

    step = SimpleNamespace(
        response='I will now read the file.\n<action>{"type":"read_file","path":"x.py"}</action>',
        intent_payload=None,
        intent_error=None,
        model_stop_reason="",
    )
    outcome = await pipeline.run_step(
        SimpleNamespace(state_machine=None, malformed_action_retries=0, audit_marker_retries=0),
        step,
    )

    assert outcome.reason == "dispatch_ready"
    assert not outcome.continue_loop


@pytest.mark.asyncio
async def test_compiler_drives_action_array_recovery():
    recovery = CapturingOutputRecovery()
    pipeline = _pipeline(recovery)

    step = SimpleNamespace(
        response='<intent mode="activate">{"intent_id":"x","intent_type":"MODIFY","goal":"Save","allowed_actions":["write_file_block"],"mode":"activate","switch_reason":"user_requested_save"}</intent>\n'
        '<action>[{"type":"read_file","path":"a.py"},{"type":"read_file","path":"b.py"}]</action>',
        intent_payload=None,
        intent_error=None,
        model_stop_reason="",
    )
    outcome = await pipeline.run_step(
        SimpleNamespace(state_machine=None, malformed_action_retries=0, audit_marker_retries=0),
        step,
    )

    assert outcome.continue_loop is True
    assert outcome.reason == "action_payload_array"
    assert recovery.calls[-1].compiler_error_code == "E_ACTION_PAYLOAD_ARRAY"


@pytest.mark.asyncio
async def test_compiler_drives_missing_file_content_pairing_recovery():
    recovery = CapturingOutputRecovery()
    pipeline = _pipeline(recovery)

    step = SimpleNamespace(
        response='<intent mode="activate">{"intent_id":"x","intent_type":"MODIFY","goal":"Save","allowed_actions":["write_file_block"],"mode":"activate","switch_reason":"user_requested_save"}</intent>\n'
        '<action>{"type":"write_file_block","path":"docs/report.md"}</action>',
        intent_payload=None,
        intent_error=None,
        model_stop_reason="",
    )
    outcome = await pipeline.run_step(
        SimpleNamespace(state_machine=None, malformed_action_retries=0, audit_marker_retries=0),
        step,
    )

    assert outcome.reason == "file_content_must_follow_action"
    assert recovery.calls[-1].compiler_error_code == "E_FILE_CONTENT_REQUIRES_ACTION"


@pytest.mark.asyncio
async def test_compiler_drives_intent_complete_with_action_recovery():
    recovery = CapturingOutputRecovery()
    pipeline = _pipeline(recovery)

    step = SimpleNamespace(
        response='<intent mode="complete">{"intent_id":"x"}</intent>\n<action>{"type":"read_file","path":"a.py"}</action>',
        intent_payload=None,
        intent_error=None,
        model_stop_reason="",
    )
    outcome = await pipeline.run_step(
        SimpleNamespace(state_machine=None, malformed_action_retries=0, audit_marker_retries=0),
        step,
    )

    assert outcome.reason == "intent_complete_with_action_not_allowed"
    assert recovery.calls[-1].compiler_error_code == "E_INTENT_COMPLETE_WITH_ACTION"


@pytest.mark.asyncio
async def test_compiler_drives_file_content_mismatch_recovery():
    recovery = CapturingOutputRecovery()
    pipeline = _pipeline(recovery)

    step = SimpleNamespace(
        response='<action>{"type":"read_file","path":"a.py"}</action>\n<file_content>body</file_content>',
        intent_payload=None,
        intent_error=None,
        model_stop_reason="",
    )
    outcome = await pipeline.run_step(
        SimpleNamespace(state_machine=None, malformed_action_retries=0, audit_marker_retries=0),
        step,
    )

    assert outcome.reason == "file_content_must_follow_action"
    assert recovery.calls[-1].compiler_error_code == "E_FILE_CONTENT_ACTION_MISMATCH"


@pytest.mark.asyncio
async def test_action_only_with_legacy_invalid_kind_is_recovered():
    """
    Tests that an ACTION_ONLY shape with a legacy invalid_kind is not
    dispatched and instead goes to recovery, proving compiler shape alone
    does not grant authority.
    """
    recovery = CapturingOutputRecovery()
    pipeline = _pipeline(recovery)

    step = SimpleNamespace(
        response='<action>{"type":"edit_file","path":"x.py","comment":"action_only_missing_checkpoint"}</action>',
        intent_payload=None,
        intent_error=None,
        model_stop_reason="",
    )
    outcome = await pipeline.run_step(
        SimpleNamespace(state_machine=None, malformed_action_retries=0, audit_marker_retries=0),
        step,
    )

    assert outcome.continue_loop is True
    assert outcome.reason == "missing_memory_update_done"
    assert recovery.calls[-1].invalid_kind == "missing_memory_update_done"
    assert recovery.calls[-1].compiler_shape == "ACTION_ONLY"


@pytest.mark.asyncio
async def test_compiler_invalid_unclosed_think_blocks_legacy_action_dispatch():
    """
    Tests that a compiler-INVALID response is recovered even if legacy
    parsing detects an action, ensuring dispatch is blocked.
    """
    recovery = CapturingOutputRecovery()
    pipeline = _pipeline(recovery)

    step = SimpleNamespace(
        response='<think>\nDraft\n<action>{"type":"read_file","path":"x.py"}</action>\n<!-- unclosed_think_with_legacy_action -->',
        intent_payload=None,
        intent_error=None,
        model_stop_reason="",
    )
    outcome = await pipeline.run_step(
        SimpleNamespace(state_machine=None, malformed_action_retries=0, audit_marker_retries=0),
        step,
    )

    assert outcome.continue_loop is True
    assert outcome.reason == "action_inside_think"
    assert "recover::action_inside_think" in outcome.next_query

    assert len(recovery.calls) == 1
    parsed_output = recovery.calls[0]
    assert parsed_output.compiler_shape == "INVALID"
    assert parsed_output.compiler_error_code == "E_ACTION_INSIDE_THINK"
    assert parsed_output.invalid_kind == "action_inside_think"
    assert parsed_output.has_action_segment is True

    # Assert on the compiler-derived semantics snapshot
    snapshot = parsed_output.runtime_protocol_semantics
    assert snapshot is not None
    assert snapshot.shape == "INVALID"
    assert snapshot.error_code == "E_ACTION_INSIDE_THINK"
    assert snapshot.has_action is False
    assert snapshot.action_count == 0


