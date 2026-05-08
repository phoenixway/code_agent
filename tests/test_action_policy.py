"""Characterization tests for ActionPolicyHandler."""

from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest

from modules.agent.orchestration.runtime.action_policy import ActionPolicyHandler


class MockAgent:
    def __init__(self):
        self.state = SimpleNamespace()
        self.config = {}


class MockIntentGuard:
    def __init__(self):
        self.action_requires_intent = MagicMock(return_value=(False, ""))


class MockPromptBuilder:
    def __init__(self):
        self.build_noop_edit_prompt = MagicMock(return_value="noop edit prompt")
        self.build_intent_payload_inside_action_prompt = MagicMock(return_value="intent in action prompt")


@pytest.fixture
def action_policy_harness():
    agent = MockAgent()
    intent_guard = MockIntentGuard()
    prompt_builder = MockPromptBuilder()
    handler = ActionPolicyHandler(agent, intent_guard, prompt_builder)
    handler.state_view = MagicMock()
    handler.state_view.has_pending_edit_mismatch_for_path.return_value = False
    handler.stage_logger = MagicMock()
    return handler


def test_validate_atomic_bundle_rejects_multiple_commands(action_policy_harness, monkeypatch):
    """validate_atomic_bundle_action rejects if there are multiple commands."""
    monkeypatch.setattr(action_policy_harness, "_atomic_bundle_candidate_commands", MagicMock(return_value=[{}, {}]))
    result = action_policy_harness.validate_atomic_bundle_action(ctx=None, segments=[], proposed_active_intent=None)
    assert not result.ok
    assert result.reason == "atomic_bundle_requires_exactly_one_action"
    assert "exactly one valid <action> block" in result.details["message"]


def test_validate_atomic_bundle_rejects_noop_edit(action_policy_harness, monkeypatch):
    """validate_atomic_bundle_action rejects no-op edits via shape guard."""
    command = {"type": "edit_file", "search_text": "foo", "replace_text": "foo"}
    monkeypatch.setattr(action_policy_harness, "_atomic_bundle_candidate_commands", MagicMock(return_value=[command]))

    result = action_policy_harness.validate_atomic_bundle_action(ctx=None, segments=[], proposed_active_intent=None)

    assert not result.ok
    assert result.reason == "noop_edit"
    assert result.details["message"] == "noop edit prompt"
    assert result.details["blocked_action"] == "edit_file"


def test_validate_atomic_bundle_rejects_missing_file_content(action_policy_harness, monkeypatch):
    """validate_atomic_bundle_action rejects write_file_block without file_content."""
    command = {"type": "write_file_block", "path": "test.txt"}
    monkeypatch.setattr(action_policy_harness, "_atomic_bundle_candidate_commands", MagicMock(return_value=[command]))

    result = action_policy_harness.validate_atomic_bundle_action(ctx=None, segments=[], proposed_active_intent=None)

    assert not result.ok
    assert result.reason == "missing_file_content_block"
    assert "requires a complete <file_content>" in result.details["message"]
    assert result.details["blocked_action"] == "write_file_block"


def test_validate_atomic_bundle_rejects_if_intent_required(action_policy_harness, monkeypatch):
    """validate_atomic_bundle_action rejects if intent is required but not satisfied."""
    command = {"type": "some_action"}
    monkeypatch.setattr(action_policy_harness, "_atomic_bundle_candidate_commands", MagicMock(return_value=[command]))
    action_policy_harness.intent_guard.action_requires_intent.return_value = (True, "intent_action_not_allowed")
    proposed_intent = SimpleNamespace(allowed_actions=["other_action"])

    result = action_policy_harness.validate_atomic_bundle_action(
        ctx=SimpleNamespace(user_input=""), segments=[], proposed_active_intent=proposed_intent
    )

    assert not result.ok
    assert result.reason == "intent_action_not_allowed"
    assert result.details["blocked_action"] == "some_action"
    assert result.details["allowed_actions"] == ["other_action"]


def test_validate_atomic_bundle_rejects_on_pre_action_check_fail(action_policy_harness, monkeypatch):
    """validate_atomic_bundle_action rejects if pre_action_check fails."""
    command = {"type": "some_action"}
    monkeypatch.setattr(action_policy_harness, "_atomic_bundle_candidate_commands", MagicMock(return_value=[command]))
    stop_info = {"reason": "pre_action_check_failed", "message": "some error"}

    mock_intent_runtime_instance = MagicMock()
    mock_intent_runtime_instance.pre_action_check.return_value = stop_info
    mock_intent_runtime_class = MagicMock(return_value=mock_intent_runtime_instance)
    monkeypatch.setattr("modules.agent.orchestration.runtime.action_policy.IntentRuntime", mock_intent_runtime_class)

    result = action_policy_harness.validate_atomic_bundle_action(
        ctx=SimpleNamespace(user_input=""), segments=[], proposed_active_intent=None
    )

    assert not result.ok
    assert result.reason == "pre_action_check_failed"
    assert result.details["message"] == "some error"
    assert result.details["blocked_action"] == "some_action"


def test_validate_atomic_bundle_passes_when_all_checks_ok(action_policy_harness, monkeypatch):
    """validate_atomic_bundle_action returns ok=True when all checks pass."""
    command = {"type": "some_action"}
    monkeypatch.setattr(action_policy_harness, "_atomic_bundle_candidate_commands", MagicMock(return_value=[command]))

    mock_intent_runtime_instance = MagicMock()
    mock_intent_runtime_instance.pre_action_check.return_value = None
    mock_intent_runtime_class = MagicMock(return_value=mock_intent_runtime_instance)
    monkeypatch.setattr("modules.agent.orchestration.runtime.action_policy.IntentRuntime", mock_intent_runtime_class)

    result = action_policy_harness.validate_atomic_bundle_action(
        ctx=SimpleNamespace(user_input=""), segments=[], proposed_active_intent=None
    )

    assert result.ok
