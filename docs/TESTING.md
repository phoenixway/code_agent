# Testing Manual

This document outlines the testing strategy for Angelica-AI.

## Overview

The project uses Python's built-in `unittest` framework. Tests are located in the `tests/` directory.

### Test Suites

1.  **`tests/test_modules.py`**
    -   **Scope**: Basic unit tests for individual modules like `FileModule` and `PermissionPolicy`.
    -   **Focus**: Verifying that file operations (read/write/create) work and that policy modes (`ask`/`always`) behave as expected.

2.  **`tests/test_core_logic.py`**
    -   **Scope**: Critical integration logic and edge cases.
    -   **Focus**:
        -   **Parser**: Validating that the agent correctly extracts JSON commands from mixed text/thoughts.
        -   **Processor**: Ensuring the fallback logic for commands works (e.g., converting "ls -la" text to a shell command).
        -   **Context**: Testing handling of permission errors and invalid paths.
        -   **History**: Verifying automatic summarization logic.
        -   **Edge Cases**: Binary file handling, malformed JSON, missing arguments.

## Running Tests

### Run All Tests
To execute the entire test suite, run the following command from the project root:

```bash
python3 -m unittest discover tests
```

### Run Specific Test File
To run only the core logic tests:

```bash
python3 -m unittest tests/test_core_logic.py
```

### Run a Specific Test Class
To run only the parser tests:

```bash
python3 -m unittest tests.test_core_logic.TestAgentParser
```

## Adding New Tests

1.  Identify the module or feature to test.
2.  If it's a core architectural component (parsing, context flow), add to `tests/test_core_logic.py`.
3.  If it's a specific utility module, add to `tests/test_modules.py` or create a new file.
4.  **Mocking**: Use `unittest.mock` (`MagicMock`, `AsyncMock`, `patch`) heavily to avoid real API calls or filesystem changes during testing.
    -   *Note*: When testing the `Agent` class initialization, ensure `asyncio.create_task` is patched if no event loop is running.

## Troubleshooting

-   **RuntimeError: no running event loop**: This often happens when initializing the `AngelicaAgent` in `setUp()` because it tries to schedule a UI task. **Solution**: Patch `asyncio.create_task` or use `unittest.IsolatedAsyncioTestCase`.
-   **PermissionError**: Tests accessing the file system should mock `pathlib` or use a temporary directory. `test_core_logic.py` uses mocks for safety.
