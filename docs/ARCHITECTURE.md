# Angelica AI Architecture Overview

Angelica AI is a modular, CLI-based AI agent designed to perform software engineering tasks. It follows a loop-based architecture where the agent perceives the environment (files, user input), processes it via an LLM, and acts through a set of defined tools.

## High-Level Structure

The application is structured around a central **Agent** class that coordinates several specialized modules.

### Core Components

1.  **Agent (`agent.py` / `AngelicaAgent`)**
    -   The main entry point and orchestrator.
    -   Manages the main execution loop: `User Input -> Context Assembly -> LLM Request -> Response Parsing -> Action Execution -> Output Feedback`.
    -   Handles high-level error catching and session management.

2.  **Response Processing (`modules/parser.py` & `modules/processor.py`)**
    -   **Parser (`ResponseParser`)**:
        -   Splits the response into a sequence of `Segment` objects: `THOUGHT`, `TEXT`, `ACTION`.
        -   **Fallback Logic**: If `<think>` tags are malformed (e.g., more closing than opening), it treats everything up to the last `</think>` as thought content.
        -   **Security**: JSONs found inside `<think>` blocks are strictly ignored.
        -   **Scanning**: Uses an iterative scanner to extract multiple sequential actions interspersed with text.
    -   **Processor (`ResponseProcessor`)**:
        -   Executes the extracted `ACTION` segments.
        -   Handles the `return_control` logic: if a tool requests to return control, the execution loop pauses and returns results to the LLM.

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
│   ├── logger.py       # Logging setup and utilities
│   ├── tools/          # Tool definitions & manager
│   ├── files.py        # File I/O
│   └── ...
├── tests/              # Unit tests
│   ├── test_modules.py # Basic component tests
│   └── test_core_logic.py # Core logic & edge case tests
└── docs/               # Documentation
```

## Logging

The application uses a two-file logging system, managed by the `modules/logger.py` module.

### Log Files

1.  **`communication.log`**:
    -   **Purpose**: Records the core interaction between the user, the agent, and the AI model. It is designed to be human-readable and provides a clean, visual representation of the conversation flow.
    -   **Content**: Contains only the formatted `OUTGOING` (to AI) and `INCOMING` (from AI) messages.
    -   **Behavior**: This log is automatically cleared at the start of each new application session.

2.  **`debug.log`**:
    -   **Purpose**: Captures all other internal logging information, including debug messages, warnings, and errors from all modules. This file is intended for developers for debugging and tracing application behavior.
    -   **Content**: Detailed, timestamped logs with log levels (DEBUG, INFO, WARNING, ERROR).
    -   **Behavior**: This log is overwritten at the start of each new application session.

### How to Log

The `modules/logger.py` module provides a simple API for logging.

-   **Debug Logging**: To log general debug information, import the logger and use its methods. The `AngelicaAgent` class instance has a `log` attribute that holds the debug logger.
    ```python
    # In a module that has access to the agent instance
    self.agent.log.debug("This is a debug message.")
    self.agent.log.error("This is an error.")
    ```

-   **Communication Logging**: To log the primary AI interactions, use the communication logger. This is typically only done within the `get_response` method in `agent.py`.
    ```python
    # In agent.py
    self.comm_log.info(f"--- OUTGOING ---\n{query}\n")
    ```
