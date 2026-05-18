"""Declarative protocol specification shared by compiler stages."""

from __future__ import annotations

from .models import BlockSpec, ConstraintSpec, EnumSpec, ErrorSpec, PayloadSpec, ProtocolSpec, ShapeSpec


PROTOCOL_SPEC = ProtocolSpec(
    version="0.1.0",
    blocks={
        "think": BlockSpec(name="think", kind="closed", payload=PayloadSpec(type="raw_text")),
        "intent": BlockSpec(
            name="intent",
            kind="closed",
            attrs={"mode": EnumSpec(("activate", "complete", "reuse", "replace"))},
            payload=PayloadSpec(type="json"),
        ),
        "action": BlockSpec(name="action", kind="closed", payload=PayloadSpec(type="json")),
        "file_content": BlockSpec(name="file_content", kind="closed", payload=PayloadSpec(type="raw_file")),
        "memory_update_done": BlockSpec(name="memory_update_done", kind="self_closing"),
        "plan_review_done": BlockSpec(name="plan_review_done", kind="self_closing"),
        "fact": BlockSpec(name="fact", kind="closed", payload=PayloadSpec(type="text")),
        "finding": BlockSpec(name="finding", kind="closed", payload=PayloadSpec(type="text")),
        "decision": BlockSpec(name="decision", kind="closed", payload=PayloadSpec(type="text")),
        "preference": BlockSpec(name="preference", kind="closed", payload=PayloadSpec(type="text")),
        "path": BlockSpec(name="path", kind="closed", payload=PayloadSpec(type="text")),
        "progress": BlockSpec(name="progress", kind="closed", payload=PayloadSpec(type="text")),
        "memory_review": BlockSpec(name="memory_review", kind="self_closing"),
        "subgoal": BlockSpec(name="subgoal", kind="closed", payload=PayloadSpec(type="text")),
    },
    shapes={
        "CHECKPOINT_ONLY": ShapeSpec(
            name="CHECKPOINT_ONLY",
            sequence=("think?", "board*", "memory_update_done?"),
        ),
        "PURE_PLAINTEXT": ShapeSpec(name="PURE_PLAINTEXT", sequence=("think?", "visible_text*")),
        "SUBGOAL_WITH_TEXT": ShapeSpec(
            name="SUBGOAL_WITH_TEXT",
            sequence=("think?", "board*", "memory_update_done?", "visible_text+"),
        ),
        "PLAINTEXT_ONLY": ShapeSpec(name="PLAINTEXT_ONLY", sequence=("visible_text*",)),
        "MEMORY_TEXT": ShapeSpec(
            name="MEMORY_TEXT",
            sequence=("think?", "board*", "memory_update_done?", "visible_text+"),
        ),
        "ACTION_ONLY": ShapeSpec(
            name="ACTION_ONLY",
            sequence=("think?", "board*", "memory_update_done?", "action", "file_content?"),
            constraints=("no_visible_text", "single_action_object"),
        ),
        "READ_ONLY_BATCH_CANDIDATE": ShapeSpec(
            name="READ_ONLY_BATCH_CANDIDATE",
            sequence=("think?", "board*", "memory_update_done?", "action", "action+"),
            constraints=("no_intent", "read_only_batch_only", "no_visible_text"),
        ),
        "PRE_ACTION_TEXT_AND_ACTION": ShapeSpec(
            name="PRE_ACTION_TEXT_AND_ACTION",
            sequence=("think?", "board*", "memory_update_done?", "visible_text+", "action", "file_content?"),
            constraints=("no_intent", "single_action_object", "no_text_after_action"),
        ),
        "INTENT_ONLY": ShapeSpec(
            name="INTENT_ONLY",
            sequence=("think?", "board*", "memory_update_done?", "intent"),
            constraints=("exactly_one_intent", "no_visible_text"),
        ),
        "INTENT_ACTION_BUNDLE": ShapeSpec(
            name="INTENT_ACTION_BUNDLE",
            sequence=("think?", "board*", "memory_update_done?", "intent", "action", "file_content?"),
            constraints=(
                "exactly_one_intent",
                "exactly_one_action",
                "atomic_all_or_nothing",
                "no_visible_text",
                "file_content_only_for_write_action",
            ),
        ),
        "INTENT_COMPLETE_WITH_TEXT": ShapeSpec(
            name="INTENT_COMPLETE_WITH_TEXT",
            sequence=("think?", "board*", "memory_update_done?", "intent_complete", "visible_text+"),
        ),
        "INVALID": ShapeSpec(name="INVALID", sequence=()),
    },
    constraints=(
        ConstraintSpec(
            id="atomic_bundle_requires_exactly_one_action",
            phase="shape",
            applies_to="INTENT_ACTION_BUNDLE",
            error_code="E_ATOMIC_BUNDLE_REQUIRES_EXACTLY_ONE_ACTION",
        ),
        ConstraintSpec(
            id="mixed_visible_text_and_control",
            phase="shape",
            applies_to="ALL",
            error_code="E_MIXED_VISIBLE_TEXT_AND_CONTROL",
        ),
        ConstraintSpec(
            id="file_content_requires_action",
            phase="shape",
            applies_to="ALL",
            error_code="E_FILE_CONTENT_REQUIRES_ACTION",
        ),
        ConstraintSpec(
            id="visible_text_after_action",
            phase="shape",
            applies_to="ALL",
            error_code="E_VISIBLE_TEXT_AFTER_ACTION",
        ),
    ),
    errors={
        "E_UNCLOSED_THINK": ErrorSpec(
            code="E_UNCLOSED_THINK",
            phase="parse",
            recovery_id="unclosed_think",
            default_message="Response opened <think> but did not close it.",
        ),
        "E_ACTION_INSIDE_THINK": ErrorSpec(
            code="E_ACTION_INSIDE_THINK",
            phase="parse",
            recovery_id="action_inside_think",
            default_message="Protocol action block appeared inside an open <think> block.",
        ),
        "E_INTENT_INSIDE_THINK": ErrorSpec(
            code="E_INTENT_INSIDE_THINK",
            phase="parse",
            recovery_id="intent_inside_think",
            default_message="Protocol intent block appeared inside an open <think> block.",
        ),
        "E_FILE_CONTENT_INSIDE_THINK": ErrorSpec(
            code="E_FILE_CONTENT_INSIDE_THINK",
            phase="parse",
            recovery_id="file_content_inside_think",
            default_message="Protocol file content block appeared inside an open <think> block.",
        ),
        "E_MEMORY_TAG_INSIDE_THINK": ErrorSpec(
            code="E_MEMORY_TAG_INSIDE_THINK",
            phase="parse",
            recovery_id="memory_tag_inside_think",
            default_message="Memory or subgoal tag appeared inside an open <think> block.",
        ),
        "E_ACTION_JSON_INVALID": ErrorSpec(
            code="E_ACTION_JSON_INVALID",
            phase="parse",
            recovery_id="action_json_invalid",
            default_message="Action payload is not valid JSON.",
        ),
        "E_ACTION_PAYLOAD_ARRAY": ErrorSpec(
            code="E_ACTION_PAYLOAD_ARRAY",
            phase="parse",
            recovery_id="action_payload_array",
            default_message="Action payload must be a JSON object, not an array.",
        ),
        "E_ACTION_PAYLOAD_XML_FIELDS": ErrorSpec(
            code="E_ACTION_PAYLOAD_XML_FIELDS",
            phase="parse",
            recovery_id="action_payload_xml_fields",
            default_message="Action payload appears to be XML fields, not a JSON object.",
        ),
        "E_ACTION_PAYLOAD_TOOL_CODE": ErrorSpec(
            code="E_ACTION_PAYLOAD_TOOL_CODE",
            phase="parse",
            recovery_id="action_payload_tool_code",
            default_message="Action payload appears to be raw tool code, not a JSON object.",
        ),
        "E_XML_TOOL_SHORTHAND": ErrorSpec(
            code="E_XML_TOOL_SHORTHAND",
            phase="parse",
            recovery_id="xml_tool_shorthand",
            default_message="XML tool shorthand is not executable. Use canonical <action>{...}</action> JSON protocol.",
        ),
        "E_FENCED_PROTOCOL_BLOCK": ErrorSpec(
            code="E_FENCED_PROTOCOL_BLOCK",
            phase="parse",
            recovery_id="fenced_protocol_block",
            default_message="Protocol block inside markdown fence is not executable.",
        ),
        "E_ACTION_PAYLOAD_NOT_OBJECT": ErrorSpec(
            code="E_ACTION_PAYLOAD_NOT_OBJECT",
            phase="parse",
            recovery_id="action_payload_not_object",
            default_message="Action payload must be a JSON object.",
        ),
        "E_PROTOCOL_TAG_IN_JSON_STRING": ErrorSpec(
            code="E_PROTOCOL_TAG_IN_JSON_STRING",
            phase="parse",
            recovery_id="protocol_tag_in_json_string",
            default_message="Protocol tag appeared inside a JSON string value.",
        ),
        "E_INTENT_JSON_INVALID": ErrorSpec(
            code="E_INTENT_JSON_INVALID",
            phase="parse",
            recovery_id="intent_json_invalid",
            default_message="Intent payload is not valid JSON.",
        ),
        "E_FILE_CONTENT_UNCLOSED": ErrorSpec(
            code="E_FILE_CONTENT_UNCLOSED",
            phase="parse",
            recovery_id="file_content_unclosed",
            default_message="File content block was not closed.",
        ),
        "E_FILE_CONTENT_ACTION_MISMATCH": ErrorSpec(
            code="E_FILE_CONTENT_ACTION_MISMATCH",
            phase="shape",
            recovery_id="file_content_must_follow_action",
            default_message="File content can only be paired with a single action that requires it, like write_file_block.",
        ),
        "E_INTENT_COMPLETE_WITH_ACTION": ErrorSpec(
            code="E_INTENT_COMPLETE_WITH_ACTION",
            phase="shape",
            recovery_id="intent_complete_with_action_not_allowed",
            default_message="A complete intent transition cannot be combined with an action.",
        ),
        "E_AMBIGUOUS_PROTOCOL_SYNTAX": ErrorSpec(
            code="E_AMBIGUOUS_PROTOCOL_SYNTAX",
            phase="parse",
            recovery_id="ambiguous_protocol_syntax",
            default_message="Protocol-like markup is ambiguous in this position.",
        ),
        "E_MIXED_VISIBLE_TEXT_AND_CONTROL": ErrorSpec(
            code="E_MIXED_VISIBLE_TEXT_AND_CONTROL",
            phase="shape",
            recovery_id="mixed_visible_control",
            default_message="Visible text cannot be mixed with control protocol in this shape.",
        ),
        "E_ATOMIC_BUNDLE_REQUIRES_EXACTLY_ONE_ACTION": ErrorSpec(
            code="E_ATOMIC_BUNDLE_REQUIRES_EXACTLY_ONE_ACTION",
            phase="shape",
            recovery_id="atomic_bundle_exactly_one_action",
            default_message="Atomic intent/action bundles require exactly one action.",
        ),
        "E_MULTIPLE_INTENTS": ErrorSpec(
            code="E_MULTIPLE_INTENTS",
            phase="shape",
            recovery_id="conflicting_intent_transitions",
            default_message="Response cannot contain multiple intent transitions.",
        ),
        "E_VISIBLE_TEXT_AFTER_ACTION": ErrorSpec(
            code="E_VISIBLE_TEXT_AFTER_ACTION",
            phase="shape",
            recovery_id="visible_text_after_action",
            default_message="Visible text cannot appear after an action.",
        ),
        "E_VISIBLE_TEXT_AFTER_INTENT": ErrorSpec(
            code="E_VISIBLE_TEXT_AFTER_INTENT",
            phase="shape",
            recovery_id="mixed_intent_transition_and_visible_answer",
            default_message="Visible text cannot appear after an intent transition.",
        ),
        "E_FILE_CONTENT_REQUIRES_ACTION": ErrorSpec(
            code="E_FILE_CONTENT_REQUIRES_ACTION",
            phase="shape",
            recovery_id="file_content_must_follow_action",
            default_message="File content cannot appear without an action, must follow it, and be paired correctly.",
        ),
    },
)
