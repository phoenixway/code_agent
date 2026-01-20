# AGENT Guidelines for this Python Project

This document outlines essential information for agents working within this codebase, covering commands, code organization, conventions, and important patterns.

## 1. Project Overview

This is a Python project primarily focused on an AI agent with a Textual User Interface (TUI). Key components include agent logic, tool management, context handling, and UI presentation.

## 2. Essential Commands

### Dependency Installation
To set up the project environment, install the required packages:
```bash
pip install -r requirements.txt
```

### Running the Application
The main application entry point is `app.py`, which launches the Textual TUI.
```bash
python app.py
```

### Running Tests
Tests are located in the `tests/` directory and use the `pytest` framework.
```bash
pytest tests/
```

## 3. Code Organization and Structure

*   `.`: Root directory contains main application files (`app.py`, `agent.py`), configuration (`requirements.txt`), and utility scripts.
*   `modules/`: Contains modular components of the application, promoting separation of concerns.
    *   `modules/tools/`: Dedicated to defining and managing various tools the agent can utilize.
    *   `modules/ui_components/`: Houses reusable UI elements for the Textual application.
*   `tests/`: Contains unit tests for the modules and core logic.
*   `sessions/`: Stores session-related data (e.g., conversation history).

## 4. Naming Conventions and Style Patterns

This project adheres to standard Python (PEP 8) naming conventions:

*   **Classes**: `PascalCase` (e.g., `AngelicaAgent`, `ContextPicker`).
*   **Functions and Variables**: `snake_case` (e.g., `_setup_logger`, `current_task`, `get_response`).
*   **Constants**: `SCREAMING_SNAKE_CASE` (e.g., `MAX_CONSECUTIVE_CALLS`, `DEFAULT_SYSTEM_PROMPT`).
*   **Imports**: Generally grouped by standard library, third-party, and then local modules.
*   **Type Hinting**: Used for function arguments and return types to improve readability and maintainability.
*   **String Formatting**: f-strings are preferred for embedding expressions inside string literals.

## 5. Testing Approach and Patterns

*   **Framework**: `pytest` is the chosen testing framework.
*   **Test File Location**: Test files are located in the `tests/` directory and follow the `test_*.py` naming convention (e.g., `test_modules.py`).
*   **Test Cases**: Focus on unit tests for individual functions and modules.

## 6. Important Gotchas or Non-Obvious Patterns

*   **Asynchronous Operations**: The agent logic in `agent.py` heavily uses `asyncio` for asynchronous operations, especially when interacting with AI providers and handling user input. Agents should be mindful of `await` calls.
*   **UI Synchronization**: The `AngelicaAgent` class includes a `ui` property with a setter that synchronizes UI references across dependent modules when the TUI is connected. This is important for ensuring UI updates are correctly routed.
*   **Communication Logging**: The `_setup_logger` method in `agent.py` configures a logger to record communication in `communication.log`, which can be useful for debugging agent interactions.
*   **Model Response Parsing**: The `_parse_output` method in `agent.py` is responsible for strictly parsing AI responses, extracting thoughts (within `<think>...</think>`) and commands (<action> wrapped JSON payloads), or plain text. Agents generating responses should adhere to this structure.
*   **Tool Manager**: The `ToolManager` in `modules/tools/manager.py` is responsible for loading and managing the tools available to the agent. New tools would likely be integrated here.
*   **Permission Policy**: The `PermissionPolicy` in `modules/policy.py` controls the agent's actions based on configured permissions, which can be in "ask" mode, requiring user confirmation for certain actions.
