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

At minimum, add a test that `ToolManager.load_tools()` contains the new tool name.

## Required Integration Checklist

Creating a `BaseTool` class is only the discovery step. Every new tool must also be classified by runtime semantics.

### A. Tool discovery and model visibility

- Put the class under `modules/tools/definitions/`.
- Inherit from `BaseTool`.
- Set a unique `name`.
- Write a precise `description`; this is the model-facing prompt text.
- Include all required and optional parameters in the description.
- Add a `ToolManager.load_tools()` test proving the tool is loaded.

### B. Action semantics

If the tool can modify files, shell state, git state, or project state, it is state-changing. Add it to:

- `modules/agent/intent_runtime.py::KNOWN_TOOL_ACTIONS`
- `modules/agent/config.py::STATE_CHANGING_OPS`
- any policy engine mutating/action classification sets
- batching exclusions, if applicable

If the tool is read-only, make sure it is allowed in read-only batches only when safe and bounded.

### C. Schema and validation

If the tool has a strict payload shape or is a common target for malformed model output, add schema/preflight validation tests.

For mutating tools, test that malformed payloads fail before execution and return actionable `next_actions`.

### D. Recovery integration

If the tool is meant to recover from another tool's failure, wire it into the relevant recovery policy. Examples:

- `fuzzy_edit_file` is recommended after `edit_file` finds a unique indentation-normalized fuzzy candidate.
- `replace_line_range` is recommended when the model attempted line-range fields in `edit_file`.

Recovery messages must say exactly when to use the tool and when not to use it.

### E. Prompt/protocol docs

Update the system prompt or architecture docs if the model needs a new decision rule. Do not rely only on tool availability.

### F. Tests required before closing a tool phase

- direct tool unit tests
- ToolManager visibility test
- intent/runtime known-action test
- state-changing/read-only classification test
- recovery-policy test, if applicable
- dispatcher/schema test, if payload validation is involved
- full `pytest -q tests`

## Required Integration Checklist

Creating a `BaseTool` class is only the discovery step. A tool is not complete until runtime semantics, recovery behavior, and tests agree with the new action.

### A. Tool discovery and model visibility

- Put the tool class under `modules/tools/definitions/`.
- Inherit from `BaseTool`.
- Set a unique `name`.
- Write a precise `description`; this text is model-facing and appears in the available tools prompt.
- Document every required and optional parameter in the description.
- Include safety constraints directly in the description when the model must know when not to use the tool.
- Add a `ToolManager.load_tools()` test proving the tool name is loaded.

### B. Classify the tool as read-only or state-changing

If the tool can modify files, shell state, git state, project state, runtime state, or user-visible artifacts, treat it as state-changing.

State-changing tools must be added to:

- `modules/agent/intent_runtime.py::KNOWN_TOOL_ACTIONS`
- `modules/agent/config.py::STATE_CHANGING_OPS`
- policy-engine mutating/action-classification sets
- batching exclusions, if applicable
- any loop/stale-evidence/plan-review logic that depends on mutation detection

Read-only tools should be added only to read-only batching paths when they are bounded and safe.

### C. Decide whether schema/preflight validation is needed

Add schema validation when:

- the payload shape is strict;
- the model commonly emits malformed variants;
- the tool is state-changing;
- the tool can accidentally perform a broad or destructive operation;
- a malformed payload should be rejected before tool execution.

Schema errors must return actionable recovery guidance, not just a generic validation failure.

Example: `edit_file` remains exact-only. A payload with `start_line`/`end_line` is malformed for `edit_file`; recovery should point to `replace_line_range`, not silently reinterpret the payload.

### D. Wire recovery policy intentionally

If the new tool is meant to recover from another tool's failure, update the relevant recovery policy.

Examples:

- `fuzzy_edit_file` is recommended only after `edit_file` reports exactly one indentation-normalized fuzzy candidate.
- `replace_line_range` is recommended when the model has reliable line numbers or attempted a line-range edit payload.
- `replace_symbol` is preferred for supported symbol-sized Kotlin/Python replacements after repeated `edit_file` mismatch.

Recovery messages must explain:

- when to use the tool;
- what evidence is required;
- when not to use the tool;
- what to do if the tool fails.

### E. Update prompt/protocol documentation if the model needs a new rule

Tool availability alone is not enough. If the model must choose the tool under specific conditions, update the relevant system prompt or architecture document.

Examples:

- Exact text replacement should still use `edit_file`.
- Line-coordinate replacement should use `replace_line_range`.
- Symbol-sized replacement should prefer `extract_symbol` → `replace_symbol` when supported.
- Indentation-only exact-match drift may use `fuzzy_edit_file` only when the backend found a unique candidate.

### F. Required tests before closing a tool phase

At minimum, add tests for:

- direct tool success path;
- direct tool failure path;
- safety guardrails;
- `ToolManager` visibility;
- known-action registration;
- state-changing or read-only classification;
- recovery-policy integration, if applicable;
- schema/preflight behavior, if applicable;
- full `pytest -q tests`.

For state-changing tools, also test that the tool returns a `ChangeProposal` or equivalent state-change result rather than silently editing files outside the normal proposal/apply flow.

### G. Closure checklist

A new tool phase is not closed until all are true:

- the tool is implemented;
- the model can see it in the tools prompt;
- runtime knows whether it is read-only or state-changing;
- intent runtime accepts it where appropriate;
- recovery policies can recommend it when intended;
- malformed payloads fail with useful guidance;
- tests cover direct behavior and integration behavior;
- full test suite is green.

### Example classifications

| Tool | Type | Notes |
| --- | --- | --- |
| `search_content` | read-only | `literal=true` is a parameter, not a new tool. |
| `fuzzy_edit_file` | state-changing | Guarded recovery tool after unique fuzzy candidate. |
| `replace_line_range` | state-changing | Use for reliable inclusive line ranges; supports empty replacement for deletion. |
| `replace_symbol` | state-changing | Preferred structural replacement for supported Kotlin/Python symbols. |
| `extract_symbol` | read-only | Evidence-gathering tool; output must be usable as current symbol content. |

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
