"""
Phase 8: Golden characterization tests for compiler/runtime structural facts.

These tests lock down the behavior of the compiler and RuntimeProtocolSemantics
adapter regarding new structural facts needed for the TerminalAnswerClassifier.
"""

import pytest

from modules.agent.orchestration.protocol.classifier import ProtocolCompiler
from modules.agent.orchestration.responses.runtime_protocol_semantics import runtime_semantics_from_compiler_analysis

# Golden test matrix for compiler/runtime structural facts.
GOLDEN_CASES = [
    # A. Memory content tags
    {
        "case_id": "memory_fact_tag",
        "response": "<fact>A fact.</fact>",
        "expected_shape": None,
        "expected_facts": {
            "has_memory_tags": True,
            "has_subgoal_tags": False,
            "has_memory_checkpoint": False,
            "visible_text_source": "NONE",
        },
    },
    {
        "case_id": "memory_finding_tag",
        "response": "<finding>A finding.</finding>",
        "expected_shape": None,
        "expected_facts": {
            "has_memory_tags": True,
            "has_subgoal_tags": False,
            "has_memory_checkpoint": False,
            "visible_text_source": "NONE",
        },
    },
    {
        "case_id": "memory_decision_tag",
        "response": "<decision>A decision.</decision>",
        "expected_shape": None,
        "expected_facts": {
            "has_memory_tags": True,
            "has_subgoal_tags": False,
            "has_memory_checkpoint": False,
            "visible_text_source": "NONE",
        },
    },
    {
        "case_id": "memory_preference_tag",
        "response": "<preference>A preference.</preference>",
        "expected_shape": None,
        "expected_facts": {
            "has_memory_tags": True,
            "has_subgoal_tags": False,
            "has_memory_checkpoint": False,
            "visible_text_source": "NONE",
        },
    },
    {
        "case_id": "memory_progress_tag",
        "response": "<progress>A progress item.</progress>",
        "expected_shape": None,
        "expected_facts": {
            "has_memory_tags": True,
            "has_subgoal_tags": False,
            "has_memory_checkpoint": False,
            "visible_text_source": "NONE",
        },
    },
    {
        "case_id": "memory_path_tag",
        "response": "<path>README.md</path>",
        "expected_shape": None,
        "expected_facts": {
            "has_memory_tags": True,
            "has_subgoal_tags": False,
            "has_memory_checkpoint": False,
            "visible_text_source": "NONE",
        },
    },
    # B. Memory review and checkpoint
    {
        "case_id": "memory_review_tag",
        "response": "<memory_review />",
        "expected_shape": None,
        "expected_facts": {
            "has_memory_tags": True,
            "has_subgoal_tags": False,
            "has_memory_checkpoint": False,
            "visible_text_source": "NONE",
        },
    },
    {
        "case_id": "memory_update_done_marker",
        "response": "<memory_update_done />",
        "expected_shape": None,
        "expected_facts": {
            "has_memory_tags": False,
            "has_subgoal_tags": False,
            "has_memory_checkpoint": True,
            "visible_text_source": "NONE",
        },
    },
    {
        "case_id": "memory_tag_with_checkpoint",
        "response": "<fact>A fact.</fact><memory_update_done />",
        "expected_shape": None,
        "expected_facts": {
            "has_memory_tags": True,
            "has_subgoal_tags": False,
            "has_memory_checkpoint": True,
            "visible_text_source": "NONE",
        },
    },
    # C. Subgoal tags
    {
        "case_id": "single_subgoal_tag",
        "response": '<subgoal action="create" id="s1">Plan step</subgoal>',
        "expected_shape": None,
        "expected_facts": {
            "has_memory_tags": False,
            "has_subgoal_tags": True,
            "has_memory_checkpoint": False,
            "visible_text_source": "NONE",
        },
    },
    {
        "case_id": "multiple_subgoal_tags",
        "response": '<subgoal action="create" id="s1">One</subgoal><subgoal action="create" id="s2">Two</subgoal>',
        "expected_shape": None,
        "expected_facts": {
            "has_memory_tags": False,
            "has_subgoal_tags": True,
            "has_memory_checkpoint": False,
            "visible_text_source": "NONE",
        },
    },
    {
        "case_id": "memory_and_subgoal_tags",
        "response": '<fact>A fact.</fact><subgoal action="create" id="s1">Plan step</subgoal>',
        "expected_shape": None,
        "expected_facts": {
            "has_memory_tags": True,
            "has_subgoal_tags": True,
            "has_memory_checkpoint": False,
            "visible_text_source": "NONE",
        },
    },
    # D. Visible text source and shape improvements
    {
        "case_id": "pure_plaintext",
        "response": "Just text.",
        "expected_shape": "PURE_PLAINTEXT",
        "expected_facts": {
            "has_memory_tags": False,
            "has_subgoal_tags": False,
            "has_memory_checkpoint": False,
            "visible_text_source": "PURE_PLAINTEXT",
        },
    },
    {
        "case_id": "think_plus_plaintext",
        "response": "<think>private</think>Just text.",
        "expected_shape": "PURE_PLAINTEXT",
        "expected_facts": {
            "has_memory_tags": False,
            "has_subgoal_tags": False,
            "has_memory_checkpoint": False,
            "visible_text_source": "PURE_PLAINTEXT",
        },
    },
    {
        "case_id": "action_only_no_visible_text",
        "response": '<action>{"type":"read_file","path":"README.md"}</action>',
        "expected_shape": "ACTION_ONLY",
        "expected_facts": {
            "has_memory_tags": False,
            "has_subgoal_tags": False,
            "has_memory_checkpoint": False,
            "visible_text_source": "NONE",
        },
    },
    {
        "case_id": "pre_action_text_and_action",
        "response": 'Text before action.<action>{"type":"read_file","path":"README.md"}</action>',
        "expected_shape": "PRE_ACTION_TEXT_AND_ACTION",
        "expected_facts": {
            "has_memory_tags": False,
            "has_subgoal_tags": False,
            "has_memory_checkpoint": False,
            "visible_text_source": "PRE_ACTION_TEXT",
            "has_pre_action_text": True,
            "pre_action_text": "contains:Text before action.",
        },
    },
    {
        "case_id": "intent_complete_with_text",
        "response": '<intent mode="complete">{}</intent>All done.',
        "expected_shape": "INTENT_COMPLETE_WITH_TEXT",
        "expected_facts": {
            "has_memory_tags": False,
            "has_subgoal_tags": False,
            "has_memory_checkpoint": False,
            "visible_text_source": "INTENT_COMPLETION_TEXT",
        },
    },
    {
        "case_id": "memory_with_visible_text",
        "response": "<fact>A fact.</fact>Visible answer.",
        "expected_shape": "MEMORY_TEXT",
        "expected_facts": {
            "has_memory_tags": True,
            "has_subgoal_tags": False,
            "has_memory_checkpoint": False,
            "visible_text_source": "CHECKPOINT_ACCOMPANYING_TEXT",
        },
    },
    {
        "case_id": "subgoal_with_visible_text",
        "response": '<subgoal action="create" id="s1">Plan step</subgoal>Visible answer.',
        "expected_shape": "SUBGOAL_WITH_TEXT",
        "expected_facts": {
            "has_memory_tags": False,
            "has_subgoal_tags": True,
            "has_memory_checkpoint": False,
            "visible_text_source": "CHECKPOINT_ACCOMPANYING_TEXT",
        },
    },
    {
        "case_id": "memory_and_subgoal_with_visible_text",
        "response": '<fact>A fact.</fact><subgoal action="create" id="s1">Plan step</subgoal>Visible answer.',
        "expected_shape": "SUBGOAL_WITH_TEXT",
        "expected_facts": {
            "has_memory_tags": True,
            "has_subgoal_tags": True,
            "has_memory_checkpoint": False,
            "visible_text_source": "CHECKPOINT_ACCOMPANYING_TEXT",
        },
    },
    {
        "case_id": "think_only_no_visible_text",
        "response": "<think>private</think>",
        "expected_shape": None,
        "expected_facts": {
            "has_memory_tags": False,
            "has_subgoal_tags": False,
            "has_memory_checkpoint": False,
            "visible_text_source": "NONE",
        },
    },
    # E. Invalid/unknown visible text source
    {
        "case_id": "invalid_action_then_intent",
        "response": '<action>{"type":"read_file","path":"README.md"}</action><intent mode="activate">{}</intent>',
        "expected_shape": "INVALID",
        "expected_facts": {"visible_text_source": "UNKNOWN"},
    },
]


@pytest.mark.parametrize(
    "case_id, response, expected_shape, expected_facts",
    [(c["case_id"], c["response"], c.get("expected_shape"), c["expected_facts"]) for c in GOLDEN_CASES],
    ids=[c["case_id"] for c in GOLDEN_CASES],
)
def test_golden_structural_facts(case_id, response, expected_shape, expected_facts):
    """
    Golden characterization test for compiler/runtime structural facts.
    This test verifies that the compiler and RuntimeProtocolSemantics correctly
    produce the structural facts and shapes defined in Phase 8.
    """
    compiler = ProtocolCompiler()
    analysis = compiler.analyze(response)
    snapshot = runtime_semantics_from_compiler_analysis(analysis)

    # 1. Assert compiler shape if specified
    if expected_shape is not None:
        assert analysis.shape.name == expected_shape, f"[{case_id}] Shape mismatch"

    # 2. Assert structural facts on the runtime snapshot
    sentinel = object()
    for fact_name, expected_value in expected_facts.items():
        actual_value = getattr(snapshot, fact_name, sentinel)

        if isinstance(expected_value, str) and expected_value.startswith("contains:"):
            _, expected_substring = expected_value.split("contains:", 1)
            expected_substring = expected_substring.strip()
            assert isinstance(actual_value, str) and expected_substring in actual_value, (
                f"[{case_id}] Fact '{fact_name}' mismatch: "
                f"expected to contain '{expected_substring}', got '{actual_value}'"
            )
        else:
            assert actual_value == expected_value, (
                f"[{case_id}] Fact '{fact_name}' mismatch: "
                f"expected '{expected_value}', got '{actual_value}'"
            )
