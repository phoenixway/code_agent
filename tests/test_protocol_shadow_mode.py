from __future__ import annotations

from types import SimpleNamespace

from modules.agent.orchestration.parsers import IntentResponseParser
from modules.agent.orchestration.responses import ModelResponsePipeline
from modules.agent.orchestration.shared.trace import snapshot_trace


class _Parser:
    def parse(self, _response):
        return []


class _PlanBoardStage:
    async def apply(self, ctx, response):
        return SimpleNamespace(handled=False, response_text=response, plan_checkpoint_only=False, plan_checkpoint_and_text=False, plan_checkpoint_and_action=False)


class _MemoryBoardStage:
    async def apply(self, ctx, response):
        return SimpleNamespace(
            handled=False,
            response_text=response,
            memory_checkpoint_only=False,
            memory_checkpoint_and_text=False,
            memory_checkpoint_and_action=False,
        )


class _IntentTransitions:
    async def handle_model_step(self, **kwargs):
        return SimpleNamespace(handled=False)


class _OutputRecovery:
    async def decide(self, parsed_output, *, malformed_action_retries, audit_marker_retries):
        return SimpleNamespace(
            handled=True,
            continue_loop=True,
            next_query=f"recover::{parsed_output.invalid_kind}",
            stop_loop=False,
            malformed_action_retries=0,
            audit_marker_retries=0,
            reason=parsed_output.invalid_kind,
            source="output_recovery",
        )


class _ActionPolicy:
    async def decide(self, ctx, segments, *, intent_payload):
        return SimpleNamespace(handled=False, continue_loop=False, next_query=None, parsed_action_count=0)


def _pipeline():
    state = SimpleNamespace(
        active_intent=None,
        last_memory_update_done=False,
        orchestration_trace_sequence=0,
        orchestration_trace=[],
        intent_required_until_activated=False,
        intent_required_reason="",
        think_reflection_repair_pending=False,
        think_reflection_repair_kind="",
    )
    agent = SimpleNamespace(
        state=state,
        config=SimpleNamespace(MEMORY_CHECKPOINT_ONLY_HARD_STOP_STREAK=4, REPEATED_THINKING_WITHOUT_VALID_OUTPUT_STREAK=2),
        memory_board_engine=None,
        log=None,
        ui=SimpleNamespace(),
    )
    return ModelResponsePipeline(
        agent=agent,
        parser=_Parser(),
        intent_response_parser=IntentResponseParser(),
        prompt_builder=SimpleNamespace(
            build_intent_required_prompt=lambda reason: reason,
            build_plain_text_completion_prompt=lambda *args, **kwargs: "plain",
            build_reflection_repair_accepted_prompt=lambda: "accepted",
            build_durable_state_repair_prompt=lambda *args, **kwargs: "repair",
            build_repeated_thinking_without_valid_output_prompt=lambda *args, **kwargs: "thinking",
        ),
        intent_transitions=_IntentTransitions(),
        output_recovery=_OutputRecovery(),
        action_policy=_ActionPolicy(),
        plan_board_stage=_PlanBoardStage(),
        memory_board_stage=_MemoryBoardStage(),
    )


def test_shadow_compiler_logs_disagreement_without_behavior_flip():
    pipeline = _pipeline()
    step = SimpleNamespace(
        response="Поясню спочатку.\n<action>{\"type\":\"read_file\",\"path\":\"x.py\"}</action>",
        intent_payload=None,
        intent_error=None,
        model_stop_reason="",
    )
    classified = pipeline._run_classification_stage(step, step.response, SimpleNamespace(
        response=step.response,
        reflection_repair_pending=False,
        reflection_repair_kind="",
        plan_checkpoint_only=False,
        plan_checkpoint_and_text=False,
        plan_checkpoint_and_action=False,
        memory_checkpoint_only=False,
        memory_checkpoint_and_text=False,
        memory_checkpoint_and_action=False,
        memory_board_decision=None,
    ))

    assert classified.parsed_output.invalid_kind == "mixed_visible_text_and_control_protocol"
    trace = snapshot_trace(pipeline.state)
    shadow_entries = [entry for entry in trace if entry["stage"] == "protocol_shadow"]
    assert shadow_entries
    assert shadow_entries[-1]["fields"]["compiler_shape"] == "INVALID"
