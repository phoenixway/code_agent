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

    def build_conflicting_intent_transitions_prompt(self):
        return "CONFLICTING INTENT TRANSITIONS"

    def build_completion_with_action_not_allowed_prompt(self):
        return "COMPLETION WITH ACTION NOT ALLOWED"

    def build_control_tag_leak_recovery_prompt(self):
        return "CONTROL TAG LEAK"

    def build_malformed_action_strict_recovery_prompt(self):
        return "MALFORMED ACTION STRICT"


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
async def test_compiler_code_routes_transition_conflict_recoveries_without_legacy_invalid_kind():
    handler = ModelOutputRecoveryHandler(DummyAgent(), DummyPromptBuilder())

    conflicting = await handler.decide(
        ParsedModelOutput(
            response='<intent>{"mode":"activate","intent_id":"i1"}</intent>\n<intent>{"mode":"complete","intent_id":"i1"}</intent>',
            invalid_kind="",
            compiler_error_code="E_MULTIPLE_INTENTS",
            compiler_recovery_id="conflicting_intent_transitions",
        ),
        malformed_action_retries=0,
        audit_marker_retries=0,
    )
    complete_with_action = await handler.decide(
        ParsedModelOutput(
            response='<intent>{"mode":"complete","intent_id":"i1"}</intent>\n<action>{"type":"read_file","path":"x.py"}</action>',
            invalid_kind="",
            compiler_error_code="E_INTENT_COMPLETE_WITH_ACTION",
            compiler_recovery_id="intent_complete_with_action_not_allowed",
        ),
        malformed_action_retries=0,
        audit_marker_retries=0,
    )

    assert conflicting.reason == "conflicting_intent_transitions"
    assert conflicting.next_query == "CONFLICTING INTENT TRANSITIONS"
    assert conflicting.source == "compiler_recovery_strategy"
    assert complete_with_action.reason == "intent_complete_with_action_not_allowed"
    assert complete_with_action.next_query == "COMPLETION WITH ACTION NOT ALLOWED"
    assert complete_with_action.source == "compiler_recovery_strategy"


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
async def test_compiler_strategy_path_emits_diagnostic_semantic_decision_record():
    handler = ModelOutputRecoveryHandler(DummyAgent(), DummyPromptBuilder())
    captured = []
    handler.stage_logger.log = lambda *args, **kwargs: captured.append((args, kwargs))

    decision = await handler.decide(
        ParsedModelOutput(
            response='<action>{"type":"read_file","path":"a.py"}</action>\n<file_content>body</file_content>',
            invalid_kind="",
            compiler_error_code="E_FILE_CONTENT_ACTION_MISMATCH",
            compiler_recovery_id="file_content_must_follow_action",
        ),
        malformed_action_retries=0,
        audit_marker_retries=0,
    )

    assert decision.reason == "file_content_must_follow_action"
    records = [
        kwargs["semantic_decision_record"]
        for _args, kwargs in captured
        if kwargs.get("source") == "semantic_decision_record"
    ]
    assert len(records) == 1
    record = records[0]
    assert record["domain"] == "output_recovery"
    assert record["stage"] == "output_recovery"
    assert record["decision"] == "compiler_strategy_resolved"
    assert record["reason"] == "file_content_must_follow_action"
    assert record["source"] == "compiler_recovery_strategy"
    assert record["diagnostic_only"] is True
    assert record["authority_affecting"] is False
    assert record["behavior_affecting"] is False
    assert record["compiler_metadata"]["error_code"] == "E_FILE_CONTENT_ACTION_MISMATCH"
    assert record["registry_resolution"]["strategy_id"] == "file_content_action_mismatch"
    assert record["registry_resolution"]["handler_key"] == "file_content_order"
    assert record["effective_decision"]["outcome_kind"] == "continue"
    assert record["effective_decision"]["prompt_family"] == "file_content_order"


@pytest.mark.asyncio
async def test_compiler_code_routes_file_content_action_mismatch_without_legacy_invalid_kind():
    handler = ModelOutputRecoveryHandler(DummyAgent(), DummyPromptBuilder())
    parsed = ParsedModelOutput(
        response='<action>{"type":"read_file","path":"a.py"}</action>\n<file_content>body</file_content>',
        invalid_kind="",
        compiler_error_code="E_FILE_CONTENT_ACTION_MISMATCH",
        compiler_recovery_id="file_content_must_follow_action",
    )

    decision = await handler.decide(parsed, malformed_action_retries=0, audit_marker_retries=0)

    assert decision.reason == "file_content_must_follow_action"
    assert decision.next_query == "FILE CONTENT ORDER"
    assert decision.source == "compiler_recovery_strategy"


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


@pytest.mark.asyncio
async def test_compiler_code_routes_xml_tool_shorthand_without_execution():
    handler = ModelOutputRecoveryHandler(DummyAgent(), DummyPromptBuilder())
    parsed = ParsedModelOutput(
        response='<run_shell command="which gradle" timeout="10" />',
        invalid_kind="",
        compiler_error_code="E_XML_TOOL_SHORTHAND",
        compiler_recovery_id="xml_tool_shorthand",
    )

    decision = await handler.decide(parsed, malformed_action_retries=0, audit_marker_retries=0)

    assert decision.reason == "invalid_action_syntax"
    assert decision.source == "compiler_recovery_strategy"
    assert decision.continue_loop is True


@pytest.mark.asyncio
async def test_compiler_code_routes_fenced_protocol_block_without_execution():
    handler = ModelOutputRecoveryHandler(DummyAgent(), DummyPromptBuilder())
    parsed = ParsedModelOutput(
        response='```xml\n<action>{"type":"run_shell","command":"which gradle"}</action>\n```',
        invalid_kind="",
        compiler_error_code="E_FENCED_PROTOCOL_BLOCK",
        compiler_recovery_id="fenced_protocol_block",
    )

    decision = await handler.decide(parsed, malformed_action_retries=0, audit_marker_retries=0)

    assert decision.reason == "fenced_protocol_block"
    assert decision.source == "compiler_recovery_strategy"
    assert decision.continue_loop is True
