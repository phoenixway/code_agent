"""Tests for the recovery prompt builder to prevent crashes."""

from __future__ import annotations

import sys
from pathlib import Path
from unittest.mock import MagicMock

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[4]))

from modules.agent.orchestration.prompts.prompting import OrchestratorPromptBuilder


class MockAgent:
    """A mock agent for initializing the prompt builder."""

    def __init__(self):
        self.state = MagicMock()
        self.config = {}
        self.recovery_policy_resolver = MagicMock()
        self.prompts = MagicMock()
        self.state.active_intent = None
        self.state.last_resumable_intent_id = ""
        self.state.last_completed_intent_type = ""
        self.state.task_kind = None


@pytest.fixture
def prompt_builder() -> OrchestratorPromptBuilder:
    """Provides a mocked prompt builder for testing."""
    agent = MockAgent()
    builder = OrchestratorPromptBuilder(agent)
    # Mock methods that are not part of RecoveryPromptBuilderMixin to isolate the test
    builder.build_action_format_recovery_prompt = MagicMock(return_value="Generic action format recovery prompt.")
    builder.typed_recovery_header = MagicMock(return_value="Recovery Header.")
    builder._recovery_context = MagicMock()
    return builder



def test_low_value_broad_search_repeat_real_action_format_prompt(prompt_builder: OrchestratorPromptBuilder):
    """
    Tests that `low_value_broad_search_repeat` with a real action format prompt builder
    produces the expected detailed prompt.
    """
    # Un-mock the method for this specific test to test the real implementation
    prompt_builder.build_action_format_recovery_prompt = (
        OrchestratorPromptBuilder.build_action_format_recovery_prompt.__get__(prompt_builder, OrchestratorPromptBuilder)
    )

    reason = "low_value_broad_search_repeat"
    stop_info = {"reason": reason}
    prompt_builder._recovery_context.return_value = MagicMock(reason=reason, to_stop_info=lambda: stop_info)

    prompt = prompt_builder.build_typed_stop_recovery_prompt(stop_info)

    assert isinstance(prompt, str)
    assert "prefer exactly one" in prompt.lower()
    assert "read-only" in prompt.lower()
    assert "low-value repeat" in prompt.lower()
    assert "bounded reconnaissance" in prompt.lower()
    assert "targeted read" in prompt.lower()
    assert "read_file" in prompt
    assert "read_chunk" in prompt
    assert "read_file_skeleton" in prompt
    assert "use a more specific path" in prompt.lower()
    assert "include_extensions" in prompt.lower()
    assert "exclude noisy" in prompt.lower()
    assert "documentation" in prompt.lower()
    assert "secondary evidence" in prompt.lower()
    assert "code is primary evidence" in prompt.lower()
    assert "docs/" in prompt.lower()


def test_typed_stop_recovery_prompt_handles_none_from_helpers(prompt_builder: OrchestratorPromptBuilder):
    """
    Tests that `build_typed_stop_recovery_prompt` is defensive against None returns from its helpers.
    """
    reason = "low_value_broad_search_repeat"
    stop_info = {"reason": reason}
    prompt_builder._recovery_context.return_value = MagicMock(reason=reason, to_stop_info=lambda: stop_info)

    # Simulate helpers returning None, which caused the original crash
    prompt_builder.build_action_format_recovery_prompt.return_value = None
    prompt_builder.typed_recovery_header.return_value = None

    prompt = prompt_builder.build_typed_stop_recovery_prompt(stop_info)

    assert isinstance(prompt, str)
    # It should still contain the appended part, not crash
    assert "too broad" in prompt.lower()
    assert "low-value repeat" in prompt.lower()
    assert "bounded reconnaissance" in prompt.lower()
    assert "unbounded searches" in prompt.lower()
    assert "targeted read" in prompt.lower()
    assert "more specific path" in prompt.lower()
    assert "shortest path to concrete evidence" in prompt.lower()


def test_typed_recovery_header_handles_none_next_hint(prompt_builder: OrchestratorPromptBuilder):
    """
    Tests that typed_recovery_header is defensive against None from _format_next_actions_hint.
    """
    # Un-mock the method to test the real implementation
    prompt_builder.typed_recovery_header = (
        OrchestratorPromptBuilder.typed_recovery_header.__get__(prompt_builder, OrchestratorPromptBuilder)
    )

    reason = "low_value_broad_search_repeat"
    stop_info = {"reason": reason}
    prompt_builder._recovery_context.return_value = MagicMock(
        reason=reason, to_stop_info=lambda: stop_info, error_code="", message=""
    )
    prompt_builder._action_hints_from_stop_info = MagicMock(return_value=([], ["some_action"], "recommended"))
    prompt_builder._format_next_actions_hint = MagicMock(return_value=None)

    # This call would crash if not defensive
    header = prompt_builder.typed_recovery_header(stop_info)

    assert isinstance(header, str)
    assert "broad" in header.lower()
    assert "search" in header.lower()


def test_history_self_reference_hit_recovery_prompt(prompt_builder: OrchestratorPromptBuilder):
    """
    Tests that `history_self_reference_hit` recovery prompt contains the correct guidance.
    """
    # Un-mock the method to test the real implementation
    prompt_builder.typed_recovery_header = (
        OrchestratorPromptBuilder.typed_recovery_header.__get__(prompt_builder, OrchestratorPromptBuilder)
    )

    reason = "history_self_reference_hit"
    stop_info = {"reason": reason}
    prompt_builder._recovery_context.return_value = MagicMock(
        reason=reason, to_stop_info=lambda: stop_info, error_code="", message=""
    )
    prompt_builder._action_hints_from_stop_info = MagicMock(return_value=([], [], ""))
    prompt_builder._format_next_actions_hint = MagicMock(return_value=None)

    header = prompt_builder.typed_recovery_header(stop_info)

    assert isinstance(header, str)
    assert "self-referential" in header.lower()
    assert "artifact" in header.lower()
    assert "not real usage evidence" in header.lower()


def test_unclosed_think_recovery_prompt(prompt_builder: OrchestratorPromptBuilder):
    """
    Tests that the recovery prompt for an unclosed think block is direct.
    """
    # This method is part of ActionFormatPromptBuilderMixin, not mocked here.
    prompt = prompt_builder.build_incomplete_think_recovery_prompt()

    assert "opened <think> but placed protocol tags before closing it" in prompt
    assert "<think> may contain draft reasoning" in prompt
    assert "closed with </think> before any memory tag" in prompt
    assert "Do not put protocol tags or actions inside <think>" in prompt
    assert "Return the corrected response from the beginning" in prompt
    assert "restart the whole response" in prompt


def test_unclosed_think_second_retry_prompt(prompt_builder: OrchestratorPromptBuilder):
    """
    Tests that the second-retry prompt for an unclosed think block is stricter.
    """
    prompt = prompt_builder.build_exact_think_skeleton_prompt()

    assert "malformed or unclosed <think> block" in prompt
    assert "<think> may contain draft reasoning" in prompt
    assert "Do not use <think>" in prompt
    assert "No internal analysis" in prompt
    assert "Return exactly one valid" in prompt
    assert "Return the corrected response from the beginning" in prompt


def test_typed_stop_recovery_with_missing_goal(prompt_builder: OrchestratorPromptBuilder):
    """
    Tests that prompt building is safe when the active intent or its goal is missing.
    """
    reason = "planned_full_read_too_large"
    stop_info = {"reason": reason}
    prompt_builder._recovery_context.return_value = MagicMock(reason=reason, to_stop_info=lambda: stop_info)

    # Case 1: No active intent
    prompt_builder.state.active_intent = None
    prompt = prompt_builder.build_typed_stop_recovery_prompt(stop_info)
    assert isinstance(prompt, str)
    assert "Current contract goal remains the same: ." in prompt

    # Case 2: Active intent exists, but `goal` attribute is missing
    active_intent_mock = MagicMock()
    del active_intent_mock.goal  # Ensure it's missing
    prompt_builder.state.active_intent = active_intent_mock
    prompt = prompt_builder.build_typed_stop_recovery_prompt(stop_info)
    assert isinstance(prompt, str)
    assert "Current contract goal remains the same: ." in prompt
