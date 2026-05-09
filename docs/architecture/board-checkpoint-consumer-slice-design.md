# Phase 10 Design: Board/Checkpoint Consumer Slice

- **Phase 10 Status**: Step 1 Preflight Complete.
- **Scope**: Board and checkpoint-related response semantics.
- **Non-Goals**:
  - No dispatch behavior changes.
  - No final-answer or stop-gate migration.
  - No `ActionPolicy` changes.
  - No runtime behavior change in this step.

## 1. Goal

This phase aims to migrate the legacy, regex-based logic for handling board and checkpoint tags (`<fact>`, `<subgoal>`, `<memory_update_done />`, etc.) to use compiler-derived structural facts (e.g., from `RuntimeProtocolSemantics`) and other typed semantic results.

## 2. Step 1: Preflight and Consumer Inventory

This preflight step inventoried the current consumers of board/checkpoint semantics.

### 2.1. Consumer Inventory

| Component | Current Source(s) | Semantic Meaning | Authority Type | Migration Blocker |
|---|---|---|---|---|
| **`MemoryBoardStageHandler`** | Regex on raw response | Extracts and commits memory board updates (`<fact>`, `<finding>`, etc.). | Board Policy | **Pipeline Order**: Runs before classification stage; cannot access typed semantic results. |
| **`PlanBoardStageHandler`** | Regex on raw response | Extracts and commits plan board updates (`<subgoal>`). | Board Policy | **Pipeline Order**: Runs before classification stage; cannot access typed semantic results. |
| **`ResponsePipelineStagesMixin._run_checkpoint_stage`** | `MemoryBoardStageHandler` and `PlanBoardStageHandler` decisions. | Orchestrates board stages and routes based on outcomes like `memory_checkpoint_only`. | Orchestration Policy | Depends on board handlers. |
| **`ResponsePipelineStagesMixin._run_post_classification_stage`** | `memory_checkpoint_and_text` flag. | Dispatches responses containing both a checkpoint and visible text. | Dispatch Routing | Depends on board handlers. |
| **`ResponseSemantics`** | Regex helpers (`has_checkpoint_tags`, `has_memory_update_done`, etc.). | Legacy structural classification. | Structural (Legacy) | N/A (provides helpers, not a direct consumer). |
| **`TerminalAnswerClassifier`** | `RuntimeProtocolSemantics` (compiler facts). | Classifies `CHECKPOINT_ONLY` and `CHECKPOINT_WITH_VISIBLE_TEXT`. | Structural (Shadow) | N/A (producer, not consumer). |

### 2.2. Preflight Analysis

The key finding of this preflight is a **major architectural blocker**:

- The `ResponsePipeline` executes the board/checkpoint stage (`_run_checkpoint_stage`) **before** the main classification stage (`_run_classification_stage`).
- Typed semantic results (e.g., from `TerminalAnswerClassifier`) and other post-classification runtime facts are computed during or after the classification stage.
- Therefore, the primary consumers (`MemoryBoardStageHandler`, `PlanBoardStageHandler`) **cannot access these typed semantic results** because they have not been computed yet.

A direct migration of these consumers to use compiler-derived facts and typed semantics is impossible without reordering the response pipeline. Reordering the pipeline is a high-risk operation that requires its own dedicated design and characterization test phase.

Board handlers are responsible for committing board updates, which is a separate concern from terminal answer classification. While the `TerminalAnswerClassifier` provides some relevant structural facts (e.g., `CHECKPOINT_WITH_VISIBLE_TEXT`), the primary migration target for board handlers should be the underlying compiler-derived structural facts from `RuntimeProtocolSemantics` and a future dedicated checkpoint semantic model, not a dependency on terminal answer policy.

### 2.3. Risk Analysis

| Risk | Level | Mitigation |
|---|---|---|
| **Pipeline Reordering** | **High** | A dedicated design phase (`Step 3`) and comprehensive characterization tests (`Step 2`) are required before attempting to reorder the pipeline. |
| **Missing Characterization** | **High** | The exact behavior of `MemoryBoardStageHandler` and `PlanBoardStageHandler`, including their regex patterns and commit logic, is not fully locked down by tests. | Add comprehensive characterization tests in `Step 2`. |
| **Behavioral Regression** | **High** | Changing the pipeline order or board handler logic could have unintended consequences for memory updates, plan execution, and loop control. | Defer all implementation until risks are mitigated by tests and a new design. |

## 3. Preflight Conclusion and Recommendation

- **Conclusion**: **NO-GO** for an immediate consumer migration. The pipeline architecture presents a fundamental blocker.
- **Recommendation**: The board/checkpoint consumer migration slice must be broken down into smaller, safer steps.

### 3.1. Proposed Phase 10 Sequence

1.  **Phase 10 Step 1: Preflight (Done)**: This analysis.
2.  **Phase 10 Step 2: Board/Checkpoint Characterization Tests**: A **tests-only** step to add orchestration characterization tests that lock down the behavior of `_run_checkpoint_stage` and its interaction with mocked board handlers.
3.  **Phase 10 Step 3: Pipeline Reordering Design**: A **design-only** step to create a detailed, risk-mitigated plan for reordering the `ResponsePipeline` to run classification before the checkpoint stage.
4.  **Phase 10 Step 4: Pipeline Reordering Implementation**: Implement the approved reordering plan.
5.  **Phase 10 Step 5: First Board/Checkpoint Consumer Migration**: With the pipeline reordered, the first narrow consumer migration can be designed and implemented.

### 3.2. Next Intended Step

The next step is **Phase 10 Step 3: Pipeline Reordering Design**. This is a design-only step. No production code changes are authorized.

### 3.3. Step 2: Characterization Test Outcome

- Orchestration characterization tests have been added to `tests/test_response_pipeline_stages.py`.
- These tests lock down the orchestration logic within `_run_checkpoint_stage`, covering how it handles decisions from mocked board stage handlers (e.g., `memory_checkpoint_only`, `memory_checkpoint_and_text`).
- This provides a safety net for the upcoming pipeline reordering design.
- The internal parsing and commit logic of the board handlers themselves is not yet characterized, as their direct migration is blocked by the pipeline order.
