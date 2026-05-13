from __future__ import annotations

from types import SimpleNamespace

import pytest

from modules.agent.orchestration.responses import ModelOutputRecoveryHandler
from modules.agent.orchestration.prompts import OrchestratorPromptBuilder
from modules.agent.orchestration.shared.decision_models import ParsedModelOutput


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
    current_turn_state_change_count = 0

    def get_stop_reason_count(self, reason):
        return 0

    def set_malformed_grace(self, steps):
        return None

    def forbid_next_action_fingerprint(self, fingerprint):
        return None


def _handler() -> ModelOutputRecoveryHandler:
    state = DummyState()
    agent = SimpleNamespace(
        state=state,
        config=SimpleNamespace(MALFORMED_ACTION_GRACE_STEPS=2),
        log=None,
        ui=SimpleNamespace(print_error=None),
    )
    builder = OrchestratorPromptBuilder(
        SimpleNamespace(
            state=state,
            config=agent.config,
            planner=None,
            memory_board_store=None,
            log=None,
        )
    )
    return ModelOutputRecoveryHandler(agent, builder)


@pytest.mark.asyncio
async def test_mixed_visible_control_strategy_contract():
    decision = await _handler().decide(
        ParsedModelOutput(
            response='Поясню.\n<action>{"type":"read_file","path":"x.py"}</action>',
            invalid_kind="",
            compiler_error_code="E_MIXED_VISIBLE_TEXT_AND_CONTROL",
            compiler_recovery_id="mixed_visible_control",
        ),
        malformed_action_retries=0,
        audit_marker_retries=0,
    )

    prompt = decision.next_query or ""
    assert decision.reason == "mixed_visible_text_and_control_protocol"
    assert "Choose exactly one" in prompt
    assert "Return only the final plain-text answer" in prompt
    assert "return internal protocol only" in prompt.lower()
    assert "Do not put visible prose before internal protocol." in prompt
    assert "malformed action json" not in prompt.lower()
    assert "opened <think> but did not close it" not in prompt.lower()


@pytest.mark.asyncio
async def test_mixed_intent_transition_visible_answer_current_contract():
    decision = await _handler().decide(
        ParsedModelOutput(
            response='<intent>{"mode":"complete","intent_id":"i1"}</intent>\nDone.',
            invalid_kind="mixed_intent_transition_and_visible_answer",
            compiler_error_code="",
            compiler_recovery_id="",
        ),
        malformed_action_retries=0,
        audit_marker_retries=0,
    )

    prompt = decision.next_query or ""
    assert decision.reason == "mixed_intent_transition_and_visible_answer"
    assert "mixed an intent transition with user-visible answer text" in prompt
    assert "Return only one valid <intent" in prompt
    assert "return only the final plain-text answer" in prompt.lower()
    assert "valid atomic bundle" in prompt
    assert "visible prose before internal protocol" not in prompt.lower()
    assert "malformed action json" not in prompt.lower()


@pytest.mark.asyncio
async def test_conflicting_intent_transitions_current_contract():
    decision = await _handler().decide(
        ParsedModelOutput(
            response='<intent>{"mode":"activate","intent_id":"i1"}</intent>\n<intent>{"mode":"complete","intent_id":"i1"}</intent>',
            invalid_kind="conflicting_intent_transitions",
            compiler_error_code="",
            compiler_recovery_id="",
        ),
        malformed_action_retries=0,
        audit_marker_retries=0,
    )

    prompt = decision.next_query or ""
    assert decision.reason == "conflicting_intent_transitions"
    assert "conflicting intent transitions" in prompt
    assert "Return only one top-level <intent> transition" in prompt
    assert "Do not include <think>" in prompt
    assert "If a contract is already active" in prompt
    assert "mixed an intent transition with user-visible answer text" not in prompt
    assert "mixed a user-visible answer with internal protocol" not in prompt


@pytest.mark.asyncio
async def test_intent_complete_with_action_not_allowed_current_contract():
    decision = await _handler().decide(
        ParsedModelOutput(
            response='<intent>{"mode":"complete","intent_id":"i1"}</intent>\n<action>{"type":"read_file","path":"x.py"}</action>',
            invalid_kind="intent_complete_with_action_not_allowed",
            compiler_error_code="",
            compiler_recovery_id="",
        ),
        malformed_action_retries=0,
        audit_marker_retries=0,
    )

    prompt = decision.next_query or ""
    assert decision.reason == "intent_complete_with_action_not_allowed"
    assert "A completed intent may not include a follow-up <action>" in prompt
    assert "If the goal is complete, return the final plain-text answer only" in prompt
    assert "If more tool work is still needed, do not complete the intent yet" in prompt
    assert "mixed an intent transition with user-visible answer text" not in prompt
    assert "conflicting intent transitions" not in prompt


@pytest.mark.asyncio
async def test_action_array_strategy_contract():
    decision = await _handler().decide(
        ParsedModelOutput(
            response='<action>[{"type":"read_file","path":"a.py"},{"type":"read_file","path":"b.py"}]</action>',
            invalid_kind="",
            compiler_error_code="E_ATOMIC_BUNDLE_REQUIRES_EXACTLY_ONE_ACTION",
            compiler_recovery_id="atomic_bundle_exactly_one_action",
        ),
        malformed_action_retries=0,
        audit_marker_retries=0,
    )

    prompt = decision.next_query or ""
    assert decision.reason == "action_payload_array"
    assert "one JSON object" in prompt
    assert "Do not wrap actions in [...]." in prompt
    assert "2-4 separate top-level <action> blocks" in prompt
    assert "State-changing actions must remain single." in prompt
    assert "visible prose" not in prompt.lower()
    assert "unclosed <think>" not in prompt.lower()


@pytest.mark.asyncio
async def test_unclosed_think_strategy_contract():
    decision = await _handler().decide(
        ParsedModelOutput(
            response="<think>\nDraft\n<action>{}</action>",
            invalid_kind="",
            compiler_error_code="E_UNCLOSED_THINK",
            compiler_recovery_id="unclosed_think",
        ),
        malformed_action_retries=0,
        audit_marker_retries=0,
    )

    prompt = decision.next_query or ""
    assert decision.reason == "malformed_incomplete_think"
    assert "opened <think> but placed protocol tags before closing it" in prompt
    assert "it must be closed with </think> before any memory tag" in prompt.lower()
    assert "<action>, <file_content>, or visible answer text" in prompt
    assert "return the corrected response from the beginning" in prompt.lower()
    assert "malformed <action>" not in prompt
    assert "visible prose before internal protocol" not in prompt.lower()


@pytest.mark.asyncio
async def test_file_content_pairing_strategy_contract():
    decision = await _handler().decide(
        ParsedModelOutput(
            response='<action>{"type":"write_file_block","path":"a.py"}</action>',
            invalid_kind="",
            compiler_error_code="E_FILE_CONTENT_REQUIRES_ACTION",
            compiler_recovery_id="file_content_requires_action",
        ),
        malformed_action_retries=0,
        audit_marker_retries=0,
    )

    prompt = decision.next_query or ""
    assert decision.reason == "file_content_must_follow_action"
    assert "The <file_content> block must appear immediately after </action>" in prompt
    assert "<file_content>\nraw content\n</file_content>" in prompt
    assert "do not put <file_content> inside <action>, before <action>" in prompt
    assert "return action first, then the raw file_content block in the required order" in prompt
    assert "JSON array" not in prompt
    assert "plain-text answer" not in prompt
