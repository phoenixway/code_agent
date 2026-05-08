"""
Phase 8, Step 4F: Sufficiency/parity tests for terminal answer semantics.

This test verifies that the structural facts implemented in Step 4E are
sufficient to distinguish the core TerminalAnswerKind candidates.

It uses a test-only helper (`_get_candidate_kind`) to simulate a future
classifier's logic based purely on the new structural facts. This proves
sufficiency without implementing the actual classifier in production code.
"""

import pytest

from modules.agent.orchestration.protocol.classifier import ProtocolCompiler
from modules.agent.orchestration.responses.runtime_protocol_semantics import (
    RuntimeProtocolSemantics,
    runtime_semantics_from_compiler_analysis,
)


# Helper to derive a candidate kind from structural facts.
# This is a test-only helper and does NOT represent the final classifier implementation.
def _get_candidate_kind(snapshot: RuntimeProtocolSemantics) -> str:
    if snapshot.visible_text_source == "PURE_PLAINTEXT":
        return "PLAINTEXT_TERMINAL_ANSWER"
    if snapshot.visible_text_source == "CHECKPOINT_ACCOMPANYING_TEXT":
        return "CHECKPOINT_WITH_VISIBLE_TEXT"
    if snapshot.visible_text_source == "INTENT_COMPLETION_TEXT":
        return "INTENT_COMPLETE_WITH_VISIBLE_TEXT"
    if snapshot.visible_text_source == "PRE_ACTION_TEXT":
        return "PRE_ACTION_VISIBLE_TEXT_WITH_ACTION"

    if not snapshot.has_visible_answer and not snapshot.has_pre_action_text:
        if snapshot.has_memory_tags or snapshot.has_subgoal_tags or snapshot.has_memory_checkpoint:
            return "CHECKPOINT_ONLY"
        # This also covers action_only, think_only, etc.
        return "NO_VISIBLE_TEXT"

    return "UNKNOWN"


# Test cases for sufficiency review
SUFFICIENCY_CASES = [
    # PLAINTEXT_TERMINAL_ANSWER
    ("pure_plaintext", "A final answer.", "PLAINTEXT_TERMINAL_ANSWER"),
    ("think_plus_plaintext", "<think>Thinking...</think>A final answer.", "PLAINTEXT_TERMINAL_ANSWER"),
    # CHECKPOINT_ONLY
    ("memory_tag_only", "<fact>A fact.</fact>", "CHECKPOINT_ONLY"),
    ("subgoal_tag_only", "<subgoal action='create' id='s1'>Subgoal</subgoal>", "CHECKPOINT_ONLY"),
    ("memory_update_done_only", "<memory_update_done />", "CHECKPOINT_ONLY"),
    # CHECKPOINT_WITH_VISIBLE_TEXT
    ("memory_tag_with_text", "<fact>A fact.</fact>And a visible answer.", "CHECKPOINT_WITH_VISIBLE_TEXT"),
    (
        "subgoal_tag_with_text",
        "<subgoal action='create' id='s1'>Subgoal</subgoal>And a visible answer.",
        "CHECKPOINT_WITH_VISIBLE_TEXT",
    ),
    # INTENT_COMPLETE_WITH_VISIBLE_TEXT
    ("intent_complete_with_text", '<intent mode="complete">{}</intent>All done.', "INTENT_COMPLETE_WITH_VISIBLE_TEXT"),
    # PRE_ACTION_VISIBLE_TEXT_WITH_ACTION
    (
        "pre_action_text_with_action",
        'Some text.<action>{"type":"read_file"}</action>',
        "PRE_ACTION_VISIBLE_TEXT_WITH_ACTION",
    ),
    # NO_VISIBLE_TEXT
    ("action_only", '<action>{"type":"read_file"}</action>', "NO_VISIBLE_TEXT"),
    ("think_only", "<think>Thinking...</think>", "NO_VISIBLE_TEXT"),
    # UNKNOWN / Policy-driven cases
    ("inline_code_action_literal", "Text with `<code><action>...</action></code>` literal.", "PLAINTEXT_TERMINAL_ANSWER"),
    ("fenced_code_action_literal", "Text with ```<action>...</action>``` literal.", "PLAINTEXT_TERMINAL_ANSWER"),
    # These cases are expected to be handled by legacy regex or runtime policy, not structural facts.
    # The structural facts correctly identify them as PLAINTEXT for now.
    ("leaked_system_result_like", "SYSTEM RESULT: The tool output is...", "PLAINTEXT_TERMINAL_ANSWER"),
    ("internal_summary_like", "ACTIVE GOAL: Refactor the file.", "PLAINTEXT_TERMINAL_ANSWER"),
]


@pytest.mark.parametrize(
    "case_id, response, expected_kind",
    SUFFICIENCY_CASES,
    ids=[c[0] for c in SUFFICIENCY_CASES],
)
def test_terminal_answer_fact_sufficiency(case_id, response, expected_kind):
    """
    Parity/sufficiency test for Phase 8 Step 4F.

    This test verifies that the structural facts implemented in Step 4E are
    sufficient to distinguish the core TerminalAnswerKind candidates.

    It uses a test-only helper (`_get_candidate_kind`) to simulate a future
    classifier's logic based purely on the new structural facts. This proves
    sufficiency without implementing the actual classifier in production code.
    """
    compiler = ProtocolCompiler()
    analysis = compiler.analyze(response)
    snapshot = runtime_semantics_from_compiler_analysis(analysis)

    candidate_kind = _get_candidate_kind(snapshot)
    assert candidate_kind == expected_kind
