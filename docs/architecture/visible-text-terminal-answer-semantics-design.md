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
- **Step 3A: Typed Model Scaffolding (Implementation)**: Create the `TerminalAnswerKind` enum and `TerminalAnswerSemanticResult` dataclass. This is a scaffolding-only step.
- **Step 4: Classifier Implementation (Shadow Mode)**: Implement the `TerminalAnswerClassifier` and run it in shadow mode, logging its classifications against legacy decisions without changing behavior.
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
The design is approved for **Phase 8, Step 3A: Typed Model Scaffolding (Implementation)**. This is a narrow, scaffolding-only step.

**Implementation is NOT authorized for the classifier itself or for any consumer migration.** The `TerminalAnswerClassifier` remains a candidate only.

## 7. Explicitly Deferred

- A full refactor of `ResponsePipeline` or `DispatchPipeline`.
- Changes to `ActionPolicy`.
- Changes to the `get_visible_text` accessor. Its role will be re-evaluated after characterization tests clarify whether it should be kept, wrap a new classifier, or be superseded.
- The `history.py` refactor.
