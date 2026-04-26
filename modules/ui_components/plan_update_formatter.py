from __future__ import annotations

from math import floor
from typing import Any

from rich.text import Text


DEFAULT_WIDTH = 40
MIN_TITLE_LEN = 8


def _clamp_width(width: int | None) -> int:
    try:
        normalized = int(width or 0)
    except Exception:
        normalized = 0
    return max(12, normalized or DEFAULT_WIDTH)


def _truncate_title(title: str, available: int) -> str:
    value = str(title or "").strip()
    if not value:
        return ""
    if available <= 0:
        return ""
    if len(value) <= available:
        return value
    if available <= 1:
        return "…"
    if available < MIN_TITLE_LEN + 1:
        return value[: available - 1].rstrip() + "…"
    visible = max(MIN_TITLE_LEN, available - 1)
    candidate = value[:visible].rstrip()
    space_idx = candidate.rfind(" ")
    if space_idx >= MIN_TITLE_LEN:
        candidate = candidate[:space_idx].rstrip()
    return candidate + "…"


def _bar_segments(completed: int, total: int, max_bar_width: int) -> tuple[int, int]:
    total = max(0, int(total or 0))
    completed = max(0, min(int(completed or 0), total))
    if total <= 0:
        return 0, 0
    bar_len = total if total <= max_bar_width else max_bar_width
    if completed <= 0:
        return 0, bar_len
    if completed >= total:
        return bar_len, bar_len
    filled = floor((completed / total) * bar_len)
    filled = max(1, min(bar_len - 1, filled))
    return filled, bar_len


def format_plan_update_compact(update: dict[str, Any], options: dict[str, Any] | None = None) -> Text:
    opts = dict(options or {})
    width = _clamp_width(opts.get("width"))
    color = bool(opts.get("color", True))
    max_bar_width = max(1, int(opts.get("maxBarWidth", 10) or 10))

    completed = max(0, int(update.get("completed") or 0))
    total = max(0, int(update.get("total") or 0))
    current_title = str(update.get("current_title") or "").strip()
    changed_steps = list(update.get("changed_steps") or [])

    prefix = f"◆ {completed}/{total}"
    available_title = width - len(prefix) - 1
    title = _truncate_title(current_title, available_title)

    text = Text()
    accent_style = "bold cyan" if color else ""
    dim_style = "dim" if color else ""

    text.append("◆", style=accent_style)
    text.append(f" {completed}/{total}")
    if title:
        text.append(" ")
        text.append(title)
    text.append("\n")

    filled, bar_len = _bar_segments(completed, total, max_bar_width)
    if bar_len > 0:
        text.append("█" * filled, style=accent_style)
        text.append("░" * max(0, bar_len - filled), style=dim_style)
    text.append("\n")

    status_styles = {
        "done": "green" if color else "",
        "in_progress": "cyan" if color else "",
        "todo": "dim" if color else "",
    }
    for step in changed_steps:
        step_id = str(step.get("id") or "").strip()
        status = str(step.get("status") or "").strip()
        if not step_id or not status:
            continue
        text.append("  ")
        text.append(step_id, style=dim_style)
        text.append(" ")
        text.append(status, style=status_styles.get(status, ""))
        text.append("\n")

    text.append("\n")
    return text
