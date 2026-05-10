"""Classification helpers for invalid filesystem action path failures."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

FILESYSTEM_PATH_ACTIONS = {
    "search_files",
    "search_content",
    "list_directory",
    "read_file",
    "read_chunk",
}
DIRECTORY_PATH_ACTIONS = {
    "search_files",
    "search_content",
    "list_directory",
}
FILE_PATH_ACTIONS = {
    "read_file",
    "read_chunk",
}
INVALID_PATH_ERROR_CODE = "INVALID_ACTION_PATH"
INVALID_PATH_RECOVERY_KIND = "INVALID_ACTION_PATH_RECOVERY"
INVALID_PATH_MARKERS = (
    "no such file or directory",
    "no valid search paths given",
    "is not a directory",
    "not a directory",
    "cannot access",
    "does not exist",
)


@dataclass(frozen=True)
class FilesystemPathFailure:
    error_code: str
    recovery_kind: str
    invalid_path: str
    failed_action_type: str
    expected_kind: str
    actual_kind: str
    reason: str
    failure_message: str
    known_valid_roots: tuple[str, ...]
    recommended_next_actions: tuple[dict[str, str], ...]

    def to_error_details(self) -> dict[str, object]:
        return {
            "recovery_kind": self.recovery_kind,
            "invalid_path": self.invalid_path,
            "failed_action_type": self.failed_action_type,
            "expected_kind": self.expected_kind,
            "actual_kind": self.actual_kind,
            "reason": self.reason,
            "message": self.failure_message,
            "known_valid_roots": list(self.known_valid_roots),
            "recommended_next_actions": [dict(item) for item in self.recommended_next_actions],
        }


def _combined_failure_text(result: dict | None) -> str:
    if not isinstance(result, dict):
        return ""
    parts = []
    for key in ("output", "stderr", "stderr_full", "stdout", "stdout_full", "message"):
        value = result.get(key)
        if isinstance(value, str) and value.strip():
            parts.append(value.strip())
    return "\n".join(parts)


def _best_reason_marker(text: str) -> str:
    lower_text = text.lower()
    for marker in INVALID_PATH_MARKERS:
        if marker in lower_text:
            return marker
    return ""


def _actual_kind_for_reason(reason: str) -> str:
    if reason in {
        "no such file or directory",
        "no valid search paths given",
        "cannot access",
        "does not exist",
    }:
        return "missing"
    if reason in {"is not a directory", "not a directory"}:
        return "wrong_type"
    return "invalid"


def _fallback_existing_root(path_value: str) -> str:
    if not path_value:
        return "."
    try:
        parent = Path(path_value).parent
        candidate = str(parent).strip() or "."
        if Path(candidate).exists() and Path(candidate).is_dir():
            return candidate
    except Exception:
        return "."
    return "."


def classify_filesystem_path_failure(command: dict | None, result: dict | None) -> FilesystemPathFailure | None:
    if not isinstance(command, dict) or not isinstance(result, dict):
        return None

    action_type = str(command.get("type") or command.get("action") or "").strip()
    if action_type not in FILESYSTEM_PATH_ACTIONS:
        return None

    invalid_path = str(command.get("path") or "").strip()
    if not invalid_path:
        return None

    combined_text = _combined_failure_text(result)
    if not combined_text:
        return None

    reason = _best_reason_marker(combined_text)
    if not reason:
        return None

    expected_kind = "directory" if action_type in DIRECTORY_PATH_ACTIONS else "file"
    known_root = _fallback_existing_root(invalid_path)
    return FilesystemPathFailure(
        error_code=INVALID_PATH_ERROR_CODE,
        recovery_kind=INVALID_PATH_RECOVERY_KIND,
        invalid_path=invalid_path,
        failed_action_type=action_type,
        expected_kind=expected_kind,
        actual_kind=_actual_kind_for_reason(reason),
        reason=reason,
        failure_message=combined_text.strip(),
        known_valid_roots=(known_root,),
        recommended_next_actions=(
            {"type": "list_directory", "path": known_root},
            {"type": "search_files", "path": "."},
            {"type": "search_content", "path": "."},
        ),
    )


def restore_filesystem_path_failure(command: dict | None, error_details: dict | None) -> FilesystemPathFailure | None:
    if not isinstance(error_details, dict):
        return None
    if str(error_details.get("recovery_kind") or "").strip() != INVALID_PATH_RECOVERY_KIND:
        return None

    invalid_path = str(error_details.get("invalid_path") or "").strip()
    failed_action_type = str(
        error_details.get("failed_action_type")
        or (command or {}).get("type")
        or (command or {}).get("action")
        or ""
    ).strip()
    if not invalid_path or not failed_action_type:
        return None

    roots = tuple(str(item).strip() for item in list(error_details.get("known_valid_roots") or []) if str(item).strip())
    actions = []
    for item in list(error_details.get("recommended_next_actions") or []):
        if isinstance(item, dict):
            action_type = str(item.get("type") or "").strip()
            path = str(item.get("path") or "").strip()
            if action_type:
                payload = {"type": action_type}
                if path:
                    payload["path"] = path
                actions.append(payload)
    expected_kind = str(error_details.get("expected_kind") or "").strip() or (
        "directory" if failed_action_type in DIRECTORY_PATH_ACTIONS else "file"
    )
    return FilesystemPathFailure(
        error_code=INVALID_PATH_ERROR_CODE,
        recovery_kind=INVALID_PATH_RECOVERY_KIND,
        invalid_path=invalid_path,
        failed_action_type=failed_action_type,
        expected_kind=expected_kind,
        actual_kind=str(error_details.get("actual_kind") or "").strip() or "invalid",
        reason=str(error_details.get("reason") or "").strip(),
        failure_message=str(error_details.get("message") or "").strip(),
        known_valid_roots=roots or (".",),
        recommended_next_actions=tuple(actions) or (
            {"type": "list_directory", "path": "."},
            {"type": "search_files", "path": "."},
            {"type": "search_content", "path": "."},
        ),
    )
