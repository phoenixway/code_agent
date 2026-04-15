import os
from pathlib import Path

from ..base import BaseTool


class ListDirectoryTool(BaseTool):
    name = "list_directory"
    description = (
        "Lists files and directories in a path. "
        "Useful for quick scoped inspection before broader search or file reads. "
        "Parameters: path (str, optional) - directory path (default: current directory); "
        "recursive (bool, optional) - include nested files/directories (default: false)."
    )

    async def execute(self, path: str = ".", recursive: bool = False, **kwargs):
        try:
            target = Path(path).expanduser().resolve()
            if not target.exists():
                return {
                    "status": "error",
                    "error_code": "NOT_FOUND",
                    "recoverable": True,
                    "next_actions": ["search_files"],
                    "output": f"Path not found: {path}",
                }
            if not target.is_dir():
                return {
                    "status": "error",
                    "error_code": "VALIDATION_ERROR",
                    "recoverable": True,
                    "next_actions": ["read_file"],
                    "output": f"Not a directory: {path}",
                }

            rows: list[str] = []

            if recursive:
                for root, dirnames, filenames in os.walk(target):
                    rel_root = Path(root).relative_to(target)
                    prefix = "." if str(rel_root) == "." else str(rel_root)
                    rows.append(f"{prefix}/")
                    for d in sorted(dirnames):
                        rows.append(f"  [D] {d}/")
                    for f in sorted(filenames):
                        rows.append(f"  [F] {f}")
            else:
                for entry in sorted(target.iterdir(), key=lambda p: (not p.is_dir(), p.name.lower())):
                    mark = "[D]" if entry.is_dir() else "[F]"
                    suffix = "/" if entry.is_dir() else ""
                    rows.append(f"{mark} {entry.name}{suffix}")

            if not rows:
                return {"status": "success", "output": f"Directory is empty: {target}"}

            full_output = f"Directory listing for {target}:\n" + "\n".join(rows)

            if len(rows) > 200:
                preview = "\n".join(rows[:200])
                hidden = len(rows) - 200
                return {
                    "status": "success",
                    "output": (
                        f"Directory listing for {target} (showing first 200 entries):\n"
                        f"{preview}\n\n...and {hidden} more."
                    ),
                    "raw_output": full_output[:200000],
                    "stdout_full": full_output[:200000],
                    "truncated": True,
                    "history_compact": True,
                    "result_count": len(rows),
                }

            return {
                "status": "success",
                "output": full_output,
                "raw_output": full_output,
                "stdout_full": full_output,
                "result_count": len(rows),
            }
        except Exception as e:
            return {
                "status": "error",
                "error_code": "INTERNAL",
                "recoverable": False,
                "output": f"Failed to list directory: {e}",
            }