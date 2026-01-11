import subprocess
import shlex
from ..base import BaseTool

class FileSearchTool(BaseTool):
    name = "search_files"
    description = (
        "Finds files matching a pattern using 'fd'. "
        "Useful for locating files by name or extension. "
        "Parameters: "
        "pattern (str, required) - the glob pattern or regex to search for (e.g. '*.py', 'main'); "
        "path (str, optional) - directory to search in (default: current)."
    )

    async def execute(self, pattern: str, path: str = ".", **kwargs):
        # Construct command: fd --color=never --hidden --exclude .git <pattern> <path>
        # Note: 'fd' respects .gitignore by default.
        # We use '--hidden' to include dotfiles (like .config) in the search, 
        # BUT they will still be ignored if they are listed in .gitignore.
        # We explicitly exclude .git just to be safe/clear.
        
        cmd = ["fd", "--color=never", "--hidden", "--exclude", ".git"]
        
        # Determine if it looks like a glob (contains *, ?) or just a substring
        # fd uses regex by default unless -g is passed.
        if any(char in pattern for char in "*?[]"):
            cmd.append("--glob")
            
        cmd.append(pattern)
        cmd.append(path)

        try:
            result = subprocess.run(
                cmd, 
                capture_output=True, 
                text=True, 
                check=True
            )
            
            output = result.stdout.strip()
            if not output:
                return {"status": "success", "output": "No files found matching the pattern."}
            
            # Limit output to prevent context flooding
            lines = output.split('\n')
            count = len(lines)
            if count > 50:
                preview = "\n".join(lines[:50])
                return {
                    "status": "success", 
                    "output": f"Found {count} files. Showing first 50:\n{preview}\n\n...and {count-50} more."
                }
            
            return {"status": "success", "output": output}
            
        except subprocess.CalledProcessError as e:
            return {"status": "error", "output": f"Error searching files: {e.stderr}"}
        except Exception as e:
            return {"status": "error", "output": str(e)}


class ContentSearchTool(BaseTool):
    name = "search_content"
    description = (
        "Searches for text patterns inside files using 'ripgrep' (rg). "
        "Useful for finding code usage, TODOs, or specific strings. "
        "Parameters: "
        "pattern (str, required) - the regex pattern to search for; "
        "path (str, optional) - directory to search in (default: current)."
    )

    async def execute(self, pattern: str, path: str = ".", **kwargs):
        # Construct command: rg --color=never --no-heading --line-number <pattern> <path>
        # Note: 'rg' respects .gitignore by default.
        # We use '--hidden' to search in hidden files, but we MUST explicitly exclude .git 
        # because 'rg --hidden' enables searching inside .git directory.
        cmd = [
            "rg", 
            "--color=never", 
            "--no-heading", 
            "--line-number", 
            "--smart-case",
            "--hidden",
            "--glob", "!.git/*", # Explicitly exclude .git content
            pattern,
            path
        ]

        try:
            result = subprocess.run(
                cmd, 
                capture_output=True, 
                text=True
            )
            
            # rg returns exit code 1 if no matches found, which is not an error for us
            if result.returncode == 1 and not result.stderr:
                return {"status": "success", "output": "No matches found."}
            
            if result.returncode != 0 and result.stderr:
                return {"status": "error", "output": f"ripgrep failed: {result.stderr}"}

            output = result.stdout.strip()
            if not output:
                return {"status": "success", "output": "No matches found."}

            lines = output.split('\n')
            count = len(lines)
            if count > 50:
                preview = "\n".join(lines[:50])
                return {
                    "status": "success", 
                    "output": f"Found {count} matches. Showing first 50:\n{preview}\n\n...and {count-50} more."
                }

            return {"status": "success", "output": output}

        except Exception as e:
            return {"status": "error", "output": str(e)}
