from __future__ import annotations

import ast
from pathlib import Path
from typing import Any


class PythonSymbolExtractor:
    SUPPORTED_SYMBOL_KINDS = {
        "auto",
        "unknown",
        "function",
        "async_function",
        "class",
        "method",
    }

    def extract_symbol(
        self,
        *,
        path: str,
        symbol_name: str,
        symbol_kind: str | None = None,
        container_name: str | None = None,
        occurrence: int = 1,
        include_body: bool = True,
        include_signature: bool = True,
        include_line_range: bool = True,
    ) -> dict[str, Any]:
        p = Path(path)
        if not p.exists():
            parent = str(p.parent) if str(p.parent) else "."
            return {
                "status": "error",
                "error_code": "NOT_FOUND",
                "recoverable": True,
                "next_actions": ["list_directory", "search_files", "read_file_skeleton", "read_file"],
                "output": f"File not found: {path}",
                "error_details": {"path": path, "suggested_path": parent},
            }
        if not p.is_file():
            return {
                "status": "error",
                "error_code": "VALIDATION_ERROR",
                "recoverable": True,
                "next_actions": ["read_file", "read_file_skeleton"],
                "output": f"Not a file: {path}",
            }
        if p.suffix.lower() != ".py":
            return {
                "status": "error",
                "error_code": "VALIDATION_ERROR",
                "recoverable": True,
                "next_actions": ["read_file", "read_file_skeleton"],
                "output": f"Python symbol extraction supports .py files only. Got: {p.suffix or '(no extension)'}",
            }
        if not isinstance(symbol_name, str) or not symbol_name.strip():
            return {
                "status": "error",
                "error_code": "VALIDATION_ERROR",
                "recoverable": True,
                "next_actions": ["extract_symbol"],
                "output": "Parameter 'symbol_name' must be a non-empty string.",
            }
        if not include_body and not include_signature:
            return {
                "status": "error",
                "error_code": "VALIDATION_ERROR",
                "recoverable": True,
                "next_actions": ["extract_symbol"],
                "output": "At least one of 'include_body' or 'include_signature' must be true.",
            }

        normalized_kind = self._normalize_symbol_kind(symbol_kind)
        if normalized_kind not in self.SUPPORTED_SYMBOL_KINDS:
            supported = ", ".join(sorted(self.SUPPORTED_SYMBOL_KINDS))
            return {
                "status": "error",
                "error_code": "VALIDATION_ERROR",
                "recoverable": True,
                "next_actions": ["extract_symbol"],
                "output": f"Unsupported Python symbol_kind '{symbol_kind}'. Supported: {supported}.",
            }

        try:
            occurrence = int(occurrence)
        except Exception:
            occurrence = 1
        if occurrence < 1:
            return {
                "status": "error",
                "error_code": "VALIDATION_ERROR",
                "recoverable": True,
                "next_actions": ["extract_symbol"],
                "output": "Parameter 'occurrence' must be >= 1.",
            }

        content = p.read_text(encoding="utf-8", errors="replace")
        try:
            tree = ast.parse(content)
        except SyntaxError as exc:
            return {
                "status": "error",
                "error_code": "SYNTAX_ERROR",
                "recoverable": True,
                "next_actions": ["read_chunk", "read_file", "edit_file"],
                "output": f"Cannot parse Python file before symbol extraction: {exc}",
                "error_details": {"path": path, "line": exc.lineno, "offset": exc.offset},
            }

        lines = content.splitlines(keepends=True)
        matches: list[dict[str, Any]] = []

        for node in ast.walk(tree):
            if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
                continue
            info = self._build_symbol_info(node, lines, include_body, include_signature)
            if info is None:
                continue
            info["owner_name"] = self._owner_name(tree, node)
            if info["name"] != symbol_name:
                continue
            if container_name and info["owner_name"] != container_name:
                continue
            if not self._kind_matches(normalized_kind, info):
                continue
            matches.append(info)

        if not matches:
            owner_hint = f" in container '{container_name}'" if container_name else ""
            kind_hint = "" if normalized_kind in {"auto", "unknown"} else f" ({normalized_kind})"
            return {
                "status": "error",
                "error_code": "NOT_FOUND",
                "recoverable": True,
                "next_actions": ["read_file_skeleton", "search_content", "read_chunk", "read_file"],
                "output": f"Python symbol '{symbol_name}'{kind_hint} was not found{owner_hint} in {path}.",
                "error_details": {
                    "path": path,
                    "symbol_name": symbol_name,
                    "symbol_kind": normalized_kind,
                    "container_name": container_name,
                    "supported_symbol_kinds": sorted(self.SUPPORTED_SYMBOL_KINDS),
                },
            }

        matches.sort(key=lambda item: (item["owner_name"] or "", item["kind"], item["start_line"], item["start_col"]))

        if occurrence > len(matches):
            return {
                "status": "error",
                "error_code": "VALIDATION_ERROR",
                "recoverable": True,
                "next_actions": ["extract_symbol"],
                "output": f"Requested occurrence={occurrence}, but only {len(matches)} matches exist for Python symbol '{symbol_name}'.",
                "error_details": {
                    "path": path,
                    "symbol_name": symbol_name,
                    "symbol_kind": normalized_kind,
                    "container_name": container_name,
                    "available_occurrences": len(matches),
                    "candidates": [self._candidate_summary(item) for item in matches],
                },
            }

        if len(matches) > 1 and container_name is None and occurrence == 1:
            return {
                "status": "error",
                "error_code": "AMBIGUOUS_MATCH",
                "recoverable": True,
                "next_actions": ["extract_symbol", "read_file_skeleton"],
                "output": f"Multiple Python symbols named '{symbol_name}' were found. Specify container_name, symbol_kind, or occurrence.",
                "error_details": {
                    "path": path,
                    "symbol_name": symbol_name,
                    "symbol_kind": normalized_kind,
                    "container_name": container_name,
                    "match_count": len(matches),
                    "candidates": [self._candidate_summary(item) for item in matches],
                },
            }

        selected = matches[occurrence - 1]
        return {
            "status": "success",
            "output": selected["selected_text"],
            "file_content": selected["selected_text"],
            "file_path": str(p),
            "tool_variant": "extract_symbol",
            "language": "python",
            "symbol_name": selected["name"],
            "symbol_kind": selected["kind"],
            "container_name": selected["owner_name"],
            "container_chain": [selected["owner_name"]] if selected["owner_name"] else [],
            "signature": selected["signature"] if include_signature else "",
            "body": selected["body"] if include_body else "",
            "start_line": selected["start_line"],
            "end_line": selected["end_line"],
            "start_col": selected["start_col"],
            "end_col": selected["end_col"],
        }

    def _build_symbol_info(self, node: ast.AST, lines: list[str], include_body: bool, include_signature: bool) -> dict[str, Any] | None:
        start_line = int(getattr(node, "lineno", 0) or 0)
        end_line = int(getattr(node, "end_lineno", 0) or 0)
        start_col = int(getattr(node, "col_offset", 0) or 0) + 1
        end_col = int(getattr(node, "end_col_offset", 0) or 0) + 1
        if start_line < 1 or end_line < start_line:
            return None

        selected_text = "".join(lines[start_line - 1:end_line])
        signature = lines[start_line - 1].rstrip("\n") if include_signature and start_line - 1 < len(lines) else ""
        body = selected_text if include_body else ""
        kind = self._node_kind(node)
        return {
            "name": str(getattr(node, "name", "") or ""),
            "kind": kind,
            "owner_name": "",
            "selected_text": selected_text,
            "signature": signature,
            "body": body,
            "start_line": start_line,
            "end_line": end_line,
            "start_col": start_col,
            "end_col": end_col,
        }

    def _owner_name(self, tree: ast.Module, target: ast.AST) -> str:
        for class_node in [n for n in ast.walk(tree) if isinstance(n, ast.ClassDef)]:
            for child in class_node.body:
                if child is target:
                    return class_node.name
        return ""

    def _node_kind(self, node: ast.AST) -> str:
        if isinstance(node, ast.ClassDef):
            return "class"
        if isinstance(node, ast.AsyncFunctionDef):
            return "async_function"
        if isinstance(node, ast.FunctionDef):
            return "function"
        return "unknown"

    def _kind_matches(self, normalized_kind: str, info: dict[str, Any]) -> bool:
        if normalized_kind in {"auto", "unknown"}:
            return True
        if normalized_kind == "method":
            return info.get("kind") in {"function", "async_function"} and bool(info.get("owner_name"))
        if normalized_kind == "function":
            return info.get("kind") in {"function", "async_function"} and not bool(info.get("owner_name"))
        return info.get("kind") == normalized_kind

    def _normalize_symbol_kind(self, symbol_kind: str | None) -> str:
        value = str(symbol_kind or "auto").strip().lower()
        if value in {"def", "func"}:
            return "function"
        return value or "auto"

    def _candidate_summary(self, item: dict[str, Any]) -> dict[str, Any]:
        return {
            "name": item.get("name"),
            "kind": item.get("kind"),
            "container_name": item.get("owner_name"),
            "start_line": item.get("start_line"),
            "end_line": item.get("end_line"),
            "signature": item.get("signature"),
        }
