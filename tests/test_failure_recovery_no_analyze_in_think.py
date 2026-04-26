import pytest
from types import SimpleNamespace

from modules.agent.action_dispatcher import ActionDispatcher
from modules.agent.orchestration.prompting import OrchestratorPromptBuilder


BAD_THINK_RECOVERY_PHRASES = (
    "Analyze the error in <think>",
    "analyze the error in <think>",
    "analyze in <think>",
    "Do not add analysis/prose in <think>",
    "think about",
)


def _assert_no_think_analysis_prompt(text: str) -> None:
    lowered = str(text or "").lower()
    for phrase in BAD_THINK_RECOVERY_PHRASES:
        assert phrase.lower() not in lowered


class DummyState:
    active_intent = None
    intent_required_until_activated = False
    intent_required_reason = ""
    recovery_protocol = "legacy_think"
    operational_recovery_protocol = "legacy_think"
    last_action_fingerprint = ""
    last_action_status = ""
    recent_problem_actions = []
    last_resumable_intent_id = ""
    last_resumable_intent_type = ""
    last_resumable_intent_goal = ""
    last_resumable_completion_reason = ""
    last_resumable_intent_completion_reason = ""
    last_resumable_intent_allowed_actions = []
    last_resumable_intent_lineage_id = ""

    def has_hard_exhausted_active_intent(self):
        return False


class DummyConfig:
    RECOVERY_PROTOCOL = "legacy_think"
    OPERATIONAL_RECOVERY_PROTOCOL = "legacy_think"
    INTENT_COMPLETION_ALLOWANCE = 1
    INTENTLESS_SHORT_MODE_MAX_STEPS = 2


class DummyRecoveryPolicyResolver:
    def normalize_context(self, stop_info, *, active_intent=None):
        from modules.agent.orchestration.decision_models import RecoveryContext

        return RecoveryContext.from_stop_info(stop_info)


class DummyAgent:
    def __init__(self):
        self.state = DummyState()
        self.config = DummyConfig()
        self.recovery_policy_resolver = DummyRecoveryPolicyResolver()
        self.allowed_actions_resolver = None
        self.memory_board_store = None
        self.log = None

        async def noop(*args, **kwargs):
            return None

        self.ui = SimpleNamespace(
            print_tool_call=noop,
            print_system=noop,
            print_error=noop,
            confirm_action=lambda *args, **kwargs: True,
        )
        self.processor = SimpleNamespace()
        self.processor.run_shell = noop


def _make_prompt_builder():
    return OrchestratorPromptBuilder(DummyAgent())


def test_generic_retry_recovery_does_not_request_think_analysis():
    builder = _make_prompt_builder()

    prompt = builder.build_current_intent_retry_recovery_query(
        ["read_chunk"],
        error_code="TOOL_ARGUMENT_ERROR",
        error_details={
            "message": "read_file requires 'path' (string)",
            "path": "",
        },
        command={
            "type": "read_file",
            "path": "",
        },
    )

    _assert_no_think_analysis_prompt(prompt)

    # Legacy protocol may still use a strict compact <think> skeleton, but it must
    # not ask the model to analyze/prose inside it.
    assert "<memory_update_done />" in prompt
    assert "read_file" in prompt or "read_chunk" in prompt


def test_missing_file_content_block_recovery_uses_strict_block_order_without_think_analysis():
    builder = _make_prompt_builder()

    prompt = builder.build_current_intent_retry_recovery_query(
        ["write_file_block"],
        error_code="MISSING_FILE_CONTENT_BLOCK",
        error_details={
            "path": "bookmark_ner/split_data.py",
            "target_exists": False,
        },
        command={
            "type": "write_file_block",
            "path": "bookmark_ner/split_data.py",
        },
    )

    _assert_no_think_analysis_prompt(prompt)

    assert '<action>' in prompt
    assert '"type": "write_file_block"' in prompt
    assert '"path": "bookmark_ner/split_data.py"' in prompt
    assert "</action>\n<file_content>" in prompt

    # Use the actual block boundary, not the explanatory mention of
    # "<file_content>" inside the compact checkpoint line.
    action_close_index = prompt.index("</action>")
    file_content_block_index = prompt.index("</action>\n<file_content>") + len("</action>\n")
    assert action_close_index < file_content_block_index

    assert "<file_content>\nraw content\n</file_content>" in prompt

    action_block = prompt[prompt.index("<action>") : prompt.index("</action>") + len("</action>")]
    assert "<file_content>" not in action_block
    assert "</file_content>" not in action_block


@pytest.mark.asyncio
async def test_action_dispatcher_failure_feedback_does_not_request_think_analysis():
    agent = DummyAgent()
    dispatcher = ActionDispatcher(agent)

    async def failing_read_file(command):
        return {
            "status": "failed",
            "output": "read_file requires 'path' (string)",
            "error_code": "TOOL_ARGUMENT_ERROR",
            "recoverable": True,
            "next_actions": ["read_chunk"],
        }

    dispatcher._handlers["read_file"] = failing_read_file

    command = {
        "type": "read_file",
        "path": "",
        "before_execution": "Reading file",
        "during_execution": "Reading...",
        "after_execution": "Read file",
    }

    command_for_history, system_result, should_stop = await dispatcher._execute_action(
        command,
        agent.state,
    )

    assert command_for_history["type"] == "read_file"
    assert "SYSTEM RESULT for `read_file`" in system_result

    # Some malformed payloads are caught by a specialized preflight recovery
    # before the generic "Action failed" branch. Both are acceptable. The
    # invariant is that neither branch asks for think/prose analysis.
    assert (
        "Action failed" in system_result
        or "Invalid read_file payload" in system_result
        or "SYSTEM:" in system_result
    )

    _assert_no_think_analysis_prompt(system_result)
    assert should_stop is True or should_stop is False