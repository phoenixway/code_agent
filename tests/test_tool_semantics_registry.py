from modules.agent.intent_runtime import KNOWN_TOOL_ACTIONS
from modules.agent.config import AgentConfig


def test_new_mutating_tools_are_known_to_intent_runtime():
    assert "fuzzy_edit_file" in KNOWN_TOOL_ACTIONS
    assert "replace_line_range" in KNOWN_TOOL_ACTIONS


def test_new_mutating_tools_are_state_changing_ops():
    config = AgentConfig()
    assert "fuzzy_edit_file" in config.STATE_CHANGING_OPS
    assert "replace_line_range" in config.STATE_CHANGING_OPS
