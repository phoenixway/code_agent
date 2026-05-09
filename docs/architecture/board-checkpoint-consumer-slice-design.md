# Phase 10 Design: Board/Checkpoint Consumer Slice

- **Phase 10 Status**: Step 6 Implementation Complete.
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
3.  **Phase 10 Step 3: Pipeline Reordering Design**: A **design-only** step to create a detailed, risk-mitigated plan for making compiler facts available before the checkpoint stage.
4.  **Phase 10 Step 4: Pure Structural Diagnosis Extraction + Early Prepass**: Add a side-effect-free compiler prepass before the checkpoint stage without changing runtime behavior.
5.  **Phase 10 Step 4B: Structural Prepass Parity / Reuse Decision**: Confirm that classification-stage reuse remains a no-go while raw-vs-normalized parity is unproven.
6.  **Phase 10 Step 5: First Board/Checkpoint Consumer Migration (Design)**: Choose the first narrow consumer slice that can use prepass facts without changing board authority.

### 3.2. Step 2: Characterization Test Outcome

- Orchestration characterization tests have been added to `tests/test_response_pipeline_stages.py`.
- These tests lock down the orchestration logic within `_run_checkpoint_stage`, covering how it handles decisions from mocked board stage handlers (e.g., `memory_checkpoint_only`, `memory_checkpoint_and_text`).
- This provides a safety net for the upcoming pipeline reordering design.
- The internal parsing and commit logic of the board handlers themselves is not yet characterized, as their direct migration is blocked by the pipeline order.

### 3.3. Step 3: Pipeline Reordering Design

This design step is complete. It analyzed options for making compiler-derived facts available to the board/checkpoint stage.

#### 3.4.1. Design Options

1.  **Option A: Full Pipeline Reordering**: Move the entire `_run_classification_stage` to execute before `_run_checkpoint_stage`.
    -   **Risk**: High. This would alter the `response` text received by the legacy board handlers due to normalization steps inside `_run_classification_stage`, likely causing behavior drift.

2.  **Option B: Early Structural Diagnosis Prepass (Chosen)**: Introduce a new, minimal prepass stage before `_run_checkpoint_stage`.
    -   **Description**: This prepass will use a new, side-effect-minimal helper to run the compiler on the raw response. It will compute the `CompilerAnalysis`, `ResponseIR`, and `RuntimeProtocolSemantics` and attach them to a preliminary `ParsedModelOutput` object. This prepass must *not* have side effects like running the `TerminalAnswerClassifier` or mutating `invalid_kind`. The full `_run_classification_stage` will still run in its current position. Reuse of the pre-computed analysis is deferred until parity can be proven.
    -   **Risk**: Low. This is an additive change that makes the required data available without changing the inputs or behavior of any existing stage.

#### 3.4.2. Chosen Design

The chosen design is **Option B**. It is the safest path forward, as it avoids the risks of a full pipeline reordering while still unblocking the board handler migration.

- **Implementation Plan (for Step 4)**:
    1. A new internal, side-effect-free helper will be extracted from `_apply_compiler_diagnosis`. This pure helper will be responsible only for computing `CompilerAnalysis`, `ResponseIR`, and `RuntimeProtocolSemantics`.
    2. A new prepass will be added before `_run_checkpoint_stage` that calls the new pure helper.
    3. The resulting structural facts will be passed to the checkpoint stage for future use.
    4. `_run_classification_stage` will continue to call the existing effectful `_apply_compiler_diagnosis` path to preserve existing behavior. Reusing pre-computed facts is deferred unless proven safe by tests.
- **Behavioral Guarantees**:
    - This change will be behavior-preserving.
    - The new pure helper must not have side effects.
    - The early prepass must only call the pure helper.
    - The board handlers will not be migrated in Step 4; they will ignore the new data.
    - No user-visible behavior, dispatch logic, or policy will change.

### 3.4. Step 4: Implementation Correction

- Step 4 did **not** refactor `_apply_compiler_diagnosis` into a wrapper around the pure helper.
- The implemented change was narrower:
  - `_run_structural_diagnosis_prepass(response)` was added.
  - It is side-effect-free and only calls `protocol_compiler.analyze(response)`.
  - `_run_checkpoint_stage(...)` calls the prepass before board handlers.
  - `CheckpointStageState.compiler_analysis` carries that prepass result.
  - `_apply_compiler_diagnosis` remains the existing effectful classification-stage path and recomputes analysis on normalized response.

### 3.5. Step 4B: Structural Prepass Parity / Reuse Decision

This design-only step is complete. It analyzed whether it is safe for the classification stage to reuse the compiler analysis from the prepass.

- **Analysis**:
    - The prepass runs on the **raw response**.
    - The classification stage runs on the **normalized response** (after `_normalize_response_stage`).
    - Because normalization can change the response text (e.g., via think-tag autorepair), the compiler analysis from the prepass may not be equivalent to the analysis that would be performed on the normalized text.
- **Conclusion**: **NO-GO** for reuse at this time. Reusing the prepass analysis could introduce subtle behavior drift.
- **Decision**:
    - The prepass analysis attached to `CheckpointStageState` remains **observational only**.
    - `_run_classification_stage` will continue to recompute its own compiler diagnosis on the normalized response to ensure behavior preservation.
    - The next step is to design the first consumer migration, which can use the observational prepass data as a secondary signal or for logging.

### 3.6. Step 5: First Board/Checkpoint Consumer Migration (Design)

- **Design Conclusion**: The first safe migration is a **checkpoint structural parity logging bridge**, not a board handler authority transfer.

#### 3.6.1. Current Consumer Roles

| Consumer | Current role | Current authority |
|---|---|---|
| `MemoryBoardStageHandler` | Parses memory/checkpoint material, commits memory updates, decides `memory_checkpoint_only` / `memory_checkpoint_and_text` / `memory_checkpoint_and_action`. | Authoritative |
| `PlanBoardStageHandler` | Parses subgoal mutations, commits planner updates, decides `plan_checkpoint_only` / `plan_checkpoint_and_text` / `plan_checkpoint_and_action`. | Authoritative |
| `_run_checkpoint_stage` | Orchestrates plan-board then memory-board handling and downstream checkpoint-only continuation behavior. | Authoritative orchestration |
| `_run_post_classification_stage` | Consumes checkpoint flags already decided upstream. | Dependent on handler flags |
| `ResponseSemantics` checkpoint helpers | Regex-based structural observations. | Legacy structural helper only |

#### 3.6.2. Chosen First Migration Target

- **Target**: prepass-vs-legacy board/checkpoint structural parity logging in or near `_run_checkpoint_stage`.
- **Why this target is safest**:
  - It uses the newly available `CheckpointStageState.compiler_analysis` without changing board commits.
  - It does not depend on classification-stage reuse.
  - It does not change dispatch, stop-gates, prompts, or board continuation behavior.
  - It produces the evidence needed before any future authority transfer.

#### 3.6.3. Migration Shape for Step 6

- Add observational parity logging for facts such as:
  - compiler/prepass has checkpoint tags
  - compiler/prepass has memory tags
  - compiler/prepass has subgoal tags
  - compiler/prepass has checkpoint marker
  - compiler/prepass action presence
  - legacy handler outcome category:
    - checkpoint only
    - checkpoint and text
    - checkpoint and action
- Logging must be diagnostic-only.
- Legacy handler outcomes remain the source of truth.

#### 3.6.4. No-Go Items

- No direct replacement of handler parsing or commit logic.
- No prepass-driven mutation of checkpoint flags.
- No reuse of prepass analysis in `_run_classification_stage`.
- No board/checkpoint semantic authority model yet.
- No dispatch, final-answer, stop-gate, `ActionPolicy`, parser, or `history.py` changes.

#### 3.6.5. Dedicated Model Decision

- A dedicated board/checkpoint semantic model is **deferred**.
- It is not needed for the first migration because the first migration is logging/parity only.
- Revisit only after parity data exists and handler commit semantics are better characterized.

#### 3.6.6. Characterization Required Before Later Authority Transfer

- Direct tests of board handler parsing and commit behavior.
- Tests for mismatch scenarios between raw-response prepass facts and cleaned-response handler decisions.
- Tests proving any future consumer narrowing does not alter:
  - board commits
  - checkpoint-only continuation prompts
  - checkpoint-with-text pass-through
  - checkpoint-with-action pass-through

### 3.7. Step 6: Board/Checkpoint Structural Parity Logging Implementation

- **Implementation Outcome**:
  - Diagnostic-only parity logging is now attached to `_run_checkpoint_stage`.
  - The parity bridge compares the early prepass compiler analysis in `CheckpointStageState.compiler_analysis` against legacy board/checkpoint handler outcomes.
  - Logged fields include compiler/prepass shape, compiler/prepass error code, visible-text source when available, action presence/count, checkpoint-like structural facts, legacy plan/memory checkpoint categories, parity alignment, and mismatch reason when obvious.
  - Logging is defensive:
    - missing or malformed compiler analysis is tolerated
    - logging failures are swallowed
    - runtime behavior is unchanged
- **Authority Boundary**:
  - `MemoryBoardStageHandler` and `PlanBoardStageHandler` remain authoritative.
  - The parity bridge is diagnostic-only and does not mutate checkpoint flags or board decisions.
  - `_run_classification_stage` still recomputes compiler diagnosis on normalized response and does not reuse prepass analysis.

### 3.8. Next Intended Step

The next step is **Phase 10 Step 7: Board/Checkpoint Parity Review / First Authority Migration Decision**.
