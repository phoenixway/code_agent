from types import SimpleNamespace

import pytest

from modules.agent.orchestration.decision_models import ParsedModelOutput
from modules.agent.orchestration.output_recovery import ModelOutputRecoveryHandler
from modules.agent.orchestration.parsing import IntentResponseParser
from modules.agent.orchestration.prompting import OrchestratorPromptBuilder


class _Agent:
    def __init__(self):
        self.state = SimpleNamespace(
            active_intent=SimpleNamespace(
                intent_id="inspect_pipeline",
                intent_type="INVESTIGATE",
                goal="Inspect the orchestration pipeline.",
            ),
            terminal_plaintext_completion_pending=False,
            terminal_plaintext_completion_text="",
            orchestration_trace=[],
            orchestration_trace_sequence=0,
            malformed_think_count=0,
            malformed_think_intent_id="",
            recovery_loop_handoff_count=0,
            recovery_loop_handoff_intent_id="",
            recovery_loop_handoff_defect_kind="",
            large_malformed_response_count=0,
            large_malformed_response_intent_id="",
            large_malformed_response_kind="",
        )
        self.config = SimpleNamespace(MALFORMED_ACTION_GRACE_STEPS=1)
        self.ui = SimpleNamespace()
        self.log = None


def _builder():
    return OrchestratorPromptBuilder(
        SimpleNamespace(
            state=SimpleNamespace(active_intent=None),
            config=SimpleNamespace(),
            planner=None,
            memory_board_store=None,
            log=None,
        )
    )


@pytest.mark.asyncio
async def test_recovery_says_close_think_before_tags():
    handler = ModelOutputRecoveryHandler(_Agent(), _builder())

    decision = await handler.decide(
        ParsedModelOutput(
            response=(
                "<think>\n"
                "I will inspect pipeline.\n"
                "<finding scope=\"intent\">fact</finding>\n"
                "<memory_update_done />\n"
                '<action>{"type":"read_file","path":"x.py"}</action>'
            ),
            invalid_kind="malformed_incomplete_think",
            has_action_tag=True,
            has_action_segment=False,
        ),
        malformed_action_retries=0,
        audit_marker_retries=0,
    )

    assert decision.reason == "malformed_incomplete_think"
    assert "closed with </think> before" in (decision.next_query or "")
    assert "Do not put protocol tags or actions inside <think>" in (decision.next_query or "")
    assert "Prefer omitting <think>" not in (decision.next_query or "")
    assert "! one verified state" not in (decision.next_query or "")
    assert "compact operational review" not in (decision.next_query or "")


@pytest.mark.asyncio
async def test_action_inside_think_recovery_preserves_reasoning_role():
    handler = ModelOutputRecoveryHandler(_Agent(), _builder())

    decision = await handler.decide(
        ParsedModelOutput(
            response='<think>\ndraft\n<action>{"type":"read_file","path":"x.py"}</action>\n</think>',
            invalid_kind="action_inside_think",
            has_action_tag=True,
            has_action_segment=False,
        ),
        malformed_action_retries=0,
        audit_marker_retries=0,
    )

    assert decision.reason == "action_inside_think"
    assert "<think> may contain draft reasoning" in (decision.next_query or "")
    assert "</think> before any memory tag" in (decision.next_query or "")
    assert "<action>" in (decision.next_query or "")


def test_long_closed_prose_think_is_valid():
    response = (
        "<think>\n"
        "Long prose plan.\n"
        "1. Read file.\n"
        "2. Compare architecture.\n"
        "3. Produce answer.\n"
        "</think>\n"
        "<memory_update_done />\n"
        '<action>{"type":"read_file","path":"x.py"}</action>'
    )
    parsed = IntentResponseParser().classify(
        response,
        [SimpleNamespace(type="action", content={"type": "read_file", "path": "x.py"})],
    )

    assert parsed.invalid_kind == ""


def test_strict_intent_only_recovery_still_says_no_think():
    prompt = _builder().build_formal_intent_required_for_multi_step_state_change_prompt(
        goal="Save orchestration analysis to docs."
    )

    assert "Return only one top-level <intent" in prompt
    assert "Do not include <think>" in prompt
