import os
import difflib
import re
from pathlib import Path
from ..base import BaseTool
from modules.types import ChangeProposal
from modules.code_parser import CodeParser


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
        "Extracts a structural skeleton (classes/functions/signatures) from a source file "
        "using tree-sitter for supported languages. Preferred first step before full read_file. "
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
                "output": f"Skeleton for {p}:\n{skeleton}\n\nNote: this is a structural view. Use read_file for exact implementation details.",
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


class EditFileTool(BaseTool):
    name = "edit_file"
    description = (
        "Surgically edits an existing file by replacing a specific block of text. "
        "Params: 'path' (str), 'search_text' (str), 'replace_text' (str). "
        "The 'search_text' must exactly match a part of the file."
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
            if search_text not in content:
                mismatch_type, mismatch_details = _classify_search_mismatch(content, search_text)
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
                return {
                    "status": "error",
                    "error_code": "VALIDATION_ERROR",
                    "recoverable": True,
                    "next_actions": ["read_file", "search_content", "edit_file", "write_file"],
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