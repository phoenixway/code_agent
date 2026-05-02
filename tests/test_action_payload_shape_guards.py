from types import SimpleNamespace

from modules.agent.orchestration.parsers import IntentResponseParser


def _segment(type_, content=None):
    return SimpleNamespace(type=type_, content=content)


def test_xml_style_write_file_block_action_payload_is_rejected_even_if_parser_recovers_action_segment():
    response = """<think>! Need write. ? Payload shape. → write block.</think>
<memory_update_done />
<action>
  <type>write_file_block</type>
  <path>bookmark_ner/split_data.py</path>
  <overwrite>true</overwrite>
</action>
<file_content>
print("hello")
</file_content>
"""

    # Simulate the dangerous case from the dump: a lower-level parser partially
    # recovers an action dict even though the raw <action> body was not JSON.
    segments = [
        _segment("thought", "! Need write. ? Payload shape. → write block."),
        _segment("action", {"type": "write_file_block"}),
        _segment("file_content", 'print("hello")'),
    ]

    parsed = IntentResponseParser().classify(response, segments)

    assert parsed.has_action_tag is True
    assert parsed.has_action_segment is True
    assert parsed.invalid_kind == "malformed_action"


def test_intent_inside_action_is_rejected_when_it_is_raw_markup():
    response = """<think>! Intent budget exhausted. ? Need reuse. → emit intent.</think>
<memory_update_done />
<action>
<intent mode="reuse">
{"intent_id":"x","mode":"reuse","requested_steps":4}
</intent>
</action>
"""

    segments = [
        _segment("thought", "! Intent budget exhausted. ? Need reuse. → emit intent."),
        _segment("action", {"type": "intent"}),
    ]

    parsed = IntentResponseParser().classify(response, segments)

    assert parsed.invalid_kind == "malformed_action"


def test_tool_code_inside_action_is_rejected_when_it_is_raw_markup():
    response = """<think>! Need edit. ? Tool format. → edit.</think>
<memory_update_done />
<action>
<tool_code>
edit_file(path="x.py", search_text="a", replace_text="b")
</tool_code>
</action>
"""

    segments = [
        _segment("thought", "! Need edit. ? Tool format. → edit."),
        _segment("action", {"type": "tool_code"}),
    ]

    parsed = IntentResponseParser().classify(response, segments)

    assert parsed.invalid_kind == "malformed_action"


def test_valid_json_write_file_block_action_with_following_file_content_is_accepted():
    response = """<think>! Need write. ? Raw body. → write_file_block.</think>
<memory_update_done />
<action>
{
  "type": "write_file_block",
  "path": "bookmark_ner/split_data.py",
  "overwrite": true
}
</action>
<file_content>
print("hello")
</file_content>
"""

    segments = [
        _segment("thought", "! Need write. ? Raw body. → write_file_block."),
        _segment(
            "action",
            {
                "type": "write_file_block",
                "path": "bookmark_ner/split_data.py",
                "overwrite": True,
            },
        ),
        _segment("file_content", 'print("hello")'),
    ]

    parsed = IntentResponseParser().classify(response, segments)

    assert parsed.invalid_kind == ""
    assert parsed.has_action_segment is True


def test_valid_json_action_may_contain_intent_like_text_inside_string_values():
    response = """<think>! Need echo. ? Payload string. → run_shell.</think>
<memory_update_done />
<action>
{
  "type": "run_shell",
  "command": "printf '%s\\n' '<intent mode=\\"reuse\\">not control</intent>'",
  "before_execution": "Testing quoted protocol text",
  "during_execution": "Running...",
  "after_execution": "Done"
}
</action>
"""

    segments = [
        _segment("thought", "! Need echo. ? Payload string. → run_shell."),
        _segment(
            "action",
            {
                "type": "run_shell",
                "command": "printf '%s\\n' '<intent mode=\"reuse\">not control</intent>'",
            },
        ),
    ]

    parsed = IntentResponseParser().classify(response, segments)

    assert parsed.invalid_kind == ""


def test_valid_json_action_may_contain_xml_like_file_content_examples_inside_string_values():
    response = """<think>! Need create. ? Content contains examples. → create_file.</think>
<memory_update_done />
<action>
{
  "type": "create_file",
  "path": "notes.txt",
  "content": "Example: <type>write_file_block</type> and <path>x.py</path> are just text here."
}
</action>
"""

    segments = [
        _segment("thought", "! Need create. ? Content contains examples. → create_file."),
        _segment(
            "action",
            {
                "type": "create_file",
                "path": "notes.txt",
                "content": "Example: <type>write_file_block</type> and <path>x.py</path> are just text here.",
            },
        ),
    ]

    parsed = IntentResponseParser().classify(response, segments)

    assert parsed.invalid_kind == ""


def test_json_action_without_type_action_or_command_is_rejected():
    response = """<think>! Need action. ? Missing tool type. → reject.</think>
<memory_update_done />
<action>
{
  "path": "x.py"
}
</action>
"""

    segments = [_segment("action", {"path": "x.py"})]

    parsed = IntentResponseParser().classify(response, segments)

    assert parsed.invalid_kind == "malformed_action"


def test_json_array_action_payload_is_rejected():
    response = """<think>! Need action. ? Payload is array. → reject.</think>
<memory_update_done />
<action>
[
  {"type": "read_file", "path": "a.py"}
]
</action>
"""

    segments = [_segment("action", [{"type": "read_file", "path": "a.py"}])]

    parsed = IntentResponseParser().classify(response, segments)

    assert parsed.invalid_kind == "action_payload_array"