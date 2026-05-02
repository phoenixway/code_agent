import pytest
from types import SimpleNamespace

from modules.agent.orchestration.shared.decision_models import (
    ActionPolicyDecision,
    IntentHandlingDecision,
    MemoryBoardDecision,
    PlanBoardDecision,
)
from modules.agent.orchestration.parsers import IntentResponseParser
from modules.agent.orchestration.responses import ModelResponsePipeline


class DummySegment:
    def __init__(self, type_, content):
        self.type = type_
        self.content = content


class DummyParser:
    """Minimal parser for this regression test.

    The production parser may split response into richer segments. For this test
    we only need to prove that a text-only assistant response with a valid
    think/checkpoint envelope is accepted by ModelResponsePipeline.
    """

    def parse(self, response):
        return [
            DummySegment(
                "thought",
                "! User wants folder analysis. ? Need recommendations. → answer from available context.",
            ),
            DummySegment("text", "Добре, ось попередні рекомендації."),
        ]


class DummyIntentTransitions:
    async def handle_model_step(self, **kwargs):
        return IntentHandlingDecision.pass_through(reason="no_intent_transition")


class DummyPlanBoardStage:
    async def apply(self, ctx, response):
        return PlanBoardDecision.pass_through(
            reason="no_plan_updates",
            source="plan_board",
            response_text=response,
            plan_checkpoint_only=False,
            plan_checkpoint_and_text=False,
            plan_checkpoint_and_action=False,
        )


class DummyMemoryBoardStage:
    async def apply(self, ctx, response):
        # This mimics the real dump shape:
        # <memory_update_done /> is present, no accepted tags, visible text remains.
        return MemoryBoardDecision.pass_through(
            reason="memory_checkpoint_and_text",
            source="memory_board",
            response_text=response,
            memory_checkpoint_only=False,
            memory_checkpoint_and_text=True,
            memory_checkpoint_and_action=False,
        )


class DummyActionPolicy:
    async def decide(self, ctx, segments, *, intent_payload):
        return ActionPolicyDecision.pass_through(
            reason="no_action_gate_needed",
            source="action_policy",
            parsed_action_count=0,
        )


class DummyOutputRecovery:
    async def decide(self, parsed_output, *, malformed_action_retries, audit_marker_retries):
        raise AssertionError(
            "Output recovery must not be reached for valid marker-only text answer"
        )


class DummyPromptBuilder:
    def build_intent_required_prompt(self, *args, **kwargs):
        return "intent required"

    def build_plain_text_completion_prompt(self, *args, **kwargs):
        return "plain text required"

    def build_multiple_actions_prompt(self):
        return "multiple actions"

    def build_reflection_repair_accepted_prompt(self):
        return "reflection repair accepted"

    def build_durable_state_repair_prompt(self, *args, **kwargs):
        return "durable state repair"

    def build_repeated_thinking_without_valid_output_prompt(self, *args, **kwargs):
        return "repeated thinking"

    def build_leaked_system_result_recovery_prompt(self):
        return "leaked system result"


class DummyState:
    active_intent = None
    intent_required_until_activated = False
    last_memory_update_done = False
    consecutive_memory_checkpoint_only_count = 0
    consecutive_nonproductive_thinking_count = 0
    think_reflection_repair_pending = False
    think_reflection_repair_kind = ""
    terminal_plaintext_completion_pending = False
    terminal_plaintext_completion_text = ""
    orchestration_trace_sequence = 0
    orchestration_trace = []


class DummyAgent:
    def __init__(self):
        self.state = DummyState()
        self.config = SimpleNamespace(
            MEMORY_CHECKPOINT_ONLY_HARD_STOP_STREAK=4,
            REPEATED_THINKING_WITHOUT_VALID_OUTPUT_STREAK=2,
        )
        self.log = None
        self.memory_board_engine = None

        async def noop(*args, **kwargs):
            return None

        self.ui = SimpleNamespace(
            print_error=noop,
            print_system=noop,
        )


@pytest.mark.asyncio
async def test_marker_only_memory_update_done_text_answer_is_valid_checkpoint():
    """Regression for dump 2026-04-26 19:31.

    A response shaped as:
        <think>...</think>
        <memory_update_done />
        plain-text answer

    is protocol-valid when there are no memory/subgoal tags.

    Semantics:
    - bare <memory_update_done /> means implicit no-change review;
    - it does NOT mean board commit;
    - checkpoint is still satisfied because valid think + marker is enough.
    """

    response = (
        "<think>! User wants folder analysis. ? Need recommendations. "
        "→ answer from available context.</think>\n"
        "<memory_update_done />\n"
        "Добре, ось попередні рекомендації."
    )

    agent = DummyAgent()

    pipeline = ModelResponsePipeline(
        agent=agent,
        parser=DummyParser(),
        intent_response_parser=IntentResponseParser(),
        prompt_builder=DummyPromptBuilder(),
        intent_transitions=DummyIntentTransitions(),
        output_recovery=DummyOutputRecovery(),
        action_policy=DummyActionPolicy(),
        plan_board_stage=DummyPlanBoardStage(),
        memory_board_stage=DummyMemoryBoardStage(),
    )

    ctx = SimpleNamespace(
        state_machine=None,
        malformed_action_retries=0,
        audit_marker_retries=0,
        user_input="досліди папки root і modules. скажи як покращити агента",
    )
    step = SimpleNamespace(
        response=response,
        intent_payload=None,
        intent_error=None,
        model_stop_reason="",
    )

    outcome = await pipeline.run_step(ctx, step)

    # ResponsePipelineOutcome does not have proceed_to_dispatch.
    # dispatch_ready is represented by:
    # - handled=True
    # - continue_loop=False
    # - stop_loop=False
    # - segments populated
    assert outcome.handled is True
    assert outcome.continue_loop is False
    assert outcome.stop_loop is False

    assert outcome.parsed_action_count == 0
    assert outcome.memory_checkpoint_and_text is True
    assert outcome.memory_checkpoint_and_action is False
    assert outcome.memory_checkpoint_only is False

    assert outcome.segments
    assert [segment.type for segment in outcome.segments] == ["thought", "text"]

    parsed = outcome.parsed_output
    assert parsed is not None

    assert parsed.invalid_kind == ""
    assert parsed.invalid_kind != "truncated_internal_response"

    assert parsed.has_action_segment is False
    assert parsed.has_action_tag is False

    assert parsed.operational_checkpoint_has_think is True
    assert parsed.operational_checkpoint_has_marker is True

    # Important distinction:
    # no memory/subgoal tags were committed, so this must remain False.
    assert parsed.operational_checkpoint_has_tags is False
    assert parsed.operational_checkpoint_has_board_commit is False

    # But marker-only is a valid implicit no-change review.
    assert parsed.operational_checkpoint_satisfied is True


@pytest.mark.asyncio
async def test_unclosed_think_still_invalid_even_with_marker_and_text():
    """Negative control: do not make truly broken think valid."""

    response = (
        "<think>! User wants folder analysis. ? Need recommendations. "
        "→ answer from available context.\n"
        "<memory_update_done />\n"
        "Добре, ось попередні рекомендації."
    )

    parser = IntentResponseParser()
    segments = DummyParser().parse(response)
    parsed = parser.classify(response, segments)

    assert parsed.invalid_kind in {
        "malformed_incomplete_think",
        "truncated_internal_response",
    }

