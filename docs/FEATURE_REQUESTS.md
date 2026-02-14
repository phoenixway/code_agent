# Feature Requests

This document tracks planned improvements and feature ideas for Angelica AI.

## Architecture & Refactoring

- [ ] **Modularize Chat Providers**: Refactor `modules/chat.py` into a plugin-based system (e.g., `modules/providers/`). Create an abstract base class for providers to allow easier addition of new services (Anthropic, Azure, etc.) without modifying core logic.
- [x] **Cleanup**: `app.py` demo entry point was removed to avoid confusion with the real `tui.py` entry point.

## User Experience (UX)

- [ ] **File Diff View**: Before applying `edit_file` or `write_file` actions, display a visual diff (colored additions/deletions) in the TUI and require explicit user confirmation.
- [ ] **Syntax Highlighting**: Render code blocks in assistant responses using Textual's `Syntax` widget (via `rich.syntax`) for better readability and clipboard interaction.

## Stability & Performance

- [ ] **Token Counting & Display**: 
    - Implement a token counter (using `tiktoken` or heuristics) for files added via `/add`.
    - Display real-time context usage in the Status Bar (e.g., "Context: 12,400 / 32,000 tokens").
    - Prevent requests that exceed the model's limit before sending them.

## Security

- [ ] **Secure API Key Management**: 
    - Implement a `/config api <provider> <key>` command.
    - Store keys securely using the OS system keyring (via `keyring` library) instead of plain text `.env` files.

## Packaging & Distribution

- [ ] **Modern Packaging**: Migrate from `requirements.txt` to `pyproject.toml` (using Poetry or uv) to facilitate installation via `pipx` and better dependency resolution.
