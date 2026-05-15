import subprocess
import re
from ..base import BaseTool

DEFAULT_EXCLUDE_DIRS = [
    ".git", "__pycache__", ".pytest_cache", ".mypy_cache", ".venv", "venv",
    "node_modules", "build", "dist", "dumps", "sessions", ".idea", ".vscode",
]

CODE_EXTENSIONS = [
    ".py", ".pyi", ".kt", ".kts", ".java", ".js", ".jsx", ".ts", ".tsx",
    ".go", ".rs", ".c", ".h", ".cpp", ".hpp", ".cc", ".hh", ".cs", ".php",
    ".rb", ".swift", ".scala", ".lua", ".sh", ".bash", ".zsh", ".sql",
    ".html", ".css", ".scss", ".xml", ".yaml", ".yml", ".toml", ".json",
    ".md", ".txt",
]

MAX_HISTORY_PREVIEW_LINES = 10
MAX_HISTORY_PREVIEW_CHARS = 4000
MAX_FULL_RESULT_CHARS = 12000


def _normalize_bool(value, default=False):
    if isinstance(value, bool):
        return value
    if value is None:
        return default
    if isinstance(value, str):
        lowered = value.strip().lower()
        if lowered in {"1", "true", "yes", "y", "on"}:
            return True
        if lowered in {"0", "false", "no", "n", "off"}:
            return False
    return default


def _normalize_list(value):
    if value is None:
        return []
    if isinstance(value, (list, tuple)):
        return [str(v).strip() for v in value if str(v).strip()]
    if isinstance(value, str):
        return [part.strip() for part in value.split(",") if part.strip()]
    return []


def _merge_excludes(extra):
    merged = []
    for item in DEFAULT_EXCLUDE_DIRS + _normalize_list(extra):
        if item not in merged:
            merged.append(item)
    return merged


def _merge_exts(code_only, include_extensions):
    exts = _normalize_list(include_extensions)
    if code_only:
        for ext in CODE_EXTENSIONS:
            if ext not in exts:
                exts.append(ext)
    return exts


def _build_histogram_summary(text: str) -> str:
    lines = text.splitlines()
    total_matches = len(lines)

    matches_by_file = {}
    for line in lines:
        parts = line.split(":", 1)
        if len(parts) > 1:
            path = parts[0]
            matches_by_file.setdefault(path, 0)
            matches_by_file[path] += 1

    total_files = len(matches_by_file)

    sorted_files = sorted(matches_by_file.items(), key=lambda item: (-item[1], item[0]))

    summary_lines = [
        f"Search was broad: {total_matches} matches across {total_files} files.",
        "",
        "Top files by match count:",
    ]

    top_n = 10
    for path, count in sorted_files[:top_n]:
        label = "match" if count == 1 else "matches"
        summary_lines.append(f"- {path} — {count} {label}")

    if len(sorted_files) > top_n:
        summary_lines.append(f"...and {len(sorted_files) - top_n} more files.")

    summary_lines.append("")
    summary_lines.append(
        "Hint: This result is broad. Useful narrowing options include requesting a file skeleton, reading a chunk of one listed file, searching within one listed path, or searching an exact symbol."
    )

    return "\n".join(summary_lines)


def _build_preview(text: str, *, limit_lines: int) -> tuple[str, int]:
    lines = text.splitlines()
    total = len(lines)
    preview = "\n".join(lines[:limit_lines])
    if len(preview) > MAX_HISTORY_PREVIEW_CHARS:
        preview = preview[:MAX_HISTORY_PREVIEW_CHARS].rstrip() + "\n...[truncated]"
    return preview, total


def _compact_large_result(kind: str, text: str, *, limit: int, exit_code: int, stderr: str = "") -> dict:
    if kind == "matches":
        output = _build_histogram_summary(text)
        return {
            "status": "success",
            "output": output,
            "exit_code": exit_code,
            "stdout": output,
            "stderr": (stderr or "")[:1000],
            "truncated": True,
            "result_count": len(text.splitlines()),
            "history_compact": True,
            "search_too_broad": True,
            "result_kind": "broad_search_summary",
            "suggested_fix": "Narrow the search path/pattern or lower the result limit before retrying.",
            "raw_output": output,
            "stdout_full": output,
            "raw_output_truncated": False,
        }

    preview_limit = min(limit, MAX_HISTORY_PREVIEW_LINES)
    preview, total = _build_preview(text, limit_lines=preview_limit)
    label = "files" if kind == "files" else "matches"
    output = (
        f"Search query is too broad and uneconomical for the current context budget. "
        f"Found {total} {label}; showing only the first {preview_limit}.\n"
        f"{preview}\n\n"
        "If these results are insufficient, narrow the search path/pattern or lower the requested result count."
    )
    # For oversized search results, never keep the full body in raw_output/history.
    compact_text = preview[:MAX_FULL_RESULT_CHARS]
    return {
        "status": "success",
        "output": output,
        "exit_code": exit_code,
        "stdout": preview,
        "stderr": (stderr or "")[:1000],
        "truncated": True,
        "result_count": total,
        "history_compact": True,
        "search_too_broad": True,
        "suggested_fix": "Narrow the search path/pattern or lower the result limit before retrying.",
        "raw_output": compact_text,
        "stdout_full": compact_text,
        "raw_output_truncated": True,
        "raw_output_chars": len(compact_text),
        "raw_output_total_chars": len(text),
    }


_HISTORY_SELF_REF_RE = re.compile(r"(^|/)(modules/)?history(?:_[a-z0-9_]+)?\.py$", re.IGNORECASE)

def _extract_result_path(line: str) -> str:
    if not isinstance(line, str):
        return ""
    m = re.match(r"^(.*?):\d+:", line)
    if m:
        return m.group(1).strip()
    m = re.match(r"^(.*?):", line)
    if m:
        return m.group(1).strip()
    return ""

def _is_history_self_reference_path(path: str) -> bool:
    p = (path or "").strip()
    return bool(_HISTORY_SELF_REF_RE.search(p))

def _split_history_self_reference_hits(lines):
    history_lines = []
    non_history_lines = []
    for line in lines:
        path = _extract_result_path(line)
        if _is_history_self_reference_path(path):
            history_lines.append(line)
        else:
            non_history_lines.append(line)
    return history_lines, non_history_lines

class FileSearchTool(BaseTool):
    name = "search_files"
    description = (
        "Finds files matching a pattern using 'fd'. "
        "Use this before full file reads when you first need to locate likely files. "
        "Parameters: pattern (str), path (str='.'), recursive (bool=True), code_only (bool=False), "
        "include_extensions (list[str], optional), exclude_dirs (list[str], optional), limit (int, optional)."
    )

    async def execute(
        self,
        pattern: str,
        path: str = ".",
        recursive: bool = True,
        code_only: bool = False,
        include_extensions=None,
        exclude_dirs=None,
        limit: int = 50,
        **kwargs
    ):
        recursive = _normalize_bool(recursive, True)
        code_only = _normalize_bool(code_only, False)
        limit = int(limit) if isinstance(limit, int) or str(limit).isdigit() else 50
        limit = max(1, min(limit, 200))

        cmd = ["fd", "--color=never", "--hidden", "--exclude", ".git"]

        excludes = _merge_excludes(exclude_dirs)
        for item in excludes:
            if item != ".git":
                cmd.extend(["--exclude", item])

        if not recursive:
            cmd.extend(["--max-depth", "1"])

        merged_exts = _merge_exts(code_only, include_extensions)
        for ext in merged_exts:
            norm = ext if str(ext).startswith(".") else f".{ext}"
            cmd.extend(["--extension", norm.lstrip(".")])

        if any(char in pattern for char in "*?[]"):
            cmd.append("--glob")

        cmd.append(pattern)
        cmd.append(path)

        try:
            result = subprocess.run(cmd, capture_output=True, text=True)

            if result.returncode == 1 and not result.stderr:
                return {
                    "status": "success",
                    "output": "No files found matching the pattern.",
                    "exit_code": 1,
                    "stdout": "",
                    "stderr": "",
                    "result_count": 0,
                }

            if result.returncode != 0:
                return {
                    "status": "failed",
                    "error_code": "SEARCH_EXIT_NONZERO",
                    "recoverable": True,
                    "next_actions": ["list_directory", "search_content"],
                    "output": (result.stderr or result.stdout or "").strip() or f"fd exited with code {result.returncode}.",
                    "exit_code": result.returncode,
                    "stdout": (result.stdout or "")[:1000],
                    "stderr": (result.stderr or "")[:1000],
                }

            output = result.stdout.strip()
            if not output:
                return {
                    "status": "success",
                    "output": "No files found matching the pattern.",
                    "exit_code": 0,
                    "stdout": "",
                    "stderr": (result.stderr or "")[:1000],
                    "result_count": 0,
                }

            lines = output.splitlines()
            count = len(lines)
            if count > limit:
                return _compact_large_result("files", output, limit=limit, exit_code=0, stderr=result.stderr or "")

            return {
                "status": "success",
                "output": output,
                "exit_code": 0,
                "stdout": output,
                "stderr": (result.stderr or "")[:1000],
                "raw_output": output,
                "stdout_full": output,
                "result_count": count,
            }

        except Exception as e:
            return {
                "status": "error",
                "error_code": "INTERNAL",
                "recoverable": True,
                "next_actions": ["list_directory", "search_content"],
                "output": str(e),
                "tool_failure": True,
                "tool_name": self.name,
            }


class ContentSearchTool(BaseTool):
    name = "search_content"
    description = (
        "Searches for text patterns inside files using 'ripgrep' (rg). "
        "Prefer this before full read_file when you need to locate exact symbols, imports, handlers, or dialog usage. "
        "Parameters: pattern (str), path (str='.'), recursive (bool=True), code_only (bool=False), "
        "include_extensions (list[str], optional), exclude_dirs (list[str], optional), limit (int, optional), "
        "ignore_case (bool=False), literal (bool=False; use fixed-string search for code text like Row( or AutocompleteSuggestions())."
    )

    async def execute(
        self,
        pattern: str,
        path: str = ".",
        recursive: bool = True,
        code_only: bool = False,
        include_extensions=None,
        exclude_dirs=None,
        limit: int = 50,
        ignore_case: bool = False,
        literal: bool = False,
        **kwargs
    ):
        recursive = _normalize_bool(recursive, True)
        code_only = _normalize_bool(code_only, False)
        ignore_case = _normalize_bool(ignore_case, False)
        literal = _normalize_bool(literal, False)
        limit = int(limit) if isinstance(limit, int) or str(limit).isdigit() else 50
        limit = max(1, min(limit, 200))

        cmd = ["rg", "--color=never", "--no-heading", "--line-number", "--hidden"]
        cmd.append("--ignore-case" if ignore_case else "--smart-case")
        if literal:
            cmd.append("--fixed-strings")

        excludes = _merge_excludes(exclude_dirs)
        for item in excludes:
            cmd.extend(["--glob", f"!{item}/*"])

        if not recursive:
            cmd.extend(["--max-depth", "1"])

        merged_exts = _merge_exts(code_only, include_extensions)
        for ext in merged_exts:
            norm = ext if str(ext).startswith(".") else f".{ext}"
            cmd.extend(["--glob", f"*{norm}"])

        cmd.extend([pattern, path])

        try:
            result = subprocess.run(cmd, capture_output=True, text=True)

            if result.returncode == 1 and not result.stderr:
                return {
                    "status": "success",
                    "output": "No matches found.",
                    "exit_code": 1,
                    "stdout": "",
                    "stderr": "",
                    "result_count": 0,
                }

            if result.returncode != 0:
                stderr = result.stderr or ""
                stdout = result.stdout or ""
                raw_output = (stderr or stdout or "").strip() or f"ripgrep exited with code {result.returncode}."
                regex_parse_error = "regex parse error" in stderr.lower()
                if regex_parse_error:
                    return {
                        "status": "failed",
                        "error_code": "SEARCH_REGEX_PARSE_ERROR",
                        "recoverable": True,
                        "next_actions": ["search_content", "read_chunk", "extract_symbol"],
                        "output": (
                            f"{raw_output}\n"
                            "Pattern was interpreted as a regular expression and failed to parse. "
                            "If this is literal code text, retry search_content with literal=true, or escape regex metacharacters."
                        ),
                        "exit_code": result.returncode,
                        "stdout": stdout[:1000],
                        "stderr": stderr[:1000],
                        "error_details": {
                            "pattern": pattern,
                            "path": path,
                            "literal": literal,
                            "suggested_retry": {
                                "type": "search_content",
                                "pattern": pattern,
                                "path": path,
                                "recursive": recursive,
                                "code_only": code_only,
                                "include_extensions": include_extensions,
                                "exclude_dirs": exclude_dirs,
                                "limit": limit,
                                "ignore_case": ignore_case,
                                "literal": True,
                            },
                        },
                    }
                return {
                    "status": "failed",
                    "error_code": "SEARCH_EXIT_NONZERO",
                    "recoverable": True,
                    "next_actions": ["list_directory", "search_files", "read_file"],
                    "output": raw_output,
                    "exit_code": result.returncode,
                    "stdout": stdout[:1000],
                    "stderr": stderr[:1000],
                }

            output = result.stdout.strip()
            if not output:
                return {
                    "status": "success",
                    "output": "No matches found.",
                    "exit_code": 0,
                    "stdout": "",
                    "stderr": (result.stderr or "")[:1000],
                    "result_count": 0,
                }

            lines = output.splitlines()
            history_lines, non_history_lines = _split_history_self_reference_hits(lines)

            # Self-referential history hits are not real usage evidence during stale-analysis.
            # If they are the only hits, return a compact explanatory result instead of misleading evidence.
            if history_lines and not non_history_lines:
                preview, total = _build_preview("\n".join(history_lines), limit_lines=min(limit, MAX_HISTORY_PREVIEW_LINES))
                return {
                    "status": "success",
                    "output": (
                        "Only self-referential history hits were found (for example in modules/history.py). "
                        "This is not real usage evidence for the searched file/module.\n"
                        f"Preview:\n{preview}"
                    ),
                    "exit_code": 0,
                    "stdout": preview,
                    "stderr": (result.stderr or "")[:1000],
                    "raw_output": "\n".join(history_lines)[:MAX_FULL_RESULT_CHARS],
                    "stdout_full": "\n".join(history_lines)[:MAX_FULL_RESULT_CHARS],
                    "result_count": total,
                    "history_compact": True,
                    "history_self_reference_only": True,
                    "real_usage_evidence": False,
                }

            # If real hits exist, silently drop history/self-reference noise from the user-visible result.
            if non_history_lines:
                lines = non_history_lines

            count = len(lines)
            filtered_output = "\n".join(lines)

            if count > limit:
                compact = _compact_large_result("matches", filtered_output, limit=limit, exit_code=0, stderr=result.stderr or "")
                if history_lines:
                    compact["history_hits_filtered"] = len(history_lines)
                return compact

            result_payload = {
                "status": "success",
                "output": filtered_output,
                "exit_code": 0,
                "stdout": filtered_output,
                "stderr": (result.stderr or "")[:1000],
                "raw_output": filtered_output,
                "stdout_full": filtered_output,
                "result_count": count,
            }
            if history_lines:
                result_payload["history_hits_filtered"] = len(history_lines)
            return result_payload

        except Exception as e:
            return {
                "status": "error",
                "error_code": "INTERNAL",
                "recoverable": True,
                "next_actions": ["list_directory", "search_files", "read_file"],
                "output": str(e),
                "tool_failure": True,
                "tool_name": self.name,
            }
