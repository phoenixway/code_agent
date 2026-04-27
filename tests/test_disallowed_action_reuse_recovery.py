import pytest
from types import SimpleNamespace

from modules.agent.orchestration.prompting import OrchestratorPromptBuilder
from modules.agent.orchestration.recovery import RecoveryCoordinator


class DummyConfig:
    RECOVERY_PROTOCOL = "legacy_think"
    OPERATIONAL_RECOVERY_PROTOCOL = "legacy_think"
    INTENT_COMPLETION_ALLOWANCE = 1
    INTENTLESS_SHORT_MODE_MAX_STEPS = 2


class DummyState:
    def __init__(self):
        self.active_intent = SimpleNamespace(
            intent_id="optimistic_delete",
            intent_type="MODIFY",
            goal="Continue delete flow",
            allowed_actions=["edit_file", "read_chunk"],
            safe_steps_limit=10,
            step_count=0,
            retry_limit=2,
            retry_count=0,
        )
        self.last_disallowed_action_fingerprint = ""
        self.last_disallowed_action_repeat_count = 0
        self.last_repeated_disallowed_action_diagnostic = ""

    def has_hard_exhausted_active_intent(self):
        return False


class DummyRecoveryPolicyResolver:
    def normalize_context(self, stop_info, *, active_intent=None):
        from modules.agent.orchestration.decision_models import RecoveryContext

        return RecoveryContext.from_stop_info(stop_info)


class DummyUI:
    def __init__(self):
        self.system_messages = []

    async def print_system(self, message):
        self.system_messages.append(message)


class DummyAgent:
    def __init__(self):
        self.state = DummyState()
        self.config = DummyConfig()
        self.ui = DummyUI()
        self.log = None
        self.planner = None
        self.memory_board_store = None
        self.allowed_actions_resolver = None
        self.recovery_policy_resolver = DummyRecoveryPolicyResolver()


def _builder():
    return OrchestratorPromptBuilder(DummyAgent())


def test_first_write_file_block_disallowed_prompt_keeps_menu_and_legacy_phrases():
    builder = _builder()

    prompt = builder.build_intent_action_not_allowed_prompt(
        blocked_action="write_file_block",
        intent_id="optimistic_delete",
        intent_type="MODIFY",
        allowed_actions=["edit_file", "read_chunk"],
        repeated=False,
    )

    assert "Tool `write_file_block` is not allowed" in prompt
    assert "Either:" in prompt
    assert "allowed_actions including write_file_block" in prompt
    assert "Do not repeat the same disallowed action" in prompt
    assert "Do not include <action> with `write_file_block` until intent reuse is accepted." in prompt
    assert "Do not repeat write_file_block until reuse is accepted." in prompt


def test_investigate_edit_file_disallowed_prompt_keeps_work_type_hint_and_no_emit_phrase():
    builder = _builder()

    prompt = builder.build_intent_action_not_allowed_prompt(
        blocked_action="edit_file",
        intent_id="optimistic_delete",
        intent_type="INVESTIGATE",
        allowed_actions=["read_chunk", "search_content", "read_file_skeleton"],
        repeated=False,
    )

    assert "current intent is INVESTIGATE and cannot modify files" in prompt
    assert 'mode="reuse"' in prompt
    assert 'switch_reason="work_type_changed"' in prompt
    assert "Do not emit edit_file until reuse is accepted." in prompt
    assert "Do not include <action> with `edit_file` until intent reuse is accepted." in prompt


def test_repeated_disallowed_action_prompt_is_strict_reuse_only():
    builder = _builder()

    prompt = builder.build_intent_action_not_allowed_prompt(
        blocked_action="create_file",
        intent_id="optimistic_delete",
        intent_type="MODIFY",
        allowed_actions=["edit_file", "read_chunk"],
        repeated=True,
    )

    assert "Return only a top-level <intent mode=\"reuse\">...</intent>." in prompt
    assert "Do not include <action> until intent reuse is accepted." in prompt
    assert "Do not repeat create_file until reuse is accepted." in prompt
    assert "Either:" not in prompt


@pytest.mark.asyncio
async def test_recovery_repeated_disallowed_action_escalates_to_strict_then_stop():
    agent = DummyAgent()
    builder = OrchestratorPromptBuilder(agent)
    recovery = RecoveryCoordinator(agent, builder)

    stop_info = {
        "reason": "intent_action_not_allowed",
        "recoverable": True,
        "command": {"type": "write_file_block", "path": "a.py"},
        "intent_allowed_actions": ["edit_file", "read_chunk"],
        "next_actions_source": "intent",
    }

    first = await recovery.handle_defect_detector_stop(stop_info)
    assert first.continue_loop is True
    assert first.reason == "intent_action_not_allowed"
    assert "Either:" in first.next_query
    assert "Tool `write_file_block` is not allowed" in first.next_query

    second = await recovery.handle_defect_detector_stop(stop_info)
    assert second.continue_loop is True
    assert second.reason == "intent_action_not_allowed"
    assert "Return only a top-level <intent mode=\"reuse\">...</intent>." in second.next_query
    assert "Do not include <action> until intent reuse is accepted." in second.next_query
    assert "Either:" not in second.next_query

    third = await recovery.handle_defect_detector_stop(stop_info)
    assert third.stop_loop is True
    assert third.reason == "repeated_disallowed_action_loop"
    assert "repeated disallowed action loop" in agent.state.last_repeated_disallowed_action_diagnostic.lower()
    assert agent.ui.system_messages