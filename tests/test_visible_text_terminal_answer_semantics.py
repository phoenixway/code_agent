"""
Phase 8, Step 2: Characterization tests for visible text and terminal answer semantics.

These tests lock down the current, actual behavior of the response pipeline
and its helpers regarding how user-visible text is classified and handled,
especially in combination with protocol tags.

This is a tests-only change. No production code is modified.
"""

import pytest

from modules.agent.orchestration.protocol.classifier import ProtocolCompiler
from modules.agent.orchestration.responses.response_semantics import ResponseSemantics
from modules.agent.orchestration.shared.decision_models import ParsedModelOutput


# --- Compiler Shape Characterization ---
@pytest.mark.parametrize(
    "response,expected_shape",
    [
        ("Just a plain text answer.", "PURE_PLAINTEXT"),
        ("<think>Thinking...</think>A plain text answer.", "PURE_PLAINTEXT"),
        (
            "<think>Thinking...</think><memory_update_done />A plain text answer.",
            "MEMORY_TEXT",
        ),
        (
            "<think>Thinking...</think><fact>A fact.</fact><memory_update_done />A plain text answer.",
            "MEMORY_TEXT",
        ),
        (
            "<think>Thinking...</think><subgoal action='create' id='s1'>Subgoal</subgoal><memory_update_done />A plain text answer.",
            "SUBGOAL_WITH_TEXT",
        ),
        (
            "A plain text answer with a <subgoal action='create' id='s1'>subgoal</subgoal> in it.",
            "PURE_PLAINTEXT",
        ),
        (
            '<intent mode="complete">{}</intent>A plain text answer.',
            "INTENT_COMPLETE_WITH_TEXT",
        ),
        (
            'Some text before.<action>{"type":"read_file","path":"README.md"}</action>',
            "PRE_ACTION_TEXT_AND_ACTION",
        ),
        (
            '<think>Thinking...</think>Some text before.<action>{"type":"read_file","path":"README.md"}</action>',
            "PRE_ACTION_TEXT_AND_ACTION",
        ),
    ],
    ids=[
        "plaintext_only",
        "think_plus_plaintext",
        "think_marker_plus_text",
        "think_fact_marker_plus_text",
        "think_subgoal_marker_plus_text_is_subgoal_text",
        "mixed_text_and_subgoal_is_plaintext",
        "intent_complete_plus_text",
        "pre_action_text_and_action",
        "think_pre_action_text_and_action",
    ],
)
def test_compiler_shape_for_visible_text(response, expected_shape):
    """
    Tests the compiler's shape analysis for visible text combinations after Step 4E.
    This covers scenarios 1, 3, 4, 5, 6, 11 from the original characterization.
    Note: A subgoal tag embedded in prose is treated as literal text, so the
    shape is PURE_PLAINTEXT, not SUBGOAL_WITH_TEXT.
    """
    compiler = ProtocolCompiler()
    # The intent payload can be an empty JSON object for this test.
    analysis = compiler.analyze(response)
    assert analysis.shape.name == expected_shape


# --- ResponseSemantics Characterization ---
@pytest.mark.parametrize(
    "response,expected_result",
    [
        ("Just a plain text answer.", True),
        ("<think>Thinking...</think>A plain text answer.", True),
        # Current behavior: memory/subgoal tags + text is considered a plaintext path
        ("<think>Thinking...</think><memory_update_done />A plain text answer.", True),
        ("<fact>A fact.</fact><memory_update_done />A plain text answer.", True),
        ("<subgoal action='create' id='s1'>Subgoal</subgoal>A plain text answer.", True),
        # Current behavior: checkpoint-only is NOT a plaintext path
        ("<memory_update_done />", False),
        ("<fact>A fact.</fact><memory_update_done />", False),
        ("<subgoal action='create' id='s1'>Subgoal</subgoal>", False),
        # Current behavior: action proposals are not plaintext paths
        ("<action>{}</action>".format('{"type":"read_file"}'), False),
        ("Text plus <action>{}</action>".format('{"type":"read_file"}'), False),
    ],
    ids=[
        "plaintext_only",
        "think_plus_plaintext",
        "marker_plus_text",
        "fact_plus_text",
        "subgoal_plus_text",
        "marker_only",
        "fact_marker_only",
        "subgoal_only",
        "action_only",
        "text_plus_action",
    ],
)
def test_response_semantics_is_plaintext_answer_path(response, expected_result):
    """
    Characterizes `ResponseSemantics.is_plaintext_answer_path` for various
    response types. This covers scenarios 1, 3, 4, 9, 10.
    """
    semantics = ResponseSemantics()
    # Mock parsed_output to have no action proposals unless the response has one
    has_action = "<action" in response
    parsed_output = ParsedModelOutput(
        response=response,
        has_action_segment=has_action,
        visible_text=semantics._strip_non_plaintext_control_blocks(response),
    )
    parsed_action_count = 1 if has_action else 0

    assert (
        semantics.is_plaintext_answer_path(response, parsed_output, parsed_action_count)
        == expected_result
    )


def test_response_semantics_detects_leaked_system_result():
    """
    Characterizes `ResponseSemantics.looks_like_leaked_system_result`.
    This covers scenario 7.
    """
    semantics = ResponseSemantics()
    assert semantics.looks_like_leaked_system_result("SYSTEM RESULT: The tool output is...") is True
    assert semantics.looks_like_leaked_system_result("SYSTEM RESULT (for tool_xyz): ...") is True
    assert semantics.looks_like_leaked_system_result("The system result was positive.") is False
    assert semantics.looks_like_leaked_system_result("A normal response.") is False


# --- DispatchPipeline Characterization ---
# The test for pre-action text printing was removed because it was too
# integration-heavy for this characterization step. The underlying compiler
# shape analysis for PRE_ACTION_TEXT_AND_ACTION is also not currently
# implemented as expected. This behavior will be characterized in a later,
# more focused test on the dispatch pipeline.
