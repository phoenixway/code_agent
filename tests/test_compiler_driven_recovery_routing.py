from __future__ import annotations

from types import SimpleNamespace

import pytest

from modules.agent.orchestration.shared.decision_models import ParsedModelOutput
from modules.agent.orchestration.responses import ModelOutputRecoveryHandler


class DummyState:
    active_intent = None
    last_completed_intent_type = ""
    state_machine = None
    last_blocked_action_type = ""
    last_blocked_action_path = ""
    missing_think_reflection_warning_count = 0
    missing_think_reflection_warning_intent_id = ""
    architecture_defect_repeat_kind = ""
    architecture_defect_repeat_count = 0
    malformed_think_intent_id = ""
    malformed_think_count = 0
    recovery_loop_handoff_intent_id = ""
    recovery_loop_handoff_count = 0
    recovery_loop_handoff_defect_kind = ""
    large_malformed_response_intent_id = ""
    large_malformed_response_count = 0
    large_malformed_response_kind = ""
    think_reflection_repair_pending = False
    think_reflection_repair_kind = ""

    def get_stop_reason_count(self, reason):
        return 0


class DummyPromptBuilder:
    def build_incomplete_think_recovery_prompt(self):
        return "INCOMPLETE THINK"

    def build_file_content_must_follow_action_prompt(self):
        return "FILE CONTENT ORDER"

    def build_action_payload_array_prompt(self):
        return "ACTION ARRAY"

    def build_multiple_actions_prompt(self):
        return "MULTIPLE ACTIONS"

    def build_mixed_visible_text_and_control_protocol_prompt(self):
        return "MIXED VISIBLE CONTROL"

    def build_mixed_intent_transition_and_visible_answer_prompt(self):
        return "MIXED INTENT TRANSITION VISIBLE ANSWER"

    def build_control_tag_leak_recovery_prompt(self):
        return "CONTROL TAG LEAK"


class DummyAgent:
    def __init__(self):
        self.state = DummyState()
        self.config = SimpleNamespace()
        self.log = None
        self.ui = SimpleNamespace(print_error=None)


@pytest.mark.asyncio
async def test_compiler_code_routes_unclosed_think_recovery_without_legacy_invalid_kind():
    handler = ModelOutputRecoveryHandler(DummyAgent(), DummyPromptBuilder())
    parsed = ParsedModelOutput(
        response="<think>\nDraft\n<action>{}</action>",
        invalid_kind="",
        compiler_error_code="E_UNCLOSED_THINK",
        compiler_recovery_id="unclosed_think",
    )

    decision = await handler.decide(parsed, malformed_action_retries=0, audit_marker_retries=0)

    assert decision.reason == "malformed_incomplete_think"
    assert decision.next_query == "INCOMPLETE THINK"


@pytest.mark.asyncio
async def test_compiler_code_routes_mixed_visible_control_recovery_without_legacy_invalid_kind():
    handler = ModelOutputRecoveryHandler(DummyAgent(), DummyPromptBuilder())
    parsed = ParsedModelOutput(
        response='Поясню.\n<action>{"type":"read_file","path":"x.py"}</action>',
        invalid_kind="",
        compiler_error_code="E_MIXED_VISIBLE_TEXT_AND_CONTROL",
        compiler_recovery_id="mixed_visible_control",
    )

    decision = await handler.decide(parsed, malformed_action_retries=0, audit_marker_retries=0)

    assert decision.reason == "mixed_visible_text_and_control_protocol"
    assert decision.next_query == "MIXED VISIBLE CONTROL"


@pytest.mark.asyncio
async def test_compiler_code_routes_mixed_intent_transition_visible_answer_without_legacy_invalid_kind():
    handler = ModelOutputRecoveryHandler(DummyAgent(), DummyPromptBuilder())
    parsed = ParsedModelOutput(
        response='<intent>{"mode":"complete","intent_id":"i1"}</intent>\nDone.',
        invalid_kind="",
        compiler_error_code="E_VISIBLE_TEXT_AFTER_INTENT",
        compiler_recovery_id="mixed_intent_transition_and_visible_answer",
    )

    decision = await handler.decide(parsed, malformed_action_retries=0, audit_marker_retries=0)

    assert decision.reason == "mixed_intent_transition_and_visible_answer"
    assert decision.next_query == "MIXED INTENT TRANSITION VISIBLE ANSWER"
    assert decision.source == "compiler_recovery_strategy"


@pytest.mark.asyncio
async def test_compiler_code_routes_file_content_pairing_recovery_without_legacy_invalid_kind():
    handler = ModelOutputRecoveryHandler(DummyAgent(), DummyPromptBuilder())
    parsed = ParsedModelOutput(
        response='<action>{"type":"write_file_block","path":"a.py"}</action>',
        invalid_kind="",
        compiler_error_code="E_FILE_CONTENT_REQUIRES_ACTION",
        compiler_recovery_id="file_content_requires_action",
    )

    decision = await handler.decide(parsed, malformed_action_retries=0, audit_marker_retries=0)

    assert decision.reason == "file_content_must_follow_action"
    assert decision.next_query == "FILE CONTENT ORDER"


@pytest.mark.asyncio
async def test_compiler_code_routes_action_array_recovery_without_legacy_invalid_kind():
    handler = ModelOutputRecoveryHandler(DummyAgent(), DummyPromptBuilder())
    parsed = ParsedModelOutput(
        response='<action>[{"type":"read_file","path":"a.py"},{"type":"read_file","path":"b.py"}]</action>',
        invalid_kind="",
        compiler_error_code="E_ATOMIC_BUNDLE_REQUIRES_EXACTLY_ONE_ACTION",
        compiler_recovery_id="atomic_bundle_exactly_one_action",
    )

    decision = await handler.decide(parsed, malformed_action_retries=0, audit_marker_retries=0)

    assert decision.reason == "action_payload_array"
    assert decision.next_query == "ACTION ARRAY"


@pytest.mark.asyncio
async def test_compiler_code_routes_multiple_actions_recovery_without_legacy_invalid_kind():
    handler = ModelOutputRecoveryHandler(DummyAgent(), DummyPromptBuilder())
    parsed = ParsedModelOutput(
        response='<action>{"type":"read_file","path":"a.py"}</action>\n<action>{"type":"read_file","path":"b.py"}</action>',
        invalid_kind="",
        compiler_error_code="E_ATOMIC_BUNDLE_REQUIRES_EXACTLY_ONE_ACTION",
        compiler_recovery_id="atomic_bundle_exactly_one_action",
    )

    decision = await handler.decide(parsed, malformed_action_retries=0, audit_marker_retries=0)

    assert decision.reason == "multiple_actions"
    assert decision.next_query == "MULTIPLE ACTIONS"
