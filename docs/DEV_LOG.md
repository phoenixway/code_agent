# Development Log

## Current Goals

- [ ] **Refactor Tool Definitions**: Move hardcoded tool logic from `processor.py` (like the shell fallback) into specific tool classes to clean up the processor.
- [ ] **Improve TUI**: Enhance the textual user interface for better file diff viewing.
- [ ] **Remote Context**: Add capability to fetch and add context from URLs.

## Achieved Goals

### 2026-01-20: Switched to <action> tags

**Objective**: Make the agent's response format more robust and less prone to parsing errors.

**Completed Tasks**:
- [x] Changed the system prompt to require JSON to be wrapped in `<action>` tags.
- [x] Updated the response parser to extract JSON from `<action>` tags.
- [x] Updated documentation and tests to reflect the new format.

**Problem Solving / Technical Details**:

1.  **Issue**: The previous raw JSON format was fragile. The model would sometimes include extra text before or after the JSON, causing parsing errors.
    -   **Solution**: By wrapping the JSON in `<action>` tags, we can use a more reliable regex to extract the action, and then parse the JSON inside. This makes the parsing much more robust.

### 2026-01-11: Core Logic Stabilization & Testing

**Objective**: Ensure the agent's "brain" (parsing and decision making) is robust and tested against edge cases.

**Completed Tasks**:
- [x] Created `tests/test_core_logic.py` to cover `AgentParser`, `ResponseProcessor`, `ContextManager`, and `HistoryManager`.
- [x] Added coverage for **Edge Cases**:
    -   Handling `PermissionError` when scanning directories (Context).
    -   Graceful failure for `UnicodeDecodeError` on binary files.
    -   Parsing "broken" JSON or mixed thought/JSON responses.
    -   Argument flattening for nested JSON parameters.

**Problem Solving / Technical Details**:

1.  **Issue**: `RuntimeError: no running event loop` when initializing `AngelicaAgent` in tests.
    -   **Context**: The agent's `__init__` calls `self.ui.print_system`, which schedules an async task. In `unittest.TestCase`, there is no active event loop during `setUp`.
    -   **Solution**: Patched `asyncio.create_task` in the `setUp` method of `TestAgentParser`.
    ```python
    with patch('asyncio.create_task'):
        self.agent = AngelicaAgent(ui=self.ui)
    ```

2.  **Issue**: `ResponseProcessor` test failure on fallback command parsing.
    -   **Context**: The test expected `command="read_file"` to be passed as an argument to the tool. However, the logic consumes the `command` key to identify the tool name and *removes* it from arguments to avoid duplication for non-shell tools.
    -   **Solution**: Updated the test expectation to match the implementation: `call('read_file', path='test.txt')` instead of `call('read_file', path='test.txt', command='read_file')`.

3.  **Issue**: JSON Parsing reliability.
    -   **Context**: Models often output text like: *"Sure, here is the command: ```json { ... } ```"*. Simple parsing fails.
    -   **Solution**: Implemented a greedy regex search `r'(\{.*\})'` with `re.DOTALL` to capture the widest possible JSON object, ignoring surrounding markdown or conversational text.
