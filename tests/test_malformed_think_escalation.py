import pytest
from types import SimpleNamespace

from modules.agent.orchestration.shared.decision_models import ParsedModelOutput
from modules.agent.orchestration.responses import ModelOutputRecoveryHandler
from modules.agent.orchestration.prompts import OrchestratorPromptBuilder


class DummyUI:
    async def print_error(self, message):
        self.last_error = message


class DummyPromptBuilder:
    def build_incomplete_think_recovery_prompt(self):
        return "INCOMPLETE_THINK_RECOVERY"

    def build_malformed_verbose_or_nested_think_prompt(self):
        return "VERBOSE_THINK_RECOVERY"

    def build_exact_think_skeleton_prompt(self):
        return "EXACT_THINK_SKELETON"

    def build_strict_compact_think_prompt(self):
        return "STRICT_COMPACT_THINK"

    def build_malformed_think_limit_prompt(self):
        return "MALFORMED_THINK_LIMIT"

    def build_terminal_malformed_think_handoff_text(self, *, defect_kind=""):
        return f"TERMINAL_MALFORMED_THINK_HANDOFF:{defect_kind}"


class DummyState:
    def __init__(self):
        self.active_intent = SimpleNamespace(
            intent_id="intent-1",
            intent_type="MODIFY",
            goal="Fix malformed think escalation",
        )
        self.terminal_plaintext_completion_pending = False
        self.terminal_plaintext_completion_text = ""
        self.pending_finalize = []

    def mark_pending_forced_plaintext_completion_close(self, reason, source):
        self.pending_finalize.append((reason, source))


class DummyAgent:
    def __init__(self):
        self.state = DummyState()
        self.config = SimpleNamespace(MALFORMED_ACTION_GRACE_STEPS=1)
        self.ui = DummyUI()
        self.log = None


def _parsed(invalid_kind, response=None):
    return ParsedModelOutput(
        response=response
        or "<think>broken\n<subgoal action=\"mark_done\" id=\"sg_1\" />\n<action>{}</action>",
        invalid_kind=invalid_kind,
        has_action_tag=True,
        has_action_segment=False,
    )


@pytest.mark.asyncio
async def test_malformed_incomplete_think_escalates_to_handoff_on_third_repeat():
    agent = DummyAgent()
    handler = ModelOutputRecoveryHandler(agent, DummyPromptBuilder())

    first = await handler.decide(
        _parsed("malformed_incomplete_think"),
        malformed_action_retries=0,
        audit_marker_retries=0,
    )
    assert first.continue_loop is True
    assert first.stop_loop is False
    assert first.next_query == "INCOMPLETE_THINK_RECOVERY"
    assert agent.state.malformed_think_count == 1

    second = await handler.decide(
        _parsed("malformed_incomplete_think"),
        malformed_action_retries=0,
        audit_marker_retries=0,
    )
    assert second.continue_loop is True
    assert second.stop_loop is False
    assert second.next_query == "EXACT_THINK_SKELETON"
    assert agent.state.malformed_think_count == 2

    third = await handler.decide(
        _parsed("malformed_incomplete_think"),
        malformed_action_retries=0,
        audit_marker_retries=0,
    )
    assert third.continue_loop is False
    assert third.stop_loop is True
    assert third.reason == "terminal_malformed_think_handoff"
    assert third.source == "output_recovery"

    assert agent.state.terminal_plaintext_completion_pending is True
    assert agent.state.terminal_plaintext_completion_text == (
        "TERMINAL_MALFORMED_THINK_HANDOFF:malformed_incomplete_think"
    )
    assert agent.state.pending_finalize == [
        ("terminal_malformed_think_handoff", "output_recovery")
    ]
    assert agent.state.malformed_think_count == 0


@pytest.mark.asyncio
async def test_nested_think_escalates_to_handoff_on_third_repeat():
    agent = DummyAgent()
    handler = ModelOutputRecoveryHandler(agent, DummyPromptBuilder())

    first = await handler.decide(
        _parsed("nested_think"),
        malformed_action_retries=0,
        audit_marker_retries=0,
    )
    assert first.continue_loop is True
    assert first.next_query == "INCOMPLETE_THINK_RECOVERY"

    second = await handler.decide(
        _parsed("nested_think"),
        malformed_action_retries=0,
        audit_marker_retries=0,
    )
    assert second.continue_loop is True
    assert second.next_query == "EXACT_THINK_SKELETON"

    third = await handler.decide(
        _parsed("nested_think"),
        malformed_action_retries=0,
        audit_marker_retries=0,
    )
    assert third.stop_loop is True
    assert third.reason == "terminal_malformed_think_handoff"
    assert "nested_think" in agent.state.terminal_plaintext_completion_text


@pytest.mark.asyncio
async def test_valid_complete_think_clears_malformed_think_streak():
    agent = DummyAgent()
    agent.state.malformed_think_intent_id = "intent-1"
    agent.state.malformed_think_count = 2

    handler = ModelOutputRecoveryHandler(agent, DummyPromptBuilder())

    decision = await handler.decide(
        ParsedModelOutput(
            response=(
                "<think>! verified state\n? exact gap\n→ read file</think>\n"
                "<memory_update_done />\n"
                "<action>{\"type\":\"read_file\",\"path\":\"a.py\"}</action>"
            ),
            invalid_kind="",
            has_action_tag=True,
            has_action_segment=True,
        ),
        malformed_action_retries=0,
        audit_marker_retries=0,
    )

    assert decision.handled is False
    assert decision.reason == "no_invalid_kind"
    assert agent.state.malformed_think_count == 0
    assert agent.state.malformed_think_intent_id == ""


@pytest.mark.asyncio
async def test_compiler_unclosed_think_repeats_escalate_to_terminal_handoff():
    agent = DummyAgent()
    agent.state.active_intent.intent_type = "INVESTIGATE"
    prompt_builder = OrchestratorPromptBuilder(
        SimpleNamespace(
            state=agent.state,
            config=agent.config,
            memory_board_store=None,
            log=None,
        )
    )
    handler = ModelOutputRecoveryHandler(agent, prompt_builder)

    parsed_output = ParsedModelOutput(
        response="<think>\nDraft\n<action>{}</action>",
        invalid_kind="malformed_incomplete_think",
        compiler_error_code="E_UNCLOSED_THINK",
        compiler_recovery_id="unclosed_think",
        has_action_segment=True,
    )

    # First call
    first = await handler.decide(
        parsed_output,
        malformed_action_retries=0,
        audit_marker_retries=0,
    )
    assert first.handled is True
    assert first.reason == "malformed_incomplete_think"
    assert first.continue_loop is True
    assert first.stop_loop is False
    assert "opened <think> but placed protocol tags before closing it" in first.next_query
    assert "Return the corrected response from the beginning" in first.next_query
    assert "Do not use <think>" not in first.next_query
    assert getattr(agent.state, "malformed_think_count", 0) == 1

    # Second call
    second = await handler.decide(
        parsed_output,
        malformed_action_retries=0,
        audit_marker_retries=0,
    )
    assert second.handled is True
    assert second.reason == "malformed_incomplete_think"
    assert second.continue_loop is True
    assert second.stop_loop is False
    assert "Do not use <think>" in second.next_query
    assert "No internal analysis" in second.next_query
    assert "Return exactly one valid" in second.next_query
    assert getattr(agent.state, "malformed_think_count", 0) == 2

    # Third call
    third = await handler.decide(
        parsed_output,
        malformed_action_retries=0,
        audit_marker_retries=0,
    )
    assert third.handled is True
    assert third.reason == "terminal_malformed_think_handoff"
    assert third.stop_loop is True
    assert agent.state.terminal_plaintext_completion_pending is True
    assert "malformed_incomplete_think" in agent.state.terminal_plaintext_completion_text
    assert "Я зупиняю виконання" in agent.state.terminal_plaintext_completion_text
