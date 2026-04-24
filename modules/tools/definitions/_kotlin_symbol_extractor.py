from __future__ import annotations

import re
from pathlib import Path
from typing import Any

from tree_sitter import Parser

from modules.code_parser import CodeParser


class KotlinSymbolExtractor:
    SUPPORTED_SYMBOL_KINDS = {
        "auto",
        "unknown",
        "function",
        "composable",
        "class",
        "enum",
        "object",
        "interface",
        "method",
        "property",
    }
    OWNER_NODE_TYPES = {
        "class_declaration",
        "enum_class_declaration",
        "object_declaration",
        "interface_declaration",
    }
    BODY_NODE_TYPES = {
        "class_body",
        "function_body",
        "enum_class_body",
        "initializer",
    }
    SYMBOL_NODE_TYPES = {
        "function_declaration",
        "class_declaration",
        "enum_class_declaration",
        "object_declaration",
        "interface_declaration",
        "property_declaration",
    }

    def __init__(self):
        self.code_parser = CodeParser()

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
        if p.suffix.lower() != ".kt":
            return {
                "status": "error",
                "error_code": "VALIDATION_ERROR",
                "recoverable": True,
                "next_actions": ["read_file", "read_file_skeleton"],
                "output": (
                    f"extract_symbol currently supports Kotlin .kt files only. "
                    f"Got: {p.suffix or '(no extension)'}"
                ),
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
                "output": f"Unsupported symbol_kind '{symbol_kind}'. Supported: {supported}.",
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
            info = self._build_symbol_info(node, content, content_bytes, include_body, include_signature)
            if info is not None:
                if info["name"] == symbol_name and self._container_matches(info, container_name) and self._kind_matches(
                    normalized_kind, info
                ):
                    matches.append(info)
            for child in node.children:
                walk(child)

        walk(tree.root_node)

        if not matches:
            skeleton_hint = self._safe_skeleton(path, content)
            owner_hint = f" in container '{container_name}'" if container_name else ""
            kind_hint = "" if normalized_kind in {"auto", "unknown"} else f" ({normalized_kind})"
            return {
                "status": "error",
                "error_code": "NOT_FOUND",
                "recoverable": True,
                "next_actions": ["extract_symbol", "read_file_skeleton", "search_content", "read_file"],
                "output": f"Symbol '{symbol_name}'{kind_hint} was not found{owner_hint} in {path}.",
                "error_details": {
                    "path": path,
                    "symbol_name": symbol_name,
                    "symbol_kind": normalized_kind,
                    "container_name": container_name,
                    "supported_symbol_kinds": sorted(self.SUPPORTED_SYMBOL_KINDS),
                    "skeleton_hint": skeleton_hint,
                },
            }

        matches.sort(
            key=lambda item: (
                item["owner_name"] or "",
                item["kind"],
                item["start_line"],
                item["start_col"],
            )
        )

        if occurrence > len(matches):
            return {
                "status": "error",
                "error_code": "VALIDATION_ERROR",
                "recoverable": True,
                "next_actions": ["extract_symbol"],
                "output": (
                    f"Requested occurrence={occurrence}, but only {len(matches)} matches exist "
                    f"for symbol '{symbol_name}'."
                ),
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
                "output": (
                    f"Multiple Kotlin symbols named '{symbol_name}' were found. "
                    "Specify container_name, symbol_kind, or occurrence."
                ),
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
            "language": "kotlin",
            "symbol_name": selected["name"],
            "symbol_kind": selected["kind"],
            "container_name": selected["owner_name"],
            "container_chain": list(selected["owner_chain"]),
            "signature": selected["signature"] if include_signature else "",
            "body": selected["body"] if include_body else "",
            "start_line": selected["start_line"],
            "end_line": selected["end_line"],
            "start_col": selected["start_col"],
            "end_col": selected["end_col"],
            "line_range": f"{selected['start_line']}-{selected['end_line']}",
            "occurrence": occurrence,
            "match_count": len(matches),
            "include_body": include_body,
            "include_signature": include_signature,
            "include_line_range": include_line_range,
            "candidates": [self._candidate_summary(item) for item in matches],
        }

    def _normalize_symbol_kind(self, symbol_kind: str | None) -> str:
        value = str(symbol_kind or "auto").strip().lower()
        aliases = {
            "": "auto",
            "any": "auto",
            "symbol": "auto",
            "top_level_function": "function",
            "composable_function": "composable",
            "property_declaration": "property",
            "val": "property",
            "var": "property",
            "enum_class": "enum",
            "enumclass": "enum",
        }
        return aliases.get(value, value)

    def _safe_skeleton(self, path: str, content: str) -> str | None:
        try:
            return self.code_parser.get_skeleton(path, content)
        except Exception:
            return None

    def _container_matches(self, info: dict[str, Any], container_name: str | None) -> bool:
        if not container_name:
            return True
        candidate = str(container_name).strip()
        if not candidate:
            return True
        return candidate == info["owner_name"] or candidate in info["owner_chain"]

    def _kind_matches(self, requested_kind: str, info: dict[str, Any]) -> bool:
        if requested_kind in {"auto", "unknown"}:
            return True
        if requested_kind == "composable":
            return info["is_composable"]
        if requested_kind == "function":
            return info["node_type"] == "function_declaration"
        if requested_kind == "method":
            return info["node_type"] == "function_declaration" and bool(info["owner_name"])
        if requested_kind == "enum":
            return info["kind"] == "enum"
        return info["kind"] == requested_kind

    def _build_symbol_info(
        self,
        node,
        content: str,
        content_bytes: bytes,
        include_body: bool,
        include_signature: bool,
    ) -> dict[str, Any] | None:
        if node.type not in self.SYMBOL_NODE_TYPES:
            return None

        declaration_start = self._expanded_declaration_start_byte(node, content)
        full_source = content_bytes[declaration_start:node.end_byte].decode("utf-8", errors="replace").strip()
        signature = self._extract_signature(node, content, content_bytes, declaration_start).strip()
        if not signature:
            return None

        if node.type == "function_declaration":
            symbol_name = self._extract_function_name(signature)
        elif node.type == "property_declaration":
            symbol_name = self._extract_property_name(signature)
        else:
            symbol_name = self._extract_owner_name(node.type, signature)
        if not symbol_name:
            return None

        owner_chain = self._find_owner_chain(node, content_bytes)
        owner_name = owner_chain[0] if owner_chain else None
        has_composable = self._is_composable_signature(signature)
        is_enum = self._is_enum_declaration(node.type, signature)
        kind = self._resolved_symbol_kind(node.type, owner_name, has_composable, is_enum)

        start_line, start_col = self._line_col_from_offset(content, declaration_start)
        end_line = node.end_point[0] + 1
        end_col = node.end_point[1] + 1
        body = self._extract_body(node, content, content_bytes)
        selected_text = self._build_selected_text(
            signature=signature,
            body=body,
            full_source=full_source,
            include_body=include_body,
            include_signature=include_signature,
        )

        return {
            "name": symbol_name,
            "kind": kind,
            "node_type": node.type,
            "owner_name": owner_name,
            "owner_chain": owner_chain,
            "is_composable": has_composable,
            "is_enum": is_enum,
            "signature": signature,
            "body": body,
            "selected_text": selected_text,
            "start_line": start_line,
            "end_line": max(start_line, end_line),
            "start_col": start_col,
            "end_col": end_col,
        }

    def _build_selected_text(
        self,
        *,
        signature: str,
        body: str,
        full_source: str,
        include_body: bool,
        include_signature: bool,
    ) -> str:
        if include_body and include_signature:
            return full_source
        if include_body and not include_signature:
            return body or full_source
        return signature

    def _resolved_symbol_kind(
        self,
        node_type: str,
        owner_name: str | None,
        has_composable: bool,
        is_enum: bool,
    ) -> str:
        if node_type == "function_declaration":
            if has_composable:
                return "composable"
            if owner_name:
                return "method"
            return "function"
        if is_enum:
            return "enum"
        if node_type == "class_declaration":
            return "class"
        if node_type == "object_declaration":
            return "object"
        if node_type == "interface_declaration":
            return "interface"
        return "property"

    def _is_enum_declaration(self, node_type: str, signature: str) -> bool:
        if node_type == "enum_class_declaration":
            return True
        compact = " ".join(signature.split())
        return bool(re.search(r"\benum\s+class\b", compact))

    def _expanded_declaration_start_byte(self, node, content: str) -> int:
        start_line = node.start_point[0]
        lines = content.splitlines(keepends=True)
        if not lines:
            return node.start_byte
        start = start_line
        while start > 0:
            prev = lines[start - 1].strip()
            if prev.startswith("@"):
                start -= 1
                continue
            break
        return len("".join(lines[:start]).encode("utf-8"))

    def _extract_signature(self, node, content: str, content_bytes: bytes, declaration_start: int) -> str:
        end_byte = self._signature_end_offset_from_bytes(node, content_bytes)
        raw = content_bytes[declaration_start:end_byte].decode("utf-8", errors="replace")
        return raw.strip()

    def _extract_body(self, node, content: str, content_bytes: bytes) -> str:
        body_node = self._first_body_child(node)
        if body_node is not None:
            return content_bytes[body_node.start_byte:node.end_byte].decode("utf-8", errors="replace").strip()
        if node.type == "function_declaration":
            node_text = content_bytes[node.start_byte:node.end_byte].decode("utf-8", errors="replace")
            eq_index = self._find_expression_body_equals(node_text)
            if eq_index is not None:
                return node_text[eq_index:].strip()
        if node.type == "property_declaration":
            node_text = content_bytes[node.start_byte:node.end_byte].decode("utf-8", errors="replace")
            eq_index = self._find_expression_body_equals(node_text)
            if eq_index is not None:
                return node_text[eq_index:].strip()
        return content_bytes[node.start_byte:node.end_byte].decode("utf-8", errors="replace").strip()

    def _first_body_child(self, node):
        for child in node.children:
            if child.type in self.BODY_NODE_TYPES:
                return child
        return None

    def _signature_end_offset_from_bytes(self, node, content_bytes: bytes) -> int:
        body_node = self._first_body_child(node)
        if body_node is not None:
            return body_node.start_byte

        node_text = content_bytes[node.start_byte:node.end_byte].decode("utf-8", errors="replace")
        if node.type in {"function_declaration", "property_declaration"}:
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
                if prev in ("=", "!", ">", "<") or nxt == "=":
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
            match = re.search(pattern, compact)
            if match:
                raw_name = match.group(1)
                return raw_name[1:-1] if raw_name.startswith("`") and raw_name.endswith("`") else raw_name
        return None

    def _extract_property_name(self, signature: str) -> str | None:
        compact = " ".join(signature.split())
        match = re.search(r"\b(?:val|var)\s+(`[^`]+`|[A-Za-z_][A-Za-z0-9_]*)", compact)
        if not match:
            return None
        raw_name = match.group(1)
        return raw_name[1:-1] if raw_name.startswith("`") and raw_name.endswith("`") else raw_name

    def _find_owner_chain(self, node, content_bytes: bytes) -> list[str]:
        owners: list[str] = []
        current = node.parent
        while current is not None:
            if current.type in self.OWNER_NODE_TYPES:
                owner_source = content_bytes[current.start_byte:current.end_byte].decode("utf-8", errors="replace")
                owner_name = self._extract_owner_name(current.type, owner_source)
                if owner_name:
                    owners.append(owner_name)
            current = current.parent
        return owners

    def _extract_owner_name(self, node_type: str, source: str) -> str | None:
        compact = " ".join(source.split())
        patterns = {
            "class_declaration": r"\bclass\s+(`[^`]+`|[A-Za-z_][A-Za-z0-9_]*)",
            "enum_class_declaration": r"\benum\s+class\s+(`[^`]+`|[A-Za-z_][A-Za-z0-9_]*)",
            "object_declaration": r"\bobject\s+(`[^`]+`|[A-Za-z_][A-Za-z0-9_]*)",
            "interface_declaration": r"\binterface\s+(`[^`]+`|[A-Za-z_][A-Za-z0-9_]*)",
        }

        pattern = patterns.get(node_type)
        if pattern:
            match = re.search(pattern, compact)
            if match:
                raw_name = match.group(1)
                return raw_name[1:-1] if raw_name.startswith("`") and raw_name.endswith("`") else raw_name

        fallback_patterns = [
            r"\benum\s+class\s+(`[^`]+`|[A-Za-z_][A-Za-z0-9_]*)",
            r"\bclass\s+(`[^`]+`|[A-Za-z_][A-Za-z0-9_]*)",
            r"\bobject\s+(`[^`]+`|[A-Za-z_][A-Za-z0-9_]*)",
            r"\binterface\s+(`[^`]+`|[A-Za-z_][A-Za-z0-9_]*)",
        ]
        for fallback in fallback_patterns:
            match = re.search(fallback, compact)
            if match:
                raw_name = match.group(1)
                return raw_name[1:-1] if raw_name.startswith("`") and raw_name.endswith("`") else raw_name
        return None

    def _is_composable_signature(self, signature: str) -> bool:
        compact = " ".join(signature.split())
        return "@Composable" in compact

    def _line_col_from_offset(self, text: str, offset: int) -> tuple[int, int]:
        offset = max(0, min(offset, len(text)))
        line = text.count("\n", 0, offset) + 1
        last_newline = text.rfind("\n", 0, offset)
        col = offset + 1 if last_newline < 0 else offset - last_newline
        return line, col

    def _candidate_summary(self, item: dict[str, Any]) -> dict[str, Any]:
        return {
            "name": item["name"],
            "kind": item["kind"],
            "owner_name": item["owner_name"],
            "signature": item["signature"],
            "start_line": item["start_line"],
            "end_line": item["end_line"],
        }
