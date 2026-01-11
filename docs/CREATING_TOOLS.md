# Creating New Tools

This guide explains how to extend Angelica AI by creating new tools.

## Architecture

Tools are modular Python classes that inherit from `BaseTool`. They are automatically discovered and loaded by the `ToolManager` if placed in the correct directory.

-   **Base Class**: `modules/tools/base.py`
-   **Directory**: `modules/tools/definitions/`

## Step-by-Step Guide

### 1. Create a New Tool File

Create a new Python file in `modules/tools/definitions/`. The filename should be descriptive (e.g., `git_tools.py`, `web_search.py`).

```bash
touch modules/tools/definitions/my_tool.py
```

### 2. Implement the Tool Class

Inherit from `BaseTool` and implement the required attributes and methods.

```python
# modules/tools/definitions/my_tool.py
from ..base import BaseTool

class MyAwesomeTool(BaseTool):
    # 1. Unique name used by the AI to call the tool
    name = "my_awesome_tool"
    
    # 2. Description for the AI (explain WHAT it does and WHEN to use it)
    description = (
        "Calculates the factorial of a number. "
        "Use this when the user asks for math calculations involving factorials. "
        "Parameters: number (int)"
    )

    # 3. The execution logic
    async def execute(self, **kwargs):
        try:
            # Extract parameters safely
            number = int(kwargs.get("number", 0))
            
            # Perform the logic
            if number < 0:
                return {"status": "error", "output": "Number must be non-negative"}
            
            import math
            result = math.factorial(number)
            
            # Return a standard dictionary
            return {
                "status": "success", 
                "output": f"The factorial of {number} is {result}"
            }
            
        except Exception as e:
            return {"status": "error", "output": str(e)}
```

### 3. Verification

The tool will be automatically loaded on the next restart. You can verify it by running the agent and checking the logs or asking the agent to list its tools.

### Best Practices

1.  **Robust Error Handling**: Always wrap your logic in `try-except` blocks. The AI depends on clear error messages to correct itself.
2.  **Clear Descriptions**: The `description` field is the prompt for the AI. Be specific about required parameters.
3.  **Return Format**: Always return a dictionary with at least `status` ("success" or "error") and `output` (string).
4.  **Dependencies**: If your tool needs external libraries, handle `ImportError` gracefully or update `requirements.txt`.

## Example: Adding a Git Commit Tool

```python
# modules/tools/definitions/git.py
import subprocess
from ..base import BaseTool

class GitCommit(BaseTool):
    name = "git_commit"
    description = "Commits changes to git. Params: message (str)"

    async def execute(self, message: str, **kwargs):
        cmd = ["git", "commit", "-m", message]
        try:
            res = subprocess.run(cmd, capture_output=True, text=True, check=True)
            return {"status": "success", "output": res.stdout}
        except subprocess.CalledProcessError as e:
            return {"status": "error", "output": e.stderr}
```
