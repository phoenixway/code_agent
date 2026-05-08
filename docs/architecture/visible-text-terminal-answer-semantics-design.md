# Phase 8 Design: Visible Text & Terminal Answer Semantics

- **Phase 8 Status**: Design Started
- **Step 1: Inventory**: Complete

## 1. Problem Statement

The runtime currently has multiple, overlapping mechanisms for identifying and handling responses that contain a final, user-visible answer. This leads to ambiguity and fragility. For example, a single response might be classified as `shape=MEMORY_TEXT`, `reason=intent_completed_with_plaintext_answer`, `reason=memory_checkpoint_and_text`, and `reason=terminal_plaintext_completion` by different pipeline stages.

This phase aims to clarify authority by creating a single, testable source of truth for terminal answer semantics, ensuring that decisions to stop, display, or recover are based on a consistent classification.

## 2. Current Behavior Inventory

This inventory documents the current state of components involved in visible text and terminal answer semantics.

| Component / Function | Input(s) | Decision / Effect | Authority Type | Dependency | Risk | Future Owner |
|---|---|---|---|---|---|---|
| **`RuntimeProtocolSemantics`** | `CompilerAnalysis` | Produces structural facts: `shape`, `has_visible_answer`, `visible_text`, `pre_action_text`. | Structural Fact | Compiler IR | Low | `RuntimeProtocolSemantics` |
| **`ResponseSemantics.is_plaintext_answer_path`** | `raw_response`, `parsed_output` | Determines if response is a plaintext answer. | Final-Answer Guard | Regex, `has_any_action_proposal_compat` | High | `TerminalAnswerClassifier` (candidate) |
| **`ResponsePipelinePrevalidationMixin._reject_truncated_terminal_completion_before_transition`** | `raw_response`, `intent_payload` | Rejects `intent mode="complete"` if visible text is missing or truncated. | Final-Answer Guard | `visible_text.terminal_plaintext_completion_status` (regex) | Medium | `TerminalAnswerClassifier` (candidate) |
| **`IntentTransitionRoutingMixin`** | `response_text`, `intent_payload` | Handles `intent_completed_with_plaintext_answer`. | Transition Policy | `TransitionSemanticValidator`, legacy regex | High | `IntentTransitionHandler` |
| **`MemoryBoardStageHandler`** | `raw_response` | Identifies `memory_checkpoint_and_text`. | Board Checkpoint | Regex | Medium | `MemoryBoardStageHandler` |
| **`PlanBoardStageHandler`** | `raw_response` | Identifies `plan_checkpoint_and_text`. | Board Checkpoint | Regex | Medium | `PlanBoardStageHandler` |
| **`ResponsePipelineStagesMixin`** | `memory_checkpoint_and_text` flag | Dispatches responses with memory checkpoints and text. | Dispatch Routing | Boolean flag from `MemoryBoardStageHandler` | Medium | `ResponsePipelineStagesMixin` |
| **`OutputRecoveryRoutingMixin`** | `parsed_output` | Recovers from `internal_summary_instead_of_final_answer`. | Recovery Routing | Heuristics on `parsed_output` | Medium | `TerminalAnswerClassifier` (candidate) |
| **`semantic_accessors.is_leaked_system_result`** | `text` | Detects leaked `SYSTEM RESULT` transcripts. | Malformed-Output Evidence | Regex | Low | `semantic_accessors` |
| **`DispatchOutcomeHandler._extract_visible_text`** | `response_text` | Extracts final text for UI display. | UI Display | `visible_text.sanitize_visible_text_for_user` (regex) | High | `DispatchOutcomeHandler` (consuming a classification) |
| **`PreDispatchPipeline`** | `state.terminal_plaintext_completion_pending` | Stops the loop for a terminal plaintext answer. | Final-Answer Stop Gate | Boolean flag set by `IntentTransitionHandler` | High | `PreDispatchPipeline` (consuming a classification) |

## 3. Desired Authority Model

- **`RuntimeProtocolSemantics`**: Continues to own raw structural facts from the compiler (`shape`, `has_visible_answer`, etc.).
- **`TerminalAnswerClassifier` (Candidate)**: A new, dedicated component could become the single source of truth for classifying terminal answer semantics. It would consume `RuntimeProtocolSemantics` and other necessary inputs to produce a strongly-typed result (e.g., `TerminalAnswerKind`). The exact component shape will be decided after characterization tests (Step 2) are complete.
- **Consumers**: If a classifier is created, consumers would be migrated to use it:
    - `IntentTransitionHandler` would consume the result for `intent_completed_with_plaintext_answer` transitions.
    - `MemoryBoardStageHandler` / `PlanBoardStageHandler` could consume the result to simplify their logic.
    - `ResponsePipeline` would consume the result for routing decisions.
    - `DispatchOutcomeHandler` would consume a `visible_text` field from the result for UI display.
    - `PreDispatchPipeline` would consume a typed `TerminalAnswerKind` to make a clear stop/continue decision.

## 4. Risks

- **Behavioral Regressions**: The interaction between these components is complex. Any change risks altering final-answer display, loop termination, or recovery behavior.
- **Regex Fragility**: Many components rely on fragile regex helpers. Refactoring them requires careful characterization.
- **Scope Creep**: This phase must remain focused on clarifying terminal answer semantics and not bleed into a full rewrite of the response pipeline or `history.py`.

## 5. Proposed Phase Slicing

- **Step 1: Design-Only Inventory (Done)**: This document.
- **Step 2: Characterization Tests (Done)**: Added characterization tests to lock down the exact behavior of all identified components and scenarios. This was a tests-only step. No production code was changed. Key behaviors characterized include compiler shape analysis, `ResponseSemantics.is_plaintext_answer_path`, `terminal_plaintext_completion_status`, and others.
- **Step 3: Typed Model Scaffolding (Design)**: The design for the typed model scaffolding is complete and approved for a scaffolding-only implementation (Step 3A).
- **Step 3A: Typed Model Scaffolding (Implementation)**: Done. Created `TerminalAnswerKind` enum and `TerminalAnswerSemanticResult` dataclass in `terminal_answer_models.py`. No classifier logic was implemented, and no consumers were migrated.
- **Step 4A: Compiler/Runtime Semantics Tag Coverage Review (Design-Only)**: Review whether `RuntimeProtocolSemantics` exposes enough structural facts to support a reliable `TerminalAnswerClassifier`.
- **Step 4B: Classifier Implementation (Shadow Mode) (Design Review)**: Design the `TerminalAnswerClassifier` and a plan for running it in shadow mode. Implementation is not authorized.
- **Step 5: First Consumer Migration**: Migrate the lowest-risk consumer (e.g., `is_leaked_system_result`) to use the new classifier.
- **Step 6: Authority Consolidation**: Systematically migrate remaining consumers (`IntentTransitionHandler`, `PreDispatchPipeline`, etc.) to the new classifier, removing legacy logic one component at a time.
- **Step 7: Cleanup**: Once all consumers are migrated, remove the old regex helpers and redundant logic.

## 6. Design Review and Decision (Step 3)

The design review of the characterization test results (Step 2) is complete.

### Characterization Findings
The tests revealed significant ambiguity in the current system:
- The compiler `shape=PLAINTEXT_ONLY` is used for multiple distinct semantic meanings, including simple plaintext, pre-action text with an action, and text with stripped subgoal tags. This makes the shape unreliable for policy decisions.
- `terminal_plaintext_completion_status` has fragile heuristics (e.g., rejecting "Done.") and strips protocol tags, hiding potential leaks.
- `_is_internal_summary_instead_of_final_answer` fails to detect planning-like text that should not be a final answer.

### Decision
The ambiguity of current signals justifies introducing a typed result model to create a single, explicit source of truth.

**Decision: Proceed with a typed model.**

The proposed model consists of:
- `TerminalAnswerKind` (Enum): A set of explicit classifications for terminal answer semantics.
- `TerminalAnswerSemanticResult` (Dataclass): A container for the `kind` and any associated data (e.g., the extracted visible text).

### Candidate `TerminalAnswerKind` Enum
Based on the characterization tests, the initial candidate kinds are:
- `UNKNOWN`: Default or unclassifiable.
- `NO_VISIBLE_TEXT`: No user-visible text was found.
- `PLAINTEXT_TERMINAL_ANSWER`: A valid, complete final answer in plain text.
- `CHECKPOINT_ONLY`: The response contains only memory/subgoal checkpoints with no visible text.
- `CHECKPOINT_WITH_VISIBLE_TEXT`: The response contains both checkpoints and visible text.
- `INTENT_COMPLETE_WITH_VISIBLE_TEXT`: The response completes an intent and provides visible text.
- `PRE_ACTION_VISIBLE_TEXT_WITH_ACTION`: The response contains visible text preceding an action.
- `LEAKED_SYSTEM_RESULT`: The response appears to contain a leaked system/tool result.
- `INTERNAL_SUMMARY_LIKE_TEXT`: The text appears to be internal planning or summary, not a final answer.
- `INVALID_OR_TRUNCATED_TERMINAL_TEXT`: The text appears to be an incomplete or invalid final answer.

### Next Step
The scaffolding (Step 3A) is complete. The approved next step is to conduct the **Phase 8, Step 4A: Compiler/Runtime Semantics Tag Coverage Review**. This is a design-only review to ensure the `TerminalAnswerClassifier` will have sufficient structural data. Implementation of the classifier is not authorized.

## 7. Compiler/Runtime Semantics Tag Coverage Review (Step 4A)

This design-only review is complete. It assessed whether `RuntimeProtocolSemantics` exposes enough structural facts to support a reliable `TerminalAnswerClassifier`.

### Conclusion
**Insufficient.** The compiler and `RuntimeProtocolSemantics` adapter currently lack the necessary structural facts to reliably classify several key `TerminalAnswerKind`s. The compiler shape `PLAINTEXT_ONLY` is ambiguous, and critical distinctions (like subgoal-accompanying text) are lost. Building the `TerminalAnswerClassifier` now would force it to rely on the same fragile regex heuristics we aim to replace.

**Recommendation:** Do not proceed with `TerminalAnswerClassifier` implementation (Step 4B). The next step must be a design-only phase to add the missing structural facts to the compiler and `RuntimeProtocolSemantics`.

### Coverage Inventory

| `TerminalAnswerKind` | Current Signals & Sufficiency | Missing Structural Facts | Recommendation |
|---|---|---|---|
| **`NO_VISIBLE_TEXT`** | **Sufficient.** `has_visible_answer=False`, `has_pre_action_text=False`. | None. | Ready for classification. |
| **`PLAINTEXT_TERMINAL_ANSWER`** | **Insufficient.** `shape=PLAINTEXT_ONLY` is ambiguous and used for other kinds. | A non-ambiguous shape like `PURE_PLAINTEXT`. | Add new shape. |
| **`CHECKPOINT_ONLY`** | **Partially sufficient for memory checkpoints.** Insufficient for general checkpoint-only semantics unless subgoal/checkpoint_kind facts are exposed. | `has_subgoal_tags`, `checkpoint_kind`, `board_checkpoint_kind` or equivalent. | Add explicit `checkpoint_kind` before using this as classifier authority. |
| **`CHECKPOINT_WITH_VISIBLE_TEXT`** | **Insufficient.** `shape=MEMORY_TEXT` is correct, but the compiler incorrectly classifies subgoal+text as `PLAINTEXT_ONLY`. | Correct classification of subgoal tags. | Fix compiler to recognize subgoals and produce a `MEMORY_TEXT`-like shape. |
| **`INTENT_COMPLETE_WITH_VISIBLE_TEXT`** | **Sufficient.** `shape=INTENT_COMPLETE_WITH_TEXT` is unique. | None. | Ready for classification. |
| **`PRE_ACTION_VISIBLE_TEXT_WITH_ACTION`** | **Insufficient.** Characterization tests showed representative pre-action text + action cases can currently classify as `PLAINTEXT_ONLY`. | `has_pre_action_visible_text`, `has_action_after_visible_text`, `visible_text_source = pre_action`. | Add compiler/runtime structural facts before classifier shadow mode. |
| **`LEAKED_SYSTEM_RESULT`** | **Insufficient.** Relies on regex (`is_leaked_system_result`). | A structural flag like `has_leaked_system_result`. | Defer. Can remain on regex for now. |
| **`INTERNAL_SUMMARY_LIKE_TEXT`** | **Insufficient.** Relies on fragile heuristics. | A structural flag like `is_internal_summary`. | Defer. This is a high-level policy decision, not a structural fact. |
| **`INVALID_OR_TRUNCATED_TERMINAL_TEXT`** | **Insufficient.** Relies on regex (`terminal_plaintext_completion_status`). | A structural flag from the compiler like `is_truncated_text`. | Defer. Can remain on regex for now. |

### Next Step
The review (Step 4A) is complete. The approved next step is to conduct **Phase 8, Step 4C: Compiler Fact Scaffolding (Design)**. This is a design-only step to plan the addition of new structural facts to the compiler and `RuntimeProtocolSemantics` to address the gaps identified above. Implementation of the classifier remains blocked.

## 8. Phase 8 Step 4C: Compiler Fact Scaffolding (Design)

This design step is complete. It defines the new structural facts required for the `TerminalAnswerClassifier` to function reliably. Implementation is not authorized until a new design for implementation steps is approved.

### Conclusion
The review in Step 4A concluded that `RuntimeProtocolSemantics` lacks sufficient structural facts. This design proposes adding them to the compiler and the runtime adapter. The goal is to provide unambiguous, structural signals that the future `TerminalAnswerClassifier` can use, replacing fragile regex heuristics.

### Proposed New Structural Facts

The following facts should be added to the compiler's analysis and exposed through `ResponseIR` and `RuntimeProtocolSemantics`.

| Fact | Type | Meaning | Source | Location |
|---|---|---|---|---|
| **`has_subgoal_tags`** | `bool` | `True` if one or more `<subgoal>` tags are present. | Compiler AST | `ResponseIR` -> `RuntimeProtocolSemantics` |
| **`has_memory_tags`** | `bool` | `True` if memory board tags (e.g., `<fact>`, `<finding>`) are present. Excludes `<subgoal>`. | Compiler AST | `ResponseIR` -> `RuntimeProtocolSemantics` |
| **`has_memory_checkpoint`** | `bool` | `True` if a `<memory_update_done />` tag is present. | Compiler AST | `ResponseIR` -> `RuntimeProtocolSemantics` |
| **`visible_text_source`** | `Enum` | Classifies the semantic context of visible text. Candidates: `NONE`, `PURE_PLAINTEXT`, `PRE_ACTION_TEXT`, `INTENT_COMPLETION_TEXT`, `CHECKPOINT_ACCOMPANYING_TEXT`, `UNKNOWN`. | Compiler Shape | `ResponseIR` -> `RuntimeProtocolSemantics` |

### Proposed Compiler Shape Improvements

To support `visible_text_source` and fix issues found during characterization, the compiler's shape classification logic needs improvement:

1.  **`PRE_ACTION_TEXT_AND_ACTION`**: The compiler must reliably identify this shape. The characterization tests showed it currently misclassifies some cases as `PLAINTEXT_ONLY`. This shape should be returned for `VisibleTextNode` followed by `ActionNode`.
2.  **`SUBGOAL_WITH_TEXT`**: A new shape should be introduced for responses containing both `<subgoal>` tags and visible text. The compiler currently misclassifies this as `PLAINTEXT_ONLY`. This would be analogous to the existing `MEMORY_TEXT` shape.
3.  **`PURE_PLAINTEXT`**: The existing `PLAINTEXT_ONLY` shape is ambiguous. A new, more specific shape should be used for responses that contain only visible text and optional `<think>` blocks, with no other control tags.

These shape improvements are the source of truth for the `visible_text_source` enum.

### Boundaries and Deferred Items

- **Structural Facts Only**: These changes are limited to exposing purely structural information. Policy decisions (e.g., `is_internal_summary`) remain deferred.
- **Legacy Fallbacks**: Detection of truncated text and leaked system results will remain on their legacy regex-based implementations for now.
- **No `TerminalAnswerClassifier`**: Implementation of the classifier remains blocked until these structural facts are implemented and verified.

### Proposed Implementation Slicing

This design will be implemented in the following sequence of steps, each requiring separate approval:

- **Step 4D: New Fact Characterization Test Design**: Design characterization tests for the new structural facts and shape improvements. This is a design-only step to define the test cases.
- **Step 4D.1: New Fact Characterization Test Implementation**: Implement the characterization tests. This is a tests-only step. The tests are expected to fail until the compiler changes are made.
- **Step 4E: Compiler/Runtime Fact Implementation**: Implement the required changes in `ProtocolCompiler` and `RuntimeProtocolSemantics` to make the new characterization tests pass. No consumers will be migrated.
- **Step 4F: Shadow Sufficiency / Parity Review**: Design and implement a "shadow mode" or parity test suite to compare the output of the (still-unwritten) `TerminalAnswerClassifier` against the existing characterization tests from Step 2, proving the new facts are sufficient.
- **Step 4B (Redux): TerminalAnswerClassifier Shadow Mode Design**: With the structural facts in place, the design of the `TerminalAnswerClassifier` (originally Step 4B) can be resumed.

### Next Step

The design (Step 4C) is complete. The approved next step was to conduct **Phase 8, Step 4D: New Fact Characterization Tests (Design)**. This design step is now complete.

## 9. Phase 8 Step 4D: New Fact Characterization Test Design

This design step is complete. It defines the characterization tests required to validate the new structural facts and compiler shape improvements proposed in Step 4C.

### Goal
To create a suite of tests that will lock down the behavior of the new compiler facts and shapes. These tests will initially be expected to fail (`xfail`) and will serve as the specification for the implementation work in Step 4E.

### Test Location
The new tests will be added to `tests/test_runtime_protocol_semantics.py` or a new dedicated test file like `tests/test_compiler_structural_facts.py`.

### Protocol Tag Inventory
To ensure full coverage, the tests must account for all compiler-visible protocol tags.

- **Non-Board Control Tags**: `<think>`, `<intent>`, `<action>`, `<file_content>`
- **Memory Content Tags**: `<fact>`, `<finding>`, `<decision>`, `<preference>`, `<progress>`, `<path>`
- **Memory Review Tag**: `<memory_review />`
- **Memory Checkpoint Marker**: `<memory_update_done />`
- **Plan/Subgoal Tag**: `<subgoal>`

**Compatibility Risk**: Legacy `ResponseSemantics` treats `<preference>` as a memory tag. The Step 4D.1 tests and Step 4E implementation must ensure the compiler also recognizes `<preference>` as a memory tag to avoid regressions.

### Test Design: Board and Checkpoint Facts

These tests will target the new boolean facts on `RuntimeProtocolSemantics`.

#### `has_subgoal_tags`
- **Test Case 1**: Response with one `<subgoal>` tag.
  - **Input**: `<subgoal action='create' id='s1'>Subgoal</subgoal>`
  - **Expected**: `snapshot.has_subgoal_tags` is `True`.
- **Test Case 2**: Response with multiple `<subgoal>` tags.
  - **Input**: `<subgoal ...>...</subgoal><subgoal ...>...</subgoal>`
  - **Expected**: `snapshot.has_subgoal_tags` is `True`.
- **Test Case 3**: Response with no `<subgoal>` tags.
  - **Input**: `<fact>A fact.</fact>`
  - **Expected**: `snapshot.has_subgoal_tags` is `False`.
- **Test Case 4**: Response with `<subgoal>` and other memory tags.
  - **Input**: `<fact>A fact.</fact><subgoal ...>...</subgoal>`
  - **Expected**: `snapshot.has_subgoal_tags` is `True`.

#### `has_memory_tags`
- **Test Case 1**: Response with memory content tags (`<fact>`, `<finding>`, `<decision>`, `<preference>`, `<progress>`, `<path>`).
  - **Input**: `<fact>A fact.</fact><preference>A preference.</preference>`
  - **Expected**: `snapshot.has_memory_tags` is `True`.
- **Test Case 2**: Response with memory review tag (`<memory_review />`).
  - **Input**: `<memory_review />`
  - **Expected**: `snapshot.has_memory_tags` is `True`.
- **Test Case 3**: Response with only `<subgoal>` tags.
  - **Input**: `<subgoal ...>...</subgoal>`
  - **Expected**: `snapshot.has_memory_tags` is `False`.
- **Test Case 4**: Response with only `<memory_update_done />`.
  - **Input**: `<memory_update_done />`
  - **Expected**: `snapshot.has_memory_tags` is `False`.
- **Test Case 5**: Response with memory tags and subgoal tags.
  - **Input**: `<fact>A fact.</fact><subgoal ...>...</subgoal>`
  - **Expected**: `snapshot.has_memory_tags` is `True`.

#### `has_memory_checkpoint`
- **Test Case 1**: Response with `<memory_update_done />`.
  - **Input**: `<memory_update_done />`
  - **Expected**: `snapshot.has_memory_checkpoint` is `True`.
- **Test Case 2**: Response with memory tags but no checkpoint.
  - **Input**: `<fact>A fact.</fact>`
  - **Expected**: `snapshot.has_memory_checkpoint` is `False`.
- **Test Case 3**: Response with both memory tags and checkpoint.
  - **Input**: `<fact>A fact.</fact><memory_update_done />`
  - **Expected**: `snapshot.has_memory_checkpoint` is `True`.

### Test Design: Compiler Shape Improvements

These tests will target the compiler's `shape` output and the corresponding `visible_text_source` on the `RuntimeProtocolSemantics` snapshot.

#### `PURE_PLAINTEXT` Shape
- **Test Case 1**: Simple plaintext.
  - **Input**: `Hello world.`
  - **Expected Shape**: `PURE_PLAINTEXT`
  - **Expected VTS**: `PURE_PLAINTEXT`
- **Test Case 2**: Plaintext with `<think>`.
  - **Input**: `<think>...</think>Hello world.`
  - **Expected Shape**: `PURE_PLAINTEXT`
  - **Expected VTS**: `PURE_PLAINTEXT`

#### `PRE_ACTION_TEXT_AND_ACTION` Shape
- **Test Case 1**: Text before an action.
  - **Input**: `Okay, I will read the file.<action>{"type":"read_file","path":"README.md"}</action>`
  - **Expected Shape**: `PRE_ACTION_TEXT_AND_ACTION`
  - **Expected VTS**: `PRE_ACTION_TEXT`
  - **Expected Facts**: `snapshot.has_pre_action_text` is `True`, `snapshot.pre_action_text` contains "Okay, I will read the file.".

#### `SUBGOAL_WITH_TEXT` Shape
- **Test Case 1**: Subgoal tag with accompanying text.
  - **Input**: `<subgoal ...>...</subgoal>Now, let's proceed.`
  - **Expected Shape**: `SUBGOAL_WITH_TEXT`
  - **Expected VTS**: `CHECKPOINT_ACCOMPANYING_TEXT`
- **Test Case 2**: Memory tags with accompanying text.
  - **Input**: `<fact>...</fact>Here is a summary.`
  - **Expected Shape**: `MEMORY_TEXT` (existing shape)
  - **Expected VTS**: `CHECKPOINT_ACCOMPANYING_TEXT`

#### `INTENT_COMPLETE_WITH_TEXT` Shape
- **Test Case 1**: Intent complete with text.
  - **Input**: `<intent mode="complete">{}</intent>All done.`
  - **Expected Shape**: `INTENT_COMPLETE_WITH_TEXT` (existing shape)
  - **Expected VTS**: `INTENT_COMPLETION_TEXT`

### Test Design: `visible_text_source` Enum

A new parameterized test will map various responses to the expected `visible_text_source` (VTS) value.

| Response Snippet | Expected `visible_text_source` | Notes |
|---|---|---|
| `(no visible text)` | `NONE` | e.g., `<action>{"type":"read_file","path":"README.md"}</action>` only |
| `Just text.` | `PURE_PLAINTEXT` | |
| `Text before <action>{"type":"read_file","path":"README.md"}</action>` | `PRE_ACTION_TEXT` | |
| `<intent mode="complete">{}</intent>Text.` | `INTENT_COMPLETION_TEXT` | |
| `<fact>...</fact>Text.` | `CHECKPOINT_ACCOMPANYING_TEXT` | |
| `<subgoal>...</subgoal>Text.` | `CHECKPOINT_ACCOMPANYING_TEXT` | |
| `<think>...</think>` | `NONE` | No visible text |
| `<action>{"type":"read_file","path":"README.md"}</action><intent>{}</intent>` | `UNKNOWN` | Invalid combination, shape is INVALID |

### Optional Facts Review

- **`has_pre_action_visible_text`**: This describes the valid `PRE_ACTION_TEXT_AND_ACTION` shape where visible text appears before an action. This is redundant with `visible_text_source`. The existing `has_pre_action_text` boolean on `RuntimeProtocolSemantics` is sufficient. No new test is needed beyond what's designed for that shape.
- **Visible text after action**: The case of visible text appearing *after* an action is an error condition (`E_VISIBLE_TEXT_AFTER_ACTION`). The compiler already detects this. It should not be a structural fact on a valid IR. No test needed.
- **`checkpoint_kind`**: This would be a useful enum (`MEMORY`, `SUBGOAL`, etc.) but is a larger change.
  - **Decision**: Defer `checkpoint_kind`. The boolean flags (`has_memory_tags`, `has_subgoal_tags`) are sufficient for the immediate needs of the `TerminalAnswerClassifier` design.

### Implementation Plan for Tests (Step 4D.1)

- The tests designed here will be implemented in Step 4D.1.
- They will be marked with `@pytest.mark.xfail(reason="Not implemented in compiler yet")`.
- This ensures the test suite remains green while providing a clear specification for the compiler implementation in Step 4E.
- No production code will be changed in Step 4D.1.

### Implementation Constraints for Step 4E

Before implementation of Step 4E is authorized, the following design constraints are established:

-   **Facts-First, Shape-Minimal**: The primary goal of Step 4E is to implement the new structural *facts* (`has_memory_tags`, etc.) in the compiler's IR and `RuntimeProtocolSemantics`. Shape improvements are secondary.
-   **No New Board-Only Shapes**: Step 4E must **not** introduce new compiler shapes for board-only or marker-only responses (e.g., `CHECKPOINT_ONLY`, `BOARD_ONLY`). These responses may retain their current shape classification for compatibility. The golden tests for these cases correctly specify `expected_shape=None`.
-   **Deferred Shape Taxonomy**: A more detailed taxonomy of board-only shapes is deferred to a future phase. Step 4E only guarantees the structural facts and the specific shape improvements (`PURE_PLAINTEXT`, `SUBGOAL_WITH_TEXT`, `PRE_ACTION_TEXT_AND_ACTION`) required by the golden tests.
-   **`<preference>` Tag Compatibility**: For legacy compatibility, the compiler implementation in Step 4E must treat the `<preference>` tag as a memory tag, ensuring `has_memory_tags` is `True` when it is present.

### Lessons learned from Step 4E

The implementation of Step 4E reinforced key architectural principles:
-   **Structural facts cannot be reliable if parser atoms are not reliable.** The implementation required parser-level repairs for cases like an action following leading visible text and a self-closing complete intent followed by visible text.
-   **Compiler/parser owns structural protocol facts.** The work was correctly confined to the compiler, parser, and IR.
-   **RuntimeProtocolSemantics adapts IR only.** The runtime adapter correctly consumed facts from the IR without adding its own parsing logic.
-   **No new runtime regex fact detection was added.** All new facts are derived from the compiler's AST/IR, upholding the design.

### Next Step

-   **Step 4D.1 (Test Implementation)** is complete. The golden characterization tests are in place.
-   **Step 4E (Compiler/Runtime Fact Implementation)** is complete. The new structural facts are implemented in the compiler, and the characterization tests from Step 4D.1 are passing.
-   **Step 4F (Shadow Sufficiency / Parity Review)** is complete. The review concluded that the structural facts are sufficient to proceed with the design of a shadow-mode `TerminalAnswerClassifier`.
-   The next step is **Phase 8, Step 4B (Redux): TerminalAnswerClassifier Shadow Mode Design**.
-   Implementation of the `TerminalAnswerClassifier` remains blocked, but the design phase is now authorized.

## 10. Phase 8 Step 4F: Shadow Sufficiency / Parity Review

This design-only review is complete. It assessed whether the new compiler/parser/IR-derived facts from Step 4E are sufficient to support a future `TerminalAnswerClassifier`.

### Conclusion
**Sufficient for Shadow-Mode Design.** The new structural facts provide a strong foundation for classifying the core `TerminalAnswerKind` candidates. While several kinds remain dependent on legacy regex or runtime policy, the structural distinctions are now clear enough to proceed with designing a `TerminalAnswerClassifier` that can run in shadow mode.

- **What this unblocks**: **Phase 8, Step 4B (Redux): TerminalAnswerClassifier Shadow Mode Design**. The design of the classifier can now begin.
- **What remains blocked**: The **implementation** of the classifier and the migration of any consumers are still forbidden until the shadow-mode design is complete and approved.

### Sufficiency Matrix

This matrix classifies each `TerminalAnswerKind` candidate based on the support from the new structural facts.

| `TerminalAnswerKind` | Status | Supporting Facts / Rationale |
|---|---|---|
| **`NO_VISIBLE_TEXT`** | `READY_FOR_SHADOW_CLASSIFIER` | `snapshot.has_visible_answer is False` and `snapshot.has_pre_action_text is False`. |
| **`PLAINTEXT_TERMINAL_ANSWER`** | `READY_FOR_SHADOW_CLASSIFIER` | `snapshot.visible_text_source == "PURE_PLAINTEXT"`. Final-answer correctness remains a runtime policy, but the structure is identifiable. |
| **`CHECKPOINT_ONLY`** | `READY_FOR_SHADOW_CLASSIFIER` | `(has_memory_tags or has_subgoal_tags or has_memory_checkpoint)` with no visible text. |
| **`CHECKPOINT_WITH_VISIBLE_TEXT`** | `READY_FOR_SHADOW_CLASSIFIER` | `snapshot.visible_text_source == "CHECKPOINT_ACCOMPANYING_TEXT"`. |
| **`INTENT_COMPLETE_WITH_VISIBLE_TEXT`** | `READY_FOR_SHADOW_CLASSIFIER` | `snapshot.visible_text_source == "INTENT_COMPLETION_TEXT"`. |
| **`PRE_ACTION_VISIBLE_TEXT_WITH_ACTION`** | `READY_FOR_SHADOW_CLASSIFIER` | `snapshot.visible_text_source == "PRE_ACTION_TEXT"`. |
| **`LEAKED_SYSTEM_RESULT`** | `DEFERRED_LEGACY_REGEX` | No structural fact exists. This remains dependent on the `is_leaked_system_result` regex helper. |
| **`INTERNAL_SUMMARY_LIKE_TEXT`** | `DEFERRED_RUNTIME_POLICY` | This is a high-level semantic/policy judgment, not a structural fact. It will remain a runtime heuristic. |
| **`INVALID_OR_TRUNCATED_TERMINAL_TEXT`** | `DEFERRED_LEGACY_REGEX` | No structural fact exists. This remains dependent on legacy regex heuristics. |
| **`UNKNOWN`** | `READY_FOR_SHADOW_CLASSIFIER` | Serves as the fallback for any unhandled or ambiguous cases. |

## 11. Phase 8 Step 4B Redux: TerminalAnswerClassifier Shadow Mode Design

This design step is complete. It defines the future `TerminalAnswerClassifier` and its shadow-mode validation plan.

- **Status**: Design Complete.
- **Next Step**: **Phase 8 Step 4H: Shadow Wiring / Diagnostic Logging**.
- **Implementation Status**: The `TerminalAnswerClassifier` class and its models are implemented as of Step 4G. Runtime integration for shadow-mode logging is deferred to Step 4H.

### 11.1. Design Overview

The `TerminalAnswerClassifier` will be a new, dedicated component responsible for classifying the semantic meaning of a model's response when it contains user-visible text. It will replace a scattered collection of regex helpers and ambiguous heuristics with a single, testable source of truth.

During its initial implementation (Step 4G), it will run in **shadow mode only**. It will have no effect on runtime behavior, dispatch decisions, or user-visible output. Its purpose will be to generate diagnostic data to prove its parity with existing logic.

### 11.2. Classifier Location and Name

- **File**: `modules/agent/orchestration/responses/terminal_answer_classifier.py`
- **Class**: `TerminalAnswerClassifier`

### 11.3. Input and Output Models

The classifier consumes an immutable input snapshot and produces a structured typed result. These models were implemented in Step 4G.

-   **Input Model**: `TerminalAnswerClassifierInput` (dataclass)
    -   `runtime_semantics`: `RuntimeProtocolSemantics`
    -   `raw_response_text`: `str`

-   **Output Model**: `TerminalAnswerSemanticResult` (dataclass)
    -   `kind`: `TerminalAnswerKind`
    -   `source`: `str` (e.g., `compiler_fact`, `legacy_regex`, `runtime_policy`, `fallback`)
    -   `reason_code`: A stable string for machine-readable classification logic.
    -   `evidence`: A tuple of strings naming the facts used for classification.
    -   `visible_text`: An optional `str` containing the extracted visible text.
    -   `details`: An optional dictionary for diagnostic data, for shadow/debug use only.

### 11.4. Classification Algorithm

The classifier must be deterministic and priority-ordered. It will use a combination of new compiler-derived structural facts and existing legacy/policy helpers.

**Note**: The implementation of legacy helper branches is proceeding incrementally in Step 4I.

| Priority | `TerminalAnswerKind` | Logic / Evidence | `source` | Status (Step 4I) |
|---|---|---|---|---|
| 1 | `LEAKED_SYSTEM_RESULT` | A pure-function regex check for the complete `SYSTEM RESULT:` marker at the start of the response. This must not match a bare `SYSTEM RESULT` prefix. | `legacy_compatible_rule` | **Done** |
| 2 | `INVALID_OR_TRUNCATED_TERMINAL_TEXT` | For `PURE_PLAINTEXT` candidates, a pure-function rule compatible with `terminal_plaintext_completion_status`, but only when the response is not a complete leaked-system marker. | `legacy_compatible_rule` | **Done** |
| 3 | `INTERNAL_SUMMARY_LIKE_TEXT` | `input.is_internal_summary is True`. The flag is computed by the caller using the legacy `_is_internal_summary_instead_of_final_answer` helper. | `runtime_policy` | **Done** |

Part 3 integrated `INVALID_OR_TRUNCATED_TERMINAL_TEXT`. Part 4 integrated `INTERNAL_SUMMARY_LIKE_TEXT` using a caller-computed boolean flag, without passing stateful runtime objects into the classifier.
| 4 | `PRE_ACTION_VISIBLE_TEXT_WITH_ACTION` | `input.runtime_semantics.visible_text_source == "PRE_ACTION_TEXT"` | `compiler_fact` | Done (Step 4G) |
| 5 | `INTENT_COMPLETE_WITH_VISIBLE_TEXT` | `input.runtime_semantics.visible_text_source == "INTENT_COMPLETION_TEXT"` | `compiler_fact` | Done (Step 4G) |
| 6 | `CHECKPOINT_WITH_VISIBLE_TEXT` | `input.runtime_semantics.visible_text_source == "CHECKPOINT_ACCOMPANYING_TEXT"` | `compiler_fact` | Done (Step 4G) |
| 7 | `CHECKPOINT_ONLY` | `(has_memory_tags or has_subgoal_tags or has_memory_checkpoint)` is `True` AND `has_visible_answer` and `has_pre_action_text` are `False`. | `compiler_fact` | Done (Step 4G) |
| 8 | `PLAINTEXT_TERMINAL_ANSWER` | `input.runtime_semantics.visible_text_source == "PURE_PLAINTEXT"` | `compiler_fact` | Done (Step 4G) |
| 9 | `NO_VISIBLE_TEXT` | `has_visible_answer` and `has_pre_action_text` are `False`. | `compiler_fact` | Done (Step 4G) |
| 10 | `UNKNOWN` | Fallback for all other cases. | `fallback` | Done (Step 4G) |

### 11.4A. Step 4I Parity Matrix

| `TerminalAnswerKind` | Implemented in classifier? | Source type | Legacy parity logging available? | Consumer migration status | Remaining risk / deferred notes |
|---|---|---|---|---|---|
| `LEAKED_SYSTEM_RESULT` | Yes | `legacy_compatible_rule` | Yes | Blocked | Uses a classifier-local pure-function rule for the complete `SYSTEM RESULT:` marker. |
| `INVALID_OR_TRUNCATED_TERMINAL_TEXT` | Yes | `legacy_compatible_rule` | Yes | Blocked | Depends on legacy-compatible plaintext completion heuristics. |
| `INTERNAL_SUMMARY_LIKE_TEXT` | Yes | `runtime_policy` | Yes | Blocked | Flag is computed by the caller from legacy runtime policy logic; classifier stays input-pure. |
| `PRE_ACTION_VISIBLE_TEXT_WITH_ACTION` | Yes | `compiler_fact` | No dedicated legacy parity kind | Blocked | Structural classification only; no dispatch or policy authority. |
| `INTENT_COMPLETE_WITH_VISIBLE_TEXT` | Yes | `compiler_fact` | No dedicated legacy parity kind | Blocked | Consumer migration remains deferred. |
| `CHECKPOINT_WITH_VISIBLE_TEXT` | Yes | `compiler_fact` | No dedicated legacy parity kind | Blocked | Board/checkpoint consumers remain on existing logic. |
| `CHECKPOINT_ONLY` | Yes | `compiler_fact` | No dedicated legacy parity kind | Blocked | Shadow-only signal; no board routing changes. |
| `PLAINTEXT_TERMINAL_ANSWER` | Yes | `compiler_fact` | Yes | Blocked | Terminal-answer correctness policy is still runtime-owned. |
| `NO_VISIBLE_TEXT` | Yes | `compiler_fact` | Indirectly | Blocked | Structural no-visible-text fallback only. |
| `UNKNOWN` | Yes | `fallback` | Indirectly | Blocked | Safe shadow fallback for all unmatched cases. |

Step 4I is complete. Any move from shadow diagnostics toward consumer migration requires a separate Phase 8 Step 4J design/review gate.

### 11.5. Shadow-Mode Validation Plan

Step 4G introduced the classifier as an isolated shadow-safe component. Step 4H wired it into the runtime for shadow execution and diagnostic logging.

1.  **Instantiation (Done in Step 4H)**: The `TerminalAnswerClassifier` is instantiated on-demand within `ResponsePipelinePrevalidationMixin`.
2.  **Execution (Done in Step 4H)**: It is called from `_apply_compiler_diagnosis` after the `RuntimeProtocolSemantics` snapshot is created. Its result is logged for diagnostic purposes and is not used for any production decisions. The call is wrapped in a `try...except` block to ensure safety.
3.  **No Behavior Change**: The result of the shadow-mode classification **must not** be used to alter control flow, dispatch decisions, UI output, or any other runtime behavior. All existing logic paths must remain unchanged.
4.  **Comparison and Logging (Step 4H / 4I)**: A dedicated logging function will be called to record the `TerminalAnswerClassifier`'s result.
    -   **Step 4H**: Logged the classifier's output as a shadow signal.
    -   **Step 4I (Part 1)**: Implemented a diagnostic helper to compute `legacy_kind` from existing legacy helpers (`looks_like_leaked_system_result`, `terminal_plaintext_completion_status`, `is_plaintext_answer_path`, etc.). The shadow log now populates `legacy_kind` and `is_match`.
    -   **Log Entry**: Each log entry now contains:
        -   `response_id`
        -   `classifier_kind`: The `kind` from the new classifier.
        -   `legacy_kind`: The classification derived from legacy logic.
        -   `is_match`: `True` if the kinds are equivalent.
        -   `classifier_evidence`: The `source`, `reason_code`, and `evidence` from the new classifier.
        -   `legacy_evidence`: The name of the legacy helper and its raw inputs (deferred).
5.  **Parity Goal**: The goal of shadow mode is to collect data and iterate on the classifier's logic (in later steps) until it achieves high parity with the legacy system for all core cases, while providing clearer, more accurate classifications for ambiguous cases.

### 11.6. Completed Step 4G Tests and Future Step 4H Tests

-   **Completed in Step 4G**:
    -   Unit tests for the `TerminalAnswerClassifier` class, testing each of the implemented compiler-fact branches in isolation (`tests/test_terminal_answer_classifier.py`).
-   **Deferred to Step 4H (or later)**:
    -   **Parity Tests**: A new test suite (`tests/test_terminal_answer_classifier_parity.py`) that runs a large set of diverse response snippets through both the legacy logic and the new classifier, asserting that the logged `is_match` field is `True` for all expected cases.
    -   **Integration Tests**: Tests to ensure the shadow-mode execution does not alter runtime behavior.

### 11.7. Explicitly Deferred

-   **Runtime Shadow Wiring/Logging**: Deferred to Step 4H.
-   **Legacy Helper Branches**: Implementation of branches that depend on legacy helpers (e.g., for `LEAKED_SYSTEM_RESULT`) is deferred until safe imports and integration can be designed.
-   **Consumer Migration**: No consumers will be migrated until shadow-mode validation is complete and a new migration phase is approved.
-   **Legacy Helper Removal**: Legacy regex helpers (`is_leaked_system_result`, etc.) will be preserved until all their consumers are migrated away.
-   **Final-Answer Correctness Policy**: The classifier provides structural classification. The runtime policy decision of whether a `PLAINTEXT_TERMINAL_ANSWER` is a *correct* final answer remains a separate, runtime-owned concern.

### 11.8. Phase 8 Step 4I Part 4 Design Gate: `INTERNAL_SUMMARY_LIKE_TEXT`

- **Status**: Complete.
- **Goal**: Integrate the `INTERNAL_SUMMARY_LIKE_TEXT` legacy rule into the `TerminalAnswerClassifier` in shadow mode.
- **Input Contract**:
    - The `TerminalAnswerClassifierInput` will be extended with a new boolean field: `is_internal_summary: bool = False`.
    - The caller (`ResponsePipelinePrevalidationMixin._run_terminal_answer_classifier_shadow`) will be responsible for computing this flag by calling the legacy helper (e.g., `ResponseSemantics._is_internal_summary_instead_of_final_answer(parsed_output)`).
    - This avoids passing `parsed_output` or other complex state into the classifier, keeping it pure with respect to its inputs.
- **Implementation Result**:
    - `TerminalAnswerClassifierInput` now carries `is_internal_summary: bool = False`.
    - `ResponsePipelinePrevalidationMixin._run_terminal_answer_classifier_shadow` computes the flag with the existing `_is_internal_summary_instead_of_final_answer(parsed_output)` helper and passes only the boolean into the classifier.
    - `TerminalAnswerClassifier.classify` returns `INTERNAL_SUMMARY_LIKE_TEXT` at priority 3 when `input.is_internal_summary` is `True`.
    - `_get_legacy_terminal_answer_kind` now includes the same internal-summary parity branch at the corresponding priority.
- **Testing**:
    - `tests/test_terminal_answer_classifier.py` covers the positive case and priority interactions with leaked-system and truncated text.
    - `tests/test_response_pipeline_prevalidation_shadow.py` verifies parity logging for the internal-summary case.
- **Forbidden Changes**:
    - The `TerminalAnswerClassifier` must not call the legacy helper directly.
    - The `TerminalAnswerClassifierInput` must not be modified to include `parsed_output`, `ResponseSemantics`, or any other stateful object.
    - The result of this classification must not affect production control flow.

## 12. Phase 8 Step 4J: Consumer Migration Design Gate

- **Status**: Complete.
- **Goal**: Review the Step 4I parity matrix and shadow-log evidence to determine if a safe, narrow consumer migration target can be proposed for a future step.
- **Conclusion**: The review is complete. The `LEAKED_SYSTEM_RESULT` classification shows high parity and is based on a pure-function, legacy-compatible rule. Its primary consumer is a simple guard in `ResponsePipelineStagesMixin`. This makes it the strongest candidate for a first, narrow, behavior-preserving migration.
- **Recommendation**: Proceed with a new design-only step, **Phase 8 Step 4K**, to formally design the migration of the `is_leaked_system_result` check in `ResponsePipelineStagesMixin` to consume the `TerminalAnswerClassifier`'s result. Implementation will be deferred to a subsequent Step 4L.

### 12.1. Migration Candidate Risk Matrix

| `TerminalAnswerKind` | Migration Risk | Rationale | Proposed Next Step |
|---|---|---|---|
| `LEAKED_SYSTEM_RESULT` | **Low** | High parity confirmed in shadow logs. Based on a simple, legacy-compatible regex rule. Consumer is a simple guard, not complex policy. | **Propose for Step 4K Design** |
| `INVALID_OR_TRUNCATED_TERMINAL_TEXT` | **Medium** | High parity, but logic is more complex (length heuristics). Consumer (`_reject_truncated_terminal_completion_before_transition`) is tied to intent completion policy. | Defer |
| `INTERNAL_SUMMARY_LIKE_TEXT` | **High** | Parity is good, but the classification depends on a caller-computed flag derived from runtime policy (`_is_internal_summary_instead_of_final_answer`). Migrating the consumer would require refactoring policy logic, which is out of scope. | Defer |
| `PLAINTEXT_TERMINAL_ANSWER` | **High** | This is a core final-answer path. While structural identification is good, migrating consumers (`IntentTransitionHandler`, `PreDispatchPipeline`) touches final-answer and stop-gate authority, which is frozen. | Defer |
| `PRE_ACTION_VISIBLE_TEXT_WITH_ACTION` | **High** | Structural fact is clear, but there is no direct legacy consumer. Creating a new behavior based on this classification is a feature change, not a migration. | Defer |
| `INTENT_COMPLETE_WITH_VISIBLE_TEXT` | **High** | Touches intent completion policy, which is a high-risk area. | Defer |
| `CHECKPOINT_WITH_VISIBLE_TEXT` | **Medium** | Consumers are board handlers. Migration is plausible but more complex than the `LEAKED_SYSTEM_RESULT` guard. | Defer |
| `CHECKPOINT_ONLY` | **Medium** | Similar to `CHECKPOINT_WITH_VISIBLE_TEXT`. | Defer |
| `NO_VISIBLE_TEXT` | **N/A** | This is a fallback case; there is no specific consumer to migrate. | Defer |

### 12.2. Next Step

The design gate (Step 4J) is complete. The next intended step is **Phase 8, Step 4K: First Consumer Migration (Design)**. This is a design-only step to plan the migration of the `is_leaked_system_result` check. Implementation is not authorized.

## 13. Phase 8 Step 4K: First Consumer Migration (Design)

- **Status**: Complete.
- **Goal**: Design the first, narrow, behavior-preserving migration of a consumer to the `TerminalAnswerClassifier`.
- **Scope**: The `is_leaked_system_result` check in `ResponsePipelineStagesMixin`.

### 13.1. Current Consumer Path

- **Consumer**: `ResponsePipelineStagesMixin._run_post_classification_stage` calls a helper that uses `semantic_accessors.is_leaked_system_result`.
- **Logic**: The helper checks if the raw response text contains a leaked `SYSTEM RESULT`.
- **Behavior**: If a leak is detected, it returns a `LoopControlDecision` to stop the loop and display a sanitized message to the user, preventing the raw tool output from being shown.
- **Data Flow**: `ResponsePipelineStagesMixin` -> `semantic_accessors.is_leaked_system_result(raw_response_text)` -> `bool`

### 13.2. Proposed Future Migration

The goal is to migrate this consumer to use the `TerminalAnswerClassifier`'s result, which is already being computed in shadow mode.

#### 13.2.1. Making the Classifier Result Available

The `TerminalAnswerClassifier` runs inside `ResponsePipelinePrevalidationMixin._run_terminal_answer_classifier_shadow`. Its result is currently only used for logging.

- **Proposed Change**: In a future implementation step (4L), the classifier result may be attached to the `parsed_output` object, but `_run_terminal_answer_classifier_shadow` should keep its current name.
- **New Field**: A new field, `terminal_answer_semantic_result: TerminalAnswerSemanticResult | None`, will be added to the `ParsedModelOutput` dataclass.
- **Population**: `_run_terminal_answer_classifier_shadow` will populate `parsed_output.terminal_answer_semantic_result` with the result from the classifier. The shadow logging will continue unchanged.

#### 13.2.2. Migrating the Consumer

- **Proposed Change**: The check in `ResponsePipelineStagesMixin._run_post_classification_stage` will be modified to read from the new field on `parsed_output`.
- **New Logic**:
  ```python
  # old
  if (
      not self.semantics.has_any_action_proposal(parsed_output, parsed_action_count)
      and is_leaked_system_result(response)
  ):
      ...

  # new
  if not self.semantics.has_any_action_proposal(parsed_output, parsed_action_count):
      typed_result = getattr(parsed_output, "terminal_answer_semantic_result", None)
      if (
          typed_result is not None
          and typed_result.kind == TerminalAnswerKind.LEAKED_SYSTEM_RESULT
      ):
          ...
      elif is_leaked_system_result(response):
          ...
  ```
- **Behavior Preservation**:
  - Step 4L must be a typed result primary signal plus legacy fallback migration.
  - It is not yet classifier sole authority.
  - Strict replacement is explicitly forbidden for Step 4L.
  - The outer guard `not self.semantics.has_any_action_proposal(parsed_output, parsed_action_count)` must remain intact.
  - The legacy accessor must remain the production fallback both when the typed result is absent and when the typed result is present but not `LEAKED_SYSTEM_RESULT`.
  - This is required because the classifier and accessor are not exact semantic equivalents today: the classifier uses a stricter prefix regex for `SYSTEM RESULT:`, the accessor uses a broader `.search(...)` pattern, and the current consumer checks raw response text.

### 13.3. Implementation Constraints (for Step 4L)

- **File Scope**: Changes are limited to:
    - `modules/agent/orchestration/shared/decision_models.py` (to add `terminal_answer_semantic_result` to `ParsedModelOutput`).
    - `modules/agent/orchestration/responses/response_pipeline_prevalidation.py` (to populate the new field).
    - `modules/agent/orchestration/responses/response_pipeline_stages.py` (to migrate the consumer).
- **No Classifier Changes**: The `TerminalAnswerClassifier` logic must not be changed.
- **Preserve Legacy Accessor**: The `semantic_accessors.is_leaked_system_result` function must not be removed, as other consumers may still use it. For Step 4L, it remains the production fallback.
- **Preserve Outer Guard**: The existing `not self.semantics.has_any_action_proposal(parsed_output, parsed_action_count)` condition must remain.
- **No Strict Replacement**: Replacing the current leaked-system-result check with typed result only is explicitly forbidden.
- **Do Not Rename Shadow Runner**: `_run_terminal_answer_classifier_shadow` should not be renamed in Step 4L.
- **No Other Migrations**: Only the `is_leaked_system_result` consumer is in scope. No other `TerminalAnswerKind` consumers should be migrated.
- **No Behavior Change**: The user-facing behavior must be identical. The change must not alter when a leaked system result is detected.

### 13.4. Safety and Rollback Plan

- **Safety Gate**: The `_run_terminal_answer_classifier_shadow` call will remain inside a `try...except` block to ensure that any unexpected failure in the classifier does not break the production pipeline.
- **Rollback**: The change is small and contained. It can be fully reverted with `git revert <commit_hash>`.
- **Fallback (Required)**: The implementation must include a fallback to the old logic when the typed result is absent and when it is present but not `LEAKED_SYSTEM_RESULT`.

### 13.5. Test Plan (for Step 4L)

1.  **Unit Tests**:
    -   Update `tests/test_response_pipeline_stages.py` to verify that the stage correctly handles the `LEAKED_SYSTEM_RESULT` kind from `parsed_output.terminal_answer_semantic_result` as the primary signal.
    -   Add a test that proves the outer `has_any_action_proposal` guard is still required.
    -   Add a test that proves the legacy accessor still triggers when the typed result is absent.
    -   Add a test that proves the legacy accessor still triggers when the typed result is present but not `LEAKED_SYSTEM_RESULT`.
2.  **Integration Tests**:
    -   Add a new integration test in a suitable location (e.g., `tests/test_response_pipeline.py`) that provides a response with a leaked system result and asserts that the pipeline correctly identifies it and produces the expected `LoopControlDecision`.
3.  **Parity Verification**:
    -   Manually inspect shadow logs after deployment to confirm that `is_match` remains `True` for the `LEAKED_SYSTEM_RESULT` classification path.
    -   Update `tests/test_response_pipeline_prevalidation_shadow.py` to assert that the `legacy_kind` and `classifier_kind` match for this case, formalizing the parity check.

### 13.6. Closure

Step 4K is complete, and the Step 4L implementation has now been completed.

- The migrated consumer is the leaked-system-result guard in `ResponsePipelineStagesMixin`.
- The implementation uses the typed `TerminalAnswerClassifier` result as the primary signal.
- The legacy `is_leaked_system_result(response)` accessor remains the production fallback.
- The fallback applies both when the typed result is absent and when it is present but not `LEAKED_SYSTEM_RESULT`.
- The outer `has_any_action_proposal(...)` guard remains in place.
- `_run_terminal_answer_classifier_shadow` was not renamed.
- No other consumers were migrated.
- `TerminalAnswerClassifier` is still not sole authority.
- Production behavior is intended to remain equivalent.
- Tests passed.

## 14. Phase 8 Step 4M: Terminal Answer Consumer Migration Batch Plan

- **Status**: Complete.
- **Goal**: Inventory the remaining terminal-answer legacy consumers, rank them, and define a safe batch plan for future migrations.
- **Scope**: Design-only planning for the remaining terminal-answer consumer migrations.
- **Allowed**: Documentation updates, ranking, and migration-sequence planning.
- **Forbidden**:
  - Fallback removal
  - Consumer migration
  - Production behavior changes
- **Review Focus**:
  - Inventory all remaining terminal-answer-related legacy consumers.
  - Rank them by bug impact, migration risk, classifier readiness, and policy/authority risk.
  - Propose an ordered migration sequence that keeps each migration narrow and behavior-preserving.
- **Conclusion**:
  - The Terminal Answers slice should remain open.
  - Legacy terminal-answer consumers are still a recurring bug source.
  - `TerminalAnswerClassifier` is not policy authority.
  - `TerminalAnswerClassifier` is not stop-gate authority.
  - Legacy fallback remains required unless exact semantic parity is proven.

### 14.1. Remaining Consumer Inventory

| Consumer / area | Target kind(s) | Bug impact | Migration risk | Classifier readiness | Policy / authority risk | Recommendation |
|---|---|---|---|---|---|---|
| `ResponsePipelinePrevalidationMixin._reject_truncated_terminal_completion_before_transition` | `INVALID_OR_TRUNCATED_TERMINAL_TEXT` | High | Medium | High | Medium | First post-4L migration candidate |
| Output-recovery internal-summary handling | `INTERNAL_SUMMARY_LIKE_TEXT` | Medium | Medium | Medium | High | Second migration slice; design separately |
| Final-answer / plaintext-answer path | `PLAINTEXT_TERMINAL_ANSWER` | High | High | Medium | High | Defer pending separate preflight |
| Board/checkpoint handlers | `CHECKPOINT_WITH_VISIBLE_TEXT`, `CHECKPOINT_ONLY` | Medium | Medium | Medium | Medium | Defer to a separate board/checkpoint slice |

### 14.2. Ordered Migration Sequence

1. `Phase 8 Step 4M.1`: `INVALID_OR_TRUNCATED_TERMINAL_TEXT` consumer migration design
2. `Phase 8 Step 4M.2`: `INVALID_OR_TRUNCATED_TERMINAL_TEXT` implementation
3. `Phase 8 Step 4N.1`: `INTERNAL_SUMMARY_LIKE_TEXT` consumer migration design
4. `Phase 8 Step 4N.2`: `INTERNAL_SUMMARY_LIKE_TEXT` implementation
5. Later: `PLAINTEXT_TERMINAL_ANSWER` / final-answer path only after separate preflight
6. Checkpoint/board consumers deferred to a separate board/checkpoint slice

## 15. Phase 8 Step 4M.1: `INVALID_OR_TRUNCATED_TERMINAL_TEXT` Consumer Migration Design

- **Status**: Complete.
- **Target consumer**:
  `ResponsePipelinePrevalidationMixin._reject_truncated_terminal_completion_before_transition`

### 15.1. Current Consumer Path

- The current guard is in
  `ResponsePipelinePrevalidationMixin._reject_truncated_terminal_completion_before_transition`.
- It only runs when `step.intent_payload` is a dict with `mode == "complete"`.
- It currently calls `terminal_plaintext_completion_status(raw_response)`.
- If the helper reports invalid/truncated terminal plaintext, the guard:
  - clears terminal plaintext completion state
  - logs `reason="truncated_terminal_plaintext_answer"` and `source="intent_completion_atomicity_guard"`
  - returns `ResponsePipelineOutcome.continue_with(...)` using `_terminal_completion_recovery_prompt(...)`

### 15.2. Classifier Readiness

- `TerminalAnswerClassifier` already classifies `INVALID_OR_TRUNCATED_TERMINAL_TEXT`.
- It uses:
  - `runtime_semantics`
  - `raw_response_text`
  - `candidate_text = visible_text or raw_response_text`
- The rule currently applies only when `visible_text_source == "PURE_PLAINTEXT"` and the text is not a complete leaked-system marker.
- After Step 4L, the classifier result is already attached to `ParsedModelOutput` as `terminal_answer_semantic_result`.
- The classifier runs early enough for this consumer family because it is executed during `_apply_compiler_diagnosis(...)`.

### 15.3. Parity / Risk Analysis

- The classifier and the legacy guard both depend on `terminal_plaintext_completion_status(...)`.
- However, they are not exact equivalents:
  - the legacy consumer evaluates the helper on `raw_response`
  - the classifier evaluates the helper on `candidate_text`
  - the classifier also scopes this branch to `PURE_PLAINTEXT`
- Because of this mismatch, legacy fallback is required for Step 4M.2.
- Additional risk:
  this consumer sits inside an intent-completion policy path, so preconditions around `intent_payload.mode == "complete"` must remain unchanged.

### 15.4. Proposed Step 4M.2 Shape

- Migrate only the existing truncated-terminal-answer guard.
- Preserve all current intent-completion preconditions.
- Use typed `INVALID_OR_TRUNCATED_TERMINAL_TEXT` as the primary hint if available.
- Always confirm the final rejection decision with `terminal_plaintext_completion_status(raw_response)`.
- Keep the legacy helper path when:
  - the typed result is absent, or
  - the typed result is present but not `INVALID_OR_TRUNCATED_TERMINAL_TEXT`
- Preserve:
  - terminal completion state clearing
  - recovery prompt behavior
  - logging fields
  - `reason`
  - `source`
- No stop-gate or final-answer authority change.
- No migration of any other consumer.

### 15.5. Required Tests For Step 4M.2

- typed result path
- legacy fallback when typed result is absent
- legacy fallback when typed result differs
- existing `intent_payload.mode == "complete"` precondition preserved
- no-behavior-change cases for valid completion

## 16. Phase 8 Step 4M.2: `INVALID_OR_TRUNCATED_TERMINAL_TEXT` Consumer Migration Implementation

- **Status**: Complete.
- **Outcome**:
  - Migrated consumer:
    `ResponsePipelinePrevalidationMixin._reject_truncated_terminal_completion_before_transition`
  - Typed `INVALID_OR_TRUNCATED_TERMINAL_TEXT` is the primary hint for this guard.
  - Legacy `terminal_plaintext_completion_status(raw_response)` remains the production confirmation/fallback path.
  - The legacy path still governs the actual rejection decision.
  - Existing `intent_payload.mode == "complete"` precondition is preserved.
  - Existing recovery behavior is preserved:
    terminal completion state clearing, recovery prompt behavior, logging fields, `reason`, and `source`.
  - No stop-gate or final-answer authority change.
  - No other consumers were migrated.
  - Tests passed.

## 17. Phase 8 Step 4N.1: `INTERNAL_SUMMARY_LIKE_TEXT` Consumer Migration Design

- **Status**: Complete.
- **Target consumer**:
  output-recovery routing for `internal_summary_instead_of_final_answer`

### 17.1. Current Consumer Path

- The current consumer is in `OutputRecoveryRoutingMixin.decide(...)`.
- It uses `_is_internal_summary_instead_of_final_answer(parsed_output)` as
  runtime-policy logic.
- If no earlier invalid kind has already been selected and the helper returns
  `True`, the routing sets
  `invalid_kind = "internal_summary_instead_of_final_answer"`.
- The recovery branch then:
  - logs `reason="internal_summary_instead_of_final_answer"`
  - returns `OutputRecoveryDecision.continue_with(...)`
  - uses `build_internal_summary_instead_of_final_answer_prompt()`
  - preserves `source="output_recovery"`

### 17.2. Classifier Readiness

- `TerminalAnswerClassifier` already classifies `INTERNAL_SUMMARY_LIKE_TEXT`.
- It does so when `TerminalAnswerClassifierInput.is_internal_summary` is `True`.
- That flag is already computed in
  `ResponsePipelinePrevalidationMixin._run_terminal_answer_classifier_shadow(...)`
  by calling the existing helper
  `_is_internal_summary_instead_of_final_answer(parsed_output)`.
- After classification, the typed result is already attached to
  `ParsedModelOutput`, so this consumer can read it without reclassifying.

### 17.3. Parity / Risk Analysis

- The typed result and the legacy consumer already depend on the same helper.
- Even so, exact consumer parity is not yet proven because:
  - this is runtime-policy logic, not a structural compiler fact
  - the branch is embedded in invalid-kind routing and ordering
  - earlier invalid kinds may still take precedence
- Because of that, typed `INTERNAL_SUMMARY_LIKE_TEXT` can only be a primary hint
  for Step 4N.2.
- The existing helper remains the confirmation/fallback path unless exact parity
  is proven.

### 17.4. Proposed Step 4N.2 Shape

- Migrate only the current internal-summary recovery consumer.
- Preserve the existing invalid-kind ordering in output recovery.
- Use typed `INTERNAL_SUMMARY_LIKE_TEXT` as a primary hint only.
- Keep `_is_internal_summary_instead_of_final_answer(parsed_output)` as the
  confirmation/fallback path.
- Preserve current recovery behavior, `reason`, `source`, logging, and prompt.
- No stop-gate or final-answer authority change.
- No migration of any other consumer.

### 17.5. Required Tests For Step 4N.2

- typed result path with legacy confirmation
- typed result alone must not expand behavior if parity is not exact
- fallback when typed result is absent
- fallback when typed result differs
- current non-summary cases pass through unchanged

## 18. Phase 8 Step 4N.2: `INTERNAL_SUMMARY_LIKE_TEXT` Consumer Migration Implementation

- **Status**: Complete.
- **Outcome**:
  - Migrated consumer:
    internal-summary recovery in `OutputRecoveryRoutingMixin.decide(...)`
  - Typed `INTERNAL_SUMMARY_LIKE_TEXT` is a primary hint only.
  - `_is_internal_summary_instead_of_final_answer(parsed_output)` remains the confirmation/fallback path.
  - Typed result alone does not create a new recovery decision.
  - Existing invalid-kind ordering and earlier invalid-kind precedence are preserved.
  - Existing recovery behavior is preserved:
    `invalid_kind="internal_summary_instead_of_final_answer"`,
    `reason="internal_summary_instead_of_final_answer"`,
    `source="output_recovery"`,
    `build_internal_summary_instead_of_final_answer_prompt()`,
    and existing logging behavior.
  - No stop-gate or final-answer authority change.
  - No other consumers were migrated.
  - Tests passed.

## 19. Explicitly Deferred

- A full refactor of `ResponsePipeline` or `DispatchPipeline`.
- Changes to `ActionPolicy`.
- Changes to the `get_visible_text` accessor. Its role will be re-evaluated after characterization tests clarify whether it should be kept, wrap a new classifier, or be superseded.
- The `history.py` refactor.
