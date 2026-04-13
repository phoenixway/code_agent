from pathlib import Path
from ..base import BaseTool


class FolderTreeTool(BaseTool):
    name = "folder_tree"
    description = (
        "Shows a directory as a tree. "
        "Useful for quickly understanding project structure. "
        "Parameters: "
        "path (str, optional) - root directory (default: current directory); "
        "max_depth (int, optional) - maximum tree depth (default: 3); "
        "include_files (bool, optional) - include files in output (default: true); "
        "show_hidden (bool, optional) - include hidden files and folders (default: false)."
    )

    async def execute(
        self,
        path: str = ".",
        max_depth: int = 3,
        include_files: bool = True,
        show_hidden: bool = False,
        **kwargs,
    ):
        try:
            root = Path(path).expanduser().resolve()

            if not root.exists():
                return {
                    "status": "error",
                    "error_code": "NOT_FOUND",
                    "recoverable": True,
                    "next_actions": ["list_directory", "search_files"],
                    "output": f"Path not found: {path}",
                }

            if not root.is_dir():
                return {
                    "status": "error",
                    "error_code": "VALIDATION_ERROR",
                    "recoverable": True,
                    "next_actions": ["read_file", "list_directory"],
                    "output": f"Not a directory: {path}",
                }

            if not isinstance(max_depth, int) or max_depth < 0:
                max_depth = 3

            lines: list[str] = [f"{root.name}/"]

            def is_hidden(p: Path) -> bool:
                return p.name.startswith(".")

            def build_tree(current: Path, prefix: str, depth: int):
                if depth >= max_depth:
                    return

                children = []
                for child in current.iterdir():
                    if not show_hidden and is_hidden(child):
                        continue
                    if child.is_dir() or include_files:
                        children.append(child)

                children.sort(key=lambda p: (not p.is_dir(), p.name.lower()))

                for i, child in enumerate(children):
                    is_last = i == len(children) - 1
                    branch = "└── " if is_last else "├── "
                    suffix = "/" if child.is_dir() else ""
                    lines.append(f"{prefix}{branch}{child.name}{suffix}")

                    if child.is_dir():
                        extension = "    " if is_last else "│   "
                        build_tree(child, prefix + extension, depth + 1)

            build_tree(root, "", 0)

            if len(lines) > 300:
                preview = "\n".join(lines[:300])
                hidden_count = len(lines) - 300
                return {
                    "status": "success",
                    "output": (
                        f"Folder tree for {root} "
                        f"(showing first 300 lines, {hidden_count} more omitted):\n{preview}"
                    ),
                }

            return {
                "status": "success",
                "output": f"Folder tree for {root}:\n" + "\n".join(lines),
            }

        except PermissionError as e:
            return {
                "status": "error",
                "error_code": "PERMISSION_DENIED",
                "recoverable": True,
                "next_actions": ["list_directory"],
                "output": f"Permission denied: {e}",
            }
        except Exception as e:
            return {
                "status": "error",
                "error_code": "INTERNAL",
                "recoverable": True,
                "next_actions": ["list_directory"],
                "output": f"Failed to build folder tree: {e}",
            }
