from __future__ import annotations

import logging
from pathlib import Path


log = logging.getLogger(__name__)

BUNDLED_DEFAULT_SYSTEM_PROMPT_PATH = Path(__file__).with_name("default_system_prompt.md")


def get_bundled_default_system_prompt() -> str:
    return BUNDLED_DEFAULT_SYSTEM_PROMPT_PATH.read_text(encoding="utf-8").rstrip()


def _as_settings_dict(settings: dict | None) -> dict:
    return settings if isinstance(settings, dict) else {}


def _expand_path(path_value: str | Path | None) -> Path | None:
    if path_value is None:
        return None
    text = str(path_value).strip()
    if not text:
        return None
    return Path(text).expanduser().resolve()


def resolve_system_prompt_directory(settings: dict | None = None) -> Path:
    settings_dict = _as_settings_dict(settings)
    configured = _expand_path(settings_dict.get("system_prompt_directory"))
    if configured is not None:
        return configured
    return BUNDLED_DEFAULT_SYSTEM_PROMPT_PATH.parent.resolve()


def resolve_current_system_prompt_path(settings: dict | None = None) -> Path:
    settings_dict = _as_settings_dict(settings)
    configured = _expand_path(settings_dict.get("current_system_prompt_path"))
    if configured is not None:
        return configured
    return BUNDLED_DEFAULT_SYSTEM_PROMPT_PATH.resolve()


def load_active_system_prompt(settings: dict | None = None) -> str:
    prompt_path = resolve_current_system_prompt_path(settings)
    try:
        return prompt_path.read_text(encoding="utf-8").rstrip()
    except Exception as exc:
        log.warning(
            "Failed to load configured system prompt from '%s': %s. Falling back to bundled default.",
            prompt_path,
            exc,
        )
        return get_bundled_default_system_prompt()


def discover_system_prompt_files(settings: dict | None = None) -> list[Path]:
    directory = resolve_system_prompt_directory(settings)
    prompt_files: list[Path] = []

    if directory.exists() and directory.is_dir():
        prompt_files.extend(
            path.resolve()
            for path in directory.rglob("*.md")
            if path.is_file()
        )

    current_path = resolve_current_system_prompt_path(settings)
    if current_path.is_file() and current_path.suffix.lower() == ".md":
        resolved_current = current_path.resolve()
        if resolved_current not in prompt_files:
            prompt_files.append(resolved_current)

    return sorted(
        prompt_files,
        key=lambda path: prompt_display_name(path, directory).lower(),
    )


def prompt_display_name(path: Path, root: Path | None = None) -> str:
    resolved_path = Path(path).resolve()
    base_root = root.resolve() if root is not None else None
    if base_root is not None:
        try:
            return resolved_path.relative_to(base_root).as_posix()
        except ValueError:
            pass
    return str(resolved_path)
