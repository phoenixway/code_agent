import os
import difflib
import re
from pathlib import Path
from ..base import BaseTool
from modules.types import ChangeProposal
from modules.code_parser import CodeParser


SOURCE_FILE_SUFFIXES = {
    ".py",
    ".kt",
    ".kts",
    ".java",
    ".xml",
    ".gradle",
    ".js",
    ".ts",
    ".tsx",
    ".jsx",
    ".swift",
    ".go",
    ".rs",
    ".rb",
    ".php",
    ".c",
    ".cc",
    ".cpp",
    ".h",
    ".hpp",
}

_GENERIC_UI_ANCHOR_RE = re.compile(
    r"^\s*(Spacer|Row|Column|Text|Box|Divider)\s*\(",
    re.IGNORECASE,
)


def _detect_line_endings(text: str) -> str:
    has_crlf = "\r\n" in text
    has_lf = "\n" in text
    if has_crlf and has_lf:
        return "mixed"
    if has_crlf:
        return "CRLF"
    if has_lf:
        return "LF"
    return "none"


def _normalize_line_endings(text: str) -> str:
    return text.replace("\r\n", "\n").replace("\r", "\n")


def _line_col_from_index(text: str, index: int) -> tuple[int, int]:
    index = max(0, min(index, len(text)))
    line = text.count("\n", 0, index) + 1
    last_nl = text.rfind("\n", 0, index)
    col = index + 1 if last_nl < 0 else index - last_nl
    return line, col


def _classify_search_mismatch(content: str, search_text: str) -> tuple[str, dict]:
    if not search_text:
        return "empty_search_text", {"first_diff": None}
    details: dict = {}
    normalized_content = _normalize_line_endings(content)
    normalized_search = _normalize_line_endings(search_text)
    if normalized_search in normalized_content and search_text not in content:
        details["line_endings_in_file"] = _detect_line_endings(content)
        return "line_ending_mismatch", details
    stripped = search_text.strip()
    if stripped and stripped in content:
        return "whitespace_mismatch", details
    first_search_line = search_text.splitlines()[0] if search_text.splitlines() else ""
    if first_search_line:
        if content.count(first_search_line) > 1:
            return "multiple_similar_blocks", details
        if first_search_line in content:
            return "indentation_or_partial_block_mismatch", details
    matcher = difflib.SequenceMatcher(None, search_text, content)
    best = matcher.find_longest_match(0, len(search_text), 0, len(content))
    similarity = matcher.ratio()
    details["similarity"] = round(float(similarity), 4)
    if best.size > 0:
        start = max(0, best.b - 120)
        end = min(len(content), best.b + best.size + 120)
        preview = content[start:end]
        details["best_match_preview"] = preview
        details["best_match_span"] = [best.b, best.b + best.size]
    if similarity >= 0.55:
        return "search_text_stale_or_block_modified", details
    return "no_similar_block_found", details


def _line_start_offsets(text: str) -> list[int]:
    offsets = [0]
    for idx, char in enumerate(text):
        if char == "\n":
            offsets.append(idx + 1)
    return offsets


def _line_number_for_offset(offsets: list[int], index: int) -> int:
    line = 1
    for idx, start in enumerate(offsets, start=1):
        if start > index:
            break
        line = idx
    return line


def _line_base_indent(line: str) -> str:
    return line[: len(line) - len(line.lstrip(" \t"))]


def _dedent_for_fuzzy_match(text: str) -> str:
    lines = _normalize_line_endings(text).split("\n")
    non_empty = [line for line in lines if line.strip()]
    if not non_empty:
        return ""
    indents = [len(line) - len(line.lstrip(" \t")) for line in non_empty]
    base = min(indents)
    return "\n".join(line[base:] if len(line) >= base else line for line in lines).strip()


def _indentation_normalized_fuzzy_candidates(content: str, search_text: str, *, max_candidates: int = 5) -> list[dict]:
    normalized_search = _dedent_for_fuzzy_match(search_text)
    if not normalized_search or len(normalized_search) < 12:
        return []

    content_norm = _normalize_line_endings(content)
    content_lines = content_norm.split("\n")
    search_line_count = max(1, len(_normalize_line_endings(search_text).split("\n")))
    offsets = _line_start_offsets(content_norm)
    candidates: list[dict] = []

    for start_idx in range(0, len(content_lines)):
        for extra in range(-2, 3):
            end_idx = start_idx + search_line_count + extra
            if end_idx <= start_idx or end_idx > len(content_lines):
                continue
            block = "\n".join(content_lines[start_idx:end_idx])
            if _dedent_for_fuzzy_match(block) != normalized_search:
                continue
            start_offset = offsets[start_idx]
            end_offset = offsets[end_idx] - 1 if end_idx < len(offsets) else len(content_norm)
            first_line = content_lines[start_idx] if start_idx < len(content_lines) else ""
            candidates.append(
                {
                    "mode": "indentation_normalized",
                    "start_line": start_idx + 1,
                    "end_line": end_idx,
                    "start_offset": start_offset,
                    "end_offset": end_offset,
                    "base_indent": _line_base_indent(first_line),
                    "preview": block[:500],
                }
            )
            if len(candidates) >= max_candidates:
                return candidates
    return candidates


def _build_first_diff(search_text: str, content: str) -> dict | None:
    limit = min(len(search_text), len(content))
    diff_idx = None
    for i in range(limit):
        if search_text[i] != content[i]:
            diff_idx = i
            break
    if diff_idx is None:
        if len(search_text) == len(content):
            return None
        diff_idx = limit
    line, col = _line_col_from_index(search_text, diff_idx)
    return {
        "index": diff_idx,
        "line": line,
        "col": col,
        "search_char": search_text[diff_idx:diff_idx + 1] or "",
        "file_char": content[diff_idx:diff_idx + 1] or "",
    }


_COMPACT_OMITTED_MARKER_RE = re.compile(
    r"\[content omitted:\s*\d+\s*chars,\s*sha256:[0-9a-f]{8,}",
    re.IGNORECASE,
)


def _compact_omitted_marker_count(text: str) -> int:
    if not isinstance(text, str) or not text:
        return 0
    return len(_COMPACT_OMITTED_MARKER_RE.findall(text))


def _validate_no_compact_markers(path: str, new_content: str, previous_content: str | None = None) -> dict | None:
    new_count = _compact_omitted_marker_count(new_content)
    if new_count == 0:
        return None
    prev_count = _compact_omitted_marker_count(previous_content or "")
    if previous_content is not None and new_count < prev_count:
        return None
    return {
        "status": "error",
        "error_code": "VALIDATION_ERROR",
        "recoverable": True,
        "next_actions": ["read_file", "write_file", "edit_file"],
        "output": "Refusing to write compact placeholder markers ('[content omitted: ... sha256: ...]') into workspace files. Use full file content instead.",
        "error_details": {
            "path": path,
            "detected_marker": "content_omitted_placeholder",
            "marker_count_new": new_count,
            "marker_count_previous": prev_count,
        },
    }


def _is_existing_source_file(path: str) -> bool:
    lowered = str(path or "").strip().lower()
    if not lowered:
        return False
    if lowered.endswith(".gradle.kts"):
        return True
    return any(lowered.endswith(suffix) for suffix in SOURCE_FILE_SUFFIXES)


def _looks_like_compose_ui_file(path: str) -> bool:
    lowered = str(path or "").strip().lower()
    return lowered.endswith(".kt") and any(token in lowered for token in ("ui", "screen", "view", "composable", "bookmark"))


def _coverage_ratio(content: str, search_text: str) -> float:
    if not content:
        return 0.0
    return float(len(search_text or "")) / float(max(1, len(content)))


def _build_edit_file_guard_error(
    path: str,
    mismatch_type: str,
    output: str,
    *,
    search_text: str,
    replace_text: str,
    content: str,
    next_actions: list[str] | None = None,
) -> dict:
    return {
        "status": "error",
        "error_code": "VALIDATION_ERROR",
        "recoverable": True,
        "next_actions": next_actions or ["read_chunk", "extract_symbol", "search_content", "edit_file", "write_file"],
        "output": output,
        "error_details": {
            "path": path,
            "mismatch_type": mismatch_type,
            "search_text_length": len(search_text),
            "replace_text_length": len(replace_text),
            "file_length": len(content),
            "coverage_ratio": round(_coverage_ratio(content, search_text), 4),
        },
    }


def _validate_edit_file_scope(path: str, content: str, search_text: str, replace_text: str) -> dict | None:
    if search_text == replace_text:
        return {
            "status": "error",
            "error_code": "VALIDATION_ERROR",
            "recoverable": True,
            "next_actions": ["read_chunk", "read_file", "search_content", "edit_file"],
            "output": (
                "This edit would not change the file. "
                "If no change is needed, answer; otherwise provide a replacement that differs."
            ),
            "error_details": {
                "path": path,
                "mismatch_type": "noop_edit",
                "search_text_length": len(search_text),
                "replace_text_length": len(replace_text),
            },
        }

    if not _is_existing_source_file(path):
        return None

    stripped_content = str(content or "").strip()
    stripped_search = str(search_text or "").strip()
    coverage = _coverage_ratio(content, search_text)
    search_lines = str(search_text or "").count("\n") + 1 if search_text else 0

    if (
        _looks_like_compose_ui_file(path)
        and search_lines == 1
        and len(replace_text or "") > 500
        and _GENERIC_UI_ANCHOR_RE.match(str(search_text or "").strip())
    ):
        return _build_edit_file_guard_error(
            path,
            "bad_edit_anchor_too_generic",
            (
                "This edit anchor is too generic for a large UI insertion. "
                "Read the exact current composable block first and use a semantically bounded multi-line anchor."
            ),
            search_text=search_text,
            replace_text=replace_text,
            content=content,
            next_actions=["read_chunk", "read_file", "extract_symbol", "search_content", "edit_file"],
        )

    if (
        stripped_search
        and stripped_content
        and stripped_search == stripped_content
        and len(search_text) >= 400
    ):
        return _build_edit_file_guard_error(
            path,
            "edit_file_full_rewrite_disallowed",
            (
                "edit_file is for targeted edits, not a whole-file rewrite of an existing source file. "
                "Read the exact smaller target block and edit only that block. "
                "If a full rewrite is truly required, reread the full current file and use write_file only if the active intent allows it."
            ),
            search_text=search_text,
            replace_text=replace_text,
            content=content,
        )

    if len(search_text) >= 1200 and coverage >= 0.6 and search_lines >= 25:
        return _build_edit_file_guard_error(
            path,
            "edit_file_full_rewrite_disallowed",
            (
                "This edit_file request targets most of an existing source file. "
                "Use edit_file only for a smaller exact block. "
                "If targeted edit is impractical, reread the full current file and use write_file only when the intent contract explicitly allows it."
            ),
            search_text=search_text,
            replace_text=replace_text,
            content=content,
        )

    if (
        "import " in replace_text
        and "import " not in search_text
        and ("class " in replace_text or "interface " in replace_text or "object " in replace_text or "fun " in replace_text)
        and search_lines <= 3
    ):
        return _build_edit_file_guard_error(
            path,
            "edit_file_crosses_import_boundary",
            (
                "Do not inject import statements by replacing a class/function anchor with edit_file. "
                "Read the current package/import header and edit that exact header block separately, "
                "then apply a separate targeted edit for the class or function body if still needed."
            ),
            search_text=search_text,
            replace_text=replace_text,
            content=content,
            next_actions=["read_chunk", "read_file", "extract_symbol", "edit_file"],
        )

    return None


def _safe_int(value, default=None):
    try:
        return int(value)
    except Exception:
        return default


class ReadChunkTool(BaseTool):
    name = "read_chunk"
    description = (
        "Reads only a region from a file. Use this instead of full read_file when a file is too large "
        "or when you only need a specific region around a known symbol. "
        "Supports either byte ranges or line ranges. "
        "Params: 'path' (str), EITHER ('start_byte' (int), optional 'end_byte' (int)) "
        "OR ('start_line' (int), optional 'end_line' (int))."
    )

    MIN_NONEMPTY_CHARS = 1

    async def execute(
        self,
        path: str,
        start_byte: int | None = None,
        end_byte: int | None = None,
        start_line: int | None = None,
        end_line: int | None = None,
        **kwargs,
    ):
        try:
            p = Path(path)
            if not p.exists():
                parent = str(p.parent) if str(p.parent) else "."
                return {
                    "status": "error",
                    "error_code": "NOT_FOUND",
                    "recoverable": True,
                    "next_actions": ["list_directory", "search_files", "read_file_skeleton"],
                    "output": f"File not found: {path}",
                    "error_details": {"path": path, "suggested_path": parent},
                }
            if not p.is_file():
                return {
                    "status": "error",
                    "error_code": "VALIDATION_ERROR",
                    "recoverable": True,
                    "next_actions": ["list_directory", "read_file_skeleton"],
                    "output": f"Not a file: {path}",
                }

            sb = _safe_int(start_byte)
            eb = _safe_int(end_byte)
            sl = _safe_int(start_line)
            el = _safe_int(end_line)

            file_size = p.stat().st_size

            using_lines = sl is not None
            using_bytes = sb is not None

            if using_lines and using_bytes:
                return {
                    "status": "error",
                    "error_code": "VALIDATION_ERROR",
                    "recoverable": True,
                    "next_actions": ["read_chunk"],
                    "output": "read_chunk accepts either byte range or line range, not both at once.",
                }

            if not using_lines and not using_bytes:
                return {
                    "status": "error",
                    "error_code": "VALIDATION_ERROR",
                    "recoverable": True,
                    "next_actions": ["read_chunk"],
                    "output": "read_chunk requires either 'start_byte' or 'start_line'.",
                }

            if using_lines:
                if sl is None or sl < 1:
                    return {
                        "status": "error",
                        "error_code": "VALIDATION_ERROR",
                        "recoverable": True,
                        "next_actions": ["read_chunk"],
                        "output": "read_chunk requires start_line >= 1.",
                    }

                full_text = p.read_text(encoding="utf-8", errors="replace")
                lines = full_text.splitlines(keepends=True)

                if sl > max(1, len(lines)):
                    return {
                        "status": "error",
                        "error_code": "EMPTY_CHUNK_RESULT",
                        "recoverable": True,
                        "next_actions": ["search_content", "read_file_skeleton", "read_chunk"],
                        "output": (
                            f"Requested chunk starts beyond EOF lines: start_line={sl}, total_lines={len(lines)}. "
                            "Choose a smaller line range or locate the symbol first with search_content."
                        ),
                        "error_details": {"path": path, "start_line": sl, "total_lines": len(lines)},
                    }

                if el is None:
                    el = min(len(lines), sl + 199)
                if el < sl:
                    return {
                        "status": "error",
                        "error_code": "VALIDATION_ERROR",
                        "recoverable": True,
                        "next_actions": ["read_chunk"],
                        "output": "read_chunk requires end_line >= start_line.",
                    }

                el = min(el, len(lines))

                start_idx = sum(len(x.encode("utf-8")) for x in lines[: sl - 1])
                end_idx = sum(len(x.encode("utf-8")) for x in lines[:el])
                content = "".join(lines[sl - 1 : el])
                sb = start_idx
                eb = end_idx

                if len(content.strip()) < self.MIN_NONEMPTY_CHARS:
                    return {
                        "status": "error",
                        "error_code": "EMPTY_CHUNK_RESULT",
                        "recoverable": True,
                        "next_actions": ["search_content", "read_file_skeleton", "read_chunk"],
                        "output": (
                            f"Line chunk [{sl}, {el}] produced no useful text. "
                            "Choose a different range, or use search_content / read_file_skeleton first."
                        ),
                        "error_details": {
                            "path": path,
                            "start_line": sl,
                            "end_line": el,
                            "total_lines": len(lines),
                            "file_size": file_size,
                        },
                    }

                return {
                    "status": "success",
                    "output": content,
                    "file_content": content,
                    "file_path": str(p),
                    "chunked": True,
                    "start_byte": sb,
                    "end_byte": eb,
                    "start_line": sl,
                    "end_line": el,
                    "file_size": file_size,
                    "total_lines": len(lines),
                    "chunk_mode": "lines",
                    "tool_variant": "read_chunk",
                }

            if sb is None:
                return {
                    "status": "error",
                    "error_code": "VALIDATION_ERROR",
                    "recoverable": True,
                    "next_actions": ["read_chunk"],
                    "output": "read_chunk requires 'start_byte' (int) when using byte mode.",
                }

            if sb < 0:
                return {
                    "status": "error",
                    "error_code": "VALIDATION_ERROR",
                    "recoverable": True,
                    "next_actions": ["read_chunk"],
                    "output": "read_chunk requires start_byte >= 0.",
                }
            if sb >= file_size:
                return {
                    "status": "error",
                    "error_code": "EMPTY_CHUNK_RESULT",
                    "recoverable": True,
                    "next_actions": ["search_content", "read_file_skeleton", "read_chunk"],
                    "output": (
                        f"Requested chunk starts beyond or at EOF: start_byte={sb}, file_size={file_size}. "
                        "Choose a smaller range or locate the symbol first with search_content."
                    ),
                    "error_details": {"path": path, "start_byte": sb, "file_size": file_size},
                }

            if eb is None:
                eb = min(file_size, sb + 8192)
            if eb <= sb:
                return {
                    "status": "error",
                    "error_code": "VALIDATION_ERROR",
                    "recoverable": True,
                    "next_actions": ["read_chunk"],
                    "output": "read_chunk requires end_byte > start_byte.",
                }

            eb = min(eb, file_size)

            with open(p, "rb") as f:
                f.seek(sb)
                raw = f.read(eb - sb)
            content = raw.decode("utf-8", errors="replace")

            if len(content.strip()) < self.MIN_NONEMPTY_CHARS:
                return {
                    "status": "error",
                    "error_code": "EMPTY_CHUNK_RESULT",
                    "recoverable": True,
                    "next_actions": ["search_content", "read_file_skeleton", "read_chunk"],
                    "output": (
                        f"Chunk [{sb}, {eb}) produced no useful text. "
                        "Choose a different range, or use search_content / read_file_skeleton first."
                    ),
                    "error_details": {"path": path, "start_byte": sb, "end_byte": eb, "file_size": file_size},
                }

            return {
                "status": "success",
                "output": content,
                "file_content": content,
                "file_path": str(p),
                "chunked": True,
                "start_byte": sb,
                "end_byte": eb,
                "file_size": file_size,
                "chunk_mode": "bytes",
                "tool_variant": "read_chunk",
            }
        except Exception as e:
            return {
                "status": "error",
                "error_code": "INTERNAL",
                "recoverable": False,
                "output": str(e),
            }


class ReadFileTool(BaseTool):
    name = "read_file"
    description = (
        "Reads a whole file. Use this only when you truly need full implementation context. "
        "Prefer read_file_skeleton first for structure, and prefer read_chunk when you only need a region of a large file. "
        "Very large full reads require explicit confirm_large_read=true after the warning. "
        "Params: 'path' (str), optional 'confirm_large_read' (bool). "
        "Chunked byte-range reading is handled by the separate read_chunk tool."
    )

    LARGE_FILE_WARNING_BYTES = 256 * 1024
    HARD_LARGE_FILE_BYTES = 1024 * 1024

    async def execute(
        self,
        path: str,
        ui=None,
        confirm_large_read: bool = False,
        start_byte: int | None = None,
        end_byte: int | None = None,
        **kwargs,
    ):
        try:
            p = Path(path)
            if not p.exists():
                parent = str(p.parent) if str(p.parent) else "."
                return {
                    "status": "error",
                    "error_code": "NOT_FOUND",
                    "recoverable": True,
                    "next_actions": ["list_directory", "search_files", "create_file"],
                    "output": f"File not found: {path}",
                    "error_details": {"path": path, "suggested_path": parent},
                }
            if not p.is_file():
                return {
                    "status": "error",
                    "error_code": "VALIDATION_ERROR",
                    "recoverable": True,
                    "next_actions": ["list_directory", "read_file_skeleton"],
                    "output": f"Not a file: {path}",
                }

            if start_byte is not None or end_byte is not None:
                return {
                    "status": "error",
                    "error_code": "VALIDATION_ERROR",
                    "recoverable": True,
                    "next_actions": ["read_chunk"],
                    "output": "Byte-range reads are not supported by read_file. Use read_chunk instead.",
                }

            file_size = p.stat().st_size

            if file_size >= self.HARD_LARGE_FILE_BYTES and not confirm_large_read:
                warning = (
                    f"File {path} is very large ({file_size} bytes). Full read will likely bloat context and may trigger summarization. "
                    "Prefer read_file_skeleton first, or use read_chunk. "
                    "If full content is truly required, repeat read_file with confirm_large_read=true."
                )
                if ui and hasattr(ui, "print_system"):
                    try:
                        await ui.print_system(warning)
                    except Exception:
                        pass
                return {
                    "status": "error",
                    "error_code": "FULL_READ_CONFIRMATION_REQUIRED",
                    "recoverable": True,
                    "next_actions": ["read_file_skeleton", "read_chunk", "search_content", "read_file"],
                    "output": warning,
                    "file_path": str(p),
                    "file_size": file_size,
                    "requires_confirm_large_read": True,
                }

            content = p.read_text(encoding="utf-8", errors="replace")
            payload = {
                "status": "success",
                "output": content,
                "file_content": content,
                "file_path": str(p),
                "file_size": file_size,
            }
            if file_size >= self.LARGE_FILE_WARNING_BYTES:
                payload["large_file_read"] = True
                payload["skip_truncation"] = True
            return payload
        except Exception as e:
            return {
                "status": "error",
                "error_code": "INTERNAL",
                "recoverable": False,
                "output": str(e),
            }


class ReadFileSkeletonTool(BaseTool):
    name = "read_file_skeleton"
    description = (
        "Extracts a structural skeleton (classes/functions/signatures with line ranges) from a source file "
        "using tree-sitter for supported languages. Preferred fast-navigation step before broad read_file. "
        "Params: 'path' (str)"
    )

    def __init__(self):
        self.code_parser = CodeParser()

    async def execute(self, path: str, **kwargs):
        try:
            p = Path(path)
            if not p.exists():
                parent = str(p.parent) if str(p.parent) else "."
                return {
                    "status": "error",
                    "error_code": "NOT_FOUND",
                    "recoverable": True,
                    "next_actions": ["list_directory", "search_files", "read_file"],
                    "output": f"File not found: {path}",
                    "error_details": {"path": path, "suggested_path": parent},
                }
            if not p.is_file():
                return {
                    "status": "error",
                    "error_code": "VALIDATION_ERROR",
                    "recoverable": True,
                    "next_actions": ["list_directory", "read_file"],
                    "output": f"Not a file: {path}",
                }
            ext = p.suffix.lower()
            if ext not in self.code_parser.configs:
                supported = ", ".join(sorted(self.code_parser.configs.keys()))
                return {
                    "status": "error",
                    "error_code": "VALIDATION_ERROR",
                    "recoverable": True,
                    "next_actions": ["read_file"],
                    "output": f"Skeleton extraction is not supported for '{ext or '(no extension)'}'. Supported: {supported}.",
                }
            content = p.read_text(encoding="utf-8", errors="replace")
            skeleton = self.code_parser.get_skeleton(str(p), content)
            return {
                "status": "success",
                "output": (
                    f"Skeleton for {p}:\n{skeleton}\n\n"
                    "Note: this is a structural view with line ranges. "
                    "Prefer read_chunk with the shown range to inspect the exact symbol body cheaply; "
                    "use read_file only when full-file context is genuinely required."
                ),
                "file_path": str(p),
                "view": "skeleton",
                "skeleton_content": skeleton,
            }
        except Exception as e:
            return {
                "status": "error",
                "error_code": "INTERNAL",
                "recoverable": True,
                "next_actions": ["read_file"],
                "output": f"Failed to extract skeleton: {e}",
            }


class CreateFileTool(BaseTool):
    name = "create_file"
    description = "Creates a NEW file with content. Fails if file exists. Params: 'path' (str), 'content' (str)"

    async def execute(self, path: str, content: str):
        p = Path(path)
        if p.exists():
            return {
                "status": "error",
                "error_code": "VALIDATION_ERROR",
                "recoverable": True,
                "next_actions": ["read_file", "edit_file", "write_file"],
                "output": f"File {path} already exists. Use 'edit_file' or 'run_shell' to modify.",
            }
        marker_error = _validate_no_compact_markers(path, content)
        if marker_error:
            return marker_error
        return ChangeProposal(file_path=path, original_content="", new_content=content)


class WriteFileTool(BaseTool):
    name = "write_file"
    description = "Overwrites an existing file. Params: 'path' (str), 'content' (str)"

    async def execute(self, path: str, content: str):
        p = Path(path)
        original = p.read_text(encoding="utf-8") if p.exists() else ""
        marker_error = _validate_no_compact_markers(path, content, previous_content=original)
        if marker_error:
            return marker_error
        return ChangeProposal(file_path=path, original_content=original, new_content=content)


class WriteFileBlockTool(BaseTool):
    name = "write_file_block"
    description = (
        "Writes a whole file from raw <file_content> block text. "
        "Params: 'path' (str), 'file_content' (str), optional 'overwrite' (bool, default true)."
    )

    async def execute(self, path: str, file_content: str, overwrite: bool = True):
        p = Path(path)
        original = p.read_text(encoding="utf-8") if p.exists() else ""
        if p.exists() and not overwrite:
            return {
                "status": "error",
                "error_code": "VALIDATION_ERROR",
                "recoverable": True,
                "next_actions": ["read_file", "edit_file", "write_file_block"],
                "output": f"File {path} already exists and overwrite=false. Use edit_file, append_file_block, or retry with overwrite=true.",
            }
        marker_error = _validate_no_compact_markers(path, file_content, previous_content=original)
        if marker_error:
            return marker_error
        return ChangeProposal(file_path=path, original_content=original, new_content=file_content)


class AppendFileBlockTool(BaseTool):
    name = "append_file_block"
    description = (
        "Appends raw <file_content> block text to a file. "
        "Params: 'path' (str), 'file_content' (str)."
    )

    async def execute(self, path: str, file_content: str):
        p = Path(path)
        original = p.read_text(encoding="utf-8") if p.exists() else ""
        new_content = original + file_content
        marker_error = _validate_no_compact_markers(path, new_content, previous_content=original)
        if marker_error:
            return marker_error
        return ChangeProposal(file_path=path, original_content=original, new_content=new_content)


class EditFileTool(BaseTool):
    name = "edit_file"
    description = (
        "Surgically edits an existing file by replacing a specific block of text. "
        "Params: 'path' (str), 'search_text' (str), 'replace_text' (str). "
        "The 'search_text' must exactly match a part of the file. "
        "Copy 'search_text' verbatim from exact file content returned by a recent read/search tool result; "
        "do not reconstruct indentation or whitespace from memory. "
        "After a successful edit to the same file, reread the current target block before another edit_file call unless you already have fresh post-edit exact content."
    )

    async def execute(self, path: str, search_text: str, replace_text: str):
        p = Path(path)
        if not p.exists():
            parent = str(p.parent) if str(p.parent) else "."
            return {
                "status": "error",
                "error_code": "NOT_FOUND",
                "recoverable": True,
                "next_actions": ["list_directory", "search_files", "create_file"],
                "output": f"File not found: {path}",
                "error_details": {"path": path, "suggested_path": parent},
            }
        try:
            content = p.read_text(encoding="utf-8")
            guard_error = _validate_edit_file_scope(path, content, search_text, replace_text)
            if guard_error:
                return guard_error
            if search_text not in content:
                mismatch_type, mismatch_details = _classify_search_mismatch(content, search_text)
                fuzzy_candidates = _indentation_normalized_fuzzy_candidates(content, search_text)
                mismatch_details["fuzzy_candidates"] = fuzzy_candidates
                mismatch_details["fuzzy_candidate_count"] = len(fuzzy_candidates)
                mismatch_details["fuzzy_unique_candidate"] = len(fuzzy_candidates) == 1
                first_diff = _build_first_diff(search_text, content)
                mismatch_details["first_diff"] = first_diff
                output_lines = [
                    "Search block not found. Ensure whitespace and indentation match exactly.",
                    f"Mismatch type: {mismatch_type}.",
                ]
                similarity = mismatch_details.get("similarity")
                if isinstance(similarity, (float, int)):
                    output_lines.append(f"Similarity hint: {similarity:.2f}.")
                if first_diff:
                    output_lines.append(f"First diff at search_text line {first_diff['line']}, col {first_diff['col']}.")
                if fuzzy_candidates:
                    if len(fuzzy_candidates) == 1:
                        candidate = fuzzy_candidates[0]
                        output_lines.append(
                            "Indentation-normalized fuzzy candidate found at "
                            f"lines {candidate['start_line']}-{candidate['end_line']}. "
                            "Do not retry blind edit_file; use fuzzy_edit_file once available, or read this exact range."
                        )
                    else:
                        output_lines.append(
                            f"Found {len(fuzzy_candidates)} indentation-normalized fuzzy candidates; candidate is ambiguous, read the exact target range before retry."
                        )
                from modules.tools.recovery.edit_file_recovery_policy import search_mismatch_recovery_actions

                next_actions = list(
                    search_mismatch_recovery_actions(
                        path=path,
                        mismatch_type=mismatch_type,
                        active_intent_type="MODIFY",
                    )
                )
                return {
                    "status": "error",
                    "error_code": "VALIDATION_ERROR",
                    "recoverable": True,
                    "next_actions": next_actions,
                    "output": "\n".join(output_lines),
                    "error_details": {
                        "path": path,
                        "mismatch_type": mismatch_type,
                        "search_text_length": len(search_text),
                        "replace_text_length": len(replace_text),
                        "line_endings_in_file": _detect_line_endings(content),
                        **mismatch_details,
                    },
                }
            new_content = content.replace(search_text, replace_text, 1)
            marker_error = _validate_no_compact_markers(path, new_content, previous_content=content)
            if marker_error:
                return marker_error
            return ChangeProposal(file_path=path, original_content=content, new_content=new_content)
        except Exception as e:
            return {
                "status": "error",
                "error_code": "INTERNAL",
                "recoverable": False,
                "output": f"Edit failed: {str(e)}",
            }
