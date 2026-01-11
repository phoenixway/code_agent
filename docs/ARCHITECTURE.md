# Angelica AI Architecture Overview

Angelica AI is a modular, CLI-based AI agent designed to perform software engineering tasks. It follows a loop-based architecture where the agent perceives the environment (files, user input), processes it via an LLM, and acts through a set of defined tools.

## High-Level Structure

The application is structured around a central **Agent** class that coordinates several specialized modules.

### Core Components

1.  **Agent (`agent.py` / `AngelicaAgent`)**
    -   The main entry point and orchestrator.
    -   Manages the main execution loop: `User Input -> Context Assembly -> LLM Request -> Response Parsing -> Action Execution -> Output Feedback`.
    -   Handles high-level error catching and session management.

2.  **Response Processor (`modules/processor.py`)**
    -   Responsible for interpreting the raw text output from the AI model.
    -   **Key Logic**:
        -   Extracts `<think>` blocks for internal reasoning.
        -   Parses JSON commands (greedy matching).
        -   Implements "Smart Fallback": if the model outputs a shell command string instead of a structured JSON, the processor attempts to wrap it into a valid `run_shell` or tool call.

3.  **Tool System (`modules/tools/`)**
    -   **`manager.py`**: Dynamically loads tool classes and exposes them to the processor.
    -   **`base.py`**: Base class for all tools.
    -   Tools are defined in `modules/tools/definitions/` (e.g., `files.py`, `shell.py`).

4.  **Context Manager (`modules/context.py`)**
    -   Prepares the "Context Window" for the LLM.
    -   **Project Structure**: Generates a tree view of the current directory, respecting `.gitignore`.
    -   **File Basket**: Manages a cache of read files to include their content in the system prompt.

5.  **History Manager (`modules/history.py`)**
    -   Stores the conversation history (User, Assistant, System).
    -   **Summarization**: Automatically calls the LLM to summarize the conversation when the token limit is exceeded, preventing context overflow.

6.  **Permission Policy (`modules/policy.py`)**
    -   Security layer that intercepts actions before execution.
    -   Modes:
        -   `ask`: Prompts the user for confirmation (default).
        -   `always`: Executes everything automatically.
        -   `never`: Denies all side-effect actions.

7.  **File System (`modules/files.py`)**
    -   A wrapper around `pathlib` to perform safe file operations (read, write, edit).

### Data Flow

1.  **Input**: User types a request in the TUI.
2.  **Context**: `ContextManager` gathers the project tree and open files. `ToolManager` provides the list of available tools.
3.  **Prompt**: `HistoryManager` combines history + context + tools definitions into a prompt.
4.  **Inference**: The `ChatProvider` sends the prompt to the configured Model (Ollama, OpenAI, etc.).
5.  **Parsing**: `ResponseProcessor` detects a JSON command in the response.
6.  **Verification**: `PermissionPolicy` checks if the action is allowed.
7.  **Execution**: `ToolManager` calls the appropriate tool.
8.  **Feedback**: The result (stdout/stderr/file content) is fed back into the history as a "System" message, allowing the agent to react to the result.

## Directory Structure

```text
/
├── agent.py            # Main application logic
├── app.py              # TUI entry point
├── modules/            # Core logic modules
│   ├── processor.py    # Parsing and execution logic
│   ├── context.py      # Context management
│   ├── history.py      # Chat history & summarization
│   ├── tools/          # Tool definitions & manager
│   ├── files.py        # File I/O
│   └── ...
├── tests/              # Unit tests
│   ├── test_modules.py # Basic component tests
│   └── test_core_logic.py # Core logic & edge case tests
└── docs/               # Documentation
```
