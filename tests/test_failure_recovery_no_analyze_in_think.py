import pytest
from types import SimpleNamespace

from modules.agent.action_dispatcher import ActionDispatcher
from modules.agent.orchestration.prompts import OrchestratorPromptBuilder


BAD_THINK_RECOVERY_PHRASES = (
    "Analyze the error in <think>",
    "analyze the error in <think>",
    "analyze in <think>",
    "Do not add analysis/prose in <think>",
    "analysis/prose in <think>",
    "think about",
)


def _assert_no_think_analysis_prompt(text: str) -> None:
    lowered = str(text or "").lower()
    for phrase in BAD_THINK_RECOVERY_PHRASES:
        assert phrase.lower() not in lowered


def _assert_generic_failure_feedback_has_no_think_tag(text: str) -> None:
    """Generic tool-failure feedback must not mention <think> at all.

    Strict recovery prompts may still contain a compact legacy <think> skeleton.
    Generic tool failure system-results are different: mentioning <think> there
    re-primes the exact malformed-think loop we are trying to avoid.
    """
    _assert_no_think_analysis_prompt(text)
    assert "<think>" not in str(text or "").lower()
    assert "</think>" not in str(text or "").lower()


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
    pending_loop_stop_info = None
    state_machine = None

    def has_hard_exhausted_active_intent(self):
        return False

    def record_action_result(self, command, result, config):
        self.last_action_status = str(result.get("status") or "")
        if self.last_action_status in {"failed", "error"}:
            self.last_error_code = result.get("error_code")
            self.last_failed_action_result = dict(result)
        return {
            "same_action_repeats": 0,
            "same_error_repeats": 0,
            "defect_info": None,
        }

    def reset_retry_budgets(self, recoverable_budget, critical_budget):
        self.recoverable_retry_budget_remaining = recoverable_budget
        self.critical_retry_budget_remaining = critical_budget

    def consume_malformed_grace(self):
        return False

    def consume_retry_budget(self, recoverable):
        return True

    def consume_forbidden_action_if_matches(self, command):
        return False


class DummyConfig:
    RECOVERY_PROTOCOL = "legacy_think"
    OPERATIONAL_RECOVERY_PROTOCOL = "legacy_think"
    INTENT_COMPLETION_ALLOWANCE = 1
    INTENTLESS_SHORT_MODE_MAX_STEPS = 2
    LOOP_ERROR_REPEAT_THRESHOLD = 2
    READ_ONLY_REPEAT_THRESHOLD = 3
    RECOVERABLE_ERROR_RETRY_BUDGET = 2
    CRITICAL_ERROR_RETRY_BUDGET = 1
    STATE_CHANGING_OPS = {
        "create_file",
        "write_file",
        "write_file_block",
        "append_file_block",
        "edit_file",
        "replace",
        "delete_file",
        "git_add",
        "git_commit",
        "git_checkout",
    }


class DummyRecoveryPolicyResolver:
    def normalize_context(self, stop_info, *, active_intent=None):
        from modules.agent.orchestration.shared.decision_models import RecoveryContext

        return RecoveryContext.from_stop_info(stop_info)


class DummyAgent:
    def __init__(self):
        self.state = DummyState()
        self.config = DummyConfig()
        self.recovery_policy_resolver = DummyRecoveryPolicyResolver()
        self.allowed_actions_resolver = None
        self.memory_board_store = None
        self.history = None
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
async def test_action_dispatcher_specialized_failure_feedback_does_not_request_think_analysis():
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

    # This malformed payload is caught by a specialized preflight recovery before
    # the generic "Action failed" branch. It still must not ask for think/prose
    # analysis.
    assert "Invalid read_file payload" in system_result or "SYSTEM:" in system_result
    _assert_no_think_analysis_prompt(system_result)
    assert should_stop is True or should_stop is False


@pytest.mark.asyncio
async def test_action_dispatcher_generic_failure_feedback_does_not_mention_think_tag():
    agent = DummyAgent()
    dispatcher = ActionDispatcher(agent)

    async def failing_read_chunk(command):
        return {
            "status": "failed",
            "output": "File not found: modules/agent/missing.py",
            "error_code": "NOT_FOUND",
            "recoverable": True,
            "next_actions": ["list_directory", "search_files", "read_file"],
        }

    dispatcher._handlers["read_chunk"] = failing_read_chunk

    command = {
        "type": "read_chunk",
        "path": "modules/agent/missing.py",
        "start_line": 1,
        "end_line": 5,
        "before_execution": "Reading chunk",
        "during_execution": "Reading...",
        "after_execution": "Read chunk",
    }

    command_for_history, system_result, should_stop = await dispatcher._execute_action(
        command,
        agent.state,
    )

    assert command_for_history["type"] == "read_chunk"
    assert "SYSTEM RESULT for `read_chunk`" in system_result
    assert "Action failed" in system_result

    _assert_generic_failure_feedback_has_no_think_tag(system_result)
    assert "Use the runtime recovery payload below" in system_result
    assert should_stop is False


@pytest.mark.asyncio
async def test_action_dispatcher_invalid_search_path_forces_root_discovery_feedback():
    agent = DummyAgent()
    dispatcher = ActionDispatcher(agent)

    async def failing_search_files(command):
        return {
            "status": "failed",
            "output": (
                "Search path 'app/src/main/java/com/romankozak/forward/' is not a directory.\n"
                "No valid search paths given."
            ),
            "error_code": "NOT_FOUND",
            "recoverable": True,
            "next_actions": ["list_directory", "search_files", "create_file"],
        }

    dispatcher._handlers["search_files"] = failing_search_files

    command = {
        "type": "search_files",
        "path": "app/src/main/java/com/romankozak/forward/",
        "pattern": "Forward",
        "before_execution": "Searching files",
        "during_execution": "Searching...",
        "after_execution": "Search files",
    }

    command_for_history, system_result, should_stop = await dispatcher._execute_action(
        command,
        agent.state,
    )

    assert command_for_history["type"] == "search_files"
    assert "SYSTEM RESULT for `search_files`" in system_result
    assert "The previous filesystem path is invalid" in system_result
    assert "Do not reuse the failed path" in system_result
    assert "Do not derive sibling, child, or package paths" in system_result
    assert "Do not guess Android/Kotlin package roots" in system_result
    assert "invalid_path=app/src/main/java/com/romankozak/forward/" in system_result
    assert "recommended_next_actions=list_directory:.,search_files:.,search_content:." in system_result
    assert should_stop is False
