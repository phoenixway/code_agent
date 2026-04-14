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

MAX_HISTORY_PREVIEW_LINES = 20
MAX_HISTORY_PREVIEW_CHARS = 4000


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


def _build_preview(text: str, *, limit_lines: int) -> tuple[str, int]:
    lines = text.splitlines()
    total = len(lines)
    preview = "\n".join(lines[:limit_lines])
    if len(preview) > MAX_HISTORY_PREVIEW_CHARS:
        preview = preview[:MAX_HISTORY_PREVIEW_CHARS].rstrip() + "\n...[truncated]"
    return preview, total


def _compact_large_result(kind: str, text: str, *, limit: int, exit_code: int, stderr: str = "") -> dict:
    preview, total = _build_preview(text, limit_lines=min(limit, MAX_HISTORY_PREVIEW_LINES))
    label = "files" if kind == "files" else "matches"
    output = f"Found {total} {label}. Showing first {min(limit, MAX_HISTORY_PREVIEW_LINES)}:\n{preview}\n\n...and {max(total - min(limit, MAX_HISTORY_PREVIEW_LINES), 0)} more."
    return {
        "status": "success",
        "output": output,
        "exit_code": exit_code,
        # CRITICAL: do not store full stdout for giant search results, or history gets flooded.
        "stdout": preview,
        "stderr": (stderr or "")[:1000],
        "truncated": True,
        "result_count": total,
        "history_compact": True,
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
        "Parameters: pattern (str), path (str='.'), recursive (bool=True), "
        "code_only (bool=False), include_extensions (list[str], optional), "
        "exclude_dirs (list[str], optional), limit (int, optional)."
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
        "Parameters: pattern (str), path (str='.'), recursive (bool=True), "
        "code_only (bool=False), include_extensions (list[str], optional), "
        "exclude_dirs (list[str], optional), limit (int, optional), ignore_case (bool=False)."
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
        **kwargs
    ):
        recursive = _normalize_bool(recursive, True)
        code_only = _normalize_bool(code_only, False)
        ignore_case = _normalize_bool(ignore_case, False)
        limit = int(limit) if isinstance(limit, int) or str(limit).isdigit() else 50
        limit = max(1, min(limit, 200))

        cmd = ["rg", "--color=never", "--no-heading", "--line-number", "--hidden"]
        cmd.append("--ignore-case" if ignore_case else "--smart-case")

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
                return {
                    "status": "failed",
                    "error_code": "SEARCH_EXIT_NONZERO",
                    "recoverable": True,
                    "next_actions": ["list_directory", "search_files", "read_file"],
                    "output": (result.stderr or result.stdout or "").strip() or f"ripgrep exited with code {result.returncode}.",
                    "exit_code": result.returncode,
                    "stdout": (result.stdout or "")[:1000],
                    "stderr": (result.stderr or "")[:1000],
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