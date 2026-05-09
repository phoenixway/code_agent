# Phase 10 Design: Board/Checkpoint Consumer Slice

- **Phase 10 Status**: Step 10 Skeleton + Shadow Population Complete.
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

### 3.8. Step 7: Board/Checkpoint Parity Review / First Authority Migration Decision

- **Review Conclusion**: **NO-GO** for a first authority migration at this time.

#### 3.8.1. Why authority migration is still blocked

- The Step 6 parity bridge is useful observability, but it does not yet prove authority parity.
- The compiler/prepass side reports structural facts on the raw response.
- The board handlers decide outcomes after their own parsing, stripping, and commit-oriented cleanup paths.
- `MemoryBoardStageHandler` still contains meaningful authority logic beyond tag detection:
  - memory-engine commit application
  - `clean_text` handling
  - marker-only continuation behavior
  - raw-vs-clean visible-text fallback
  - checkpoint-only streak behavior
- `PlanBoardStageHandler` still contains meaningful authority logic beyond structural recognition:
  - planner extraction and mutation application
  - raw-vs-clean action detection
  - visible-text stripping and follow-up routing
- Because of that, mismatch reasons from Step 6 must be treated as **diagnostic hints only**, not authoritative proof that compiler facts can replace handler parsing or commits.

#### 3.8.2. Safe migration decision

- **No-go items remain**:
  - no replacement of handler parsing
  - no replacement of handler commit logic
  - no prepass-driven checkpoint flag decisions
  - no classification-stage reuse of prepass analysis
- The parity bridge remains diagnostic-only.
- Legacy board handlers remain authoritative.
- Compiler/prepass facts remain structural-only observations.

#### 3.8.3. Additional characterization required before any authority transfer

- Direct tests for `MemoryBoardStageHandler` parsing/commit behavior:
  - accepted/rejected memory mutations
  - `clean_text` dependence
  - raw-vs-clean visible-text fallback
  - marker-only checkpoint behavior
  - checkpoint-only streak behavior
- Direct tests for `PlanBoardStageHandler` parsing/commit behavior:
  - planner extraction outcomes
  - action preservation
  - visible-text stripping outcomes
  - checkpoint-only vs checkpoint-with-text decisions
- Mismatch characterization between:
  - raw-response prepass structural facts
  - handler-local cleaned response / commit-aware outputs

### 3.9. Step 8: Direct Board Handler Parsing/Commit Characterization Tests

- **Test Outcome**:
  - Direct unit-level characterization now exists for both `MemoryBoardStageHandler` and `PlanBoardStageHandler`.
  - The tests lock down:
    - accepted memory mutations
    - rejected/no-op memory mutation behavior
    - `clean_text` dependence
    - raw-vs-clean visible-text fallback
    - marker-only checkpoint behavior
    - checkpoint-only vs checkpoint-with-text decisions
    - checkpoint-with-action decisions
    - planner unavailable / extract-error / no-op plan-update cases
    - plan visible-text and action detection behavior
    - plan summary print side effects
- **Surprising current behavior recorded by tests**:
  - `MemoryBoardStageHandler.apply()` resets the local checkpoint-only streak before incrementing it again, so the handler-local streak does not accumulate across calls by itself.
  - This is now treated as current behavior, not a target behavior change.
- **Authority boundary unchanged**:
  - Legacy board handlers remain authoritative.
  - Compiler/prepass facts remain structural-only observations.
  - The Step 6 parity bridge remains diagnostic-only.

### 3.10. Step 9: Board/Checkpoint Semantic Model Design

- **Design Goal**:
  - Introduce the smallest typed semantic model that can describe current board/checkpoint outcomes without transferring authority.
  - The model is observational only. It must not decide policy, replace commits, mutate checkpoint flags, or drive routing in its first implementation.

#### 3.10.1. Proposed Model

- **Working name**: `BoardCheckpointSemanticResult`
- **Companion enums / helper types**:
  - `BoardCheckpointKind`
  - `BoardCheckpointSource`
  - `BoardCheckpointEvidence`

#### 3.10.2. Proposed `BoardCheckpointKind`

- `NONE`
- `MEMORY_CHECKPOINT_ONLY`
- `MEMORY_CHECKPOINT_WITH_TEXT`
- `MEMORY_CHECKPOINT_WITH_ACTION`
- `PLAN_CHECKPOINT_ONLY`
- `PLAN_CHECKPOINT_WITH_TEXT`
- `PLAN_CHECKPOINT_WITH_ACTION`
- `MIXED_BOARD_CHECKPOINT`
- `UNKNOWN`

#### 3.10.3. Proposed `BoardCheckpointSource`

- `legacy_handler_outcome`
- `compiler_prepass_fact`
- `combined_shadow`
- `fallback`

#### 3.10.4. Proposed Result Fields

- `kind`
- `source`
- `reason_code`
- `evidence`
- `has_visible_text`
- `has_action`
- `clean_text_present`
- `raw_text_present`
- `legacy_plan_outcome`
- `legacy_memory_outcome`
- `compiler_shape`
- `compiler_error_code`
- `compiler_recovery_id`
- `compiler_has_checkpoint`
- `compiler_has_memory_tags`
- `compiler_has_subgoal_tags`
- `compiler_has_memory_checkpoint`
- `compiler_visible_text_source`
- `parity_available`
- `parity_aligned`
- `parity_mismatch_reason`

#### 3.10.5. Model Semantics

- The model must describe both:
  - legacy handler outcomes
  - structural compiler/prepass facts
- The model must not flatten those into fake authority.
- In particular:
  - legacy memory outcome remains the authoritative description of what the memory handler decided
  - legacy plan outcome remains the authoritative description of what the plan handler decided
  - compiler/prepass fields remain structural observations attached for comparison and future migration planning

#### 3.10.6. Authority Boundaries

- `BoardCheckpointSemanticResult` is **not**:
  - commit authority
  - planner mutation authority
  - memory-engine authority
  - checkpoint routing authority
  - dispatch authority
  - final-answer or stop-gate authority
- It must not:
  - replace memory-engine commit results
  - replace planner mutation results
  - mutate checkpoint flags
  - drive routing in its first implementation

#### 3.10.7. Why this is the smallest safe model

- It matches the current split architecture:
  - handler-local commit-aware outcomes
  - compiler/prepass structural observations
- It avoids pretending structural facts are policy.
- It gives a stable typed surface for later shadow population and parity review before any authority migration.

### 3.11. Next Intended Step

### 3.11. Step 10: Board/Checkpoint Semantic Model Skeleton + Shadow Population

- **Implementation Outcome**:
  - A new observational typed model now exists in `modules/agent/orchestration/responses/board_checkpoint_models.py`.
  - The model includes:
    - `BoardCheckpointKind`
    - `BoardCheckpointSource`
    - `BoardCheckpointSemanticResult`
  - `ResponsePipelineStagesMixin._run_checkpoint_stage(...)` now populates a `BoardCheckpointSemanticResult` after legacy handler outcomes are known.
  - The populated result is attached to `CheckpointStageState.board_checkpoint_semantic_result`.
  - Population uses:
    - legacy plan-board outcome category
    - legacy memory-board outcome category
    - early structural prepass compiler facts from `CheckpointStageState.compiler_analysis`
  - Missing compiler/prepass analysis is handled defensively with safe fallback fields.
- **Behavior boundary**:
  - This model is observational only.
  - It does not change checkpoint routing.
  - It does not mutate checkpoint flags.
  - It does not replace memory-engine or planner commit results.
  - Legacy board handlers remain authoritative.
  - Step 6 parity logging remains diagnostic-only.
- **Test coverage now includes**:
  - semantic result attachment for:
    - `memory_checkpoint_only`
    - `memory_checkpoint_and_text`
    - `plan_checkpoint_only`
  - mixed plan + memory outcomes producing `MIXED_BOARD_CHECKPOINT`
  - safe fallback when compiler/prepass analysis is missing
  - confirmation that routing behavior is unchanged

### 3.12. Step 11: Board/Checkpoint Semantic Model Parity Review / First Consumer Migration Decision

- **Review Conclusion**: **NO-GO** for a first authority migration.
- **Why authority migration is still blocked**:
  - `BoardCheckpointSemanticResult` is now a useful typed observational surface, but it is still too coarse to prove commit-equivalence or routing-equivalence.
  - Current parity fields are mostly presence-level:
    - checkpoint presence
    - visible-text presence
    - action presence
  - They do not yet prove:
    - plan-vs-memory outcome equivalence in all edge cases
    - raw-vs-clean text equivalence
    - compiler-invalid vs handler-cleanup interactions
    - commit-result-aware equivalence for planner or memory-engine application
  - `_build_board_checkpoint_semantic_result(...)` is still a large embedded builder inside `ResponsePipelineStagesMixin`, which makes later refinement and direct characterization harder than a dedicated pure helper would.
- **Decision**:
  - Legacy board handlers remain authoritative.
  - `BoardCheckpointSemanticResult` remains observational only.
  - Compiler/prepass facts remain structural-only observations.
  - Step 10 parity fields are diagnostic hints, not migration proof.
- **Most important remaining risks**:
  - visible-text parity is still coarser than handler-local cleaned-text behavior
  - action parity is still coarser than commit-aware checkpoint-with-action behavior
  - mixed plan+memory outcomes are typed, but not yet strong enough to drive any consumer
  - compiler-invalid cases still need stronger parity framing before any authority narrowing

### 3.13. Step 12: BoardCheckpoint Semantic Model Refinement + Pure Builder Extraction

- **Implementation Outcome**:
  - The embedded `_build_board_checkpoint_semantic_result(...)` logic was extracted out of `ResponsePipelineStagesMixin`.
  - A new pure helper module now owns the semantic builder:
    - `modules/agent/orchestration/responses/board_checkpoint_semantics.py`
  - The extracted pure helper:
    - has no logging
    - has no state mutation
    - makes no handler calls
    - makes no pipeline calls
    - has no side effects
  - `_run_checkpoint_stage(...)` now calls the pure helper and attaches the returned observational result exactly as before.
- **Low-risk refinement added**:
  - Additional observational-only parity fields were added:
    - `legacy_has_checkpoint`
    - `compiler_has_checkpoint_like`
    - `legacy_has_visible_text`
    - `compiler_has_visible_text`
    - `legacy_has_action`
    - `compiler_has_action`
  - These fields are not used for routing or authority.
- **Characterization outcome**:
  - Direct unit tests now cover the pure builder for:
    - `memory_checkpoint_only`
    - `memory_checkpoint_and_text`
    - `plan_checkpoint_only`
    - mixed plan + memory outcomes
    - no checkpoint
    - missing compiler analysis
    - checkpoint presence mismatch
  - `_run_checkpoint_stage(...)` parity is also characterized against the pure helper output.
- **Boundary remains unchanged**:
  - `BoardCheckpointSemanticResult` remains observational only.
  - Legacy board handlers remain authoritative.
  - No routing, commit, or checkpoint-flag behavior changed.

### 3.14. Step 13: First Narrow BoardCheckpoint Consumer Migration

- **Implementation Outcome**:
  - `_run_checkpoint_stage(...)` now performs a first narrow typed read-through for memory checkpoint routing.
  - The migrated read-through is limited to legacy-derived typed results:
    - `MEMORY_CHECKPOINT_ONLY`
    - `MEMORY_CHECKPOINT_WITH_TEXT`
  - Read-through only applies when:
    - `BoardCheckpointSemanticResult.source` is legacy-derived
    - the typed kind matches the corresponding legacy bool
  - Legacy flags still win on any disagreement.
- **What did not change**:
  - Compiler/prepass facts still do not decide checkpoint routing.
  - Board commit behavior did not change.
  - `PlanBoardStageHandler` and `MemoryBoardStageHandler` behavior did not change.
  - Checkpoint flags are not mutated from compiler/prepass facts.
  - The migration is a legacy-derived typed mirror only, not an authority transfer.
- **Why this step is safe**:
  - The typed path is gated by the same legacy bools it mirrors.
  - If the semantic result disagrees, the code falls back to legacy flags.
  - Compiler/prepass-only checkpoint facts cannot trigger routing by themselves.
- **Coverage added**:
  - typed read-through for `memory_checkpoint_only`
  - typed read-through for `memory_checkpoint_and_text`
  - disagreement tests proving legacy flags win
  - confirmation that compiler/prepass-only checkpoint facts do not trigger routing

### 3.15. Step 14: Plan Checkpoint Typed Read-Through

- **Implementation Outcome**:
  - `_run_checkpoint_stage(...)` now completes the safe legacy-derived typed read-through micro-slice for checkpoint routing branches that are already backed by legacy handler bools.
  - Migrated branches:
    - `MEMORY_CHECKPOINT_ONLY`
    - `MEMORY_CHECKPOINT_WITH_TEXT`
    - `MEMORY_CHECKPOINT_WITH_ACTION`
    - `PLAN_CHECKPOINT_ONLY`
    - `PLAN_CHECKPOINT_WITH_TEXT`
    - `PLAN_CHECKPOINT_WITH_ACTION`
  - The typed result is used only when it is legacy-derived and confirms the same legacy bool.
  - Legacy flags still win on disagreement.
- **What did not change**:
  - Compiler/prepass facts still do not decide checkpoint routing.
  - Board commit behavior did not change.
  - `PlanBoardStageHandler` and `MemoryBoardStageHandler` behavior did not change.
  - Checkpoint flags are not mutated from compiler/prepass facts.
  - This remains a legacy-derived typed mirror, not an authority transfer.
- **Coverage added**:
  - typed read-through for all safe legacy-bool-backed branches listed above
  - disagreement test proving legacy `plan_checkpoint_only` still wins
  - disagreement coverage for memory branches remains in place
  - confirmation that compiler/prepass-only plan and memory checkpoint facts do not trigger routing
- **Deferred branches**
  - No additional safe legacy-bool-backed checkpoint routing branches remain in this micro-slice.
  - Any next migration would be a different class of work and requires a new authority/design step.

### 3.16. Step 16: BoardCheckpoint Legacy-Derived Authority Candidate Implementation

- **Outcome**:
  - effective checkpoint-flag resolution is now centralized in a pure helper
  - `_run_checkpoint_stage(...)` no longer computes the typed read-through effective booleans inline
  - `CheckpointStageState(...)` construction now consistently uses effective plan and memory checkpoint flags once they are available
- **What did not change**:
  - no compiler/prepass authority was introduced
  - no observable checkpoint routing behavior changed
  - no board commit behavior changed
  - legacy board handlers remain authoritative
- **Coverage added**:
  - direct resolver tests for legacy fallback, matching typed confirmation, conflicting typed kinds, and non-legacy compiler/prepass-only sources
  - a stage-level regression test that would fail if an early `CheckpointStageState(...)` return path mixed raw memory flags with helper-resolved effective flags

### 3.17. Step 17: Use EffectiveCheckpointFlags as the Single Local Checkpoint Routing Surface

- **Outcome**:
  - `_run_checkpoint_stage(...)` now uses `EffectiveCheckpointFlags` as the single local checkpoint routing/state surface after resolution.
  - This is a local cleanup / authority narrowing from scattered legacy bools to resolver-owned effective flags.
- **What did not change**:
  - No compiler/prepass authority was introduced.
  - No observable routing or commit behavior changed.
  - Legacy board handlers remain authoritative.
  - Legacy flags still win on disagreement.

### 3.18. Step 18: First True Authority Candidate — Legacy-Derived Typed Result Primary With Legacy Fallback

- **Outcome**:
  - The first true authority narrowing was attempted for the `memory_checkpoint_only` branch.
  - A new pure helper, `resolve_memory_checkpoint_only_typed_primary`, was introduced as a typed-primary candidate for this branch. It remains behavior-preserving with a legacy disagreement guard; the typed result cannot change the memory branch category.
- **What did not change**:
  - Legacy fallback remains fully in place. If the typed result is absent, non-legacy-derived, or disagrees with another active legacy branch, the legacy boolean flag remains authoritative.
  - No compiler/prepass authority was introduced.
  - No observable routing or commit behavior changed.

### 3.19. Step 19: Extend Typed Primary to Remaining Legacy-Derived Memory Branches

- **Outcome**:
  - The typed-primary candidate pattern from Step 18 was extended to the remaining memory branches: `MEMORY_CHECKPOINT_WITH_TEXT` and `MEMORY_CHECKPOINT_WITH_ACTION`.
  - New pure helpers were added for these branches, following the same behavior-preserving pattern with legacy disagreement guards.
- **What did not change**:
  - The typed result still cannot change the memory branch category.
  - Legacy fallback remains fully in place.
  - No compiler/prepass authority was introduced.
  - No observable routing or commit behavior changed.

### 3.20. Step 20: Typed-Primary Candidate for Legacy-Derived Plan Branches

- **Outcome**:
  - The typed-primary candidate pattern was extended to the legacy-derived plan checkpoint branches: `PLAN_CHECKPOINT_ONLY`, `PLAN_CHECKPOINT_WITH_TEXT`, and `PLAN_CHECKPOINT_WITH_ACTION`.
  - New pure helpers were added for these branches, following the same behavior-preserving pattern with legacy disagreement guards.
- **What did not change**:
  - The typed result still cannot change the plan branch category.
  - Legacy fallback remains fully in place.
  - No compiler/prepass authority was introduced.
  - No observable routing or commit behavior changed.

### 3.21. Step 21: Consolidate BoardCheckpoint Typed-Primary Candidate Helpers / Reduce Boilerplate

- **Outcome**:
  - The six behavior-preserving typed-primary candidate helpers for board/checkpoint routing were consolidated into a single generic private helper.
  - This reduces boilerplate while keeping the public-facing helper signatures and call sites unchanged.
- **What did not change**:
  - No authority was expanded.
  - No compiler/prepass authority was introduced.
  - No observable routing or commit behavior changed.
  - Legacy fallback and disagreement guards remain fully in place.

### 3.22. Next Intended Step

The next step is **Phase 10 Step 22: BoardCheckpoint Authority Readiness Review / Decide Whether to Attempt Real Authority Transfer or Close Slice**.
