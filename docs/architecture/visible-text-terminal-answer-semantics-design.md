# Phase 8 Design: Visible Text & Terminal Answer Semantics

- **Phase 8 Status**: Design Started

## 1. Purpose and Guiding Principles

This document will define the design for clarifying the authority and implementation of visible text and terminal answer semantics.

The primary goal is to resolve the overlapping and sometimes conflicting classifications for responses that contain a final, user-visible answer, especially when combined with other protocol elements like memory checkpoints or intent completions.

- **Clarify Authority**: Establish a single source of truth for what constitutes a terminal answer.
- **Improve Testability**: Create a dedicated, testable component for classifying terminal answer states.
- **Strict Behavior Preservation**: Any refactoring must preserve the exact legacy behavior for final answer routing, display, and recovery.

## 2. Current Behavior Inventory (Step 1)

The first step of this phase is to create a detailed inventory of all components that currently participate in visible text or terminal answer logic. This includes:

- `ResponsePipelinePrevalidationMixin` (`_reject_truncated_terminal_completion_before_transition`)
- `IntentTransitionHandler` (plaintext completion logic)
- `PlanBoardStageHandler` (`plan_checkpoint_and_text` logic)
- `MemoryBoardStageHandler` (`memory_checkpoint_and_text` logic)
- `ResponsePipelineStagesMixin` (dispatch routing for `memory_checkpoint_and_text`)
- `DispatchOutcomeHandler` (`_extract_visible_text`, `_strip_leaked_system_results_from_ui_text`)
- `PreDispatchPipeline` (`terminal_plaintext_completion` stop logic)
- `RuntimeProtocolSemantics` (`MEMORY_TEXT` vs. `PLAINTEXT_ONLY` shapes)

## 3. Implementation Slicing

Implementation is not authorized until a full design is approved.
