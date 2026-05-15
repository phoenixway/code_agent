from __future__ import annotations

from dataclasses import dataclass

from modules.tools.recovery.edit_file_recovery_policy import malformed_edit_file_recovery_actions


@dataclass(frozen=True)
class ToolActionSchemaViolation:
    action_type: str
    reason: str
    error_code: str
    message: str
    missing_fields: tuple[str, ...] = ()
    forbidden_fields: tuple[str, ...] = ()
    recommended_actions: tuple[str, ...] = ()


@dataclass(frozen=True)
class ToolActionSchema:
    action_type: str
    required_fields: tuple[str, ...] = ()
    forbidden_fields: tuple[str, ...] = ()
    malformed_reason: str = "malformed_action_payload"
    malformed_error_code: str = "MALFORMED_ACTION_PAYLOAD"
    recommended_actions: tuple[str, ...] = ()

    def validate(self, command: dict) -> ToolActionSchemaViolation | None:
        payload = command if isinstance(command, dict) else {}
        missing = tuple(
            field
            for field in self.required_fields
            if not _has_required_string(
                payload,
                field,
                allow_empty=self.action_type == "edit_file" and field == "replace_text",
            )
        )
        forbidden = tuple(field for field in self.forbidden_fields if field in payload)
        if not missing and not forbidden:
            return None

        parts: list[str] = []
        if missing:
            parts.append("missing required fields: " + ", ".join(missing))
        if forbidden:
            parts.append("unsupported fields: " + ", ".join(forbidden))

        if self.action_type == "edit_file":
            message = (
                "Invalid edit_file payload: "
                + "; ".join(parts)
                + ". edit_file accepts only an exact text replacement contract: path, search_text, and replace_text. "
                "It does not accept line ranges, byte ranges, file_content, or replace_block. "
                "Accepted edit_file payload has exactly top-level path, search_text, and replace_text strings. "
                "Do not use edits arrays, search_block, replace_block, start_line/end_line, byte ranges, content, file_content, patches, or diff-style payloads with edit_file. "
                "If you only know a line range, call read_chunk first. If you know a Kotlin/Python symbol target, use extract_symbol or replace_symbol. "
                "Call edit_file again only after you can provide exact top-level search_text and replace_text."
            )
        else:
            message = f"Invalid {self.action_type} payload: " + "; ".join(parts) + "."

        return ToolActionSchemaViolation(
            action_type=self.action_type,
            reason=self.malformed_reason,
            error_code=self.malformed_error_code,
            message=message,
            missing_fields=missing,
            forbidden_fields=forbidden,
            recommended_actions=self.recommended_actions,
        )


def _has_non_empty_string(value) -> bool:
    return isinstance(value, str) and bool(value.strip())


def _has_required_string(payload: dict, field: str, *, allow_empty: bool = False) -> bool:
    if field not in payload:
        return False
    value = payload.get(field)
    if not isinstance(value, str):
        return False
    if allow_empty:
        return True
    return bool(value.strip())


EDIT_FILE_SCHEMA = ToolActionSchema(
    action_type="edit_file",
    required_fields=("path", "search_text", "replace_text"),
    forbidden_fields=(
        "start_line",
        "end_line",
        "start_byte",
        "end_byte",
        "file_content",
        "content",
        "replace_block",
        "old_text",
        "new_text",
    ),
    malformed_reason="malformed_edit_file_payload",
    malformed_error_code="MALFORMED_EDIT_FILE_PAYLOAD",
    recommended_actions=malformed_edit_file_recovery_actions(active_intent_type="MODIFY"),
)


ACTION_SCHEMAS = {
    EDIT_FILE_SCHEMA.action_type: EDIT_FILE_SCHEMA,
}


def command_action_type(command: dict) -> str:
    if not isinstance(command, dict):
        return ""
    return str(command.get("type") or command.get("action") or "").strip()


def validate_tool_action_schema(command: dict) -> ToolActionSchemaViolation | None:
    action_type = command_action_type(command)
    schema = ACTION_SCHEMAS.get(action_type)
    if schema is None:
        return None
    return schema.validate(command)
