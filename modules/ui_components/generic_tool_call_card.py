from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from pathlib import PurePath
from typing import Any

from rich.console import Group
from rich.text import Text
from textual.widgets import Static


SPECIALIZED_TOOL_CALLS = {"run_shell", "read_file", "edit_file"}
_SERVICE_FIELDS = {
    "type",
    "action",
    "before_execution",
    "during_execution",
    "after_execution",
    "return_control",
}


@dataclass(slots=True)
class GenericToolCallPresentation:
    tool_name: str
    icon: str
    status_text: str
    status_tone: str
    summary: str
    primary_result: str
    query_items: list[tuple[str, str]] = field(default_factory=list)
    evidence_items: list[str] = field(default_factory=list)
    hidden_evidence_count: int = 0
    is_expandable: bool = False


def get_tool_name(command: dict[str, Any] | None) -> str:
    if not isinstance(command, dict):
        return "unknown"
    return str(command.get("type") or command.get("action") or "unknown")


def has_specialized_tool_call_renderer(command: dict[str, Any] | None) -> bool:
    return get_tool_name(command) in SPECIALIZED_TOOL_CALLS


def _tool_icon(tool_name: str) -> str:
    return {
        "search_content": "S",
        "search_files": "F",
        "find_files": "F",
        "list_directory": "D",
        "read_file_skeleton": "R",
        "create_file": "+",
        "write_file": "W",
        "write_file_block": "W",
        "append_file_block": "A",
        "replace": "W",
        "git_diff": "G",
    }.get(tool_name, "*")


def _compact_path(path: str, limit: int = 44) -> str:
    path = str(path or "").strip()
    if not path:
        return ""
    normalized = path.replace("\\", "/")
    if len(normalized) <= limit:
        return normalized
    name = PurePath(normalized).name
    if len(name) + 4 >= limit:
        return "..." + name[-(limit - 3):]
    head = max(3, limit - len(name) - 4)
    return f"...{normalized[:head]}/{name}"


def _truncate_inline(text: str, limit: int = 92) -> str:
    text = re.sub(r"\s+", " ", str(text or "")).strip()
    if len(text) <= limit:
        return text
    return text[: limit - 1].rstrip() + "…"


def _safe_value(value: Any, limit: int = 120) -> str:
    if isinstance(value, bool):
        return "true" if value else "false"
    if value is None:
        return ""
    if isinstance(value, (int, float)):
        return str(value)
    if isinstance(value, str):
        return _truncate_inline(value, limit=limit)
    try:
        return _truncate_inline(json.dumps(value, ensure_ascii=False), limit=limit)
    except Exception:
        return _truncate_inline(str(value), limit=limit)


def _first_meaningful_line(text: str) -> str:
    for raw in str(text or "").splitlines():
        line = raw.strip()
        if not line:
            continue
        if line.lower() in {"done", "success", "ok"}:
            continue
        return line
    return ""


def _extract_evidence_lines(result: dict[str, Any] | None, *, max_lines: int = 4) -> tuple[list[str], int]:
    if not isinstance(result, dict):
        return [], 0

    candidates: list[str] = []
    for key in ("raw_output", "stdout_full", "stdout", "output", "stderr_full", "stderr"):
        value = result.get(key)
        if isinstance(value, str) and value.strip():
            candidates.extend(value.splitlines())
            break

    cleaned: list[str] = []
    for raw in candidates:
        line = raw.strip()
        if not line:
            continue
        cleaned.append(_truncate_inline(line, limit=120))

    if not cleaned:
        file_path = result.get("file_path")
        if isinstance(file_path, str) and file_path.strip():
            cleaned.append(_compact_path(file_path))

    if not cleaned:
        return [], 0

    visible = cleaned[:max_lines]
    hidden = max(0, len(cleaned) - len(visible))
    return visible, hidden


def _count_status_text(command: dict[str, Any], result: dict[str, Any] | None) -> tuple[str, str]:
    if result is None:
        return "…", "running"

    status = str(result.get("status") or "").lower()
    result_count = result.get("result_count")
    if isinstance(result_count, int):
        if result_count > 0:
            label = "hit" if result_count == 1 else "hits"
            return f"{result_count} {label}", "success"
        return "0", "muted"

    if status in {"error", "failed"}:
        return "×", "error"

    no_result_markers = ("no matches", "no results", "not found", "0 matches")
    output_line = _first_meaningful_line(result.get("output", ""))
    if output_line and any(marker in output_line.lower() for marker in no_result_markers):
        return "0", "muted"

    if status == "success":
        return "✓", "success"
    if status in {"running", "pending"}:
        return "…", "running"
    return "✓", "success"


def _narrated_summary(command: dict[str, Any], result: dict[str, Any] | None) -> str:
    for key in ("after_execution", "during_execution", "before_execution"):
        value = command.get(key)
        if isinstance(value, str) and value.strip():
            return _truncate_inline(value, limit=88)

    tool_name = get_tool_name(command)
    pattern = command.get("pattern") or command.get("query") or command.get("name")
    path = command.get("path")

    if tool_name == "search_content" and pattern:
        return _truncate_inline(f"Find {pattern}", limit=88)
    if tool_name in {"search_files", "find_files"} and pattern:
        return _truncate_inline(f"Search files for {pattern}", limit=88)
    if tool_name == "list_directory":
        return "List directory contents"
    if tool_name == "create_file":
        return "Create file"
    if tool_name in {"write_file", "write_file_block", "append_file_block", "replace"}:
        return "Write file"
    if tool_name == "read_file_skeleton":
        return "Inspect file structure"
    if tool_name == "git_diff":
        return "Inspect git diff"
    if path:
        return _truncate_inline(f"{tool_name.replace('_', ' ').capitalize()} on {PurePath(str(path)).name}", limit=88)
    return "Execute tool action"


def _primary_result(command: dict[str, Any], result: dict[str, Any] | None, evidence_items: list[str]) -> str:
    if evidence_items:
        return evidence_items[0]

    for source in (result or {}, command):
        path = source.get("path") or source.get("file_path")
        if isinstance(path, str) and path.strip():
            start_line = source.get("start_line")
            if isinstance(start_line, int):
                end_line = source.get("end_line")
                if isinstance(end_line, int):
                    return f"{_compact_path(path)}:{start_line}-{end_line}"
            return _compact_path(path)

    return ""


def _query_items(command: dict[str, Any]) -> list[tuple[str, str]]:
    items: list[tuple[str, str]] = []

    path = command.get("path")
    if isinstance(path, str) and path.strip():
        items.append(("Path", _compact_path(path, limit=68)))

    for key, label in (
        ("pattern", "Pattern"),
        ("query", "Query"),
        ("name", "Name"),
        ("command", "Command"),
        ("search_text", "Search"),
        ("replace_text", "Replace"),
    ):
        value = command.get(key)
        if value not in (None, ""):
            items.append((label, _safe_value(value)))

    if isinstance(command.get("start_line"), int) and isinstance(command.get("end_line"), int):
        items.append(("Lines", f"{command['start_line']}-{command['end_line']}"))
    elif isinstance(command.get("start_byte"), int) and isinstance(command.get("end_byte"), int):
        items.append(("Bytes", f"{command['start_byte']}-{command['end_byte']}"))

    flags: list[str] = []
    for key, label in (
        ("recursive", "recursive"),
        ("code_only", "code only"),
        ("confirm_large_read", "confirmed"),
    ):
        if command.get(key) is True:
            flags.append(label)
    if command.get("limit") not in (None, ""):
        flags.append(f"limit {command['limit']}")
    if flags:
        items.append(("Flags", " • ".join(flags)))

    for key, value in command.items():
        if key in _SERVICE_FIELDS:
            continue
        if key in {
            "path",
            "pattern",
            "query",
            "name",
            "command",
            "search_text",
            "replace_text",
            "start_line",
            "end_line",
            "start_byte",
            "end_byte",
            "recursive",
            "code_only",
            "confirm_large_read",
            "limit",
            "content",
        }:
            continue
        if value in (None, "", False):
            continue
        items.append((key.replace("_", " ").title(), _safe_value(value)))

    return items


def build_generic_tool_call_presentation(
    command: dict[str, Any] | None,
    result: dict[str, Any] | None = None,
) -> GenericToolCallPresentation:
    safe_command = command if isinstance(command, dict) else {}
    tool_name = get_tool_name(safe_command)
    evidence_items, hidden_count = _extract_evidence_lines(result)
    summary = _narrated_summary(safe_command, result)
    primary = _primary_result(safe_command, result, evidence_items)
    status_text, status_tone = _count_status_text(safe_command, result)
    query = _query_items(safe_command)

    if isinstance(result, dict) and result.get("status") in {"error", "failed"}:
        error_line = _first_meaningful_line(result.get("output", "")) or _first_meaningful_line(result.get("stderr", ""))
        if error_line:
            primary = _truncate_inline(error_line, limit=96)

    return GenericToolCallPresentation(
        tool_name=tool_name,
        icon=_tool_icon(tool_name),
        status_text=status_text,
        status_tone=status_tone,
        summary=summary,
        primary_result=primary,
        query_items=query,
        evidence_items=evidence_items[:4],
        hidden_evidence_count=hidden_count,
        is_expandable=bool(query or evidence_items or hidden_count),
    )


class GenericToolCallCard(Static):
    DEFAULT_CSS = """
    GenericToolCallCard {
        background: $surface;
        color: $text;
        border-left: wide $surface-lighten-1;
        padding: 1 2;
        margin: 0;
        height: auto;
    }

    GenericToolCallCard:focus {
        border-left: wide $primary;
    }

    GenericToolCallCard.-success {
        border-left: wide $success;
    }

    GenericToolCallCard.-error {
        border-left: wide $error;
    }

    GenericToolCallCard.-running {
        border-left: wide $warning;
    }
    """

    def __init__(self, command: dict[str, Any], result: dict[str, Any] | None = None):
        super().__init__("", classes="chat-message generic-tool-call-card", expand=False)
        self.command = command
        self.result = result
        self.expanded = False
        self.can_focus = True
        self.presentation = build_generic_tool_call_presentation(command, result)
        self._apply_status_classes()
        self._refresh_render()

    def update_presentation(self, command: dict[str, Any] | None = None, result: dict[str, Any] | None = None) -> None:
        if isinstance(command, dict):
            self.command = command
        self.result = result
        self.presentation = build_generic_tool_call_presentation(self.command, result)
        if not self.presentation.is_expandable:
            self.expanded = False
        self._apply_status_classes()
        self._refresh_render()

    def on_click(self, event) -> None:
        if self.presentation.is_expandable:
            self.expanded = not self.expanded
            self._refresh_render()
            event.stop()

    def on_key(self, event) -> None:
        if event.key in {"enter", "space"} and self.presentation.is_expandable:
            self.expanded = not self.expanded
            self._refresh_render()
            event.stop()

    def _apply_status_classes(self) -> None:
        self.remove_class("-success")
        self.remove_class("-error")
        self.remove_class("-running")
        tone = self.presentation.status_tone
        if tone == "success":
            self.add_class("-success")
        elif tone == "error":
            self.add_class("-error")
        elif tone == "running":
            self.add_class("-running")

    def _chip_style(self) -> str:
        return {
            "success": "black on green",
            "error": "white on red",
            "running": "black on yellow",
        }.get(self.presentation.status_tone, "black on bright_black")

    def _section_lines(self, title: str, items: list[str]) -> list[Text]:
        lines: list[Text] = []
        if not items:
            return lines
        lines.append(Text(title, style="bold dim"))
        for item in items:
            lines.append(Text(f"  {item}", style=""))
        return lines

    def _refresh_render(self) -> None:
        self.update(self.build_renderable())

    def build_renderable(self):
        p = self.presentation
        lines: list[Text] = []

        header = Text()
        header.append(p.tool_name, style="bold")
        header.append("  ")
        header.append(f" {p.status_text} ", style=self._chip_style())
        lines.append(header)

        if p.summary:
            lines.append(Text(_truncate_inline(p.summary, limit=96), style="bold"))

        if self.expanded and p.primary_result:
            lines.append(Text(_truncate_inline(p.primary_result, limit=108), style="dim"))

        if p.is_expandable:
            chevron = "▴" if self.expanded else "▾"
            lines.append(Text(f"{chevron} details", style="dim"))

        if self.expanded:
            query_lines = [f"{label}: {value}" for label, value in p.query_items]
            result_lines = list(p.evidence_items)
            if p.hidden_evidence_count:
                result_lines.append(f"+{p.hidden_evidence_count} more")

            if query_lines:
                lines.append(Text(""))
                lines.extend(self._section_lines("Query", query_lines))
            if result_lines:
                lines.append(Text(""))
                lines.extend(self._section_lines("Result / Evidence", result_lines))

        return Group(*lines)
