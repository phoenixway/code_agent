import os
import difflib
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


class ReadFileTool(BaseTool):
    name = "read_file"
    description = (
        "Reads the full content of a file. "
        "Use only when full source is strictly required for exact edits. "
        "Prefer `read_file_skeleton` first for supported languages. "
        "Params: 'path' (str)"
    )

    async def execute(self, path: str, ui=None):
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

            # Check file size
            file_size = p.stat().st_size
            if file_size > 1024 * 1024:  # 1MB
                if ui:
                    if not await ui.confirm_action({
                        "type": "read_large_file",
                        "path": path,
                        "size": f"{file_size / (1024 * 1024):.2f} MB"
                    }):
                        return {
                            "status": "error",
                            "error_code": "PERMISSION_DENIED",
                            "recoverable": False,
                            "output": "User denied reading large file.",
                        }
                    else:
                        # User confirmed reading the large file, so we should not truncate it.
                        content = p.read_text(encoding='utf-8')
                        return {
                            "status": "success",
                            "output": content,
                            "skip_truncation": True,
                            "file_path": str(p),
                        }
                else:
                    # No UI, so we can't ask for confirmation.
                    # For now, we will proceed with reading the file.
                    # In the future, we might want to have a different behavior here.
                    pass

            content = p.read_text(encoding='utf-8')
            return {"status": "success", "output": content, "file_path": str(p)}
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
        "using tree-sitter for supported languages. "
        "Preferred first step before full `read_file` to save context tokens. "
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
                    "output": (
                        f"Skeleton extraction is not supported for '{ext or '(no extension)'}'. "
                        f"Supported: {supported}."
                    ),
                }

            content = p.read_text(encoding="utf-8")
            skeleton = self.code_parser.get_skeleton(str(p), content)
            return {
                "status": "success",
                "output": (
                    f"Skeleton for {p}:\n"
                    f"{skeleton}\n\n"
                    "Note: this is a structural view. Use read_file for exact implementation details."
                ),
                "file_path": str(p),
                "view": "skeleton",
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
        
        # Return proposal instead of writing directly
        proposal = ChangeProposal(
            file_path=path,
            original_content="",
            new_content=content
        )
        return proposal

class WriteFileTool(BaseTool):
    name = "write_file"
    description = "Overwrites an existing file. Params: 'path' (str), 'content' (str)"

    async def execute(self, path: str, content: str):
        p = Path(path)
        original = ""
        if p.exists():
            original = p.read_text(encoding='utf-8')
        
        # Return proposal
        proposal = ChangeProposal(
            file_path=path,
            original_content=original,
            new_content=content
        )
        return proposal

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
            content = p.read_text(encoding='utf-8')
            
            # Verify search text exists
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
                    output_lines.append(
                        "First diff at search_text "
                        f"line {first_diff['line']}, col {first_diff['col']}."
                    )

                return {
                    "status": "error",
                    "error_code": "VALIDATION_ERROR",
                    "recoverable": True,
                    "next_actions": [
                        "read_file",
                        "search_content",
                        "edit_file",
                        "write_file",
                    ],
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
            
            # Perform replacement
            new_content = content.replace(search_text, replace_text, 1)
            
            # Return proposal
            proposal = ChangeProposal(
                file_path=path,
                original_content=content,
                new_content=new_content
            )
            return proposal
            
        except Exception as e:
            return {
                "status": "error",
                "error_code": "INTERNAL",
                "recoverable": False,
                "output": f"Edit failed: {str(e)}",
            }
