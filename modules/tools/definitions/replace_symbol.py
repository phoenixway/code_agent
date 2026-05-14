from __future__ import annotations

import re
from pathlib import Path
from typing import Any

from modules.types import ChangeProposal

from ..base import BaseTool
from ._kotlin_symbol_extractor import KotlinSymbolExtractor


class ReplaceSymbolTool(BaseTool):
    name = "replace_symbol"
    description = (
        "Replaces exactly one Kotlin symbol using tree-sitter symbol boundaries. "
        "Use this after extract_symbol/read_chunk when edit_file exact text replacement is brittle. "
        "Params: 'path' (str), 'symbol_name' (str; alias 'name'), optional "
        "'symbol_kind' (str; alias 'symbol_type': auto|function|composable|class|enum|object|interface|method|property), "
        "optional 'container_name' (str), optional 'occurrence' (int, default 1), "
        "and 'new_content' (str; alias 'newcontent'). "
        "Fails if the symbol is missing, ambiguous, or the resolved source block is not unique in the file."
    )

    def __init__(self):
        self.extractor = KotlinSymbolExtractor()

    async def execute(
        self,
        path: str,
        symbol_name: str | None = None,
        new_content: str | None = None,
        symbol_kind: str | None = None,
        container_name: str | None = None,
        occurrence: int = 1,
        name: str | None = None,
        symbol_type: str | None = None,
        newcontent: str | None = None,
        **kwargs,
    ) -> dict[str, Any] | ChangeProposal:
        resolved_name = _first_nonempty(symbol_name, name)
        resolved_kind = _first_nonempty(symbol_kind, symbol_type) or "auto"
        resolved_new_content = _first_nonempty(new_content, newcontent)

        if not isinstance(path, str) or not path.strip():
            return _validation_error(
                "Parameter 'path' must be a non-empty string.",
                next_actions=["read_file_skeleton", "extract_symbol"],
            )
        if not isinstance(resolved_name, str) or not resolved_name.strip():
            return _validation_error(
                "Parameter 'symbol_name' must be a non-empty string. Alias 'name' is accepted.",
                next_actions=["read_file_skeleton", "extract_symbol"],
            )
        if not isinstance(resolved_new_content, str) or not resolved_new_content.strip():
            return _validation_error(
                "Parameter 'new_content' must be a non-empty string. Alias 'newcontent' is accepted.",
                next_actions=["extract_symbol", "read_chunk"],
            )

        p = Path(path)
        if p.suffix.lower() != ".kt":
            return _validation_error(
                f"replace_symbol currently supports Kotlin .kt files only. Got: {p.suffix or '(no extension)'}",
                next_actions=["read_file", "read_file_skeleton", "edit_file"],
            )

        selected = self.extractor.extract_symbol(
            path=path,
            symbol_name=resolved_name.strip(),
            symbol_kind=resolved_kind,
            container_name=container_name,
            occurrence=occurrence,
            include_body=True,
            include_signature=True,
            include_line_range=True,
        )
        if selected.get("status") != "success":
            return selected

        selected_text = str(selected.get("file_content") or selected.get("output") or "")
        if not selected_text:
            return _validation_error(
                "Resolved symbol did not return source text; refusing to replace.",
                next_actions=["extract_symbol", "read_chunk"],
                error_details={"path": path, "symbol_name": resolved_name, "symbol_kind": resolved_kind},
            )

        actual_kind = str(selected.get("symbol_kind") or resolved_kind or "auto")
        if not _new_content_declares_same_symbol(resolved_new_content, resolved_name.strip(), actual_kind):
            return _validation_error(
                (
                    "new_content does not appear to declare the same symbol. "
                    "replace_symbol requires the replacement to preserve the target symbol name/kind. "
                    "Use write_file_block only when a broader rewrite is explicitly intended."
                ),
                next_actions=["extract_symbol", "read_chunk", "replace_symbol"],
                error_details={
                    "path": path,
                    "symbol_name": resolved_name,
                    "symbol_kind": actual_kind,
                    "container_name": container_name,
                },
            )

        content = p.read_text(encoding="utf-8", errors="replace")
        occurrence_count = content.count(selected_text)
        if occurrence_count != 1:
            return {
                "status": "error",
                "error_code": "AMBIGUOUS_REPLACEMENT_TEXT",
                "recoverable": True,
                "next_actions": ["extract_symbol", "read_chunk", "edit_file"],
                "output": (
                    f"Resolved symbol text occurs {occurrence_count} times in {path}; refusing replacement. "
                    "Use a narrower container_name/symbol_kind/occurrence or inspect the exact range."
                ),
                "error_details": {
                    "path": path,
                    "symbol_name": resolved_name,
                    "symbol_kind": actual_kind,
                    "container_name": container_name,
                    "occurrence": occurrence,
                    "selected_start_line": selected.get("start_line"),
                    "selected_end_line": selected.get("end_line"),
                    "occurrence_count": occurrence_count,
                },
            }

        new_file_content = content.replace(selected_text, resolved_new_content, 1)
        return ChangeProposal(file_path=str(p), original_content=content, new_content=new_file_content)


def _first_nonempty(*values) -> str | None:
    for value in values:
        if isinstance(value, str) and value.strip():
            return value
    return None


def _validation_error(message: str, *, next_actions: list[str], error_details: dict[str, Any] | None = None) -> dict[str, Any]:
    return {
        "status": "error",
        "error_code": "VALIDATION_ERROR",
        "recoverable": True,
        "next_actions": list(next_actions),
        "output": message,
        "error_details": dict(error_details or {}),
    }


def _new_content_declares_same_symbol(new_content: str, symbol_name: str, symbol_kind: str) -> bool:
    escaped = re.escape(symbol_name)
    kind = str(symbol_kind or "auto").strip().lower()
    text = str(new_content or "")

    if kind in {"function", "method", "composable"}:
        return re.search(rf"\bfun\s+(?:<[^>]+>\s*)?`?{escaped}`?\s*\(", text) is not None
    if kind == "class":
        return re.search(rf"\bclass\s+`?{escaped}`?\b", text) is not None
    if kind == "enum":
        return re.search(rf"\benum\s+class\s+`?{escaped}`?\b", text) is not None
    if kind == "object":
        return re.search(rf"\bobject\s+`?{escaped}`?\b", text) is not None
    if kind == "interface":
        return re.search(rf"\binterface\s+`?{escaped}`?\b", text) is not None
    if kind == "property":
        return re.search(rf"\b(?:val|var)\s+`?{escaped}`?\b", text) is not None

    return re.search(rf"\b`?{escaped}`?\b", text) is not None
