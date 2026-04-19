import os
import re
from pathlib import Path
from typing import Any

from ..base import BaseTool
from modules.code_parser import CodeParser
from tree_sitter import Parser


class ExtractKotlinFunctionTool(BaseTool):
    name = "extract_kotlin_function"
    description = (
        "Extracts a Kotlin function or method from a .kt file using tree-sitter. "
        "Params: 'path' (str), 'function_name' (str), optional "
        "'class_name' (str), optional 'occurrence' (int, default 1), "
        "optional 'include_body' (bool, default True). "
        "Returns exact source, signature, and line range. "
        "If multiple matches exist, returns candidates and requires refinement."
    )

    _FUNCTION_NODE_TYPE = "function_declaration"
    _OWNER_NODE_TYPES = {
        "class_declaration",
        "object_declaration",
        "interface_declaration",
    }

    def __init__(self):
        self.code_parser = CodeParser()

    async def execute(
        self,
        path: str,
        function_name: str,
        class_name: str | None = None,
        occurrence: int = 1,
        include_body: bool = True,
        **kwargs,
    ) -> dict[str, Any]:
        try:
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

            if p.suffix.lower() != ".kt":
                return {
                    "status": "error",
                    "error_code": "VALIDATION_ERROR",
                    "recoverable": True,
                    "next_actions": ["read_file", "read_file_skeleton"],
                    "output": (
                        f"extract_kotlin_function only supports .kt files. "
                        f"Got: {p.suffix or '(no extension)'}"
                    ),
                }

            if not isinstance(function_name, str) or not function_name.strip():
                return {
                    "status": "error",
                    "error_code": "VALIDATION_ERROR",
                    "recoverable": True,
                    "next_actions": ["extract_kotlin_function"],
                    "output": "Parameter 'function_name' must be a non-empty string.",
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
                    "next_actions": ["extract_kotlin_function"],
                    "output": "Parameter 'occurrence' must be >= 1.",
                }

            content = p.read_text(encoding="utf-8", errors="replace")
            content_bytes = content.encode("utf-8")

            lang = self.code_parser._get_language(".kt")
            if lang is None:
                return {
                    "status": "error",
                    "error_code": "DEPENDENCY_UNAVAILABLE",
                    "recoverable": True,
                    "next_actions": ["read_file", "read_file_skeleton"],
                    "output": (
                        "Kotlin tree-sitter language is unavailable. "
                        "Check libs/kotlin.so for the current platform."
                    ),
                    "error_details": {
                        "path": path,
                        "expected_so": self.code_parser._get_lib_path(
                            self.code_parser.configs[".kt"]["so"]
                        ),
                    },
                }

            parser = Parser()
            if hasattr(parser, "set_language"):
                parser.set_language(lang)
            else:
                parser.language = lang

            tree = parser.parse(content_bytes)
            matches: list[dict[str, Any]] = []

            def walk(node):
                if node.type == self._FUNCTION_NODE_TYPE:
                    info = self._build_function_info(
                        node=node,
                        content=content,
                        content_bytes=content_bytes,
                        include_body=include_body,
                    )
                    if info is not None:
                        name_ok = info["name"] == function_name
                        class_ok = class_name is None or info["owner_name"] == class_name
                        if name_ok and class_ok:
                            matches.append(info)

                for child in node.children:
                    walk(child)

            walk(tree.root_node)

            if not matches:
                skeleton_hint = self._safe_skeleton(path, content)
                owner_hint = f" in class/object/interface '{class_name}'" if class_name else ""
                return {
                    "status": "error",
                    "error_code": "NOT_FOUND",
                    "recoverable": True,
                    "next_actions": ["read_file_skeleton", "read_file", "search_content"],
                    "output": (
                        f"Kotlin function '{function_name}' was not found{owner_hint} in {path}."
                    ),
                    "error_details": {
                        "path": path,
                        "function_name": function_name,
                        "class_name": class_name,
                        "skeleton_hint": skeleton_hint,
                    },
                }

            matches.sort(
                key=lambda x: (
                    x["owner_name"] or "",
                    x["start_line"],
                    x["start_col"],
                )
            )

            if len(matches) > 1 and occurrence > len(matches):
                return {
                    "status": "error",
                    "error_code": "VALIDATION_ERROR",
                    "recoverable": True,
                    "next_actions": ["extract_kotlin_function"],
                    "output": (
                        f"Requested occurrence={occurrence}, but only {len(matches)} matches exist "
                        f"for function '{function_name}'."
                    ),
                    "error_details": {
                        "path": path,
                        "function_name": function_name,
                        "class_name": class_name,
                        "available_occurrences": len(matches),
                        "candidates": [self._candidate_summary(m) for m in matches],
                    },
                }

            if len(matches) > 1 and class_name is None and occurrence == 1:
                return {
                    "status": "error",
                    "error_code": "AMBIGUOUS_MATCH",
                    "recoverable": True,
                    "next_actions": ["extract_kotlin_function", "read_file_skeleton"],
                    "output": (
                        f"Multiple Kotlin functions named '{function_name}' were found. "
                        "Specify class_name or occurrence."
                    ),
                    "error_details": {
                        "path": path,
                        "function_name": function_name,
                        "class_name": class_name,
                        "match_count": len(matches),
                        "candidates": [self._candidate_summary(m) for m in matches],
                    },
                }

            selected = matches[occurrence - 1]

            return {
                "status": "success",
                "output": selected["source"],
                "file_content": selected["source"],
                "file_path": str(p),
                "tool_variant": "extract_kotlin_function",
                "language": "kotlin",
                "function_name": selected["name"],
                "class_name": selected["owner_name"],
                "signature": selected["signature"],
                "start_line": selected["start_line"],
                "end_line": selected["end_line"],
                "start_col": selected["start_col"],
                "end_col": selected["end_col"],
                "occurrence": occurrence,
                "match_count": len(matches),
                "include_body": include_body,
                "candidates": [self._candidate_summary(m) for m in matches],
            }

        except Exception as e:
            return {
                "status": "error",
                "error_code": "INTERNAL",
                "recoverable": False,
                "output": f"extract_kotlin_function failed: {str(e)}",
            }

    def _safe_skeleton(self, path: str, content: str) -> str | None:
        try:
            return self.code_parser.get_skeleton(path, content)
        except Exception:
            return None

    def _candidate_summary(self, item: dict[str, Any]) -> dict[str, Any]:
        return {
            "name": item["name"],
            "owner_name": item["owner_name"],
            "signature": item["signature"],
            "start_line": item["start_line"],
            "end_line": item["end_line"],
        }

    def _build_function_info(
        self,
        node,
        content: str,
        content_bytes: bytes,
        include_body: bool,
    ) -> dict[str, Any] | None:
        source = content_bytes[node.start_byte:node.end_byte].decode("utf-8", errors="replace")
        signature = self._extract_signature(node, content_bytes)
        function_name = self._extract_function_name(signature)

        if not function_name:
            return None

        owner_name = self._find_owner_name(node, content_bytes)

        if include_body:
            selected_source = source
            end_line = node.end_point[0] + 1
            end_col = node.end_point[1] + 1
        else:
            selected_source = signature
            sig_end_line, sig_end_col = self._line_col_from_offset(
                content,
                self._signature_end_offset(node, content_bytes),
            )
            end_line = sig_end_line
            end_col = sig_end_col

        start_line = node.start_point[0] + 1
        start_col = node.start_point[1] + 1

        return {
            "name": function_name,
            "owner_name": owner_name,
            "signature": signature,
            "source": selected_source,
            "start_line": start_line,
            "end_line": end_line,
            "start_col": start_col,
            "end_col": end_col,
        }

    def _extract_signature(self, node, content_bytes: bytes) -> str:
        end_byte = self._signature_end_offset_from_bytes(node, content_bytes)
        raw = content_bytes[node.start_byte:end_byte].decode("utf-8", errors="replace")
        return raw.strip()

    def _signature_end_offset(self, node, content: bytes | str) -> int:
        if isinstance(content, str):
            content_bytes = content.encode("utf-8")
        else:
            content_bytes = content
        return self._signature_end_offset_from_bytes(node, content_bytes)

    def _signature_end_offset_from_bytes(self, node, content_bytes: bytes) -> int:
        body_node = None
        for child in node.children:
            if child.type in ("function_body", "block"):
                body_node = child
                break

        if body_node is not None:
            return body_node.start_byte

        node_text = content_bytes[node.start_byte:node.end_byte].decode("utf-8", errors="replace")
        eq_index = self._find_expression_body_equals(node_text)
        if eq_index is not None:
            prefix = node_text[:eq_index]
            return node.start_byte + len(prefix.encode("utf-8"))

        return node.end_byte

    def _find_expression_body_equals(self, text: str) -> int | None:
        in_line_comment = False
        in_block_comment = False
        in_string = False
        string_char = ""
        escape = False

        i = 0
        while i < len(text):
            ch = text[i]
            nxt = text[i + 1] if i + 1 < len(text) else ""

            if in_line_comment:
                if ch == "\n":
                    in_line_comment = False
                i += 1
                continue

            if in_block_comment:
                if ch == "*" and nxt == "/":
                    in_block_comment = False
                    i += 2
                    continue
                i += 1
                continue

            if in_string:
                if escape:
                    escape = False
                    i += 1
                    continue
                if ch == "\\":
                    escape = True
                    i += 1
                    continue
                if ch == string_char:
                    in_string = False
                    string_char = ""
                i += 1
                continue

            if ch == "/" and nxt == "/":
                in_line_comment = True
                i += 2
                continue

            if ch == "/" and nxt == "*":
                in_block_comment = True
                i += 2
                continue

            if ch in ('"', "'"):
                in_string = True
                string_char = ch
                i += 1
                continue

            if ch == "=":
                prev = text[i - 1] if i > 0 else ""
                next_ch = nxt
                if prev in ("=", "!", ">", "<") or next_ch == "=":
                    i += 1
                    continue
                return i

            i += 1

        return None

    def _extract_function_name(self, signature: str) -> str | None:
        compact = " ".join(signature.split())

        patterns = [
            r"\bfun\s+(?:<[^>]*>\s*)?(?:`[^`]+`|[A-Za-z_][A-Za-z0-9_]*)\s*\.\s*(`[^`]+`|[A-Za-z_][A-Za-z0-9_]*)\s*\(",
            r"\bfun\s+(?:<[^>]*>\s*)?(`[^`]+`|[A-Za-z_][A-Za-z0-9_]*)\s*\(",
        ]

        for pattern in patterns:
            m = re.search(pattern, compact)
            if m:
                raw_name = m.group(1)
                return raw_name[1:-1] if raw_name.startswith("`") and raw_name.endswith("`") else raw_name

        return None

    def _find_owner_name(self, node, content_bytes: bytes) -> str | None:
        current = node.parent
        while current is not None:
            if current.type in self._OWNER_NODE_TYPES:
                owner_source = content_bytes[current.start_byte:current.end_byte].decode("utf-8", errors="replace")
                owner_name = self._extract_owner_name(current.type, owner_source)
                if owner_name:
                    return owner_name
            current = current.parent
        return None

    def _extract_owner_name(self, node_type: str, source: str) -> str | None:
        compact = " ".join(source.split())

        patterns = {
            "class_declaration": r"\bclass\s+(`[^`]+`|[A-Za-z_][A-Za-z0-9_]*)",
            "object_declaration": r"\bobject\s+(`[^`]+`|[A-Za-z_][A-Za-z0-9_]*)",
            "interface_declaration": r"\binterface\s+(`[^`]+`|[A-Za-z_][A-Za-z0-9_]*)",
        }

        pattern = patterns.get(node_type)
        if not pattern:
            return None

        m = re.search(pattern, compact)
        if not m:
            return None

        raw_name = m.group(1)
        return raw_name[1:-1] if raw_name.startswith("`") and raw_name.endswith("`") else raw_name

    def _line_col_from_offset(self, text: str, offset: int) -> tuple[int, int]:
        offset = max(0, min(offset, len(text)))
        line = text.count("\n", 0, offset) + 1
        last_newline = text.rfind("\n", 0, offset)
        col = offset + 1 if last_newline < 0 else offset - last_newline
        return line, col
