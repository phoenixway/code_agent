this file content is DEPRECATED.

# Masterplan: A New Architecture for History Management

This document outlines the architecture for a new, robust history management system in the Angelica Agent.

## 1. The Core Problem

The current history system mixes chat conversation (user, assistant, system messages) with large blobs of file content. This leads to several issues:
- **Inefficient Context:** The same file content might be included multiple times, wasting valuable context window space.
- **Lack of Versioning:** It's difficult to track which version of a file was being discussed at a specific point in the conversation.
- **Inflexible History Generation:** It's hard to implement "intelligent" rules, such as "only include the latest 2 versions of a file" or "generate a diff between versions."
- **Model Expectation Conflict:** A naive separation of history can cause the model to fail. When the model calls `read_file`, it expects to see the file's content in the very next turn. Simply storing the file externally and adding a "File saved as v1" message would break the model's workflow.

## 2. The New Architecture: Separation and "Just-in-Time" Context

The new architecture is based on two core principles:
1.  **Separation of Concerns:** The `HistoryManager` will maintain two distinct structures:
    - `self.messages`: A list of conversation events, including user/assistant messages and special *markers* that reference files.
    - `self.files`: A dictionary (`{filename: [versions]}`) that stores the actual content of every version of every file ever read. This is the canonical source of truth for file content.
2.  **"Just-in-Time" Context Generation:** The history sent to the LLM (`api_history`) is dynamically generated before each API call. This process intelligently assembles the context, including file content, based on a set of rules, and handles the model's expectation for immediate feedback.

### 2.1. New Message Marker Types

To make this work, we introduce two new structured `system` message types within `self.messages`:

A. **`file_context` (File Context Marker)**
   - **Purpose:** To signify that a specific version of a file became relevant at a certain point in the conversation. This is the "permanent" reference to a file version.
   - **Trigger:** Created when a file is added by the user (`/add`) or read by the model (`read_file`).
   - **Structure:**
     ```json
     { "role": "system", "type": "file_context", "filename": "path/to/file.py", "version": 1 }
     ```

B. **`transient_file_content` (Transient File Content)**
   - **Purpose:** To satisfy the model's immediate expectation after a `read_file` call. This is a **temporary** message containing the full file content, which is intended to be "cleaned up" in subsequent turns.
   - **Trigger:** Created *only* when the model executes a `read_file` action.
   - **Structure:**
     ```json
     { "role": "system", "type": "transient_file_content", "filename": "f1.py", "version": 1, "content": "[...file content...]" }
     ```

## 3. Detailed Implementation Plan

### 3.1. `modules/history.py` (`HistoryManager`)

- **`add_file_version`:** This method will continue to store file content in `self.files` and manage versioning. It will be updated to return the new `version_number`.
- **`add_file_context_marker`:** A new method to add a `file_context` marker to `self.messages`.
- **`add_transient_file_content`:** A new method to add a `transient_file_content` message to `self.messages`.
- **`get_history_for_api` (The Core Engine):** This method will be completely rewritten to implement the "Just-in-Time" logic.
    1. It initializes an empty `api_history` and a tracker for included files (`included_files`).
    2. It iterates through `self.messages` from oldest to newest.
    3. **If it sees a `transient_file_content` message:** It is **ignored**. Its purpose is not to be part of the long-term, cleaned-up history.
    4. **If it sees a `file_context` marker:** It applies the "intelligent" rules:
        - Check `included_files`.
        - If the file is new or a new version is allowed (e.g., we don't have more than 2 versions of it in `api_history` yet), it fetches the content from `self.files` and formats it into a clean, readable system message for the `api_history`.
        - It updates `included_files`.
    5. **If it sees a standard message:** It's added to `api_history`.
    6. **The Final, Crucial Step:** After the loop, it performs one final check: "Is the very last message in the original `self.messages` a `transient_file_content` message?"
        - If YES, it means the model *just* asked for a file, so it appends this message (with its full content) to the very end of the `api_history`.
        - This ensures the model's expectation is always met, while all previous `transient` messages have been cleaned up.

### 3.2. `modules/processor.py` (`ResponseProcessor`)

- The `__init__` method will be updated to accept the `history` manager instance.
- The `process_single_action` method for `read_file` will be the central point of action:
    1. After successfully reading the file content.
    2. It calls `version = self.history.add_file_version(...)` to store the content.
    3. It immediately calls `self.history.add_file_context_marker(...)` to create the permanent record.
    4. It then calls `self.history.add_transient_file_content(...)` to create the temporary message for the model.
    5. It returns a simple, human-readable confirmation to the agent loop, e.g., `Read file 'f1.py' and added to history as v1.`. The main loop no longer has to deal with large file blobs.

### 3.3. Handling the `/add` command

- The code responsible for the `/add` command will be located and modified.
- It will call `agent.history.add_file_version(...)` followed by `agent.history.add_file_context_marker(...)`.
- It will **NOT** create a `transient_file_content` message, because the action was initiated by the user, and there is no model expectation to fulfill. The `get_history_for_api` method will pick up the `file_context` marker on the next turn and introduce the file content according to the rules.

## 4. Example Scenario Walkthrough

**Scenario:**
1.  **Turn 1:** Model calls `read_file('f1.py')`.
2.  **Turn 2:** Model calls `read_file('f2.py')`.

**Execution Flow for Turn 2 `get_history_for_api`:**

1.  The method starts building a new, clean `api_history`.
2.  It encounters the `transient_file_content` for `f1.py` from the previous turn. It **ignores** it.
3.  It encounters the `file_context` marker for `f1.py`. It checks its rules, sees `f1.py` is not yet in the clean history, fetches its content from `self.files`, and adds it.
4.  It processes the rest of the messages (user/assistant conversation).
5.  At the very end, it checks the last message in `self.messages`. It's the `transient_file_content` for `f2.py`.
6.  It appends this message with the full content of `f2.py` to the end of the `api_history`.

**Final prompt for the model:** The context will contain the cleanly-inserted content of `f1.py` and the just-requested content of `f2.py`. The redundant `f1.py` content from the previous turn has been successfully "cleaned up".
