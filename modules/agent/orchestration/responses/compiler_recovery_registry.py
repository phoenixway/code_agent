"""Registry of compiler-driven recovery strategies."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class CompilerRecoveryStrategy:
    id: str
    error_codes: tuple[str, ...]
    recovery_ids: tuple[str, ...]
    invalid_kind: str
    handler_key: str
    allowed_next_shapes: tuple[str, ...] = ()
    forbidden_next_patterns: tuple[str, ...] = ()


class CompilerRecoveryRegistry:
    def __init__(self):
        self._strategies = (
            CompilerRecoveryStrategy(
                id="unclosed_think",
                error_codes=("E_UNCLOSED_THINK",),
                recovery_ids=("unclosed_think",),
                invalid_kind="malformed_incomplete_think",
                handler_key="malformed_think",
                allowed_next_shapes=("ACTION_ONLY", "INTENT_ONLY", "INTENT_ACTION_BUNDLE", "PLAINTEXT_ONLY"),
            ),
            CompilerRecoveryStrategy(
                id="action_inside_think",
                error_codes=("E_ACTION_INSIDE_THINK",),
                recovery_ids=("action_inside_think",),
                invalid_kind="action_inside_think",
                handler_key="malformed_think",
                forbidden_next_patterns=("<action inside think>",),
            ),
            CompilerRecoveryStrategy(
                id="intent_inside_think",
                error_codes=("E_INTENT_INSIDE_THINK",),
                recovery_ids=("intent_inside_think",),
                invalid_kind="intent_inside_think",
                handler_key="malformed_think",
            ),
            CompilerRecoveryStrategy(
                id="file_content_inside_think",
                error_codes=("E_FILE_CONTENT_INSIDE_THINK",),
                recovery_ids=("file_content_inside_think",),
                invalid_kind="file_content_inside_think",
                handler_key="malformed_think",
            ),
            CompilerRecoveryStrategy(
                id="file_content_unclosed",
                error_codes=("E_FILE_CONTENT_UNCLOSED",),
                recovery_ids=("file_content_unclosed",),
                invalid_kind="malformed_incomplete_file_content",
                handler_key="incomplete_file_content",
            ),
            CompilerRecoveryStrategy(
                id="mixed_visible_control",
                error_codes=("E_MIXED_VISIBLE_TEXT_AND_CONTROL",),
                recovery_ids=("mixed_visible_control",),
                invalid_kind="mixed_visible_text_and_control_protocol",
                handler_key="mixed_visible_control",
                allowed_next_shapes=("PLAINTEXT_ONLY", "ACTION_ONLY", "INTENT_ONLY", "INTENT_ACTION_BUNDLE"),
            ),
            CompilerRecoveryStrategy(
                id="file_content_requires_action",
                error_codes=("E_FILE_CONTENT_REQUIRES_ACTION",),
                recovery_ids=("file_content_requires_action",),
                invalid_kind="file_content_must_follow_action",
                handler_key="file_content_order",
            ),
            CompilerRecoveryStrategy(
                id="action_payload_array",
                error_codes=("E_ACTION_PAYLOAD_ARRAY",),
                recovery_ids=("action_payload_array",),
                invalid_kind="action_payload_array",
                handler_key="action_array",
            ),
            CompilerRecoveryStrategy(
                id="action_payload_xml_fields",
                error_codes=("E_ACTION_PAYLOAD_XML_FIELDS",),
                recovery_ids=("action_payload_xml_fields",),
                invalid_kind="action_payload_xml_fields",
                handler_key="malformed_action",
            ),
            CompilerRecoveryStrategy(
                id="action_payload_tool_code",
                error_codes=("E_ACTION_PAYLOAD_TOOL_CODE",),
                recovery_ids=("action_payload_tool_code",),
                invalid_kind="action_payload_tool_code",
                handler_key="malformed_action",
            ),
            CompilerRecoveryStrategy(
                id="action_payload_not_object",
                error_codes=("E_ACTION_PAYLOAD_NOT_OBJECT",),
                recovery_ids=("action_payload_not_object",),
                invalid_kind="action_payload_not_object",
                handler_key="malformed_action",
            ),
            CompilerRecoveryStrategy(
                id="atomic_bundle_exactly_one_action_array",
                error_codes=("E_ATOMIC_BUNDLE_REQUIRES_EXACTLY_ONE_ACTION",),
                recovery_ids=("atomic_bundle_exactly_one_action",),
                invalid_kind="action_payload_array",
                handler_key="action_array",
            ),
            CompilerRecoveryStrategy(
                id="atomic_bundle_exactly_one_action_multiple",
                error_codes=("E_ATOMIC_BUNDLE_REQUIRES_EXACTLY_ONE_ACTION",),
                recovery_ids=("atomic_bundle_exactly_one_action",),
                invalid_kind="multiple_actions",
                handler_key="multiple_actions",
            ),
        )

    def resolve(self, *, error_code: str, recovery_id: str, invalid_kind: str) -> CompilerRecoveryStrategy | None:
        normalized_code = str(error_code or "").strip()
        normalized_recovery = str(recovery_id or "").strip()
        normalized_invalid = str(invalid_kind or "").strip()
        for strategy in self._strategies:
            if normalized_invalid and strategy.invalid_kind != normalized_invalid:
                continue
            if normalized_code and normalized_code not in strategy.error_codes:
                continue
            if normalized_recovery and normalized_recovery not in strategy.recovery_ids:
                continue
            return strategy
        return None
