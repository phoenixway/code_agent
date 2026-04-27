
import pytest
from types import SimpleNamespace

from modules.agent.orchestration.decision_models import (
    ActionPolicyDecision,
    IntentHandlingDecision,
    MemoryBoardDecision,
    OutputRecoveryDecision,
    PlanBoardDecision,
)
from modules.agent.orchestration.parsing import IntentResponseParser
from modules.agent.orchestration.response_pipeline import ModelResponsePipeline
from modules.agent.orchestration.visible_text import (
    extract_visible_text_for_user,
    terminal_plaintext_completion_status,
)


class DummySegment:
    def __init__(self, type_, content):
        self.type = type_
        self.content = content


class DummyParser:
    def parse(self, response):
        # Enough structure for this pipeline regression. The real intent payload
        # has already been extracted by the caller and is passed in step.intent_payload.
        visible = extract_visible_text_for_user(response)
        segments = []
        if "<think" in str(response).lower():
            segments.append(DummySegment("thought", "compact operational review"))
        if "<action" in str(response).lower():
            segments.append(DummySegment("action", {"type": "read_chunk", "path": "x.py"}))
        elif visible:
            segments.append(DummySegment("text", visible))
        return segments


class DummyPromptBuilder:
    def build_plain_text_completion_prompt(self, state_machine=None, stop_info=None):
        return (
            "SYSTEM: The final answer after intent completion was missing or looked truncated.\n"
            "Return only a complete concise plain-text final answer. Do not emit <intent> or <action>."
        )

    def build_intent_required_prompt(self, reason):
        return f"intent required: {reason}"

    def build_reflection_repair_accepted_prompt(self):
        return "reflection repair accepted"

    def build_durable_state_repair_prompt(self, *args, **kwargs):
        return "durable state repair"

    def build_repeated_thinking_without_valid_output_prompt(self, *args, **kwargs):
        return "repeated thinking"

    def build_leaked_system_result_recovery_prompt(self):
        return "leaked system result"

    def build_missing_action_or_answer_prompt(self):
        return "missing action or answer"

    def build_multiple_actions_prompt(self):
        return "multiple actions"


class DummyIntentTransitions:
    def __init__(self, state):
        self.state = state

    async def handle_model_step(self, *, intent_payload, intent_error, response_text, state_machine=None):
        if isinstance(intent_payload, dict) and str(intent_payload.get("mode") or "").lower() == "complete":
            self.state.intent_transition_called = True
            self.state.active_intent = None
            self.state.terminal_plaintext_completion_pending = True
            self.state.terminal_plaintext_completion_text = str(response_text or "").strip()
            return IntentHandlingDecision(handled=False, reason="intent_completed_with_plaintext_answer")
        return IntentHandlingDecision(handled=False)


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
            reason="memory_checkpoint_and_text",
            source="memory_board",
            response_text=response,
            memory_checkpoint_only=False,
            memory_checkpoint_and_text=True,
            memory_checkpoint_and_action=False,
        )


class DummyActionPolicy:
    async def decide(self, ctx, segments, *, intent_payload):
        action_count = sum(1 for seg in segments if getattr(seg, "type", "") == "action")
        return ActionPolicyDecision.pass_through(
            reason="no_action_gate_needed",
            source="action_policy",
            parsed_action_count=action_count,
        )


class DummyOutputRecovery:
    async def decide(self, parsed_output, *, malformed_action_retries, audit_marker_retries):
        return OutputRecoveryDecision.pass_through(reason="no_recovery", source="output_recovery")


class DummyState:
    def __init__(self):
        self.active_intent = SimpleNamespace(
            intent_id="save_plan",
            intent_type="MODIFY",
            goal="Save refactoring plan",
        )
        self.intent_transition_called = False
        self.terminal_plaintext_completion_pending = False
        self.terminal_plaintext_completion_text = ""

        self.intent_required_until_activated = False
        self.intent_required_reason = ""
        self.last_memory_update_done = False
        self.consecutive_memory_checkpoint_only_count = 0
        self.consecutive_nonproductive_thinking_count = 0
        self.think_reflection_repair_pending = False
        self.think_reflection_repair_kind = ""
        self.orchestration_trace_sequence = 0
        self.orchestration_trace = []


class DummyAgent:
    def __init__(self, state):
        self.state = state
        self.config = SimpleNamespace(
            MEMORY_CHECKPOINT_ONLY_HARD_STOP_STREAK=4,
            REPEATED_THINKING_WITHOUT_VALID_OUTPUT_STREAK=2,
        )
        self.memory_board_engine = None
        self.log = None
        self.ui = SimpleNamespace()


def make_pipeline(state):
    return ModelResponsePipeline(
        agent=DummyAgent(state),
        parser=DummyParser(),
        intent_response_parser=IntentResponseParser(),
        prompt_builder=DummyPromptBuilder(),
        intent_transitions=DummyIntentTransitions(state),
        output_recovery=DummyOutputRecovery(),
        action_policy=DummyActionPolicy(),
        plan_board_stage=DummyPlanBoardStage(),
        memory_board_stage=DummyMemoryBoardStage(),
    )


def completion_payload():
    return {
        "intent_id": "save_plan",
        "mode": "complete",
        "completion_reason": "goal_completed",
        "completion_explanation": "The plan was saved.",
    }


def completion_response(final_text):
    return (
        "<think>! The file was written. ? The user needs confirmation. → Complete and answer.</think>\n"
        "<progress scope=\"intent\">Saved docs/refactoring_plan.md.</progress>\n"
        "<memory_update_done />\n"
        "<intent mode=\"complete\">\n"
        "{\n"
        "  \"intent_id\": \"save_plan\",\n"
        "  \"mode\": \"complete\",\n"
        "  \"completion_reason\": \"goal_completed\"\n"
        "}\n"
        "</intent>\n"
        f"{final_text}"
    )


def test_terminal_plaintext_status_rejects_obvious_truncation_from_dump():
    ok, reason, visible = terminal_plaintext_completion_status(completion_response("Готово. Я"))

    assert ok is False
    assert reason in {
        "terminal_plaintext_too_short",
        "terminal_plaintext_too_few_words",
        "terminal_plaintext_dangling_word",
    }
    assert visible == "Готово. Я"


def test_terminal_plaintext_status_accepts_complete_short_confirmation():
    ok, reason, visible = terminal_plaintext_completion_status(
        completion_response("Готово. План збережено у `docs/refactoring_plan.md`.")
    )

    assert ok is True
    assert reason == ""
    assert visible == "Готово. План збережено у `docs/refactoring_plan.md`."


@pytest.mark.asyncio
async def test_complete_with_truncated_plaintext_is_rejected_before_intent_commit():
    state = DummyState()
    pipeline = make_pipeline(state)

    step = SimpleNamespace(
        response=completion_response("Готово. Я"),
        intent_payload=completion_payload(),
        intent_error=None,
        model_stop_reason="",
    )
    ctx = SimpleNamespace(
        state_machine=None,
        malformed_action_retries=0,
        audit_marker_retries=0,
        user_input="збережи це в файл",
    )

    outcome = await pipeline.run_step(ctx, step)

    assert outcome.handled is True
    assert outcome.continue_loop is True
    assert outcome.stop_loop is False
    assert outcome.reason == "truncated_terminal_plaintext_answer"
    assert outcome.source == "intent_completion_atomicity_guard"
    assert "final answer" in (outcome.next_query or "")

    # Atomicity: completion transition was not applied.
    assert state.intent_transition_called is False
    assert state.active_intent is not None
    assert state.terminal_plaintext_completion_pending is False
    assert state.terminal_plaintext_completion_text == ""


@pytest.mark.asyncio
async def test_complete_with_valid_plaintext_can_commit_and_dispatch_text():
    state = DummyState()
    pipeline = make_pipeline(state)

    step = SimpleNamespace(
        response=completion_response("Готово. План збережено у `docs/refactoring_plan.md`."),
        intent_payload=completion_payload(),
        intent_error=None,
        model_stop_reason="",
    )
    ctx = SimpleNamespace(
        state_machine=None,
        malformed_action_retries=0,
        audit_marker_retries=0,
        user_input="збережи це в файл",
    )

    outcome = await pipeline.run_step(ctx, step)

    assert state.intent_transition_called is True
    assert state.active_intent is None
    assert state.terminal_plaintext_completion_pending is True
    assert "docs/refactoring_plan.md" in state.terminal_plaintext_completion_text

    assert outcome.handled is True
    assert outcome.continue_loop is False
    assert outcome.stop_loop is False
    assert outcome.parsed_action_count == 0
    assert outcome.memory_checkpoint_and_text is True
