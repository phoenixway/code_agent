# Semantic Shadow Test Report

This document summarizes the known semantic mismatches between the legacy `ResponseSemantics` (regex-based) and the new `ProtocolCompiler` (parser-based) as of the creation of the shadow test suite.

A passing shadow test suite indicates that all disagreements are documented and expected.

---

### 1. Invalid & Malformed Protocol

-   **Affected Cases**: `action_inside_think.yaml`, `unclosed_think.yaml`, `file_content_unclosed.yaml`, `mixed_visible_text_and_action.yaml`
-   **Legacy Behavior**: The regex-based system is not aware of the overall structure and often misinterprets malformed input. For example, it may find an `<action>` tag inside a `<think>` block and treat it as a valid action, while ignoring the `think` context entirely. For unclosed tags, it simply fails to find a match.
-   **Compiler Behavior**: The compiler uses a formal grammar and correctly identifies specific syntax errors (e.g., `E_UNCLOSED_THINK`, `E_AMBIGUOUS_PROTOCOL_SYNTAX`, `E_MIXED_VISIBLE_TEXT_AND_CONTROL`). It produces a structured `error` object in its analysis.
-   **Desired Future**: The compiler's behavior is correct and should be the source of truth for protocol validity.
-   **Migration Note**: Replace brittle, ad-hoc regex checks for malformed content with checks against the `analysis.error` field from the compiler's output.

---

### 2. Definition of "Visible Answer"

-   **Affected Cases**: `valid_single_action.yaml`, `valid_multi_readonly_actions.yaml`
-   **Legacy Behavior**: The `_strip_non_plaintext_control_blocks` helper incorrectly treats the JSON content inside `<action>` tags as user-visible text. This causes it to report `has_visible_answer: true` for responses that only contain actions.
-   **Compiler Behavior**: The compiler correctly distinguishes between `VisibleTextNode` (for user-facing text) and other nodes like `ActionNode`. It correctly reports `has_visible_answer: false` for action-only responses.
-   **Desired Future**: The compiler's behavior is correct. Only text outside of explicit protocol tags should be considered a visible answer.
-   **Migration Note**: The `has_visible_answer` flag should be sourced from the compiler analysis (or the resulting `ResponseIR`). The legacy logic is buggy and should be deprecated.

---

### 3. Definition of "Think" Content

-   **Affected Cases**: `valid_multi_readonly_actions.yaml`
-   **Legacy Behavior**: The `has_substantial_think` helper requires a `<think>` block to contain at least 5 words to be considered significant. A block with fewer words is ignored.
-   **Compiler Behavior**: The compiler's AST correctly identifies any non-empty `<think>` block, regardless of word count.
-   **Desired Future**: The compiler's behavior is more direct and less heuristic. The "substantial" check was a workaround to avoid empty or trivial `<think>` blocks. If this logic is still needed, it should be a higher-level policy or linter rule, not a core parsing semantic.
-   **Migration Note**: The `has_think` flag should be sourced from the compiler's analysis. The 5-word-minimum heuristic should be retired.

---

### 4. Definition of "Checkpoint"

-   **Affected Cases**: `valid_single_action.yaml`, `valid_multi_readonly_actions.yaml`
-   **Legacy Behavior**: The `has_checkpoint_tags` helper uses a specific regex that does **not** include `<memory_update_done />` in its definition of a checkpoint.
-   **Compiler Behavior**: The compiler's parser correctly identifies `<memory_update_done />` as a `MarkerNode`. For the purpose of the shadow tests, we are treating `MarkerNode` as a form of checkpoint, leading to a mismatch.
-   **Desired Future**: A unified, explicit definition of what constitutes a "checkpoint" is needed. The compiler provides the correct foundation by parsing all tags into a structured tree. The semantic meaning ("is this a checkpoint?") should be layered on top of the IR.
-   **Migration Note**: Define checkpoint semantics based on the compiler's IR. The legacy regex has an incomplete and inconsistent definition of what constitutes a checkpoint or reflection tag.
