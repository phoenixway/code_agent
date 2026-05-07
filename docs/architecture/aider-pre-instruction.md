# Aider Pre-Instruction: Semantic Runtime Migration

**INSTRUCTION**: Before starting any task, you must read, understand, and follow these instructions.

## 1. Read Canonical Documents

First, read and internalize the following governance documents from `docs/architecture/`:
- `semantic-runtime-constitution.md` (Highest Authority)
- `current-refactor-state.md`
- `semantic-runtime-roadmap.md`
- `refactor-stop-lines.md`
- `test-contracts.md`

## 2. State Your Understanding

Before proposing any changes, you must state:
1.  **Current Phase**: The current refactor phase, based on `semantic-runtime-roadmap.md`.
2.  **Task Classification**: Classify the user's request as one of:
    - `docs-only`
    - `test-only`
    - `diagnostic-only` (e.g., adding logs)
    - `production-behavior-preserving-refactor`
    - `production-behavior-changing`
3.  **Scope and Boundaries**:
    - **Allowed Files**: List the files you are permitted to edit for this task.
    - **Forbidden Changes**: List specific stop lines from `refactor-stop-lines.md` or other constraints that apply to this task.

## 3. Adhere to Phase Boundaries

-   **Do not expand the scope.** Your work must be strictly confined to the current phase defined in the roadmap.
-   **Do not implement future phases.** If a task seems to bleed into a future phase, state this and wait for confirmation.
-   **Default to behavior-preserving changes.** Unless explicitly instructed to change behavior as part of an approved design, all production code changes must be behavior-preserving refactors.

## 4. Propose and Verify Changes

When you propose changes, you must:
1.  **Show changed files**: List all files you intend to modify.
2.  **Show relevant tests**: List the key tests that will verify your changes and protect against regressions.
3.  **Provide `git diff --stat`**: Show the stat diff.
4.  **Provide focused `git diff`**: Show the diff for the most important changed files.
5.  **State behavior change**: Explicitly state "No behavior change" or describe the intended behavior change.
6.  **Propose next safe step**: Suggest the next logical, safe step according to the roadmap.
