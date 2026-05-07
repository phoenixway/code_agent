"""
Central authority matrix for resolving conflicts between legacy and compiler-driven
protocol decisions.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class ProtocolAuthorityDecision:
    """
    Represents the outcome of the protocol authority resolution.
    """

    source: str  # "compiler" | "legacy" | "fallback"
    reason: str
    suppress_legacy_invalid_kind: bool
    dispatch_allowed: bool | None


COMPILER_INVALID_KIND_BY_CODE = {
    "E_UNCLOSED_THINK": "malformed_incomplete_think",
    "E_ACTION_INSIDE_THINK": "action_inside_think",
    "E_INTENT_INSIDE_THINK": "intent_inside_think",
    "E_FILE_CONTENT_INSIDE_THINK": "file_content_inside_think",
    "E_FILE_CONTENT_UNCLOSED": "malformed_incomplete_file_content",
    "E_MIXED_VISIBLE_TEXT_AND_CONTROL": "mixed_visible_text_and_control_protocol",
    "E_FILE_CONTENT_REQUIRES_ACTION": "file_content_must_follow_action",
    "E_ACTION_PAYLOAD_ARRAY": "action_payload_array",
    "E_ACTION_PAYLOAD_XML_FIELDS": "action_payload_xml_fields",
    "E_ACTION_PAYLOAD_TOOL_CODE": "action_payload_tool_code",
    "E_ACTION_PAYLOAD_NOT_OBJECT": "action_payload_not_object",
    "E_PROTOCOL_TAG_IN_JSON_STRING": "protocol_tag_in_json_string",
    "E_VISIBLE_TEXT_AFTER_ACTION": "mixed_visible_text_and_control_protocol",
    "E_VISIBLE_TEXT_AFTER_INTENT": "mixed_intent_transition_and_visible_answer",
    "E_MULTIPLE_INTENTS": "conflicting_intent_transitions",
}


COMPILER_ATOMIC_BUNDLE_ERROR_CODES = {
    "E_ATOMIC_BUNDLE_REQUIRES_EXACTLY_ONE_ACTION",
}


COMPILER_ACTION_PAYLOAD_ERROR_CODES = {
    "E_ACTION_PAYLOAD_ARRAY",
    "E_ACTION_PAYLOAD_NOT_OBJECT",
    "E_ACTION_PAYLOAD_XML_FIELDS",
    "E_ACTION_PAYLOAD_TOOL_CODE",
    "E_PROTOCOL_TAG_IN_JSON_STRING",
}


COMPILER_INTENT_COUNT_ERROR_CODES = {
    "E_MULTIPLE_INTENTS",
}


COMPILER_FILE_CONTENT_ERROR_CODES = {
    "E_FILE_CONTENT_REQUIRES_ACTION",
    "E_FILE_CONTENT_UNCLOSED",
}


COMPILER_TAGS_INSIDE_THINK_ERROR_CODES = {
    "E_ACTION_INSIDE_THINK",
    "E_INTENT_INSIDE_THINK",
    "E_FILE_CONTENT_INSIDE_THINK",
}


COMPILER_UNCLOSED_TAG_ERROR_CODES = {
    "E_UNCLOSED_THINK",
}


COMPILER_VISIBLE_TEXT_POSITION_ERROR_CODES = {
    "E_VISIBLE_TEXT_AFTER_ACTION",
    "E_VISIBLE_TEXT_AFTER_INTENT",
}


def compiler_action_array_hint(parsed_output, *, response_text: str, recovery_id: str) -> bool:
    legacy_invalid_kind = str(getattr(parsed_output, "invalid_kind", "") or "").strip()
    if legacy_invalid_kind == "action_payload_array":
        return True
    if recovery_id == "atomic_bundle_exactly_one_action":
        compact = "".join(str(response_text or "").split())
        if "<action>[" in compact.lower():
            return True
    return False


def compiler_invalid_kind_for_output(parsed_output) -> str:
    compiler_code = str(getattr(parsed_output, "compiler_error_code", "") or "").strip()
    if compiler_code == "E_ATOMIC_BUNDLE_REQUIRES_EXACTLY_ONE_ACTION":
        recovery_id = str(getattr(parsed_output, "compiler_recovery_id", "") or "").strip()
        response_text = str(getattr(parsed_output, "response", "") or "")
        if compiler_action_array_hint(parsed_output, response_text=response_text, recovery_id=recovery_id):
            return "action_payload_array"
        return "multiple_actions"
    return COMPILER_INVALID_KIND_BY_CODE.get(compiler_code, "")


def _is_compiler_valid_pre_action_text(parsed_output, parsed_action_count: int) -> bool:
    compiler_shape = str(getattr(parsed_output, "compiler_shape", "") or "").strip()
    compiler_error_code = str(getattr(parsed_output, "compiler_error_code", "") or "").strip()
    has_action = parsed_action_count > 0 or bool(getattr(parsed_output, "has_action_segment", False))
    ir = getattr(parsed_output, "compiler_ir", None)
    if ir and (getattr(ir, "has_think", False) or getattr(ir, "has_checkpoint", False)):
        return False
    return (
        str(getattr(parsed_output, "invalid_kind", "") or "").strip() == "mixed_visible_text_and_control_protocol"
        and compiler_shape == "PRE_ACTION_TEXT_AND_ACTION"
        and not compiler_error_code
        and has_action
    )


def resolve_protocol_authority(parsed_output, parsed_action_count: int) -> ProtocolAuthorityDecision:
    """
    Determines whether the compiler or legacy semantics should be authoritative for a given response.
    """
    if _is_compiler_valid_pre_action_text(parsed_output, parsed_action_count):
        return ProtocolAuthorityDecision(
            source="compiler",
            reason="compiler_valid_pre_action_text",
            suppress_legacy_invalid_kind=True,
            dispatch_allowed=True,
        )

    compiler_error_code = str(getattr(parsed_output, "compiler_error_code", "") or "").strip()
    if compiler_error_code in COMPILER_ACTION_PAYLOAD_ERROR_CODES:
        return ProtocolAuthorityDecision(
            source="compiler",
            reason="compiler_action_payload_diagnostic",
            suppress_legacy_invalid_kind=False,
            dispatch_allowed=False,
        )

    if compiler_error_code in COMPILER_FILE_CONTENT_ERROR_CODES:
        return ProtocolAuthorityDecision(
            source="compiler",
            reason="compiler_file_content_diagnostic",
            suppress_legacy_invalid_kind=False,
            dispatch_allowed=False,
        )

    if compiler_error_code in COMPILER_TAGS_INSIDE_THINK_ERROR_CODES:
        return ProtocolAuthorityDecision(
            source="compiler",
            reason="compiler_tag_inside_think_diagnostic",
            suppress_legacy_invalid_kind=False,
            dispatch_allowed=False,
        )

    if compiler_error_code in COMPILER_UNCLOSED_TAG_ERROR_CODES:
        return ProtocolAuthorityDecision(
            source="compiler",
            reason="compiler_unclosed_tag_diagnostic",
            suppress_legacy_invalid_kind=False,
            dispatch_allowed=False,
        )

    if compiler_error_code in COMPILER_VISIBLE_TEXT_POSITION_ERROR_CODES:
        return ProtocolAuthorityDecision(
            source="compiler",
            reason="compiler_visible_text_position_diagnostic",
            suppress_legacy_invalid_kind=False,
            dispatch_allowed=False,
        )

    if compiler_error_code in COMPILER_ATOMIC_BUNDLE_ERROR_CODES:
        return ProtocolAuthorityDecision(
            source="compiler",
            reason="compiler_atomic_bundle_diagnostic",
            suppress_legacy_invalid_kind=False,
            dispatch_allowed=False,
        )

    if compiler_error_code in COMPILER_INTENT_COUNT_ERROR_CODES:
        return ProtocolAuthorityDecision(
            source="compiler",
            reason="compiler_intent_count_diagnostic",
            suppress_legacy_invalid_kind=False,
            dispatch_allowed=False,
        )

    return ProtocolAuthorityDecision(
        source="legacy",
        reason="legacy_default",
        suppress_legacy_invalid_kind=False,
        dispatch_allowed=None,
    )
