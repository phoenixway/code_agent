from __future__ import annotations

from types import SimpleNamespace

import pytest

from modules.agent.orchestration.responses import ModelOutputRecoveryHandler
from modules.agent.orchestration.shared.decision_models import ParsedModelOutput


class DummyUI:
    async def print_error(self, message):
        self.last_error = message


class DummyPromptBuilder:
    def build_action_payload_array_prompt(self):
        return "ARRAY PROMPT"

    def build_multiple_actions_prompt(self):
        return "MULTIPLE PROMPT"

    def build_mixed_visible_text_and_control_protocol_prompt(self):
        return "MIXED PROMPT"

    def build_terminal_recovery_loop_handoff_text(self, *, defect_kind="", blocked_action="", path_or_action=""):
        return f"TERMINAL:{defect_kind}:{blocked_action}:{path_or_action}"


class DummyState:
    def __init__(self):
        self.active_intent = SimpleNamespace(intent_id="intent-1", intent_type="MODIFY", goal="Save output")
        self.last_completed_intent_type = ""
        self.state_machine = None
        self.last_blocked_action_type = ""
        self.last_blocked_action_path = ""
        self.missing_think_reflection_warning_count = 0
        self.missing_think_reflection_warning_intent_id = ""
        self.architecture_defect_repeat_kind = ""
        self.architecture_defect_repeat_count = 0
        self.malformed_think_intent_id = ""
        self.malformed_think_count = 0
        self.recovery_loop_handoff_intent_id = ""
        self.recovery_loop_handoff_count = 0
        self.recovery_loop_handoff_defect_kind = ""
        self.large_malformed_response_intent_id = ""
        self.large_malformed_response_count = 0
        self.large_malformed_response_kind = ""
        self.think_reflection_repair_pending = False
        self.think_reflection_repair_kind = ""
        self.terminal_plaintext_completion_pending = False
        self.terminal_plaintext_completion_text = ""
        self.compiler_recovery_fingerprint = ""
        self.compiler_recovery_fingerprint_count = 0
        self.pending_finalize = []

    def get_stop_reason_count(self, reason):
        return 0

    def mark_pending_forced_plaintext_completion_close(self, reason, source):
        self.pending_finalize.append((reason, source))


class DummyAgent:
    def __init__(self):
        self.state = DummyState()
        self.config = SimpleNamespace(MALFORMED_ACTION_GRACE_STEPS=1)
        self.ui = DummyUI()
        self.log = None


def _parsed_array():
    return ParsedModelOutput(
        response='<action>[{"type":"read_file","path":"a.py"},{"type":"read_file","path":"b.py"}]</action>',
        invalid_kind="",
        compiler_error_code="E_ATOMIC_BUNDLE_REQUIRES_EXACTLY_ONE_ACTION",
        compiler_recovery_id="atomic_bundle_exactly_one_action",
    )


def _parsed_multiple():
    return ParsedModelOutput(
        response='<action>{"type":"read_file","path":"a.py"}</action>\n<action>{"type":"read_file","path":"b.py"}</action>',
        invalid_kind="",
        compiler_error_code="E_ATOMIC_BUNDLE_REQUIRES_EXACTLY_ONE_ACTION",
        compiler_recovery_id="atomic_bundle_exactly_one_action",
    )


def _parsed_mixed():
    return ParsedModelOutput(
        response='Поясню.\n<action>{"type":"read_file","path":"x.py"}</action>',
        invalid_kind="",
        compiler_error_code="E_MIXED_VISIBLE_TEXT_AND_CONTROL",
        compiler_recovery_id="mixed_visible_control",
    )


@pytest.mark.asyncio
async def test_action_array_escalates_to_intent_only_on_second_repeat():
    handler = ModelOutputRecoveryHandler(DummyAgent(), DummyPromptBuilder())

    first = await handler.decide(_parsed_array(), malformed_action_retries=0, audit_marker_retries=0)
    second = await handler.decide(_parsed_array(), malformed_action_retries=0, audit_marker_retries=0)

    assert first.next_query == "ARRAY PROMPT"
    assert second.reason == "action_payload_array"
    assert "Return only one valid <intent mode=\"activate\">...</intent> block now." in (second.next_query or "")
    assert "Do not include <action>, <file_content>, visible text, or multiple blocks." in (second.next_query or "")


@pytest.mark.asyncio
async def test_multiple_actions_escalates_to_intent_only_on_second_repeat():
    handler = ModelOutputRecoveryHandler(DummyAgent(), DummyPromptBuilder())

    first = await handler.decide(_parsed_multiple(), malformed_action_retries=0, audit_marker_retries=0)
    second = await handler.decide(_parsed_multiple(), malformed_action_retries=0, audit_marker_retries=0)

    assert first.next_query == "MULTIPLE PROMPT"
    assert second.reason == "multiple_actions"
    assert "Return only one valid <intent mode=\"activate\">...</intent> block now." in (second.next_query or "")
    assert "Do not return multiple <action> blocks." in (second.next_query or "")


@pytest.mark.asyncio
async def test_compiler_shape_recovery_handoffs_on_third_repeat():
    agent = DummyAgent()
    handler = ModelOutputRecoveryHandler(agent, DummyPromptBuilder())

    await handler.decide(_parsed_mixed(), malformed_action_retries=0, audit_marker_retries=0)
    await handler.decide(_parsed_mixed(), malformed_action_retries=0, audit_marker_retries=0)
    third = await handler.decide(_parsed_mixed(), malformed_action_retries=0, audit_marker_retries=0)

    assert third.stop_loop is True
    assert third.reason == "terminal_recovery_loop_handoff"
    assert agent.state.terminal_plaintext_completion_pending is True
    assert "mixed_visible_text_and_control_protocol" in agent.state.terminal_plaintext_completion_text
