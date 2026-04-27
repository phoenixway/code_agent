import pytest
from types import SimpleNamespace

from modules.agent.orchestration.decision_models import ParsedModelOutput
from modules.agent.orchestration.intent_transitions import IntentTransitionHandler
from modules.agent.orchestration.output_recovery import ModelOutputRecoveryHandler
from modules.agent.orchestration.parsing import IntentResponseParser


class DummySegment:
    def __init__(self, type_, content):
        self.type = type_
        self.content = content


class DummyState:
    def __init__(self, active_intent=None):
        self.active_intent = active_intent
        self.apply_called = False
        self.intent_required_until_activated = False
        self.intent_required_reason = ""
        self.required_reasons = []
        self.last_resumable_intent_id = ""
        self.last_resumable_intent_type = ""
        self.last_resumable_intent_goal = ""

    def require_intent(self, reason):
        self.intent_required_until_activated = True
        self.intent_required_reason = reason
        self.required_reasons.append(reason)


class DummyPromptBuilder:
    def build_intent_body_contains_action_prompt(self):
        return (
            "SYSTEM: Your last <intent> block contained an <action> wrapper inside the intent body.\n"
            "The body of <intent> must be exactly one JSON object.\n"
            "Do not put <action> inside <intent>."
        )

    def build_invalid_intent_contract_prompt(self, reason):
        return f"invalid intent: {reason}"

    def build_invalid_intent_resumable_available_prompt(self, *args, **kwargs):
        return "invalid intent resumable"

    def build_intent_completed_prompt(self):
        return "intent completed"


class DummyAgent:
    def __init__(self, active_intent=None):
        self.state = DummyState(active_intent=active_intent)
        self.config = SimpleNamespace()
        self.log = None


class DummyUI:
    async def print_error(self, *args, **kwargs):
        return None


def test_extract_intent_rejects_action_wrapper_inside_intent_body():
    parser = IntentResponseParser()

    response = (
        '<intent mode="complete">'
        '<action>{"intent_id":"deep_analysis","mode":"complete","completion_reason":"goal_completed"}</action>'
        '</intent>'
    )

    clean_text, payload, error = parser.extract_intent_update_and_strip(response)

    assert payload is None
    assert error == "intent_body_contains_action"
    assert "<action>" not in clean_text


def test_classify_labels_action_inside_intent_before_generic_malformed_action():
    parser = IntentResponseParser()

    response = (
        '<intent mode="replace">'
        '<action>{"intent_id":"refactor","mode":"replace","intent_type":"MODIFY"}</action>'
        '</intent>'
    )
    segments = [
        # Simulate a lower-level parser that managed to recover an action segment
        # from the nested action wrapper. The intent-body violation must still win.
        DummySegment("action", {"intent_id": "refactor", "mode": "replace", "intent_type": "MODIFY"}),
    ]

    parsed = parser.classify(response, segments)

    assert parsed.invalid_kind == "intent_body_contains_action"
    assert parsed.invalid_kind != "malformed_action"
    assert parsed.invalid_kind != "multiple_actions"


def test_valid_intent_json_may_contain_action_like_text_inside_string_value():
    parser = IntentResponseParser()

    response = (
        '<intent mode="complete">'
        '{"intent_id":"deep_analysis","mode":"complete",'
        '"completion_reason":"goal_completed",'
        '"completion_explanation":"The docs mention <action> only as literal text."}'
        '</intent>'
    )

    clean_text, payload, error = parser.extract_intent_update_and_strip(response)

    assert error is None
    assert payload is not None
    assert payload["mode"] == "complete"
    assert payload["intent_id"] == "deep_analysis"


@pytest.mark.asyncio
async def test_intent_transition_handles_intent_body_contains_action_without_applying_transition():
    agent = DummyAgent(active_intent=SimpleNamespace(intent_id="deep_analysis", intent_type="INVESTIGATE"))
    handler = IntentTransitionHandler(
        agent=agent,
        prompt_builder=DummyPromptBuilder(),
        recovery=SimpleNamespace(),
    )

    decision = await handler.handle_model_step(
        intent_payload=None,
        intent_error="intent_body_contains_action",
        response_text=(
            '<intent mode="complete">'
            '<action>{"intent_id":"deep_analysis","mode":"complete"}</action>'
            '</intent>'
        ),
        state_machine=None,
    )

    assert decision.handled is True
    assert decision.next_query
    assert decision.reason == "intent_body_contains_action"
    assert agent.state.apply_called is False
    assert "Do not put <action> inside <intent>" in decision.next_query
    # Active intent remains active; malformed transition must not half-commit.
    assert agent.state.active_intent is not None


@pytest.mark.asyncio
async def test_output_recovery_routes_intent_body_contains_action_to_specific_prompt():
    agent = DummyAgent(active_intent=SimpleNamespace(intent_id="deep_analysis", intent_type="INVESTIGATE"))
    agent.ui = DummyUI()
    recovery = ModelOutputRecoveryHandler(agent, DummyPromptBuilder())

    parsed = ParsedModelOutput(
        response='<intent mode="complete"><action>{"intent_id":"x","mode":"complete"}</action></intent>',
        segments=[],
        has_action_tag=True,
        has_action_segment=False,
        has_intent_segment=True,
        visible_text="",
        invalid_kind="intent_body_contains_action",
    )

    decision = await recovery.decide(parsed, malformed_action_retries=0, audit_marker_retries=0)

    assert decision.handled is True
    assert decision.continue_loop is True
    assert decision.reason == "intent_body_contains_action"
    assert "Do not put <action> inside <intent>" in decision.next_query
