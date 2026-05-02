
import pytest
from types import SimpleNamespace

from modules.agent.orchestration.decision_models import ParsedModelOutput
from modules.agent.orchestration.output_recovery import ModelOutputRecoveryHandler
from modules.agent.orchestration.parsing import IntentResponseParser
from modules.agent.orchestration.prompting import OrchestratorPromptBuilder


class DummySegment:
    def __init__(self, type_, content):
        self.type = type_
        self.content = content


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

    def get_stop_reason_count(self, reason):
        return 0


class DummyPromptBuilder:
    def build_action_payload_array_prompt(self):
        return "ARRAY PAYLOAD PROMPT"

    def build_multiple_actions_prompt(self):
        return "MULTIPLE ACTIONS PROMPT"


class DummyAgent:
    def __init__(self):
        self.state = DummyState()
        self.config = SimpleNamespace()
        self.log = None


def test_single_action_block_with_json_array_gets_specific_invalid_kind():
    response = """
<think>! Need several reads. ? Must choose one. → incorrectly batch.</think>
<memory_update_done />
<action>
[
  {"type": "read_file_skeleton", "path": "modules/agent/state_manager.py"},
  {"type": "read_file_skeleton", "path": "modules/history.py"}
]
</action>
""".strip()

    parsed = IntentResponseParser().classify(response, segments=[])

    assert parsed.has_action_tag is True
    assert parsed.invalid_kind == "action_payload_array"
    assert parsed.invalid_kind != "multiple_actions"
    assert parsed.invalid_kind != "malformed_action"


def test_multiple_top_level_state_changing_action_blocks_still_get_multiple_actions():
    response = """
<think>! Need two edits. ? Must choose one. → incorrectly emit two actions.</think>
<memory_update_done />
<action>{"type": "edit_file", "path": "modules/a.py", "search_text": "old", "replace_text": "new"}</action>
<action>{"type": "edit_file", "path": "modules/b.py", "search_text": "old", "replace_text": "new"}</action>
""".strip()
    segments = [
        DummySegment("action", {"type": "edit_file", "path": "modules/a.py", "search_text": "old", "replace_text": "new"}),
        DummySegment("action", {"type": "edit_file", "path": "modules/b.py", "search_text": "old", "replace_text": "new"}),
    ]

    parsed = IntentResponseParser().classify(response, segments)

    assert parsed.invalid_kind == "multiple_actions"


def test_multiple_top_level_read_only_action_blocks_are_not_multiple_actions():
    response = """
<think>! Need two reads. ? Need current file states. → read both files.</think>
<memory_update_done />
<action>{"type": "read_file_skeleton", "path": "modules/agent/state_manager.py"}</action>
<action>{"type": "read_file_skeleton", "path": "modules/history.py"}</action>
""".strip()
    segments = [
        DummySegment("action", {"type": "read_file_skeleton", "path": "modules/agent/state_manager.py"}),
        DummySegment("action", {"type": "read_file_skeleton", "path": "modules/history.py"}),
    ]

    parsed = IntentResponseParser().classify(response, segments)

    assert parsed.invalid_kind == ""


@pytest.mark.asyncio
async def test_output_recovery_uses_action_array_prompt_not_multiple_action_prompt():
    handler = ModelOutputRecoveryHandler(
        DummyAgent(),
        DummyPromptBuilder(),
    )
    parsed = ParsedModelOutput(
        response='<action>[{"type":"read_file"},{"type":"read_chunk"}]</action>',
        invalid_kind="action_payload_array",
        has_action_tag=True,
        has_action_segment=False,
        segments=[],
    )

    decision = await handler.decide(
        parsed,
        malformed_action_retries=0,
        audit_marker_retries=0,
    )

    assert decision.handled is True
    assert decision.continue_loop is True
    assert decision.next_query == "ARRAY PAYLOAD PROMPT"
    assert decision.reason == "action_payload_array"
    assert decision.next_query != "MULTIPLE ACTIONS PROMPT"


def test_action_array_prompt_mentions_separate_read_only_batch_rule():
    prompt = OrchestratorPromptBuilder(
        SimpleNamespace(
            state=SimpleNamespace(active_intent=None),
            config=SimpleNamespace(),
            planner=None,
            memory_board_store=None,
        )
    ).build_action_payload_array_prompt()

    assert "one JSON object" in prompt
    assert "2-4 separate top-level <action> blocks" in prompt
    assert "allowed only when every action is read-only and already narrowed" in prompt
    assert "State-changing actions must remain single." in prompt
