from modules.agent.orchestration.parsers import IntentResponseParser
from modules.agent.orchestration.prompts import OrchestratorPromptBuilder
from modules.defaults import DEFAULT_SYSTEM_PROMPT
from modules.parser import ResponseParser
from types import SimpleNamespace


class _Segment:
    def __init__(self, seg_type, content):
        self.type = seg_type
        self.content = content


def test_action_without_think_is_valid():
    response = '<memory_update_done />\n<action>{"type":"read_file","path":"x.kt"}</action>'
    parsed = IntentResponseParser().classify(
        response,
        [_Segment("action", {"type": "read_file", "path": "x.kt"})],
    )
    assert parsed.invalid_kind == ""
    assert parsed.has_action_segment is True


def test_text_answer_without_think_is_valid():
    response = "<memory_update_done />\nОсь відповідь користувачу."
    parsed = IntentResponseParser().classify(
        response,
        [_Segment("text", "Ось відповідь користувачу.")],
    )
    assert parsed.invalid_kind == ""
    assert parsed.visible_text == "Ось відповідь користувачу."


def test_strict_reuse_only_intent_without_think_is_valid():
    response = (
        '<intent mode="reuse">'
        '{"intent_id":"x","intent_type":"MODIFY","goal":"g","allowed_actions":["read_file","write_file_block"],"mode":"reuse","requested_steps":5,"switch_reason":"work_type_changed","switch_explanation":"Need write_file_block."}'
        "</intent>"
    )
    parsed = IntentResponseParser().classify(response, [])
    assert parsed.invalid_kind == ""


def test_unclosed_think_before_action_is_invalid():
    response = '<think>\nDraft reasoning\n<action>{"type":"read_file","path":"x.kt"}</action>'
    parsed = IntentResponseParser().classify(response, ResponseParser().parse(response))
    assert parsed.invalid_kind == ""
    assert parsed.auto_closed_think is True


def test_unclosed_think_before_marker_is_invalid():
    response = (
        '<think>\nDraft reasoning\n<memory_update_done />\n'
        '<action>{"type":"read_file","path":"x.kt"}</action>'
    )
    parsed = IntentResponseParser().classify(response, ResponseParser().parse(response))
    assert parsed.invalid_kind == ""
    assert parsed.auto_closed_think is True


def test_unclosed_think_before_intent_is_invalid():
    response = '<think>\ndraft\n<intent mode="reuse">{"intent_id":"x","mode":"reuse"}</intent>'
    parsed = IntentResponseParser().classify(response, [])
    assert parsed.invalid_kind in {"malformed_incomplete_think", "intent_inside_think"}


def test_long_closed_think_is_valid():
    response = (
        "<think>\n"
        "Long draft reasoning.\n"
        "It may include prose and lists.\n"
        "1. inspect\n"
        "2. decide\n"
        "3. act\n"
        "</think>\n"
        "<memory_update_done />\n"
        '<action>{"type":"read_file","path":"x.kt"}</action>'
    )
    parsed = IntentResponseParser().classify(
        response,
        [_Segment("action", {"type": "read_file", "path": "x.kt"})],
    )
    assert parsed.invalid_kind == ""


def test_formal_intent_recovery_prompt_allows_intent_only_or_atomic_bundle():
    builder = OrchestratorPromptBuilder(
        SimpleNamespace(
            state=SimpleNamespace(active_intent=None),
            config=SimpleNamespace(),
            planner=None,
            memory_board_store=None,
        )
    )
    prompt = builder.build_formal_intent_required_for_multi_step_state_change_prompt(
        goal="Fix KSP/Room build failure after bookmark import/export changes."
    )

    assert "Return a valid formal intent before the action." in prompt
    assert "Return only one top-level <intent mode=\"activate\">...</intent>." not in prompt
    assert "Do not include <think>, <memory_update_done />, <action>, <file_content>, or final answer." not in prompt
    assert "You may either:" in prompt
    assert "Or return an atomic bundle" in prompt
    assert "all-or-nothing" in prompt
    assert "If you also need an action now, place the <intent> block before the action." not in prompt


def test_system_prompt_no_longer_says_think_mandatory():
    assert "Thinking Block (Mandatory)" not in DEFAULT_SYSTEM_PROMPT
    assert "Mandatory: exactly one <think>" not in DEFAULT_SYSTEM_PROMPT
    assert "<think>...</think> required for every response" not in DEFAULT_SYSTEM_PROMPT
    assert "Every response follows this exact sequence" not in DEFAULT_SYSTEM_PROMPT
    assert "<think> is optional" in DEFAULT_SYSTEM_PROMPT
    assert "If opened, it must be closed" in DEFAULT_SYSTEM_PROMPT


def test_structural_think_recovery_prompt_uses_boundary_rules_not_style_rules():
    builder = OrchestratorPromptBuilder(
        SimpleNamespace(
            state=SimpleNamespace(active_intent=None),
            config=SimpleNamespace(),
            planner=None,
            memory_board_store=None,
        )
    )

    prompt = builder.build_incomplete_think_recovery_prompt()

    assert "closed with </think> before any memory tag" in prompt
    assert "Do not put protocol tags or actions inside <think>." in prompt
    assert "Return the corrected response from the beginning." in prompt
    assert "keep it compact and exact" not in prompt
    assert "No plans, no prose paragraphs" not in prompt
    assert "! one verified state" not in prompt


def test_strict_transition_recovery_prompt_says_no_think_and_no_old_compact_wording():
    builder = OrchestratorPromptBuilder(
        SimpleNamespace(
            state=SimpleNamespace(active_intent=SimpleNamespace(intent_id="x", intent_type="INVESTIGATE", goal="g", allowed_actions=["read_chunk"])),
            config=SimpleNamespace(),
            planner=None,
            memory_board_store=None,
        )
    )

    prompt = builder.build_intent_action_not_allowed_prompt(
        blocked_action="write_file_block",
        intent_id="x",
        intent_type="INVESTIGATE",
        allowed_actions=["read_chunk"],
    )

    assert "Do not include <think>, <memory_update_done />, <action>, <file_content>, or final answer" in prompt
    assert "keep it compact and exact" not in prompt
    assert "No plans, no prose paragraphs" not in prompt
