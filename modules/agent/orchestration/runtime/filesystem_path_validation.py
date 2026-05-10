"""Shared filesystem path validation for action diagnostics."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

DIRECTORY_PATH_ACTIONS = {
    "search_files",
    "search_content",
    "list_directory",
}
FILE_PATH_ACTIONS = {
    "read_file",
    "read_chunk",
}
FILESYSTEM_PATH_ACTIONS = DIRECTORY_PATH_ACTIONS | FILE_PATH_ACTIONS
INVALID_ACTION_PATH = "INVALID_ACTION_PATH"
SEARCH_ROOT_NOT_FOUND = "SEARCH_ROOT_NOT_FOUND"


@dataclass(frozen=True)
class PathValidationResult:
    ok: bool
    path: str
    expected_kind: str | None = None
    actual_kind: str | None = None
    error_code: str | None = None
    message: str | None = None


def _normalized_action_type(action: object) -> str:
    if not isinstance(action, dict):
        return ""
    return str(action.get("type") or action.get("action") or "").strip()


def _expected_path_kind(action_type: str) -> str | None:
    if action_type in DIRECTORY_PATH_ACTIONS:
        return "directory"
    if action_type in FILE_PATH_ACTIONS:
        return "file"
    return None


def _effective_action_path(action: dict, action_type: str) -> str:
    raw_path = str(action.get("path") or "").strip()
    if raw_path:
        return raw_path
    if action_type in {"search_files", "search_content"}:
        return "."
    return raw_path


def _actual_kind(path: Path) -> str:
    try:
        if not path.exists():
            return "missing"
        if path.is_dir():
            return "directory"
        if path.is_file():
            return "file"
    except Exception:
        return "unknown"
    return "other"


def validate_filesystem_action_path(action: object, cwd: str | Path | None = None) -> PathValidationResult:
    if not isinstance(action, dict):
        return PathValidationResult(ok=True, path="", expected_kind=None, actual_kind=None, error_code=None, message=None)

    action_type = _normalized_action_type(action)
    expected_kind = _expected_path_kind(action_type)
    if expected_kind is None:
        return PathValidationResult(ok=True, path="", expected_kind=None, actual_kind=None, error_code=None, message=None)

    effective_path = _effective_action_path(action, action_type)
    if not effective_path:
        return PathValidationResult(
            ok=False,
            path="",
            expected_kind=expected_kind,
            actual_kind="unknown",
            error_code=None,
            message="path_missing",
        )

    base_dir = Path(cwd) if cwd is not None else Path.cwd()
    candidate = Path(effective_path)
    if not candidate.is_absolute():
        candidate = base_dir / candidate

    actual_kind = _actual_kind(candidate)
    if actual_kind == expected_kind:
        return PathValidationResult(
            ok=True,
            path=effective_path,
            expected_kind=expected_kind,
            actual_kind=actual_kind,
            error_code=None,
            message=None,
        )

    error_code = SEARCH_ROOT_NOT_FOUND if expected_kind == "directory" else INVALID_ACTION_PATH
    if actual_kind == "missing":
        message = f"{effective_path} does not exist."
    else:
        message = f"{effective_path} is not a {expected_kind}."
    return PathValidationResult(
        ok=False,
        path=effective_path,
        expected_kind=expected_kind,
        actual_kind=actual_kind,
        error_code=error_code,
        message=message,
    )
