import pytest
from types import SimpleNamespace

from modules.agent.orchestration.runtime.action_policy import ActionPolicyHandler
from modules.agent.orchestration.shared.decision_models import (
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
    def parse(self, response):
        raise AssertionError("Parser should not run when exhausted intent gate blocks <action> early")


class DummyIntentTransitions:
    async def handle_model_step(self, **kwargs):
        assert kwargs.get("intent_payload") is None
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
        return MemoryBoardDecision.pass_through(
            reason="no_memory_updates",
            source="memory_board",
            response_text=response,
            memory_checkpoint_only=False,
            memory_checkpoint_and_text=False,
            memory_checkpoint_and_action=False,
        )


class DummyOutputRecovery:
    async def decide(self, *args, **kwargs):
        raise AssertionError("Output recovery should not be reached by this gate test")


class DummyPromptBuilder:
    def build_intent_required_prompt(self, reason, *args, **kwargs):
        return f"INTENT REQUIRED: {reason}"

    def build_limit_aware_reuse_prompt(self, reason, allowed_actions=None, *, goal=None, requested_steps=None):
        return f"REUSE REQUIRED: {reason}; allowed={','.join(allowed_actions or [])}; goal={goal or ''}"


class DummyState:
    def __init__(self):
        self.active_intent = SimpleNamespace(
            intent_id="reuse_gate_intent",
            intent_type="INVESTIGATE",
            goal="Continue investigating the same failing runtime gate",
            allowed_actions=["read_file", "read_chunk"],
            step_count=10,
            safe_steps_limit=2,
        )
        self.intent_required_until_activated = True
        self.intent_required_reason = "exhausted_intent_requires_reuse_or_completion"

        self.last_memory_update_done = False
        self.consecutive_memory_checkpoint_only_count = 0
        self.consecutive_nonproductive_thinking_count = 0
        self.think_reflection_repair_pending = False
        self.think_reflection_repair_kind = ""
        self.terminal_plaintext_completion_pending = False
        self.terminal_plaintext_completion_text = ""
        self.orchestration_trace_sequence = 0
        self.orchestration_trace = []

    def require_intent(self, reason):
        self.intent_required_until_activated = True
        self.intent_required_reason = str(reason or "").strip()

    def has_hard_exhausted_active_intent(self):
        return True


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


def test_extract_intent_ignores_reuse_intent_nested_inside_action():
    parser = IntentResponseParser()
    response = (
        '<action>\n'
        '<intent mode="reuse">\n'
        '{"intent_id":"reuse_gate_intent","mode":"reuse","requested_steps":4}\n'
        '</intent>\n'
        '</action>'
    )

    clean_text, payload, error = parser.extract_intent_update_and_strip(response)

    assert payload is None
    assert error is None
    assert clean_text == response


def test_extract_intent_still_accepts_top_level_reuse_intent():
    parser = IntentResponseParser()
    response = (
        '<intent mode="reuse">\n'
        '{"intent_id":"reuse_gate_intent","mode":"reuse","requested_steps":4}\n'
        '</intent>'
    )

    clean_text, payload, error = parser.extract_intent_update_and_strip(response)

    assert error is None
    assert payload is not None
    assert payload["mode"] == "reuse"
    assert payload["intent_id"] == "reuse_gate_intent"
    assert clean_text == ""


@pytest.mark.asyncio
async def test_exhausted_intent_gate_blocks_action_after_malformed_reuse_inside_action():
    """Regression for the leak seen in dumps.

    A malformed reuse attempt shaped as:
        <action><intent mode="reuse">...</intent></action>

    must not be treated as an accepted reuse transition. The nested intent must
    remain ordinary malformed action text, and the exhausted-intent gate must keep
    normal actions forbidden.
    """

    raw_response = (
        '<think>! Intent exhausted. ? Need reuse. → request reuse.</think>\n'
        '<memory_update_done />\n'
        '<action>\n'
        '<intent mode="reuse">\n'
        '{"intent_id":"reuse_gate_intent","mode":"reuse","requested_steps":4}\n'
        '</intent>\n'
        '</action>'
    )

    intent_parser = IntentResponseParser()
    response_after_extract, intent_payload, intent_error = intent_parser.extract_intent_update_and_strip(raw_response)

    assert intent_payload is None
    assert intent_error is None
    assert "<action>" in response_after_extract
    assert "<intent" in response_after_extract

    agent = DummyAgent()
    pipeline = ModelResponsePipeline(
        agent=agent,
        parser=DummyParser(),
        intent_response_parser=intent_parser,
        prompt_builder=DummyPromptBuilder(),
        intent_transitions=DummyIntentTransitions(),
        output_recovery=DummyOutputRecovery(),
        action_policy=SimpleNamespace(),
        plan_board_stage=DummyPlanBoardStage(),
        memory_board_stage=DummyMemoryBoardStage(),
    )

    ctx = SimpleNamespace(
        state_machine=None,
        malformed_action_retries=0,
        audit_marker_retries=0,
        user_input="continue same investigation",
    )
    step = SimpleNamespace(
        response=response_after_extract,
        intent_payload=intent_payload,
        intent_error=intent_error,
        model_stop_reason="",
    )

    outcome = await pipeline.run_step(ctx, step)

    assert outcome.continue_loop is True
    assert outcome.stop_loop is False
    assert outcome.reason == "exhausted_intent_requires_reuse_or_completion"
    assert "INTENT REQUIRED: exhausted_intent_requires_reuse_or_completion" in outcome.next_query
    assert agent.state.intent_required_until_activated is True
    assert agent.state.intent_required_reason == "exhausted_intent_requires_reuse_or_completion"


@pytest.mark.asyncio
async def test_action_policy_blocks_normal_action_while_active_intent_is_hard_exhausted():
    agent = DummyAgent()
    handler = ActionPolicyHandler(
        agent=agent,
        intent_guard=SimpleNamespace(),
        prompt_builder=DummyPromptBuilder(),
    )

    segments = [
        DummySegment(
            "action",
            {
                "type": "read_file",
                "path": "modules/agent/orchestration/response_pipeline.py",
            },
        )
    ]

    decision = await handler.decide(
        SimpleNamespace(),
        segments,
        intent_payload=None,
    )

    assert decision.continue_loop is True
    assert decision.reason == "exhausted_intent_normal_action_blocked"
    assert "REUSE REQUIRED: exhausted_intent_requires_reuse_or_completion" in decision.next_query
    assert agent.state.intent_required_until_activated is True
    assert agent.state.intent_required_reason == "exhausted_intent_requires_reuse_or_completion"
