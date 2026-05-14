from types import SimpleNamespace

from modules.agent.action_dispatcher import ActionDispatcher
from modules.tools.action_schema import EDIT_FILE_SCHEMA, validate_tool_action_schema


class DummyLog:
    def debug(self, *_args, **_kwargs):
        pass


class DummyAgent:
    def __init__(self):
        self.ui = None
        self.processor = None
        self.config = SimpleNamespace()
        self.log = DummyLog()


class DummyState:
    def __init__(self, *, active_intent=None):
        self.active_intent = active_intent
        self.pending_loop_stop_info = None


class DummyIntent:
    def __init__(self, *, intent_type="MODIFY", allowed_actions=None):
        self.intent_type = intent_type
        self.allowed_actions = list(allowed_actions or [])


def test_edit_file_schema_rejects_line_range_fields():
    violation = validate_tool_action_schema(
        {
            "type": "edit_file",
            "path": "src/example.py",
            "start_line": 10,
            "end_line": 20,
            "replace_text": "x",
        }
    )

    assert violation is not None
    assert violation.reason == "malformed_edit_file_payload"
    assert violation.error_code == "MALFORMED_EDIT_FILE_PAYLOAD"
    assert "search_text" in violation.missing_fields
    assert "start_line" in violation.forbidden_fields
    assert "end_line" in violation.forbidden_fields
    assert "line ranges" in violation.message


def test_edit_file_schema_recommended_actions_come_from_structural_policy():
    assert EDIT_FILE_SCHEMA.recommended_actions == (
        "read_chunk",
        "read_file_skeleton",
        "extract_symbol",
        "replace_symbol",
        "edit_file",
        "write_file_block",
    )


def test_edit_file_schema_accepts_exact_replacement_contract():
    violation = validate_tool_action_schema(
        {
            "type": "edit_file",
            "path": "src/example.py",
            "search_text": "old",
            "replace_text": "new",
        }
    )

    assert violation is None


def test_dispatcher_schema_preflight_adds_write_file_block_for_modify_recovery():
    dispatcher = ActionDispatcher(DummyAgent())
    state = DummyState(
        active_intent=DummyIntent(
            intent_type="MODIFY",
            allowed_actions=["read_chunk", "edit_file"],
        )
    )

    stop = dispatcher._schema_validation_preflight(
        {
            "type": "edit_file",
            "path": "src/example.py",
            "start_line": 10,
            "end_line": 20,
            "replace_text": "x",
        },
        state,
    )

    assert stop is not None
    assert stop["reason"] == "malformed_edit_file_payload"
    assert stop["error_code"] == "MALFORMED_EDIT_FILE_PAYLOAD"
    assert stop["policy_allowed_actions"] == ["read_chunk", "extract_symbol", "replace_symbol", "edit_file", "write_file_block"]
    assert stop["policy_recommended_actions"] == ["read_chunk", "extract_symbol", "replace_symbol", "edit_file", "write_file_block"]
    assert stop["validation_snapshot"]["active_intent_type"] == "MODIFY"


def test_dispatcher_schema_preflight_does_not_recommend_write_file_block_for_non_modify_intent():
    dispatcher = ActionDispatcher(DummyAgent())
    state = DummyState(
        active_intent=DummyIntent(
            intent_type="INVESTIGATE",
            allowed_actions=["read_chunk", "edit_file"],
        )
    )

    stop = dispatcher._schema_validation_preflight(
        {
            "type": "edit_file",
            "path": "src/example.py",
            "start_line": 10,
            "replace_text": "x",
        },
        state,
    )

    assert stop is not None
    assert stop["policy_allowed_actions"] == ["read_chunk", "edit_file"]
    assert "write_file_block" not in stop["policy_allowed_actions"]


def test_dispatcher_schema_preflight_has_no_decision_for_valid_edit_file():
    dispatcher = ActionDispatcher(DummyAgent())
    state = DummyState(active_intent=DummyIntent(intent_type="MODIFY", allowed_actions=["edit_file"]))

    stop = dispatcher._schema_validation_preflight(
        {
            "type": "edit_file",
            "path": "src/example.py",
            "search_text": "old",
            "replace_text": "new",
        },
        state,
    )

    assert stop is None


def test_repeated_edit_failure_recovery_actions_add_write_file_block_for_modify():
    dispatcher = ActionDispatcher(DummyAgent())
    state = DummyState(
        active_intent=DummyIntent(
            intent_type="MODIFY",
            allowed_actions=["read_chunk", "read_file", "search_content", "edit_file"],
        )
    )

    actions = dispatcher._repeated_edit_failure_recovery_actions(state)

    assert actions == ["read_chunk", "extract_symbol", "replace_symbol", "read_file", "search_content", "edit_file", "write_file_block"]


def test_repeated_edit_failure_recovery_actions_do_not_add_write_file_block_for_non_modify():
    dispatcher = ActionDispatcher(DummyAgent())
    state = DummyState(
        active_intent=DummyIntent(
            intent_type="INVESTIGATE",
            allowed_actions=["read_chunk", "read_file", "search_content", "edit_file"],
        )
    )

    actions = dispatcher._repeated_edit_failure_recovery_actions(state)

    assert actions == ["read_chunk", "read_file", "search_content", "edit_file"]


def test_repeated_edit_failure_recovery_actions_respect_existing_non_modify_contract():
    dispatcher = ActionDispatcher(DummyAgent())
    state = DummyState(
        active_intent=DummyIntent(
            intent_type="SUMMARIZE",
            allowed_actions=["read_chunk", "search_content"],
        )
    )

    actions = dispatcher._repeated_edit_failure_recovery_actions(state)

    assert actions == ["read_chunk", "search_content"]
