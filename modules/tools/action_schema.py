from __future__ import annotations

from dataclasses import dataclass


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
        missing = tuple(field for field in self.required_fields if not _has_non_empty_string(payload.get(field)))
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
                "Use read_chunk/read_file/search_content to inspect the exact current block first, then call edit_file with exact search_text/replace_text. "
                "If exact replacement remains unreliable and the active intent is MODIFY, use write_file_block only after obtaining sufficient fresh file content."
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
    recommended_actions=("read_chunk", "extract_symbol", "replace_symbol", "read_file", "search_content", "edit_file", "write_file_block"),
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
