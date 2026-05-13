# Semantic Runtime Migration Roadmap

This document outlines the phased plan to migrate the runtime from legacy response parsing to a robust semantic access layer over the compiler's Intermediate Representation (IR).

**Goal**: Systematically replace legacy semantic extraction with a new `RuntimeProtocolSemantics` adapter, making the runtime more robust, efficient, and maintainable.

---

### Phase 0: Boundary Freeze (Done)

- **Goal**: Stabilize the existing compiler/runtime boundary before major changes.
- **Allowed**: Consolidate compiler metadata reads in `output_recovery` into a single helper. Add diagnostic logging.
- **Forbidden**: No behavior changes. No new compiler authority.
- **Done When**: `output_recovery` uses a single, tested helper for `error_code`, `recovery_id`, and `invalid_kind` with fallbacks.

---

### Governance Phase 1: Governance Alignment (Done)

- **Goal**: Align all governance documents with the actual completed work and established boundaries.
- **Allowed**: Create and align documentation in `docs/architecture/`.
- **Forbidden**: No production code changes.
- **Done When**: Constitution, roadmap, authority boundaries, stop lines, and test contracts are aligned and approved.

---

### Phase 2: Consumer Inventory (Done)

- **Goal**: Create a detailed inventory of all locations that consume response semantics.
- **Allowed**: Audit the codebase and create a comprehensive inventory document.
- **Forbidden**: No refactoring of consumer logic. No production code changes.
- **Done When**: The `Consumer Inventory` table in `protocol-authority-boundaries.md` is complete and approved.

---

### Phase 3: Accessor Module (API Design: Done)

- **Goal**: Design and document the API for the new semantic accessor functions in a dedicated module.
- **Allowed**: Create API documentation and design for a new module (e.g., `modules/agent/orchestration/responses/semantic_accessors.py`). The canonical design lives in `docs/architecture/semantic-accessor-api-design.md`.
- **Forbidden**: No implementation of the module or its functions. Migrating any existing consumer to use the new accessors.
- **Done When**: The API design in `semantic-accessor-api-design.md` is complete, reviewed, and approved.

---

### Phase 3: Accessor Module (Implementation) (Done)

- **Status**: Done.
- **Goal**: Implement the initial set of approved semantic accessors with full test coverage.
- **Allowed**:
    - Create `modules/agent/orchestration/responses/semantic_accessors.py`.
    - Add tests for the four approved accessors.
- **Forbidden**:
    - Consumer migration.
    - `ActionPolicy` changes.
    - Dispatch behavior changes.
    - Output recovery behavior changes.
    - Final-answer/sufficiency changes.
    - Intent transition changes.
    - Memory/plan board changes.
    - Touching `history.py`.
- **Done When**:
    - `semantic_accessors.py` exists.
    - Tests cover the API design requirements.
    - All relevant tests pass.
    - No consumers have been migrated.

---

### Phase 4: Behavior-Preserving Wrapper Migration

- **Status**: Done.
- **Goal**: Begin migrating consumers to the new accessors in a behavior-preserving way.
- **Allowed**: Replace direct field reads (`parsed_output.invalid_kind`) or simple `ResponseSemantics` calls with the equivalent new accessor.
- **Forbidden**: Changing any logic. This is a pure "find and replace" with the new function call.
- **Done When**: All simple, 1-to-1 replacements are complete.

---

### Phase 4 Implementation Step 1: `ResponseSemantics.has_any_action_proposal` wrapper delegation (Done)

- **Status**: Done.
- **Goal**: Implement the approved delegation of `ResponseSemantics.has_any_action_proposal` to its `semantic_accessors` counterpart.
- **Allowed**:
    - Edit `modules/agent/orchestration/responses/response_semantics.py` for this method only.
    - Add/update tests in `tests/test_response_semantics.py` for behavior and delegation.
- **Forbidden**:
    - Any other consumer migration.
    - `ActionPolicy` changes.
    - Dispatch behavior changes.
    - Output recovery behavior changes.
    - Final-answer/sufficiency changes.
    - Intent transition changes.
    - Memory/plan board changes.
    - Touching `history.py`.
- **Done When**:
    - `ResponseSemantics.has_any_action_proposal` delegates to the accessor.
    - Tests confirm behavior is preserved.
    - All relevant tests pass.

---

### Phase 4 Batch 1 Migration Plan

- **Status**: Approved.
- **Goal**: Plan the next set of safe, behavior-preserving wrapper migrations.
- **Scope**:
    - `OutputRecoveryRoutingMixin._compiler_strategy_decision` call site for `output_recovery_compiler_metadata`.
    - `ModelOutputRecoveryHandler._has_any_action_proposal` internal call site.
- **Forbidden**:
    - Implementation before plan approval.
    - Deletion of any existing helper functions.
    - Changes to output recovery behavior or recovery strategy logic.
    - Changes to `ActionPolicy`, dispatch, final-answer, or transition behavior.
    - Migration of any other call sites unless explicitly listed.
- **Done When**:
    - The batch migration plan is reviewed and approved.

---

### Phase 4 Batch 1 Implementation

- **Status**: Done.
- **Goal**: Implement the two approved call-site migrations from the Batch 1 plan.
- **Allowed Files**:
    - `modules/agent/orchestration/responses/output_recovery_routing.py`
    - `modules/agent/orchestration/responses/output_recovery.py`
    - `tests/test_runtime_protocol_semantics.py`
    - `tests/test_output_recovery.py` (or equivalent test file for `ModelOutputRecoveryHandler`)
- **Forbidden**:
    - Editing any other production files.
    - Deleting the `output_recovery_compiler_metadata` helper function.
    - Changing runtime behavior.
    - Any changes to `ActionPolicy`, dispatch, final-answer, transitions, boards, or `history.py`.
- **Done When**:
    - The two call sites are migrated to use the accessors.
    - Tests confirm behavior is preserved.
    - All relevant tests pass.

---

### Phase 4 Batch 2 Planning

- **Status**: Done.
- **Goal**: Analyze consumer inventory for next safe migration candidates.
- **Conclusion**: The fast-lane of simple migrations using the current accessor set is exhausted. All remaining safe candidates require new accessors.
- **Next Step**: Design the next batch of semantic accessors.

---

### Next Accessor Batch Design

- **Status**: Approved.
- **Goal**: Design the next small, conservative batch of accessors.
- **Scope**:
    - `is_leaked_system_result`
    - `has_substantial_think`
- **Deferred**: `get_visible_text` requires a separate design.
- **Forbidden**: Implementation before plan approval.
- **Done When**: The accessor batch design is reviewed and approved.

---

### Next Accessor Batch Implementation

- **Status**: Done.
- **Goal**: Implement the two approved accessors with full test coverage.
- **Allowed**:
    - Add `is_leaked_system_result` to `semantic_accessors.py`.
    - Add `has_substantial_think` to `semantic_accessors.py`.
    - Add dedicated unit tests for these two accessors.
- **Forbidden**:
    - Implementing `get_visible_text`.
    - Migrating any consumers.
    - Any changes to runtime behavior, final-answer/sufficiency, stop-decisions, `ActionPolicy`, dispatch, transitions, boards, or `history.py`.
- **Done When**:
    - The two accessors are implemented.
    - Tests confirm their behavior matches the design.
    - All relevant tests pass.

---

### Phase 4 Batch 2 Migration Plan

- **Status**: Approved.
- **Goal**: Design the consumer migration batch for the new accessors.
- **Scope**:
    - `ResponsePipelineStagesMixin` -> `is_leaked_system_result`
    - `ResponseGuardPolicy.is_nonproductive_thinking_turn` -> `has_substantial_think`
- **Forbidden**: Implementation before plan approval.
- **Done When**: The batch migration plan is reviewed and approved.

---

### Phase 4 Batch 2 Implementation

- **Status**: Done.
- **Goal**: Implement the two approved call-site migrations from the Batch 2 plan.
- **Allowed Files**:
    - `modules/agent/orchestration/responses/response_pipeline_stages.py`
    - `modules/agent/orchestration/responses/response_guards.py`
    - Test files covering these modules (implementation must locate existing tests before creating new ones).
- **Forbidden**:
    - Editing any other production files.
    - Implementing `get_visible_text`.
    - Any changes to runtime behavior, final-answer/sufficiency, stop-decisions, `ActionPolicy`, dispatch, transitions, boards, or `history.py`.
- **Done When**:
    - The two call sites are migrated to use the accessors.
    - Tests confirm behavior is preserved.
    - All relevant tests pass.

---

### Phase 4 Remaining Migration Review

- **Status**: Done.
- **Goal**: Classify remaining inventory rows after Batch 2.
- **Conclusion**: The review is complete. All simple, safe, behavior-preserving wrapper migrations that can be done with the current accessor set are finished. All remaining consumers in the inventory are either:
    - High-risk, touching dispatch authority, or runtime policy (e.g., `ActionPolicy`, bundle validation).
    - In need of new accessors (`get_visible_text`, `get_action_ops`, board tag helpers) that are themselves tied to frozen policy domains (final-answer, transitions, memory boards).
    - Too minor to justify a dedicated migration batch (`protocol_decision_bridge.compiler_invalid_kind_for_output`).
- **Recommendation**: Phase 4 (Behavior-Preserving Wrapper Migration) is complete. The next step should be to move to a later phase focused on policy-level refactoring, such as Phase 5.
- **Done When**: The review was documented and the recommendation was made.

---

### Phase 5: TransitionSemanticValidator (Complete)

- **Goal**: Refactor `IntentTransitionHandler` to use a dedicated semantic validator.
- **Allowed**: Create a `TransitionSemanticValidator` class that uses the new accessors to check for valid transitions. Refactor `IntentTransitionHandler` to delegate to this validator.
- **Forbidden**: Changing transition logic itself.
- **Done When**: The majority of `IntentTransitionHandler` followup parsing was migrated to the `TransitionSemanticValidator`. The `FOLLOWUP_PLAINTEXT` and `UNKNOWN` paths remain on a legacy fallback.

---

#### Phase 5 Design

- **Status**: Approved.
- **Goal**: Create the formal design for the `TransitionSemanticValidator`.
- **Forbidden**: Implementation before design approval.
- **Done When**: The `transition-semantic-validator-design.md` document is approved.

---

#### Phase 5 Step 1: Scaffolding and Type Definition

- **Status**: Done.
- **Goal**: Create the initial file, types, and class scaffold for the `TransitionSemanticValidator`.
- **Done When**: The scaffolding is in place with passing tests, and no logic has been migrated.

---

#### Phase 5 Step 2A: Core Structural Logic Migration (Design)

- **Status**: Approved.
- **Goal**: Design the migration of core structural classification logic into the validator.
- **Scope**:
    - `NO_FOLLOWUP`
    - `FOLLOWUP_ACTION`
    - `FOLLOWUP_CONFLICT`
- **Forbidden**:
    - Implementation before design approval.
    - Migrating context-sensitive logic (`TRANSITION_ONLY_VIOLATION`, etc.).
    - Implementing plaintext followup logic.
    - Migrating any consumers.
- **Done When**: The design for Step 2A is approved.

---

#### Phase 5 Step 2A: Core Structural Logic Migration (Implementation)

- **Status**: Done.
- **Goal**: Implement the core structural classification logic in `TransitionSemanticValidator`.
- **Done When**: The Step 2A logic is implemented in the validator with passing parity tests, and no consumers are migrated.

---

#### Phase 5 Step 2B: Context-Sensitive Logic Migration (Design)

- **Status**: Approved.
- **Goal**: Design the migration of context-sensitive classification logic into the validator.
- **Scope**:
    - `TRANSITION_ONLY_VIOLATION`
    - `REUSE_ONLY_VIOLATION`
    - `COMPLETE_WITH_ACTION_VIOLATION`
- **Forbidden**:
    - Implementation before design approval.
    - Migrating consumers.
- **Done When**: The design for Step 2B is approved.

---

#### Phase 5 Step 2B: Context-Sensitive Logic Migration (Implementation)

- **Status**: Done.
- **Goal**: Implement the context-sensitive classification logic in `TransitionSemanticValidator`.
- **Done When**: The Step 2B logic is implemented in the validator with passing parity tests, and no consumers are migrated.

---

#### Phase 5 Step 3: Consumer Migration (Design)

- **Status**: Approved.
- **Goal**: Design the migration of `IntentTransitionRoutingMixin` to use the `TransitionSemanticValidator`.
- **Forbidden**:
    - Implementation before design approval.
    - Deleting old helpers from `IntentTransitionHandler`.
- **Done When**: The design for Step 3 is approved.

---

#### Phase 5 Step 3: Consumer Migration (Implementation)

- **Status**: Done.
- **Goal**: Implement the first narrow consumer migration slice in `IntentTransitionRoutingMixin`.
- **Allowed**:
    - Update `IntentTransitionRoutingMixin` to use the validator **only** for the approved recovery/violation slice (`TRANSITION_ONLY_VIOLATION`, `REUSE_ONLY_VIOLATION`, `COMPLETE_WITH_ACTION_VIOLATION`, `FOLLOWUP_CONFLICT`).
    - Add/update tests for the migrated slice and fallback paths.
- **Forbidden**:
    - Migrating `NO_FOLLOWUP`, `FOLLOWUP_ACTION`, `FOLLOWUP_PLAINTEXT`, or `UNKNOWN` classifications.
    - Implementing `get_visible_text`.
    - Deleting or modifying old helpers.
    - Changing prompts, reason strings, or source markers.
    - Any runtime behavior changes.
- **Done When**: The first slice in `IntentTransitionRoutingMixin` was migrated to use the validator for recovery/violation classifications. A fallback to legacy logic was preserved for all other cases (`NO_FOLLOWUP`, `FOLLOWUP_ACTION`, `FOLLOWUP_PLAINTEXT`, `UNKNOWN`). All tests passed, and runtime behavior is unchanged.

---

#### Phase 5 Review: Next Migration Slice

- **Status**: Done.
- **Goal**: Review whether Phase 5 should continue with a second consumer migration slice for `NO_FOLLOWUP` and `FOLLOWUP_ACTION`.
- **Forbidden**: Implementation before a new design or review conclusion is approved.
- **Done When**: The review was completed. `NO_FOLLOWUP` and `FOLLOWUP_ACTION` were approved as safe candidates for a second migration slice. `FOLLOWUP_PLAINTEXT` remains deferred, and `UNKNOWN` remains a fallback.

---

#### Phase 5 Step 4: Second Consumer Migration (Design)

- **Status**: Done.
- **Goal**: Design the migration of `IntentTransitionRoutingMixin` to use the validator for `NO_FOLLOWUP` and `FOLLOWUP_ACTION`.
- **Forbidden**:
    - Implementation before design approval.
    - Migrating `FOLLOWUP_PLAINTEXT` or `UNKNOWN`.
    - Deleting old helpers.
- **Done When**: The design for Step 4 was approved.

---

#### Phase 5 Step 4: Second Consumer Migration (Implementation)

- **Status**: Done.
- **Goal**: Implement the second narrow consumer migration slice in `IntentTransitionRoutingMixin`.
- **Allowed**:
    - Update `IntentTransitionRoutingMixin` to use the validator for `NO_FOLLOWUP` and `FOLLOWUP_ACTION`.
    - Add/update tests for the migrated slice and fallback paths.
- **Forbidden**:
    - Migrating `FOLLOWUP_PLAINTEXT` or `UNKNOWN` classifications.
    - Implementing `get_visible_text`.
    - Deleting or modifying old helpers.
    - Changing prompts, reason strings, or source markers.
    - Any runtime behavior changes.
- **Done When**: The second slice (`NO_FOLLOWUP`, `FOLLOWUP_ACTION`) was migrated. A fallback for `FOLLOWUP_PLAINTEXT` and `UNKNOWN` was preserved. All tests passed, and runtime behavior is unchanged.

---

#### Phase 5 Boundary Review

- **Status**: Done.
- **Goal**: Decide whether to conclude Phase 5 before tackling `FOLLOWUP_PLAINTEXT` and its `get_visible_text` dependency.
- **Conclusion**: Phase 5 is complete. The `FOLLOWUP_PLAINTEXT` path is deferred due to its dependency on `get_visible_text`, which requires a separate design phase. The `UNKNOWN` path will remain a legacy fallback. Old helpers are preserved.
- **Done When**: The review was completed and the decision to conclude Phase 5 was documented.

---

### Phase 6: Bundle Semantic Validation Pass (Complete)

- **Status**: Done.
- **Goal**: Centralize atomic bundle validation logic into a new `BundleSemanticValidator`.
- **Outcome**: The `BundleSemanticValidator` was created and successfully centralized all compiler-only bundle prevalidation logic. The first consumer was migrated. `ActionPolicy`/`segments`-dependent logic remains deferred.
- **Done When**: The review in Step 4 concluded the phase.

---

#### Phase 6 Step 1: Scaffolding and Type Definition

- **Status**: Done.
- **Goal**: Create the initial file, types, and class scaffold for the `BundleSemanticValidator`.
- **Allowed**:
    - Create `modules/agent/orchestration/responses/bundle_semantic_validator.py`.
    - Add `BundleResultKind` enum, `BundleValidationResult` dataclass, and `BundleSemanticValidator` class scaffold.
    - The `validate` method returns `UNKNOWN` by default.
    - Add basic unit tests for the scaffolding and types.
- **Forbidden**:
    - Implementing any classification logic.
    - Migrating any consumers.
    - `ActionPolicy` or `DispatchPipeline` changes.
    - `get_visible_text` implementation or `INVALID_MIXED_VISIBLE_TEXT` classification.
    - Any runtime behavior changes.
- **Done When**: The scaffolding is in place with passing tests, and no logic has been migrated.

---

#### Phase 6 Step 2: Validator Implementation (Compiler-Only)

- **Status**: Design Approved for Step 2A.
- **Goal**: Design and document the compiler-only classification logic for `BundleSemanticValidator`.
- **Allowed**:
    - Update `docs/architecture/bundle-semantic-validation-design.md` with the detailed design for Step 2.
    - The design should cover classification logic for `INVALID_ACTION_ARRAY`, `INVALID_MULTIPLE_ACTIONS`, `INVALID_FILE_CONTENT_PAIRING`, `INVALID_INTENT_COMPLETE_WITH_ACTION`, `INTENT_ACTION_BUNDLE_CANDIDATE`, and `READONLY_ACTION_BATCH_CANDIDATE` based on compiler metadata only.
- **Forbidden**:
    - Implementation before design approval.
    - Designing logic that requires `ActionPolicyHandler` or runtime state.
    - Designing logic for `INVALID_MIXED_VISIBLE_TEXT`.
- **Done When**: The design for Step 2 is documented and Step 2A is approved for implementation.

---

#### Phase 6 Step 2A: Error-Code-Driven Classification

- **Status**: Done.
- **Goal**: Implement the approved error-code-driven classifications in `BundleSemanticValidator`.
- **Allowed**:
    - Add logic to `BundleSemanticValidator.validate` to classify `INVALID_ACTION_ARRAY`, `INVALID_MULTIPLE_ACTIONS`, and `INVALID_FILE_CONTENT_PAIRING` based on `compiler_error_code` and `invalid_kind`.
    - Update unit tests in `tests/test_bundle_semantic_validator.py`.
- **Forbidden**:
    - Implementing shape-driven classifications (`INTENT_ACTION_BUNDLE_CANDIDATE`, etc.).
    - Migrating any consumers.
    - Inspecting `segments`.
    - Calling `ActionPolicy`.
    - Inspecting runtime state.
    - Implementing `get_visible_text` or `INVALID_MIXED_VISIBLE_TEXT` logic.
    - Any runtime behavior changes.
- **Done When**: The Step 2A logic is implemented with passing tests, and no consumers are migrated.

---

#### Phase 6 Step 2B: Shape-Driven Classification

- **Status**: Step 2B.1 and 2B.2 Done.
- **Goal**: Design the implementation of shape-driven classifications in `BundleSemanticValidator`.
- **Allowed**:
    - Update `docs/architecture/bundle-semantic-validation-design.md` with the detailed design for Step 2B.
    - The design should cover classification logic for `INTENT_ACTION_BUNDLE_CANDIDATE`, `READONLY_ACTION_BATCH_CANDIDATE`, and `NO_BUNDLE_SHAPE` based on `compiler_ir.shape`.
- **Forbidden**:
    - Implementation before design approval.
    - Designing logic that requires `ActionPolicyHandler` or runtime state.
    - Designing logic for `INVALID_MIXED_VISIBLE_TEXT` or any other visible-text shapes.
- **Done When**: The design for Step 2B is documented and sub-steps are approved for implementation.

---

#### Phase 6 Step 2B.1: INTENT_ACTION_BUNDLE Shape Classification

- **Status**: Done.
- **Goal**: Implement the `INTENT_ACTION_BUNDLE` shape classification in `BundleSemanticValidator`.
- **Allowed**:
    - Add logic to `BundleSemanticValidator.validate` to classify `INTENT_ACTION_BUNDLE_CANDIDATE` based on compiler shape.
    - Add shape normalization logic as needed for this classification.
    - Update unit tests in `tests/test_bundle_semantic_validator.py`.
- **Forbidden**:
    - Implementing any other shape-driven classifications (`READONLY_ACTION_BATCH_CANDIDATE`, `NO_BUNDLE_SHAPE`, etc.).
    - Migrating any consumers.
    - Calling `ActionPolicy`.
    - Any runtime behavior changes.
- **Done When**: The Step 2B.1 logic is implemented with passing tests, and no consumers are migrated.

---

#### Phase 6 Step 2B.2: READONLY_ACTION_BATCH_CANDIDATE Shape Classification

- **Status**: Done.
- **Goal**: Implement the `READONLY_ACTION_BATCH_CANDIDATE` shape classification in `BundleSemanticValidator`.
- **Allowed**:
    - Add logic to `BundleSemanticValidator.validate` to classify `READONLY_ACTION_BATCH_CANDIDATE` based on compiler shape.
    - Reuse existing shape normalization.
    - Update unit tests in `tests/test_bundle_semantic_validator.py`.
- **Forbidden**:
    - Implementing any other shape-driven classifications (`NO_BUNDLE_SHAPE`, etc.).
    - Migrating any consumers.
    - Calling `ActionPolicy`.
    - Any runtime behavior changes.
- **Done When**: The Step 2B.2 logic is implemented with passing tests, and no consumers are migrated.

---

#### Phase 6 Step 2B.3: NO_BUNDLE_SHAPE Classification

- **Status**: Done.
- **Goal**: Implement the `NO_BUNDLE_SHAPE` classification for the `INTENT_ONLY` shape.
- **Allowed**:
    - Add logic to `BundleSemanticValidator.validate` to classify `NO_BUNDLE_SHAPE` for the `INTENT_ONLY` compiler shape.
    - Reuse existing shape normalization.
    - Update unit tests in `tests/test_bundle_semantic_validator.py`.
- **Forbidden**:
    - Classifying `ACTION_ONLY` or any other shape as `NO_BUNDLE_SHAPE`.
    - Classifying any visible-text shapes.
    - Migrating any consumers.
    - Calling `ActionPolicy`.
    - Any runtime behavior changes.
- **Done When**: The Step 2B.3 logic was implemented with passing tests, and no consumers were migrated.

---

#### Phase 6 Step 2C: Parity Testing

- **Status**: Done.
- **Goal**: Implement parity tests to prove behavioral equivalence between the `BundleSemanticValidator` and the documented legacy logic for all classifications implemented through Step 2B.
- **Allowed**:
    - Create a new test file: `tests/test_bundle_semantic_validator_parity.py`.
    - Use explicit mapping tables and `pytest.mark.parametrize` fixtures.
    - Update `tests/test_bundle_semantic_validator.py` only if necessary for shared test fixtures.
- **Forbidden**:
    - Any production code changes.
    - Migrating any consumers.
    - Adding any new classification behavior to the validator.
    - Classifying `ACTION_ONLY` or any visible-text shapes.
    - Implementing `INVALID_INTENT_COMPLETE_WITH_ACTION`.
- **Done When**: The parity tests were implemented in `tests/test_bundle_semantic_validator_parity.py` with passing results, and no production code was changed.

---

#### Phase 6 Step 3: First Consumer Migration

- **Status**: Done.
- **Goal**: Implement the first, lowest-risk consumer migration to use the `BundleSemanticValidator`.
- **Scope**: `ResponsePipelinePrevalidationMixin._reject_compiler_invalid_atomic_bundle_before_transition` only.
- **Allowed**:
    - Migrate `_reject_compiler_invalid_atomic_bundle_before_transition` to use `BundleSemanticValidator`.
    - Update relevant tests to prove exact behavior preservation.
- **Forbidden**:
    - Migrating any other consumer.
    - `ActionPolicy` or `DispatchPipeline` changes.
    - `BundleSemanticValidator` classification changes.
    - Changing prompts, reason strings, or source markers.
    - Any runtime behavior changes.
- **Done When**: The consumer was migrated, `tests/test_response_pipeline_prevalidation.py` was added, all tests passed, and runtime behavior was unchanged.

---

#### Phase 6 Step 4: Next Consumer Migration Review

- **Status**: Done.
- **Goal**: Review whether to migrate another consumer or conclude Phase 6 before `ActionPolicy`/`segments`-dependent branches.
- **Conclusion**: Phase 6 is complete. The next candidate consumer (`_reject_invalid_atomic_bundle_before_transition`) is deferred as it depends on `ActionPolicy` and `segments`, which are out of scope.
- **Done When**: The review was completed and the decision to conclude Phase 6 was documented.

---

### Phase 7: ActionPolicy-Dependent Bundle Validation (Complete)

- **Status**: Done.
- **Goal**: Refactor `ActionPolicy`-dependent bundle validation logic, focusing on the `_reject_invalid_atomic_bundle_before_transition` consumer.
- **Outcome**: Characterization tests were added, a typed result model was introduced, the `ActionPolicyHandler` producer was refactored, and the `ResponsePipelinePrevalidationMixin` consumer was migrated. Legacy `reason`/`details` compatibility was preserved.
- **Next**: Cleanup of legacy `reason`/`details` fields is deferred to a future compatibility-focused phase.

---

#### Phase 7 Step 2: Characterization Tests

- **Status**: Done.
- **Goal**: Add characterization tests to lock down the exact current behavior of `ActionPolicy`-dependent bundle validation.
- **Allowed**:
    - Add characterization tests in `tests/test_response_pipeline_prevalidation.py` and/or a new `tests/test_action_policy.py`.
- **Forbidden**:
    - Any production code changes.
    - Introducing typed result enums.
    - Refactoring `ActionPolicyHandler` or `ResponsePipelinePrevalidationMixin`.
    - Migrating any consumers.
    - Any runtime behavior changes.
- **Done When**: Characterization tests were added in `tests/test_action_policy.py` and `tests/test_response_pipeline_prevalidation.py`. All tests passed, and no production code was changed.

---

#### Phase 7 Step 3: Typed Result Introduction (Design Review)

- **Status**: Done.
- **Goal**: Review characterization test results and decide whether to approve the implementation of a typed result model for `ActionPolicyHandler`.
- **Allowed**:
    - Documentation updates to approve or reject the candidate design for Step 3.
- **Forbidden**:
    - Any production code or test changes.
- **Done When**: The review was completed. The decision is to proceed with a new Step 3A for scaffolding only.

---

#### Phase 7 Step 3A: Typed Result Scaffolding

- **Status**: Done.
- **Goal**: Create the scaffolding for the typed result model for `ActionPolicyHandler`.
- **Allowed**:
    - Create `modules/agent/orchestration/runtime/action_policy_models.py`.
    - Define `AtomicBundlePolicyResultKind` enum and `AtomicBundleActionValidationResult` dataclass.
    - Add `tests/test_action_policy_models.py`.
- **Forbidden**:
    - Changing `ActionPolicyHandler` or `ResponsePipelinePrevalidationMixin`.
    - Migrating any consumers.
    - Any runtime behavior changes.
- **Done When**: `modules/agent/orchestration/runtime/action_policy_models.py` and `tests/test_action_policy_models.py` were created. All tests passed. No runtime behavior was changed.

---

#### Phase 7 Step 3B: `ActionPolicyHandler` Refactor (Design)

- **Status**: Done.
- **Goal**: Review and approve the internal refactor of `ActionPolicyHandler.validate_atomic_bundle_action` to use the new typed result model.
- **Allowed**:
    - Documentation updates to approve or reject the candidate design for Step 3B.
- **Forbidden**:
    - Any production code or test changes.
- **Done When**: A decision on whether to proceed with the Step 3B implementation was documented.

---

#### Phase 7 Step 3B: `ActionPolicyHandler` Refactor (Implementation)

- **Status**: Done.
- **Goal**: Internally refactor `ActionPolicyHandler.validate_atomic_bundle_action` to return the new typed `AtomicBundleActionValidationResult`.
- **Allowed**:
    - Refactor `validate_atomic_bundle_action` to return `AtomicBundleActionValidationResult` with a `kind`.
    - Preserve the legacy `ok`, `reason`, and `details` fields in the result for compatibility.
    - Keep all characterization tests in `tests/test_action_policy.py` green without modification.
- **Forbidden**:
    - Migrating `ResponsePipelinePrevalidationMixin` or any other consumer.
    - Changing prompts, reason strings, or source markers.
    - Any runtime behavior changes.
- **Done When**: `validate_atomic_bundle_action` was refactored. Legacy `ok`/`reason`/`details` were preserved. All characterization tests passed. No consumers were migrated.

---

#### Phase 7 Step 4: Consumer Migration

- **Status**: Done.
- **Goal**: Migrate `ResponsePipelinePrevalidationMixin._reject_invalid_atomic_bundle_before_transition` to use the typed `AtomicBundleActionValidationResult.kind`.
- **Allowed**:
    - Refactor `_reject_invalid_atomic_bundle_before_transition` to branch on `result.kind`.
    - Preserve legacy `result.reason` and `result.details` usage for prompts, logs, and plans.
    - Update characterization tests in `tests/test_response_pipeline_prevalidation.py` to keep them green.
- **Forbidden**:
    - Migrating any other consumer.
    - Changing `ActionPolicyHandler`.
    - Changing prompts, reason strings, or source markers.
    - Any runtime behavior changes.
- **Done When**: The consumer was migrated with a legacy `reason` fallback, all characterization tests passed, and runtime behavior was unchanged.

---

#### Phase 7 Closure Review

- **Status**: Done.
- **Goal**: Decide whether to conclude Phase 7 or defer any cleanup/removal of legacy `reason`/`details` branching.
- **Conclusion**: Phase 7 is complete. Cleanup of legacy `reason`/`details` fields is explicitly deferred to a future compatibility-focused phase.
- **Done When**: The decision to conclude Phase 7 was documented.

---

### Phase 8: Visible Text & Terminal Answer Semantics

- **Status**: Design Started.
- **Goal**: Clarify authority for visible text, terminal answers, and checkpoint+text combinations.
- **Forbidden**: Implementation of production code changes before characterization tests are complete and a refactoring plan is approved.
- **Done When**: A dedicated `TerminalAnswerClassifier` is implemented, all relevant consumers are migrated, and legacy helpers are removed.

---

#### Phase 8 Step 1: Design-Only Inventory

- **Status**: Done.
- **Goal**: Create a detailed inventory of all components involved in visible text and terminal answer semantics.
- **Done When**: The inventory in `docs/architecture/visible-text-terminal-answer-semantics-design.md` was completed.

---

#### Phase 8 Step 2: Characterization Tests

- **Status**: Done.
- **Goal**: Add characterization tests to lock down the exact behavior of all identified components and scenarios related to visible text and terminal answers.
- **Allowed**: Add new test files and test cases that assert current behavior. This is a tests-only step.
- **Forbidden**: Any production code changes. Do not implement `TerminalAnswerClassifier` or any typed models. Do not migrate any consumers. Do not change runtime behavior.
- **Done When**: The characterization test suite was completed, and all tests passed. No production code was changed.

---

#### Phase 8 Step 3: Typed Model Scaffolding (Design)

- **Status**: Done.
- **Goal**: Review characterization test results and decide whether to approve the design of a typed result model for terminal answer semantics (e.g., `TerminalAnswerKind`).
- **Forbidden**: Implementation was not authorized by default.
- **Done When**: The design review was completed. The decision was to approve the design and proceed with a scaffolding-only implementation step (3A).

---

#### Phase 8 Step 3A: Typed Model Scaffolding (Implementation)

- **Status**: Done.
- **Goal**: Create the scaffolding for the `TerminalAnswerKind` enum and `TerminalAnswerSemanticResult` dataclass.
- **Allowed**: Create new files for the typed models and add basic unit tests for the types themselves.
- **Forbidden**: Do not implement the `TerminalAnswerClassifier`. Do not implement any classification logic. Do not migrate any consumers. Do not change any runtime behavior.
- **Done When**: `terminal_answer_models.py` and `test_terminal_answer_models.py` were created. The `TerminalAnswerKind` enum and `TerminalAnswerSemanticResult` dataclass were defined. All tests passed, and no runtime behavior was changed.

---

#### Phase 8 Step 4A: Compiler/Runtime Semantics Tag Coverage Review (Design-Only)

- **Status**: Done.
- **Goal**: Review whether `RuntimeProtocolSemantics` exposes enough structural facts to support a reliable `TerminalAnswerClassifier`.
- **Forbidden**: Any production code or test changes.
- **Done When**: The design-only review was completed and documented. The conclusion was that signals are insufficient, and classifier implementation is blocked.

---

#### Phase 8 Step 4C: Compiler Fact Scaffolding (Design)

- **Status**: Done.
- **Goal**: Design the addition of new structural facts to the compiler and `RuntimeProtocolSemantics` to address coverage gaps.
- **Forbidden**: Any production code or test changes.
- **Done When**: The design for adding new structural facts was completed and documented in `visible-text-terminal-answer-semantics-design.md`.

---

#### Phase 8 Step 4D: New Fact Characterization Test Design

- **Status**: Done.
- **Goal**: Design characterization tests for the new structural facts and shape improvements proposed in Step 4C.
- **Forbidden**: Any production code or test changes.
- **Done When**: The test cases were designed and documented in `visible-text-terminal-answer-semantics-design.md`.

---

#### Phase 8 Step 4D.1: New Fact Characterization Test Implementation

- **Status**: Done.
- **Goal**: Implement the characterization tests designed in Step 4D.
- **Prerequisite**: Step 4D must be complete.
- **Forbidden**: Any production code changes.
- **Done When**: The new golden characterization tests were implemented in `tests/test_compiler_structural_facts.py` and marked as `xfail`.

---

#### Phase 8 Step 4E: Compiler/Runtime Fact Implementation

- **Status**: Done.
- **Goal**: Implement the compiler/runtime changes for the new structural facts.
- **Prerequisite**: Step 4D.1 is complete. The Step 4E design gate for compiler authority is documented and accepted.
- **Forbidden**: Consumer migration. Implementing new facts with regex scans in `RuntimeProtocolSemantics`.
- **Done When**: The new structural facts are implemented in the compiler/IR and the new characterization tests pass.
- **Note**: Parser atom correctness is a prerequisite for semantic facts. Future semantic fact phases must begin with parser/tokenizer golden coverage for the atoms they depend on. Example atoms include:
    - `text_then_action`
    - `think_text_then_action`
    - `self_closing_complete_intent_then_text`
    - `inline_code_action_literal`
    - `fenced_action_literal`
    - `standalone_subgoal`
    - `subgoal_embedded_in_prose`
    - `action_then_text_invalid`
    - `action_then_intent_invalid`

---

#### Phase 8 Step 4F: Shadow Sufficiency / Parity Review

- **Status**: Done.
- **Goal**: Prove the new structural facts are sufficient for the `TerminalAnswerClassifier`.
- **Prerequisite**: Step 4E must be complete.
- **Forbidden**: Consumer migration.
- **Done When**: The design-only review was completed and documented. The review concluded that the facts are sufficient to proceed with designing a shadow-mode classifier. A sufficiency test was added in `tests/test_terminal_answer_fact_sufficiency.py`.

---

#### Phase 8 Step 4B (Redux): TerminalAnswerClassifier Shadow Mode Design

- **Status**: Done.
- **Goal**: Design the `TerminalAnswerClassifier` and a plan for running it in shadow mode.
- **Prerequisite**: Phase 8 Step 4F must be complete.
- **Forbidden**: Implementation is not authorized. Any production code changes.
- **Done When**: The design for the classifier and its shadow-mode operation was completed and documented.

---

#### Phase 8 Step 4G: TerminalAnswerClassifier Shadow Implementation

- **Status**: Done.
- **Goal**: Implement the `TerminalAnswerClassifier` as an isolated, shadow-safe component.
- **Prerequisite**: Step 4B (Redux) design must be complete and approved.
- **Forbidden**: Consumer migration. Any changes to runtime behavior, dispatch, or policy. The classifier must not affect any production logic.
- **Done When**: The `TerminalAnswerClassifier` was implemented with unit tests covering compiler-fact branches. The implementation is isolated, and no runtime shadow hook was added.

---

#### Phase 8 Step 4H: Shadow Wiring / Diagnostic Logging

- **Status**: Done.
- **Goal**: Wire the isolated `TerminalAnswerClassifier` into the `ResponsePipeline` for shadow-mode execution and add diagnostic logging.
- **Prerequisite**: Step 4G must be complete.
- **Forbidden**: Consumer migration. Any changes to runtime behavior.
- **Done When**: The classifier was wired into `ResponsePipelinePrevalidationMixin` in shadow mode. It logs its own classification as a shadow signal; parity comparison logic is not yet implemented. The call is protected by an exception handler. No production behavior was changed.

---

#### Phase 8 Step 4I: Parity Matrix / Legacy Helper Integration

- **Status**: Done.
- **Goal**: Analyze shadow logs and begin integrating legacy helper branches into the classifier.
- **Prerequisite**: Step 4H must be complete.
- **Forbidden**: Consumer migration. Any changes to runtime behavior.
- **Done When (Part 1)**: The shadow logging was updated to compute and record `legacy_kind` and `is_match`, enabling parity analysis.
- **Done When (Part 2)**: The `LEAKED_SYSTEM_RESULT` legacy rule was integrated into the classifier.
- **Done When (Part 3)**: The `INVALID_OR_TRUNCATED_TERMINAL_TEXT` legacy rule was integrated into the classifier.
- **Done When (Part 4)**: The `INTERNAL_SUMMARY_LIKE_TEXT` legacy rule is implemented in the classifier.
- **Done When (Full)**: A parity matrix is documented, and all key legacy helper branches are integrated into the classifier with passing tests.
- **Post-Step Boundary**: The classifier remains shadow/diagnostic only. Any consumer migration or authority change requires a new explicitly approved step after the Step 4I parity/closure review.

#### Phase 8 Step 4J: Consumer Migration Design Gate

- **Status**: Done.
- **Goal**: Review the completed Step 4I parity matrix and available shadow-log parity evidence, then decide whether a narrow consumer migration target can be proposed.
- **Allowed**: Design-only review, parity analysis, migration-candidate selection, and documentation updates.
- **Forbidden**: Consumer migration. Any dispatch, policy, UI, or other production behavior change. Any authority transfer to the classifier.
- **Done When**: The review was completed and documented in `visible-text-terminal-answer-semantics-design.md`. The review proposed a new Step 4K to design the first consumer migration.

---

#### Phase 8 Step 4K: First Consumer Migration (Design)

- **Status**: Done.
- **Goal**: Design the first, narrow, behavior-preserving migration of a consumer to the `TerminalAnswerClassifier`.
- **Scope**: The `is_leaked_system_result` check in `ResponsePipelineStagesMixin`.
- **Allowed**: Design-only documentation updates.
- **Forbidden**: Implementation. Any production code changes. Any behavior changes. Migration of any other consumer.
- **Done When**: The design for migrating the `is_leaked_system_result` check was documented and approved as a typed-result-primary, legacy-fallback migration.

---

#### Phase 8 Step 4L: First Consumer Migration (Implementation)

- **Status**: Done.
- **Goal**: Implement the first, narrow, behavior-preserving migration of a consumer to the `TerminalAnswerClassifier`.
- **Scope**: The `is_leaked_system_result` check in `ResponsePipelineStagesMixin`.
- **Prerequisite**: Step 4K design must be complete and approved.
- **Allowed**: Implement the changes as specified in the Step 4K design.
- **Forbidden**:
  - A strict replacement of `is_leaked_system_result(response)` with `TerminalAnswerKind.LEAKED_SYSTEM_RESULT`
  - Removing the existing outer guard `not self.semantics.has_any_action_proposal(parsed_output, parsed_action_count)`
  - Treating the classifier as sole authority for leaked-system-result detection
  - Any runtime behavior changes
  - Migration of any other consumer
- **Implementation Shape Required**:
  - Use the typed classifier result as the primary signal
  - Keep the legacy `is_leaked_system_result(response)` accessor as the production fallback
  - Apply the fallback both when the typed result is absent and when it is present but not `LEAKED_SYSTEM_RESULT`
  - Preserve the existing outer no-action guard
  - Keep `_run_terminal_answer_classifier_shadow` named as-is
- **Rationale**:
  - The classifier and legacy accessor are not exact semantic equivalents
  - The classifier uses a stricter prefix regex for `SYSTEM RESULT:`
  - The accessor uses a broader `.search(...)` pattern
  - The current consumer checks raw response text
- **Done When**: The `is_leaked_system_result` consumer is migrated in a behavior-preserving way, all tests pass, and the legacy accessor remains the production fallback.
- **Completed Outcome**:
  - The leaked-system-result guard in `ResponsePipelineStagesMixin` now uses the typed `TerminalAnswerClassifier` result as the primary signal.
  - The legacy `is_leaked_system_result(response)` accessor remains the production fallback.
  - The fallback applies both when the typed result is absent and when it is present but not `LEAKED_SYSTEM_RESULT`.
  - The outer guard `not self.semantics.has_any_action_proposal(parsed_output, parsed_action_count)` is preserved.
  - `_run_terminal_answer_classifier_shadow` was not renamed.
  - No other consumers were migrated.
  - `TerminalAnswerClassifier` is not sole authority.
  - Production behavior is intended to remain equivalent.
  - Tests passed.

---

#### Phase 8 Step 4M: Terminal Answer Consumer Migration Batch Plan

- **Status**: Done.
- **Goal**: Inventory the remaining terminal-answer legacy consumers, rank them, and define a safe ordered migration sequence.
- **Prerequisite**: Step 4L must be complete.
- **Allowed**: Design-only review and documentation updates.
- **Forbidden**:
  - Any consumer migration
  - Any production behavior change
- **Review Focus**:
  - Inventory all remaining terminal-answer-related legacy consumers
  - Rank them by bug impact, migration risk, classifier readiness, and policy/authority risk
  - Propose a narrow migration sequence with legacy fallback where parity is not exact
- **Done When**: The inventory, ranking, and ordered migration sequence are documented.
- **Conclusion**:
  - The Terminal Answers slice should not be closed yet.
  - Legacy terminal-answer consumers remain a recurring bug source.
  - Future migrations must stay narrow and behavior-preserving.
  - Legacy fallback remains required unless exact semantic parity is proven.
  - `TerminalAnswerClassifier` is not policy authority or stop-gate authority.
  - Recommended sequence:
    - `Step 4M.1`: `INVALID_OR_TRUNCATED_TERMINAL_TEXT` consumer migration design
    - `Step 4M.2`: `INVALID_OR_TRUNCATED_TERMINAL_TEXT` implementation
    - `Step 4N.1`: `INTERNAL_SUMMARY_LIKE_TEXT` consumer migration design
    - `Step 4N.2`: `INTERNAL_SUMMARY_LIKE_TEXT` implementation
    - Later: `PLAINTEXT_TERMINAL_ANSWER` / final-answer path only after separate preflight
    - Board/checkpoint consumers deferred to a separate slice

---

#### Phase 8 Step 4M.1: `INVALID_OR_TRUNCATED_TERMINAL_TEXT` Consumer Migration Design

- **Status**: Done.
- **Goal**: Design the first post-Step-4L terminal-answer consumer migration around the existing truncated-terminal-answer guard.
- **Allowed**: Docs-only review and documentation updates.
- **Forbidden**:
  - Fallback removal
  - New consumer migration
  - Production behavior changes
- **Done When**: A narrow, behavior-preserving design exists for migrating the existing truncated-terminal-answer guard with legacy fallback where parity is not exact.
- **Design Summary**:
  - Current consumer:
    `ResponsePipelinePrevalidationMixin._reject_truncated_terminal_completion_before_transition`
  - Current helper:
    `terminal_plaintext_completion_status(raw_response)`
  - Current behavior:
    on invalid/truncated terminal plaintext for `intent_payload.mode == "complete"`, clear terminal completion state, log `truncated_terminal_plaintext_answer`, and return `ResponsePipelineOutcome.continue_with(...)`.
  - Classifier readiness:
    `TerminalAnswerClassifier` already produces `INVALID_OR_TRUNCATED_TERMINAL_TEXT` and the result is attached to `ParsedModelOutput` after Step 4L.
  - Parity risk:
    the classifier evaluates the helper on `candidate_text` and only for `PURE_PLAINTEXT`, while the current guard evaluates the helper on `raw_response`.
  - Design decision:
    Step 4M.2 must use the typed result as the primary hint only inside the existing intent-completion guard, with legacy confirmation on `raw_response`.
  - Authority boundary:
    no stop-gate or final-answer authority change.

---

#### Phase 8 Step 4M.2: `INVALID_OR_TRUNCATED_TERMINAL_TEXT` Consumer Migration Implementation

- **Status**: Done.
- **Goal**: Implement the narrow, behavior-preserving migration designed in Step 4M.1.
- **Allowed**: Limited implementation of the existing truncated-terminal-answer guard only.
- **Forbidden**:
  - Fallback removal
  - Classifier logic changes
  - Migration of any other consumer
  - Production behavior changes
- **Required Shape**:
  - Preserve the existing `intent_payload.mode == "complete"` guard.
  - Use typed `INVALID_OR_TRUNCATED_TERMINAL_TEXT` as the primary hint if safe.
  - Confirm the final rejection decision with `terminal_plaintext_completion_status(raw_response)`.
  - Preserve current recovery behavior, logging, reason, and source.
- **Completed Outcome**:
  - The migrated consumer is `ResponsePipelinePrevalidationMixin._reject_truncated_terminal_completion_before_transition`.
  - Typed `INVALID_OR_TRUNCATED_TERMINAL_TEXT` is now the primary hint for this guard.
  - The legacy helper remains the production confirmation/fallback path.
  - The existing `intent_payload.mode == "complete"` precondition is preserved.
  - Existing recovery behavior, logging, `reason`, and `source` are preserved.
  - No other consumers were migrated.
  - Tests passed.

---

#### Phase 8 Step 4N.1: `INTERNAL_SUMMARY_LIKE_TEXT` Consumer Migration Design

- **Status**: Done.
- **Goal**: Design the next narrow consumer migration around the existing internal-summary recovery path.
- **Allowed**: Docs-only review and documentation updates.
- **Forbidden**:
  - Fallback removal
  - New consumer migration
  - Production behavior changes
- **Done When**: A concrete, behavior-preserving design exists for the existing internal-summary recovery consumer.
- **Design Summary**:
  - Current consumer path:
    `OutputRecoveryRoutingMixin.decide(...)` sets
    `invalid_kind = "internal_summary_instead_of_final_answer"` when
    `_is_internal_summary_instead_of_final_answer(parsed_output)` returns `True`
    and no earlier invalid kind has already won.
  - Current behavior:
    log `reason="internal_summary_instead_of_final_answer"` and return
    `OutputRecoveryDecision.continue_with(...)` via
    `build_internal_summary_instead_of_final_answer_prompt()`.
  - Classifier readiness:
    `TerminalAnswerClassifier` already produces `INTERNAL_SUMMARY_LIKE_TEXT`,
    using a caller-computed `is_internal_summary` flag from the same legacy helper,
    and the result is already attached to `ParsedModelOutput`.
  - Parity risk:
    exact consumer parity is not yet proven because this branch lives inside
    invalid-kind routing and runtime-policy ordering.
  - Design decision:
    Step 4N.2 may use the typed result as a primary hint only; the legacy helper
    remains confirmation/fallback unless exact parity is proven.

---

#### Phase 8 Step 4N.2: `INTERNAL_SUMMARY_LIKE_TEXT` Consumer Migration Implementation

- **Status**: Done.
- **Goal**: Implement the narrow, behavior-preserving migration designed in Step 4N.1.
- **Allowed**: Limited implementation of the existing internal-summary recovery consumer only.
- **Forbidden**:
  - Fallback removal
  - Classifier logic changes
  - Migration of any other consumer
  - Production behavior changes
- **Completed Outcome**:
  - The migrated consumer is the internal-summary recovery path in `OutputRecoveryRoutingMixin.decide(...)`.
  - Typed `INTERNAL_SUMMARY_LIKE_TEXT` is now a primary hint only.
  - `_is_internal_summary_instead_of_final_answer(parsed_output)` remains the confirmation/fallback path.
  - Typed result alone does not create a new recovery decision.
  - Existing invalid-kind ordering and earlier invalid-kind precedence are preserved.
  - Existing recovery behavior, `reason`, `source`, prompt, and logging are preserved.
  - No other consumers were migrated.
  - Tests passed.

---

#### Phase 8 Step 4O: Terminal Answer Remaining Consumer Review / Final-Answer Path Preflight

- **Status**: Done.
- **Goal**: Review the remaining terminal-answer consumers and decide whether any final-answer-path migration can be proposed safely.
- **Allowed**: Design-only review and documentation updates.
- **Forbidden**:
  - Final-answer authority changes
  - Stop-gate authority changes
  - Consumer migration
  - Production behavior changes
- **Conclusion**:
  - **NO-GO** for a `PLAINTEXT_TERMINAL_ANSWER` migration in the current slice.
  - Remaining consumers sit on final-answer authority, intent-completion finalization,
    visible-text extraction semantics, and stop-gate behavior.
  - No very narrow behavior-preserving migration target was identified.
  - Recommendation:
    defer `PLAINTEXT_TERMINAL_ANSWER` migration and close the Terminal Answers
    slice for now.

---

#### Phase 8 Step 4P: Terminal Answers Slice Closure / Deferred Final-Answer Migration

- **Status**: Done.
- **Goal**: Close the current Terminal Answers consumer-migration slice and record final-answer-path migration as deferred.
- **Allowed**: Documentation updates and closure review only.
- **Forbidden**:
  - Final-answer authority changes
  - Stop-gate authority changes
  - Consumer migration
  - Production behavior changes
- **Completed Outcome**:
  - The Terminal Answers consumer-migration slice is complete for now.
  - Completed migrations:
    - `LEAKED_SYSTEM_RESULT`
    - `INVALID_OR_TRUNCATED_TERMINAL_TEXT`
    - `INTERNAL_SUMMARY_LIKE_TEXT`
  - `PLAINTEXT_TERMINAL_ANSWER` / final-answer-path migration is deferred.
  - Checkpoint/board consumers are deferred to a separate board/checkpoint slice.
  - `TerminalAnswerClassifier` remains outside policy, stop-gate, and sole final-answer authority.
  - Legacy fallback/confirmation remains in place where exact parity is not proven.

---

#### Phase 9 Step 1: Plan-First Bundle Execution Design Gate

- **Status**: Done.
- **Goal**: Re-open the Plan-First Bundle Execution thread with a design gate before any implementation.
- **Allowed**: Design-only review and documentation updates.
- **Forbidden**: Dispatch behavior changes before the design gate is complete.
- **Completed Outcome**:
  - The current action / bundle execution path was inventoried.
  - The current compiler IR usage, `ActionPolicy` boundary, `ResponsePipeline` orchestration role, and post-dispatch side-effect boundary were documented.
  - The design gate concluded that the slice is safe to continue only as a narrow plan-first bundle/action execution refactor.
  - Final-answer, stop-gate, and board/checkpoint migrations remain out of scope.
  - The current design baseline is documented in `docs/architecture/plan-first-bundle-execution-design.md`.

#### Phase 9 Step 2: ExecutionPlan Producer/Consumer Contract Design

- **Status**: Done.
- **Goal**: Define the smallest behavior-preserving producer/consumer contract that can move bundle/action dispatch closer to true plan-first execution.
- **Allowed**:
  - Design-only review
  - ExecutionPlan contract inventory
  - Characterization-test planning
- **Forbidden**:
  - Dispatch side-effect changes
  - `ActionPolicy` authority changes
  - Final-answer or stop-gate changes
  - Parser rewrite
- **Completed Outcome**:
  - The current producer/consumer flow is documented:
    `ResponsePipelineStagesMixin._build_execution_plan(...)` produces the plan,
    `ActionPolicy` validates before `dispatch_ready`, and `DispatchPipeline`
    still executes raw `segments`.
  - The minimal `ExecutionPlan` contract for the first migrated slice is documented.
  - The first migration candidate is narrowed to the single-action dispatch-ready
    path where compiler IR already provides exactly one authoritative `ActionOpIR`.
  - `segments` fallback remains explicitly required whenever IR parity is not proven
    or the path is outside the migrated slice.

#### Phase 9 Step 3: ExecutionPlan Contract Characterization Tests

- **Status**: Done.
- **Goal**: Lock down the current `ExecutionPlan` producer behavior and add
  plan-vs-segment parity coverage before any dispatch consumer migration.
- **Allowed**:
  - Test-only additions
  - Characterization coverage for `ExecutionPlan`
  - Parity coverage for the first migrated slice
- **Forbidden**:
  - Dispatch behavior changes
  - `ActionPolicy` authority changes
  - Execution-path migration in this step
- **Completed Outcome**:
  - Current `ExecutionPlan` field population is characterized.
  - Compiler IR plan-first candidate fields are characterized.
  - Parity coverage exists for plan-derived versus segment-derived action
    summaries on the first migrated single-action bundle path.
  - Fallback behavior is locked down for non-migrated paths.
  - No production behavior changed.

#### Phase 9 Step 4: ExecutionPlan First Producer Migration / Dispatch Consumer Preflight

- **Status**: Done.
- **Goal**: Review the characterized contract and decide whether the first
  narrow producer or dispatch-consumer migration is safe.
- **Allowed**:
  - Read-only code inspection
  - Design-only review
  - Risk analysis for the first migrated slice
- **Forbidden**:
  - Dispatch behavior changes
  - `ActionPolicy` authority changes
  - Execution-path migration in this step
- **Completed Outcome**:
  - The first implementation target is chosen:
    a narrow dispatch bridge/helper for the single-action dispatch-ready slice.
  - Broad producer rewrite is deferred.
  - Full consumer replacement is deferred.
  - Required compatibility fallback points are confirmed.
  - Step 5 is limited to a bridge implementation with explicit segment fallback.

#### Phase 9 Step 5A: Dispatch Bridge Parity Probe

- **Status**: Done.
- **Goal**: Add the first narrow dispatch-boundary parity probe for the
  single-action dispatch-ready slice while preserving the current
  segment-based dispatch path.
- **Allowed**:
  - Narrow dispatch-boundary helper/adapter work
  - Tests for eligible single-action bridge behavior
  - Compatibility fallback preservation
- **Forbidden**:
  - Broad producer rewrite
  - Multi-action batch migration
  - `ActionPolicy` authority changes
  - Final-answer, stop-gate, board/checkpoint, or parser changes
  - Fallback removal
- **Completed Outcome**:
  - The parity probe is implemented only for the eligible single-action slice.
  - Actual dispatch remains segment-driven.
  - The probe returns the existing `segments`, not a new plan-authoritative
    dispatch input.
  - Eligibility requires exact IR/segment payload parity and exact action-effect
    summary parity.
  - Unsupported action shapes still fall back.
  - No observable dispatch behavior changed.

#### Phase 9 Step 5B: IR-Derived Dispatch Candidate Contract

- **Status**: Done.
- **Goal**: Define the first lossless IR-derived dispatch candidate contract for
  the eligible single-action slice, using the Step 5A parity evidence as the gate.
- **Allowed**:
  - Read-only code inspection
  - Design-only review
  - Contract design
  - Parity/risk analysis
- **Forbidden**:
  - Broad producer rewrite
  - Dispatch behavior changes
  - Fallback removal without explicit parity proof
  - Multi-action migration
- **Completed Outcome**:
  - The current segment-dispatch input contract is documented.
  - The first IR-derived candidate surface is defined as a narrow internal
    candidate contract for the eligible single-action slice.
  - Losslessness rules are explicit.
  - File-content-backed and multi-action paths remain excluded.
  - Step 5C implementation can proceed narrowly without changing dispatch behavior.

#### Phase 9 Step 5C: IR-Derived Dispatch Candidate Implementation

- **Status**: Done.
- **Goal**: Implement the first internal IR-derived dispatch candidate surface
  for the eligible single-action slice while keeping actual dispatch segment-driven.
- **Allowed**:
  - Narrow helper/type work for candidate construction
  - Test coverage for candidate eligibility and fallback
  - Segment-dispatch preservation
- **Forbidden**:
  - Dispatch side-effect changes
  - Fallback removal
  - Multi-action migration
  - File-content-backed candidate migration
  - `ActionPolicy` authority changes
- **Completed Outcome**:
  - A lossless `PlanDispatchCandidate` is built for the eligible slice.
  - Non-eligible paths still produce no candidate and fall back explicitly.
  - Actual dispatch remains segment-driven.
  - The parity probe remains compatible and now builds on the candidate surface.

#### Phase 9 Step 5D: Candidate-to-Dispatcher Bridge Preflight

- **Status**: Done.
- **Goal**: Review the implemented candidate surface and decide whether a
  candidate-to-dispatcher bridge can be introduced without behavior drift.
- **Allowed**:
  - Read-only code inspection
  - Design-only review
  - Risk analysis for bridge introduction
- **Forbidden**:
  - Dispatch side-effect changes
  - Fallback removal
  - Multi-action migration
  - `ActionPolicy` authority changes
- **Completed Outcome**:
  - Direct candidate-driven dispatcher input is not approved.
  - Synthetic candidate-derived segment adaptation is deferred.
  - The safest next step is metadata-only bridging while dispatch remains
    segment-driven.

#### Phase 9 Step 5E: Candidate Metadata Bridge Implementation

- **Status**: Done.
- **Goal**: Surface `PlanDispatchCandidate` as metadata/bridge evidence only,
  while keeping actual dispatch segment-driven.
- **Allowed**:
  - Narrow metadata plumbing at the dispatch boundary
  - Test coverage for eligible candidate metadata
  - Compatibility/fallback preservation
- **Forbidden**:
  - Dispatch side-effect changes
  - Candidate-driven dispatcher input
  - Synthetic segment replacement
  - Multi-action migration
  - `ActionPolicy` authority changes
- **Completed Outcome**:
  - Eligible paths surface candidate metadata without changing dispatcher input.
  - `processed_segs` / dispatch outcome behavior remains unchanged.
  - Fallback remains explicit on all non-eligible paths.
  - Actual dispatch remains segment-driven.

#### Phase 9 Step 5F: Metadata Bridge Parity Review / Candidate Adapter Decision

- **Status**: Done.
- **Goal**: Review the metadata bridge evidence and decide whether any
  candidate-derived adapter is justified for the eligible single-action slice.
- **Allowed**:
  - Read-only code inspection
  - Design-only review
  - Parity/risk analysis
- **Forbidden**:
  - Dispatch side-effect changes
  - Synthetic segment replacement without explicit approval
  - Direct candidate-driven dispatcher input
  - Fallback removal
  - Multi-action migration
- **Completed Outcome**:
  - Synthetic segment adapter is a no-go for the immediate next step.
  - Direct candidate-driven dispatcher input remains a no-go.
  - The Step 5A-5F bridge sub-slice is complete.
  - The safest next step is to return to producer-side narrowing / ExecutionPlan enrichment review.

#### Phase 9 Step 6: Plan-First Producer Narrowing / ExecutionPlan Enrichment Review

- **Status**: Done.
- **Goal**: Review the next safe producer-side plan-first slice after the bridge
  sub-slice, including whether `ExecutionPlan` needs enrichment before any further
  dispatch narrowing.
- **Allowed**:
  - Read-only code inspection
  - Design-only review
  - Producer-side contract analysis
- **Forbidden**:
  - Dispatch side-effect changes
  - Synthetic segment adapter work
  - Candidate-driven dispatcher input
  - Fallback removal
  - `ActionPolicy` authority changes
- **Completed Outcome**:
  - The producer-side `ExecutionPlan` creation path was reviewed.
  - The review concluded that `ExecutionPlan` is not yet rich enough to be the sole source for a plan-first dispatch consumer, as it lacks action payloads and other metadata.
  - The safest next step is to enrich `ExecutionPlan` with new observational-only metadata fields.
  - This enrichment must not authorize dispatch, replace segments, bypass `ActionPolicy`, or change side effects.
  - A new Step 6A was proposed to design this enrichment.
- **Done When**:
  - The review was completed and documented.
  - The next implementation shape (Step 6A) was proposed.

---

#### Phase 9 Step 6A: ExecutionPlan Observational Enrichment Implementation

- **Status**: Done.
- **Goal**: Enrich `ExecutionPlan` with new observational-only metadata fields.
- **Allowed**:
  - Add non-authoritative metadata fields to `ExecutionPlan`.
  - Populate them in `ResponsePipelineStagesMixin._build_execution_plan(...)`.
  - Add characterization tests for new field population.
- **Forbidden**:
  - Consumer logic changes.
  - Dispatch behavior changes.
  - Candidate-driven dispatch or synthetic segment adapter.
  - Fallback removal.
  - `ActionPolicy` authority changes.
  - Parser, `history.py`, final-answer, or board/checkpoint changes.
- **Completed Outcome**:
  - `ExecutionPlan` was enriched with non-authoritative observational metadata fields.
  - The producer now populates these fields from `compiler_ir`.
  - Characterization tests were added to lock down the new field population.
  - No consumer logic was changed, and no dispatch behavior was changed.
- **Done When**:
  - The new fields were added to `ExecutionPlan` as observational-only metadata.
  - The producer populates them for the eligible plan-first slice.
  - Characterization tests pass.
  - No dispatch behavior has changed.

---

#### Phase 9 Step 6B: ExecutionPlan Enrichment Parity Review / Consumer Narrowing Decision

- **Status**: Done.
- **Goal**: Review the enriched `ExecutionPlan` and decide if a narrow consumer migration is safe.
- **Allowed**:
  - Read-only code inspection.
  - Design-only documentation updates.
- **Forbidden**:
  - Implementation before design approval.
  - Any production code or test changes.
  - Any consumer migration.
  - Any dispatch behavior changes.
- **Completed Outcome**:
  - The review concluded that the enriched `ExecutionPlan` metadata is not yet sufficient to replace the `DispatchPipeline`'s direct `compiler_ir` and `segments` checks.
  - `candidate_eligibility_status` is a coarse producer-side hint and must not be used for dispatch authority.
  - The safest next step is to use the new metadata as diagnostic-only input to the `DispatchPipeline` candidate builder.
  - A new Step 6C was proposed for this diagnostic alignment.
- **Done When**:
  - The review was complete and a decision on the next consumer migration was documented.

---

#### Phase 9 Step 6C: Candidate Eligibility Metadata Alignment

- **Status**: Done.
- **Goal**: Use the new `ExecutionPlan` metadata as diagnostic input to the `DispatchPipeline` candidate builder and log parity.
- **Allowed**:
  - `DispatchPipeline` can read `ExecutionPlan` metadata.
  - Add diagnostic logging to compare `ExecutionPlan` metadata with `DispatchPipeline`'s own checks.
- **Forbidden**:
  - Any change to dispatch behavior.
  - Removing existing `compiler_ir` or `segments` checks in `DispatchPipeline`.
  - Using `ExecutionPlan` metadata for dispatch authority.
  - Any consumer migration.
- **Completed Outcome**:
  - The `DispatchPipeline` now reads `ExecutionPlan` metadata for diagnostic logging only.
  - A new `dispatch_bridge_metadata_parity` log field compares producer-side metadata with consumer-side checks.
  - No dispatch behavior was changed.
  - The candidate builder remains authoritative via direct `compiler_ir` and `segments` inspection.
- **Done When**:
  - `DispatchPipeline` reads the new metadata for logging/diagnostics.
  - Parity between producer-side metadata and consumer-side checks is logged.
  - No dispatch behavior has changed.

---

#### Phase 9 Step 6D: Metadata Alignment Review / Producer-Consumer Contract Closure

- **Status**: Done.
- **Goal**: Review the diagnostic parity evidence from Step 6C and decide if the producer/consumer contracts are aligned enough to simplify the consumer.
- **Allowed**:
  - Read-only code inspection.
  - Design-only documentation updates.
- **Forbidden**:
  - Implementation before design approval.
  - Any production code or test changes.
  - Any consumer migration or simplification.
  - Any dispatch behavior changes.
- **Completed Outcome**:
  - The review of diagnostic parity evidence is complete.
  - The producer-side `ExecutionPlan` metadata is useful for diagnostics but not yet sufficient to replace the consumer's direct `compiler_ir` and `segments` checks.
  - No consumer simplification is approved.
  - Candidate-driven dispatch and synthetic segment adapters remain deferred.
  - The Phase 9 Step 6A-6D producer/metadata alignment mini-slice is complete.
- **Done When**:
  - The review was complete and a decision on the next consumer-side step was documented.

---

#### Phase 9 Step 7: Plan-First Dispatch Boundary Closure / Next Slice Selection

- **Status**: Done.
- **Goal**: Review the completed Step 5/6 bridge and metadata work and decide on the next safe plan-first migration slice.
- **Allowed**:
  - Read-only code inspection.
  - Design-only documentation updates.
- **Forbidden**:
  - Implementation before design approval.
  - Any production code or test changes.
  - Any dispatch behavior changes.
- **Completed Outcome**:
  - The review of the Phase 9 plan-first dispatch boundary work is complete.
  - The current slice is closed for now. Candidate-driven dispatch and synthetic segment adapters remain deferred.
  - The next safest slice is to address the deferred board/checkpoint consumers.
- **Done When**:
  - The review was complete and a decision on the next slice was documented.

---

### Phase 9: Plan-First Bundle Execution

- **Goal**: Refactor bundle/action execution toward a plan-first model where compiler/IR owns structure, `ActionPolicy` owns permission, and the execution layer owns side effects.
- **Allowed**: Narrow producer/consumer migrations that preserve behavior and keep legacy fallback where parity is not yet proven.
- **Forbidden**:
  - Final-answer authority changes
  - Stop-gate changes
  - Board/checkpoint migration in this slice
  - Dispatch side-effect changes
- **Done When**:
  - The first migrated slice executes from an authoritative `ExecutionPlan` contract.
  - Legacy segment-based dispatch fallback is reduced to explicitly documented compatibility paths only.

---

### Phase 10: Board/Checkpoint Consumer Migration

#### Phase 10 Step 1: Board/Checkpoint Consumer Slice Preflight

- **Status**: Done.
- **Goal**: Re-open the deferred board/checkpoint consumer migration slice with a design-only preflight.
- **Allowed**:
  - Read-only code inspection of `PlanBoardStageHandler` and `MemoryBoardStageHandler`.
  - Inventory and characterization of current board/checkpoint consumer behavior.
  - Design-only documentation updates.
- **Forbidden**:
  - Implementation before design approval.
  - Any production code or test changes.
  - Any dispatch, final-answer, or `ActionPolicy` changes.
- **Completed Outcome**:
  - The preflight review is complete and documented in `docs/architecture/board-checkpoint-consumer-slice-design.md`.
  - The review identified a major architectural blocker: the board/checkpoint stage runs *before* the classification stage, preventing consumers from accessing typed semantic results.
  - **Conclusion**: **NO-GO** for immediate consumer migration.
  - The next step is `Phase 10 Step 2: Board/Checkpoint Characterization Tests`.

---

#### Phase 10 Step 2: Board/Checkpoint Characterization Tests

- **Status**: Done.
- **Goal**: Add orchestration characterization tests to lock down the behavior of `_run_checkpoint_stage` and its interaction with mocked board handlers.
- **Allowed**:
  - Test-only additions to lock down existing behavior.
- **Forbidden**:
  - Any production code changes.
  - Any consumer migration.
  - Any pipeline reordering.
- **Completed Outcome**:
  - Orchestration characterization tests were added to `tests/test_response_pipeline_stages.py` to lock down the orchestration logic of `_run_checkpoint_stage`.
  - The tests cover outcomes from mocked board handlers, such as `memory_checkpoint_only` and `memory_checkpoint_and_text`.
  - The internal parsing and commit logic of the board handlers themselves remains deferred.
  - No production code was changed.
  - The next step is to design the pipeline reordering.

---

#### Phase 10 Step 3: Pipeline Reordering Design

- **Status**: Done.
- **Goal**: Design a risk-mitigated plan to reorder the `ResponsePipeline` to run classification before the checkpoint stage.
- **Allowed**:
  - Design-only documentation updates.
- **Forbidden**:
  - Implementation before design approval.
- **Completed Outcome**:
  - The design is complete. A full reordering was rejected as too high-risk.
  - The chosen design is a low-risk "Early Structural Diagnosis Prepass" using a new, side-effect-minimal helper to make compiler facts available to the checkpoint stage without changing behavior.
  - The prepass must not include side effects like terminal-answer classification or `invalid_kind` mutation.
  - No production code was changed.
  - The next step is to implement this prepass.

---

#### Phase 10 Step 4: Pure Structural Diagnosis Extraction + Early Prepass

- **Status**: Done.
- **Goal**: Add a pure structural diagnosis prepass before the checkpoint stage without changing classification-stage authority.
- **Allowed**:
  - Create a new, side-effect-free helper for pure structural analysis.
  - Add a new prepass before `_run_checkpoint_stage` that calls the pure helper.
- **Forbidden**:
  - Any change to user-visible behavior, dispatch, or policy.
  - The new pure helper having any side effects (`invalid_kind` mutation, shadow logging, etc.).
  - The early prepass calling anything other than the pure helper.
  - Migrating the board handlers to use the new data.
- **Completed Outcome**:
  - A pure `_run_structural_diagnosis_prepass` helper was implemented.
  - It runs before the checkpoint stage, and its result is attached to `CheckpointStageState` for observation.
  - `_apply_compiler_diagnosis` remains the existing effectful classification-stage path and continues to recompute its own analysis on normalized response.
  - No production behavior was changed.

---

#### Phase 10 Step 4B: Structural Prepass Parity / Reuse Decision

- **Status**: Done.
- **Goal**: Analyze parity between the prepass analysis (on raw response) and classification-stage analysis (on normalized response) and decide if reuse is safe.
- **Allowed**:
  - Design-only documentation updates.
  - Parity analysis via logging or temporary test changes.
- **Forbidden**:
  - Any production code changes.
- **Completed Outcome**:
  - The review concluded that reusing the prepass analysis is not safe due to potential mismatches between raw and normalized responses.
  - **Decision**: **NO-GO** for reuse. The prepass analysis remains observational, and the classification stage will continue to recompute its own diagnosis.
  - The next step is to design the first consumer migration.

---

#### Phase 10 Step 5: First Board/Checkpoint Consumer Migration (Design)

- **Status**: Done.
- **Goal**: Design the first narrow, behavior-preserving migration of a board/checkpoint consumer using the newly available prepass compiler facts.
- **Allowed**:
  - Design-only documentation updates.
- **Forbidden**:
  - Any production code or test changes.
- **Completed Outcome**:
  - The first safe migration target is a **board/checkpoint structural parity logging bridge** in or near `_run_checkpoint_stage`.
  - `MemoryBoardStageHandler` and `PlanBoardStageHandler` remain authoritative for parsing, commits, and checkpoint outcome flags.
  - Prepass compiler facts remain structural and observational only.
  - A dedicated board/checkpoint semantic model is deferred until parity evidence exists.
  - Direct board handler commit migration is a no-go for the next step.
  - The next step is `Phase 10 Step 6: Board/Checkpoint Structural Parity Logging Implementation`.

---

#### Phase 10 Step 6: Board/Checkpoint Structural Parity Logging Implementation

- **Status**: Done.
- **Goal**: Implement diagnostic-only parity logging between prepass compiler facts and legacy board/checkpoint handler outcomes.
- **Allowed**:
  - Narrow logging / checkpoint-state observation updates only.
  - Characterization tests for the new diagnostic bridge if needed.
- **Forbidden**:
  - Any authority transfer to board handlers.
  - Any board commit logic changes.
  - Any mutation of checkpoint outcome flags from prepass facts.
  - Any reuse of prepass analysis inside `_run_classification_stage`.
  - Any dispatch, final-answer, stop-gate, `ActionPolicy`, parser, or `history.py` changes.
- **Completed Outcome**:
  - Prepass-vs-legacy checkpoint parity is now observable in `_run_checkpoint_stage`.
  - The bridge logs compiler/prepass structural facts alongside legacy plan/memory checkpoint outcome categories.
  - Missing compiler analysis is tolerated, and logging failures do not affect runtime behavior.
  - No authority transfer happened. Legacy board handlers remain authoritative.
  - No board commit, checkpoint routing, dispatch, final-answer, stop-gate, `ActionPolicy`, parser, or `history.py` behavior changed.

---

#### Phase 10 Step 7: Board/Checkpoint Parity Review / First Authority Migration Decision

- **Status**: Done.
- **Goal**: Review parity evidence from Step 6 and decide whether any first authority migration is safe.
- **Allowed**:
  - Read-only analysis.
  - Docs-only design updates.
- **Forbidden**:
  - Any authority transfer before the review is complete.
  - Any board commit logic changes.
  - Any checkpoint routing changes.
  - Any reuse of prepass analysis inside `_run_classification_stage`.
- **Completed Outcome**:
  - **NO-GO** for a first authority migration at this time.
  - Step 6 parity logs are useful observability, but they are not enough to replace handler parsing or commits.
  - Mismatch reasons must be treated as diagnostic hints only.
  - Legacy board handlers remain authoritative.
  - The next safe step is direct characterization of board handler parsing/commit behavior.

---

#### Phase 10 Step 8: Direct Board Handler Parsing/Commit Characterization Tests

- **Status**: Done.
- **Goal**: Add direct characterization tests for `MemoryBoardStageHandler` and `PlanBoardStageHandler` parsing, cleanup, commit-aware behavior, and checkpoint outcome decisions.
- **Allowed**:
  - Tests only.
  - Docs-only updates after tests pass.
- **Forbidden**:
  - Any production code changes.
  - Any authority transfer.
  - Any board commit logic changes.
  - Any checkpoint routing changes.
  - Any reuse of prepass analysis inside `_run_classification_stage`.
- **Completed Outcome**:
  - Direct handler characterization tests now lock down memory-board and plan-board parsing/cleanup/commit-aware decision surfaces.
  - The current raw-vs-clean behavior and checkpoint outcome categories are now explicit.
  - A surprising current behavior was recorded: `MemoryBoardStageHandler` resets its local checkpoint-only streak before incrementing it again.
  - No production code changed.
  - Authority remains unchanged: legacy board handlers are still authoritative and compiler/prepass facts remain structural-only observations.

---

#### Phase 10 Step 9: Board/Checkpoint Semantic Model Design

- **Status**: Done.
- **Goal**: Design the smallest semantic model that can describe board/checkpoint outcomes without transferring authority yet.
- **Allowed**:
  - Read-only code inspection.
  - Docs-only design work.
- **Forbidden**:
  - Any production code changes.
  - Any authority transfer.
  - Any board commit logic or checkpoint routing changes.
  - Any reuse of prepass analysis inside `_run_classification_stage`.
- **Completed Outcome**:
  - A smallest-safe observational model is now defined: `BoardCheckpointSemanticResult`.
  - The model is separate from `TerminalAnswerClassifier`.
  - It describes both legacy handler outcomes and compiler/prepass structural facts without transferring authority.
  - The first implementation target is a skeleton + shadow population only.

---

#### Phase 10 Step 10: Board/Checkpoint Semantic Model Skeleton + Shadow Population

- **Status**: Done.
- **Goal**: Add the board/checkpoint semantic model types and populate them observationally from legacy handler outcomes and prepass/compiler facts.
- **Allowed**:
  - Dataclass / enum scaffolding only.
  - Shadow/diagnostic population from already available handler outcomes and prepass facts.
  - Attachment to `CheckpointStageState`.
  - Diagnostic logging or observation.
- **Forbidden**:
  - Any routing change.
  - Any board commit logic change.
  - Any checkpoint flag mutation from the new model.
  - Any authority transfer.
  - Any reuse of prepass analysis inside `_run_classification_stage`.
- **Done When**:
  - The semantic model exists, is populated observationally, and no runtime behavior changes.
- **Completed Outcome**:
  - `BoardCheckpointKind`, `BoardCheckpointSource`, and `BoardCheckpointSemanticResult` now exist.
  - `CheckpointStageState` now carries `board_checkpoint_semantic_result`.
  - `_run_checkpoint_stage(...)` populates the model from legacy board handler outcomes plus compiler/prepass structural facts.
  - Missing compiler analysis falls back safely without affecting runtime behavior.
  - Routing, commit behavior, checkpoint flags, and authority boundaries are unchanged.

---

#### Phase 10 Step 11: Board/Checkpoint Semantic Model Parity Review / First Consumer Migration Decision

- **Status**: Done.
- **Goal**: Review the new observational semantic model and decide whether any first narrow board/checkpoint consumer migration is safe.
- **Allowed**:
  - Read-only review of semantic-model population and parity evidence.
  - Docs-only migration decision work.
- **Forbidden**:
  - Any authority transfer before parity is proven.
  - Any board commit logic or checkpoint routing changes.
  - Any mutation of checkpoint flags from the semantic model.
- **Done When**:
  - A clear GO / NO-GO decision exists for the first consumer migration candidate.
- **Completed Outcome**:
  - The decision is **NO-GO** for authority migration.
  - `BoardCheckpointSemanticResult` is useful but still too coarse for production consumer authority.
  - Presence-level parity is not commit-equivalence proof and is not yet sufficient to replace handler-local parsing, cleanup, or commit-aware outcomes.
  - Legacy board handlers remain authoritative.
  - The semantic model remains observational only.

---

#### Phase 10 Step 12: BoardCheckpoint Semantic Model Refinement + Pure Builder Extraction

- **Status**: Done.
- **Goal**: Refine the observational semantic model and extract `_build_board_checkpoint_semantic_result(...)` into a dedicated pure helper before any consumer migration is reconsidered.
- **Allowed**:
  - Pure-builder extraction.
  - Additional parity fields and characterization coverage.
  - Shadow-only observational refinement.
- **Forbidden**:
  - Any authority transfer.
  - Any board commit logic or checkpoint routing changes.
  - Any mutation of checkpoint flags from the semantic model.
  - Any reuse of prepass analysis inside `_run_classification_stage`.
- **Done When**:
  - The builder is easier to characterize directly and the semantic/parity surface is refined enough for a later migration review.
- **Completed Outcome**:
  - The board/checkpoint semantic-result builder was extracted into a dedicated pure helper module.
  - Direct unit tests now characterize the helper independently from `_run_checkpoint_stage(...)`.
  - Low-risk observational parity fields were added without changing authority or routing.
  - `BoardCheckpointSemanticResult` remains observational only.

---

#### Phase 10 Step 13: First Narrow BoardCheckpoint Consumer Migration

- **Status**: Done.
- **Goal**: Introduce the first safe typed read-through consumer, limited to legacy-derived checkpoint kinds.
- **Allowed**:
  - Legacy-derived typed read-through only.
  - Explicit legacy fallback.
  - Tests proving no behavior drift.
- **Forbidden**:
  - Any compiler/prepass authority transfer.
  - Any board commit logic changes.
  - Any checkpoint routing changes beyond legacy-confirmed typed mirroring.
  - Any mutation of checkpoint flags from compiler/prepass facts.
- **Done When**:
  - A first narrow consumer uses legacy-derived typed kinds without changing runtime behavior.
- **Completed Outcome**:
  - `_run_checkpoint_stage(...)` now reads legacy-derived typed kinds for:
    - `MEMORY_CHECKPOINT_ONLY`
    - `MEMORY_CHECKPOINT_WITH_TEXT`
  - Legacy flags remain the final fallback and win on disagreement.
  - Compiler/prepass-only checkpoint facts still cannot trigger routing.
  - No board commit or routing behavior changed.

---

#### Phase 10 Step 14: Complete Legacy-Derived Typed Read-Through for Board Checkpoint Routing

- **Status**: Done.
- **Goal**: Complete the safe legacy-derived typed read-through micro-slice for checkpoint-routing branches backed by legacy handler bools.
- **Allowed**:
  - Legacy-derived typed read-through only.
  - Explicit legacy fallback.
  - Tests proving no behavior drift.
- **Forbidden**:
  - Any compiler/prepass authority transfer.
  - Any board commit logic changes.
  - Any mutation of checkpoint flags from compiler/prepass facts.
  - Any reuse of prepass analysis inside `_run_classification_stage`.
- **Done When**:
  - All safe legacy-bool-backed checkpoint-routing branches use legacy-derived typed read-through without changing runtime behavior.
- **Completed Outcome**:
  - `_run_checkpoint_stage(...)` now reads legacy-derived typed results for:
    - `MEMORY_CHECKPOINT_ONLY`
    - `MEMORY_CHECKPOINT_WITH_TEXT`
    - `MEMORY_CHECKPOINT_WITH_ACTION`
    - `PLAN_CHECKPOINT_ONLY`
    - `PLAN_CHECKPOINT_WITH_TEXT`
    - `PLAN_CHECKPOINT_WITH_ACTION`
  - Legacy flags remain the final fallback and win on disagreement.
  - Compiler/prepass-only plan and memory checkpoint facts still cannot trigger routing.
  - No board commit or routing behavior changed.

---

#### Phase 10 Step 16: BoardCheckpoint Legacy-Derived Authority Candidate Implementation

- **Status**: Done.
- **Goal**: Reduce scattered checkpoint bool routing logic by centralizing legacy-derived effective-flag resolution in a pure helper without changing authority.
- **Allowed**:
  - Extract a pure effective-flag resolver for plan/memory checkpoint routing.
  - Refactor `_run_checkpoint_stage(...)` to use the resolver.
  - Add direct tests for the resolver and stage-state consistency.
- **Forbidden**:
  - Any compiler/prepass authority transfer.
  - Any board commit logic changes.
  - Any mutation of checkpoint flags from compiler/prepass facts.
  - Any reuse of prepass analysis inside `_run_classification_stage`.
- **Done When**:
  - Effective checkpoint flag resolution is centralized.
  - `CheckpointStageState(...)` consistently uses effective flags once available.
  - Tests prove legacy fallback still wins and compiler/prepass-only facts still cannot trigger routing.

#### Phase 10 Step 17: Use EffectiveCheckpointFlags as the Single Local Checkpoint Routing Surface

- **Status**: Done.
- **Goal**: Make `_run_checkpoint_stage(...)` consistently use `EffectiveCheckpointFlags` as the single local routing/state surface once the resolver has run.
- **Allowed**:
  - Local refactoring inside `_run_checkpoint_stage(...)` to use `EffectiveCheckpointFlags` fields instead of raw legacy bools after resolution.
  - Update tests to confirm no behavior change.
- **Forbidden**:
  - Any observable checkpoint routing behavior change.
  - Any board commit behavior change.
  - Any mutation of checkpoint flags from compiler/prepass facts.
  - Any compiler/prepass-only facts triggering routing.
  - Any change to `PlanBoardStageHandler` or `MemoryBoardStageHandler` behavior.
- **Done When**:
  - `_run_checkpoint_stage(...)` uses `EffectiveCheckpointFlags` as the single local checkpoint routing/state surface after resolution.
  - No compiler/prepass authority was introduced, and no observable routing or commit behavior changed.
  - Legacy board handlers remain authoritative.

#### Phase 10 Step 18: First True Authority Candidate — Legacy-Derived Typed Result Primary With Legacy Fallback

- **Status**: Done.
- **Goal**: Make `BoardCheckpointSemanticResult.kind == MEMORY_CHECKPOINT_ONLY` the primary local signal for the memory checkpoint-only branch, but only when the semantic result is legacy-derived. Keep legacy bool fallback.
- **Allowed**:
  - Add a pure helper for typed-primary resolution for memory checkpoint-only.
  - Use this helper only for the memory checkpoint-only routing decision in `_run_checkpoint_stage(...)`.
- **Forbidden**:
  - Any observable checkpoint routing behavior change.
  - Any board commit behavior change.
  - Any compiler/prepass authority transfer.
  - Any change to `PlanBoardStageHandler` or `MemoryBoardStageHandler` behavior.
- **Done When**:
  - The first true authority narrowing was attempted for the `memory_checkpoint_only` branch.
  - The typed-primary candidate is implemented with a legacy disagreement guard, preserving existing behavior. The typed result cannot change the memory branch category.
  - No compiler/prepass authority was introduced, and no observable routing or commit behavior changed.

#### Phase 10 Step 19: Extend Typed Primary to Remaining Legacy-Derived Memory Branches

- **Status**: Done.
- **Goal**: Extend the typed-primary-with-legacy-fallback pattern to the remaining memory checkpoint branches (`MEMORY_CHECKPOINT_WITH_TEXT`, `MEMORY_CHECKPOINT_WITH_ACTION`).
- **Allowed**:
  - Add pure helpers for typed-primary resolution for the remaining memory branches.
  - Use these helpers in `_run_checkpoint_stage(...)`.
- **Forbidden**:
  - Any observable checkpoint routing behavior change.
  - Any compiler/prepass authority transfer.
  - Any change to `PlanBoardStageHandler` or `MemoryBoardStageHandler` behavior.
- **Done When**:
  - The typed-primary candidate pattern is extended to all memory branches.
  - The implementation remains behavior-preserving with legacy disagreement guards.
  - No observable routing or commit behavior changed.

#### Phase 10 Step 20: Typed-Primary Candidate for Legacy-Derived Plan Branches

- **Status**: Done.
- **Goal**: Extend the typed-primary-with-legacy-fallback pattern to the legacy-derived plan checkpoint branches.
- **Allowed**:
  - Add pure helpers for typed-primary resolution for all plan branches.
  - Use these helpers in `_run_checkpoint_stage(...)`.
- **Forbidden**:
  - Any observable checkpoint routing behavior change.
  - Any compiler/prepass authority transfer.
  - Any change to `PlanBoardStageHandler` or `MemoryBoardStageHandler` behavior.
- **Done When**:
  - The typed-primary candidate pattern is extended to all plan branches.
  - The implementation remains behavior-preserving with legacy disagreement guards.
  - No observable routing or commit behavior changed.

#### Phase 10 Step 21: Consolidate BoardCheckpoint Typed-Primary Candidate Helpers / Reduce Boilerplate

- **Status**: Done.
- **Goal**: Refactor the board/checkpoint typed-primary candidate helpers to reduce boilerplate and improve maintainability.
- **Allowed**:
  - Consolidate the six typed-primary candidate helpers into a generic private helper.
  - Keep public helper signatures and call sites unchanged.
  - Add test coverage for plan helpers to match memory helper coverage.
- **Forbidden**:
  - Any observable checkpoint routing behavior change.
  - Any authority expansion.
  - Any compiler/prepass authority transfer.
- **Done When**:
  - The helpers are consolidated.
  - No authority was expanded, and no observable routing or commit behavior changed.

#### Phase 10 Step 22: First Compiler-Authority Switch for BoardCheckpoint Routing

- **Status**: Done.
- **Goal**: Implement the first real, default-off compiler-authority switch for `PLAN_CHECKPOINT_ONLY`.
- **Allowed**:
  - Add a feature flag for `PLAN_CHECKPOINT_ONLY` compiler authority, default-off.
  - Add a pure helper to resolve the flag based on the switch and clean compiler facts.
  - Update `_run_checkpoint_stage` to use the helper and trigger the plan checkpoint outcome on a compiler-only signal when the switch is on.
- **Forbidden**:
  - Enabling the switch by default.
  - Migrating any other branch.
  - Changing board commit behavior or handler internals.
- **Done When**:
  - The default-off switch is implemented for `PLAN_CHECKPOINT_ONLY`.
  - A stage-level test proves the routing change when the switch is on and proves no change when off.
  - Default behavior is unchanged.

#### Phase 10 Step 23: PLAN_CHECKPOINT_ONLY Compiler Authority Guard Tightening + Angelica Smoke Run

- **Status**: Done.
- **Goal**: Validate and harden the first compiler-authority switch, run smoke tests, and decide whether to expand or close the slice.
- **Allowed**:
  - Harden the predicate in `resolve_plan_checkpoint_only_with_compiler_switch`.
  - Add more fallback tests.
  - Manually enable the switch and run smoke tests.
- **Forbidden**:
  - Enabling the switch by default in production code.
  - Expanding authority to other branches before the review.
- **Done When**:
  - The authority predicate is hardened and tested.
  - Smoke tests are complete and the outcome is documented.
  - A decision is made to close the slice and proceed to Phase 11.

#### Phase 10 Governance Update: Branch Authority Switches

- **Status**: Done.
- **Goal**: Document the new refactor governance principle of using explicit, branch-level switches to manage the transition from legacy to compiler-driven authority.
- **Outcome**:
  - The new strategy is now documented in `docs/architecture/board-checkpoint-consumer-slice-design.md`.
  - Key principles:
    - Accessors/resolvers are the common consumption path for typed semantic decisions.
    - Branch-specific switches control whether legacy or compiler/typed authority wins.
    - Switches must be centralized and documented.
    - Smoke tests are required after enabling compiler authority.
    - Regressions found via compiler authority should be fixed in the compiler/semantic layer, not bypassed with more legacy logic.

#### Phase 10 Step 24: Central Refactor Switch Registry TOML

- **Status**: Done.
- **Goal**: Introduce a centralized TOML registry for refactor authority switches.
- **Allowed**:
  - Create registry file.
  - Load switch defaults from the registry.
  - Keep default behavior controlled and explicit.
- **Forbidden**:
  - Broad authority expansion in this step.
  - Hardcoded scattered switch constants.
  - Changing unrelated runtime behavior.
- **Done When**:
  - The central registry was created in `modules/agent/orchestration/config/refactor_switches.toml`.
  - The existing `PLAN_CHECKPOINT_ONLY` switch was wired to the registry.
  - Tests prove defaults are stable.
  - No authority was expanded.

#### Phase 10 Step 25: Refactor Switch Registry Smoke Profile

- **Status**: Done.
- **Goal**: Add a practical way to run smoke tests with selected compiler-authority switches enabled through a separate registry profile, while keeping production/default registry safe.
- **Allowed**:
  - Add an environment variable override for the switch registry path.
  - Add a smoke-test TOML profile.
  - Update tests to cover the override mechanism.
- **Forbidden**:
  - Enabling compiler authority in the default `refactor_switches.toml`.
  - Adding new authority branches.
  - Changing runtime behavior unless the smoke override is used.
- **Completed Outcome**:
  - The switch registry loader now supports an `ANGELICA_REFACTOR_SWITCH_REGISTRY` environment variable.
  - A `refactor_switches.smoke.toml` profile was added to enable `PLAN_CHECKPOINT_ONLY` compiler authority for validation.
  - The default registry remains unchanged, with all switches set to `legacy`.
  - No runtime behavior changed unless the smoke override is used.

---

#### Phase 10 Step 26: Run Angelica smoke with PLAN_CHECKPOINT_ONLY compiler-authority profile

- **Status**: Pending explicit approval.
- **Goal**: Run Angelica smoke tests with the `PLAN_CHECKPOINT_ONLY` compiler-authority switch enabled via the smoke profile.
- **Allowed**:
  - Run smoke tests using the `ANGELICA_REFACTOR_SWITCH_REGISTRY` override.
  - Document any behavior drift or regressions.
- **Forbidden**:
  - Committing enabled switches to the main branch without approval.
  - Fixing regressions in this step; they must be documented for a separate fix-forward step.

#### Phase 10 Step 26B: Synthetic Smoke Harness + Self-Closing Subgoal Compiler Fix

- **Status**: Done.
- **Goal**: Fix the concrete compiler gap found by targeted Angelica smoke and add deterministic synthetic smoke coverage for the `PLAN_CHECKPOINT_ONLY` compiler-authority branch.
- **Completed Outcome**:
  - The parser/compiler now recognizes self-closing `<subgoal .../>` and `<subgoal ... />` as structural checkpoint/subgoal tags.
  - Safe board-only checkpoint protocol now compiles to `CHECKPOINT_ONLY` instead of `PURE_PLAINTEXT` or ambiguous invalid fallback.
  - Deterministic synthetic smoke coverage was added for:
    - self-closing `PLAN_CHECKPOINT_ONLY`
    - checkpoint-with-text negative control
    - checkpoint-with-action negative control
    - action-only negative control
  - The default registry remains unchanged, with all relevant switches on `legacy`.
  - No runtime behavior changed outside the smoke-profile override.
- **Next**:
  - Phase 10 Step 26C: rerun targeted Angelica smoke with the `PLAN_CHECKPOINT_ONLY` compiler-authority profile.

#### Phase 10 Step 26D: BoardCheckpoint Authority-Source Logging

- **Status**: Done.
- **Goal**: Add explicit diagnostics that distinguish shadow parity from actual board/checkpoint authority selection.
- **Completed Outcome**:
  - A new authority-resolution diagnostic was added for `board_checkpoint.plan_checkpoint_only`.
  - The logged data now makes it explicit whether the effective branch decision came from:
    - `legacy`
    - `compiler`
    - `legacy_fallback`
  - Tests cover:
    - default registry legacy mode
    - smoke-profile compiler selection on an eligible compiler-only path
    - compiler-switch fallback on incompatible typed facts
    - non-checkpoint action-only negative control
  - No routing or behavior changed.
  - The default registry remains `legacy`.
- **Next**:
  - Phase 27 Step 1: Board/Checkpoint Synthetic Smoke Matrix Expansion.

#### Phase 27: Synthetic Smoke Matrix Expansion Plan

- **Status**: Planned.
- **Goal**: Make synthetic smoke a required precondition for all branch-authority switches.
- **Policy**:
  - Synthetic smoke is mandatory before enabling compiler authority for any branch.
  - Live Angelica smoke remains required, but cannot replace deterministic branch coverage.
- **Initial matrix scope**:
  - Board/checkpoint branches
  - Terminal-answer / final-answer branches
  - Dispatch / action branches
  - Recovery / invalid-output branches
  - Intent / protocol branches

#### Phase 27 Step 1: Board/Checkpoint Synthetic Smoke Matrix Expansion

- **Status**: Done.
- **Goal**: Expand deterministic synthetic smoke coverage across the board/checkpoint slice so future compiler-authority switches can be validated branch-by-branch.
- **Completed Outcome**:
  - Added coverage for:
    - `PLAN_CHECKPOINT_ONLY`
    - `PLAN_CHECKPOINT_WITH_TEXT`
    - `PLAN_CHECKPOINT_WITH_ACTION`
    - `MEMORY_CHECKPOINT_ONLY`
    - `MEMORY_CHECKPOINT_WITH_TEXT`
    - `MEMORY_CHECKPOINT_WITH_ACTION`
    - mixed plan+memory checkpoint
    - action-only negative control
    - plaintext-only negative control
    - invalid checkpoint/think negative control
  - The default registry remains `legacy`.
  - No runtime behavior changed.
- **Next**:
  - Phase 27 Step 2: enable/validate compiler authority for the next board/checkpoint branch via smoke profile.

#### Phase 27 Step 2: `PLAN_CHECKPOINT_WITH_TEXT` Smoke-Profile Compiler Authority

- **Status**: Done.
- **Goal**: Enable the next narrow non-action plan-checkpoint branch via the smoke profile only, using typed semantic result -> resolver -> branch switch -> effective decision.
- **Completed Outcome**:
  - Added branch-specific authority resolution and authority-source diagnostics for `board_checkpoint.plan_checkpoint_with_text`.
  - The smoke registry now enables:
    - `board_checkpoint.plan_checkpoint_only = "compiler"`
    - `board_checkpoint.plan_checkpoint_with_text = "compiler"`
  - Synthetic smoke validates:
    - default-registry legacy behavior for clean `PLAN_CHECKPOINT_WITH_TEXT`
    - smoke-profile compiler authority selection for clean `PLAN_CHECKPOINT_WITH_TEXT`
    - negative controls for checkpoint-only, checkpoint-with-action, memory-checkpoint-with-text, and invalid open-`<think>` cases
  - The default registry remains `legacy`.
  - No runtime behavior changed under the default registry.
- **Next**:
  - Phase 27 Step 3: rerun live Angelica smoke for `board_checkpoint.plan_checkpoint_with_text` under the smoke profile.

#### Phase 27 Step 3: `PLAN_CHECKPOINT_WITH_TEXT` Live Angelica Smoke

- **Status**: Done.
- **Goal**: Confirm that the smoke-profile compiler-authority branch works in a real Angelica run, not only in deterministic synthetic coverage.
- **Completed Outcome**:
  - Targeted live Angelica smoke passed.
  - Compiler authority was selected for `board_checkpoint.plan_checkpoint_with_text`.
  - Structural parity remained aligned.
  - No fallback was used.
  - No runtime crash occurred.
  - The default registry remains `legacy`.
- **Next**:
  - Phase 27 Step 4: enable/validate compiler authority for `board_checkpoint.plan_checkpoint_with_action` via smoke profile.

#### Phase 27 Step 4: `PLAN_CHECKPOINT_WITH_ACTION` Smoke-Profile Compiler Authority

- **Status**: Done.
- **Goal**: Enable the next plan-domain sibling branch under the smoke profile only, while preserving action availability and preventing any checkpoint-only/text-only swallowing of the dispatch path.
- **Completed Outcome**:
  - Added branch-specific authority resolution and authority-source diagnostics for `board_checkpoint.plan_checkpoint_with_action`.
  - The smoke registry now enables:
    - `board_checkpoint.plan_checkpoint_only = "compiler"`
    - `board_checkpoint.plan_checkpoint_with_text = "compiler"`
    - `board_checkpoint.plan_checkpoint_with_action = "compiler"`
  - Synthetic smoke validates:
    - default-registry legacy behavior for clean `PLAN_CHECKPOINT_WITH_ACTION`
    - smoke-profile compiler authority selection for clean `PLAN_CHECKPOINT_WITH_ACTION`
    - negative controls for:
      - `PLAN_CHECKPOINT_ONLY`
      - `PLAN_CHECKPOINT_WITH_TEXT`
      - `MEMORY_CHECKPOINT_WITH_ACTION`
      - action-only
      - mixed plan+memory+action
      - invalid open-`<think>` checkpoint action
  - No dispatch/action behavior changed.
  - The default registry remains `legacy`.
  - No runtime behavior changed under the default registry.
- **Next**:
  - Phase 27 Step 5: live Angelica smoke for `board_checkpoint.plan_checkpoint_with_action` under the smoke profile.

#### Phase 27 Step 5: `PLAN_CHECKPOINT_WITH_ACTION` Live Angelica Smoke

- **Status**: Done.
- **Goal**: Confirm that the smoke-profile compiler-authority action-bearing plan-checkpoint branch works in a real Angelica run without swallowing dispatch.
- **Completed Outcome**:
  - Targeted live Angelica smoke passed.
  - Compiler authority was selected for `board_checkpoint.plan_checkpoint_with_action`.
  - No fallback was used.
  - The action/dispatch path remained preserved through:
    - `action_policy`
    - `response_pipeline`
    - `pre_dispatch_pipeline`
  - Structural parity remained aligned.
  - No runtime crash occurred.
  - The default registry remains `legacy`.
- **Next**:
  - Phase 27 Step 6: close the plan-domain board/checkpoint compiler-authority smoke slice and select the next validation domain.

#### Phase 27 Step 6: Plan-Domain Board/Checkpoint Smoke Closure

- **Status**: Done.
- **Goal**: Close the validated plan-domain board/checkpoint compiler-authority smoke slice without enabling production authority by default.
- **Completed Outcome**:
  - The plan-domain branches validated under the smoke profile are:
    - `PLAN_CHECKPOINT_ONLY`
    - `PLAN_CHECKPOINT_WITH_TEXT`
    - `PLAN_CHECKPOINT_WITH_ACTION`
  - Each of those branches now has:
    - synthetic smoke coverage
    - authority diagnostics
    - live Angelica smoke pass under the smoke profile
  - Smoke profile may keep the plan-domain compiler switches enabled for continued validation.
  - The default registry remains `legacy`; no production authority flip happened.
  - No memory checkpoint authority transfer happened.
  - No board commit logic changed.
  - No dispatch/action behavior changed.
  - Memory checkpoint branches remain deferred because they include memory-engine commit semantics.
- **Next**:
  - Phase 28 Step 1: Terminal Answer Synthetic Smoke Matrix Preflight.

#### Phase 28 Step 1: Terminal Answer Synthetic Smoke Matrix Preflight

- **Status**: Done.
- **Goal**: Inventory the terminal-answer/final-answer authority surface and define the synthetic smoke matrix before enabling any new compiler-authority terminal-answer branches.
- **Completed Outcome**:
  - Inventory complete for the main terminal/final-answer consumers:
    - `TerminalAnswerClassifier`
    - `response_pipeline_prevalidation`
    - `response_pipeline_stages`
    - `output_recovery_routing`
    - `response_semantics.is_plaintext_answer_path`
    - leaked-system and malformed-output helpers
  - Current authority split identified:
    - typed terminal-answer results exist and are attached to `ParsedModelOutput`
    - some narrow migrated consumers already use typed result with legacy fallback
    - final-answer / plaintext-answer authority remains mostly legacy/runtime-policy driven
  - Existing terminal-answer switch placeholders confirmed and left `legacy`:
    - `terminal_answer.plaintext_terminal_answer`
    - `terminal_answer.checkpoint_only`
    - `terminal_answer.checkpoint_with_visible_text`
  - Proposed synthetic smoke matrix rows include:
    - pure plaintext terminal answer
    - checkpoint only
    - checkpoint with visible text
    - pre-action text and action
    - action only
    - malformed or unclosed think
    - leaked system result
    - empty or missing answer
    - intent plus terminal-answer mixed edge
    - file-content plus visible-answer edge if supported
  - No runtime behavior changed.
  - No authority transfer happened.
- **Next**:
  - Phase 28 Step 2: Terminal Answer Synthetic Smoke Harness Skeleton + Authority Diagnostics.

#### Phase 28 Step 2: Terminal Answer Synthetic Smoke Harness Skeleton + Authority Diagnostics

- **Status**: Done.
- **Goal**: Add the first lightweight synthetic smoke harness and observational authority diagnostics for the terminal-answer slice, without transferring authority.
- **Completed Outcome**:
  - Added observational authority diagnostics for:
    - `terminal_answer.plaintext_terminal_answer`
  - Added a lightweight synthetic smoke harness covering:
    - pure plaintext terminal answer
    - action only
    - pre-action text and action
    - checkpoint only
    - checkpoint with visible text
    - malformed or unclosed think
    - empty output
    - leaked system result
  - The new diagnostics characterize:
    - typed/legacy alignment for clean plaintext
    - typed/legacy disagreement for checkpoint-with-visible-text
    - coexistence of legacy plaintext-path detection and later leaked-system recovery
  - Terminal-answer switches remain `legacy`.
  - No runtime behavior changed.
  - No authority transfer happened.
- **Next**:
  - Phase 28 Step 3: Terminal Answer Synthetic Matrix Expansion / First Authority Candidate Decision.

#### Phase 28 Step 3: Terminal Answer Synthetic Matrix Expansion / First Authority Candidate Decision

- **Status**: Done.
- **Goal**: Expand the terminal-answer synthetic matrix enough to decide whether `terminal_answer.plaintext_terminal_answer` is a safe first authority candidate.
- **Completed Outcome**:
  - Expanded the synthetic smoke harness to characterize:
    - clean single-line plaintext (`Done.`)
    - multi-line plaintext
    - markdown-ish plaintext
    - plaintext that looks like a pre-action explanation but has no action
    - action-only
    - pre-action text plus action
    - checkpoint-only
    - checkpoint-with-visible-text
    - leaked system result
    - empty / whitespace-only output
    - malformed / unclosed think
  - Hardened the observational plaintext-terminal diagnostic with:
    - `legacy_active`
    - `has_action`
    - `has_checkpoint`
    - `is_leaked_system_result`
    - more specific `mismatch_reason` values
  - Decision:
    - `terminal_answer.plaintext_terminal_answer` is **NO-GO** for smoke-profile compiler authority in the current state.
  - Blocking evidence:
    - `Done.` remains a legacy plaintext-answer path while the typed classifier currently marks it `INVALID_OR_TRUNCATED_TERMINAL_TEXT`.
    - markdown-style plaintext currently shares the same mismatch pattern.
    - `CHECKPOINT_WITH_VISIBLE_TEXT` still overlaps the legacy plaintext path.
    - leaked system result can still overlap the legacy plaintext path even though later leak recovery takes authority.
  - Safe but insufficient positive evidence:
    - multi-line plaintext and ordinary explanatory plaintext with no action can align typed and legacy signals.
  - Terminal-answer switches remain `legacy`.
  - No runtime behavior changed.
  - No authority transfer happened.
- **Next**:
  - Phase 28 Step 4: Terminal Answer Diagnostics Hardening.

#### Phase 28 Step 4: Terminal Answer Diagnostics Hardening

- **Status**: Done.
- **Goal**: Harden plaintext-terminal diagnostics so the next authority decision can cleanly separate valid plaintext from truncated/invalid overlaps, checkpoint-visible-text overlaps, leaked-system-result overlaps, and action-bearing cases.
- **Completed Outcome**:
  - Expanded `TerminalAnswerAuthorityDiagnostic` with explicit observational fields for:
    - `typed_plaintext_eligible`
    - `legacy_active`
    - `invalid_or_truncated_terminal_text`
    - `checkpoint_with_visible_text_overlap`
    - `leaked_system_result_overlap`
    - `action_or_pre_action_overlap`
    - `clean_plaintext_candidate`
    - `blocking_reasons`
  - Refined the observational plaintext resolver to expose stable diagnostic buckets for:
    - clean plaintext candidate
    - invalid/truncated mismatch
    - checkpoint-visible-text overlap
    - leaked-system-result overlap
    - action/pre-action overlap
    - empty / malformed inactive cases
  - Expanded the synthetic smoke assertions and added a direct helper-level characterization test for the resolver buckets.
  - Terminal-answer switches remain `legacy`.
  - No authority transfer happened.
  - No runtime behavior changed.
  - Remaining blocker:
    - typed plaintext classification for short answers like `Done.` and markdown-ish plaintext still needs review/fix before any authority-transfer step can be proposed.
- **Next**:
  - Phase 28 Step 5: Typed Plaintext Classification Review / Fix Candidate.

#### Phase 28 Step 5: Typed Plaintext Classification Review / Fix Candidate

- **Status**: Done.
- **Goal**: Review the typed plaintext classifier and, if safe, fix short valid plaintext terminal answers like `Done.` and markdown-ish plaintext without changing runtime authority.
- **Completed Outcome**:
  - Identified the root cause:
    - `TerminalAnswerClassifier` was using `terminal_plaintext_completion_status(...)` for all `PURE_PLAINTEXT` candidates.
    - That helper is stricter than the typed terminal-answer shadow classifier needs because it is designed to guard intent-completion final answers.
  - Implemented a narrow classifier-only fix:
    - short punctuated `PURE_PLAINTEXT` answers that do not end in a dangling word now remain typed `PLAINTEXT_TERMINAL_ANSWER`
    - examples now aligned:
      - `Done.`
      - `# Summary` followed by `Done.`
  - Retained all negative controls:
    - action-only
    - pre-action text plus action
    - checkpoint-only
    - checkpoint-with-visible-text
    - leaked system result
    - empty output
    - unclosed think
  - Expanded direct classifier tests and synthetic smoke assertions accordingly.
  - Terminal-answer switches remain `legacy`.
  - No authority transfer happened.
  - No runtime behavior changed.
- **Next**:
  - Phase 28 Step 6: Plaintext Terminal Authority Re-review / Smoke-Profile Candidate.

#### Phase 28 Step 6: Plaintext Terminal Authority Re-review / Smoke-Profile Candidate

- **Status**: Done.
- **Goal**: Re-review `terminal_answer.plaintext_terminal_answer` after the typed plaintext classifier fix and, if safe, enable a smoke-profile-only compiler authority candidate with strict fallback.
- **Completed Outcome**:
  - Decision:
    - **GO** for a smoke-profile-only compiler authority candidate for clean plaintext terminal answers.
  - Implemented smoke-profile-only configuration:
    - `terminal_answer.plaintext_terminal_answer = "compiler"` in `refactor_switches.smoke.toml`
    - default registry remains `legacy`
  - Refined the plaintext authority resolver so that compiler selection is allowed only when:
    - `clean_plaintext_candidate=True`
    - `typed_plaintext_eligible=True`
    - typed and legacy agree
    - no blocking reasons are present
  - Positive synthetic smoke validates compiler selection for:
    - `Done.`
    - markdown-ish plaintext
    - multi-line plaintext
  - Negative controls remain protected with `legacy_fallback` for:
    - action-only
    - pre-action text plus action
    - checkpoint-with-visible-text
    - leaked system result
    - empty or malformed output
    - dangling short text such as `And.`
  - Important boundary:
    - actual post-classification routing remains legacy in this step
    - smoke-profile compiler selection is diagnostic-only until live validation is complete
  - No production authority flip happened.
  - No runtime behavior changed under the default registry.
- **Next**:
  - Phase 28 Step 7: Live Angelica smoke for plaintext terminal answer under smoke profile.

#### Phase 28 Step 7: Live Angelica Smoke for Plaintext Terminal Answer under Smoke Profile

- **Status**: Done.
- **Goal**: Validate the smoke-profile plaintext terminal authority candidate against live Angelica behavior before any actual routing use.
- **Completed Outcome**:
  - Live smoke passed for clean plaintext terminal output (`Done.`).
  - Authority diagnostics showed:
    - `switch_value="compiler"`
    - `authority_source="compiler"`
    - `typed_kind="PLAINTEXT_TERMINAL_ANSWER"`
    - `legacy_kind="plaintext_answer_path"`
    - `agreement=True`
    - `fallback_used=False`
    - `clean_plaintext_candidate=True`
    - no action/checkpoint/leak overlap
  - Runtime remained stable (`last_error_code=None`, `consecutive_same_error_count=0`).
  - Up to this step, actual routing remained legacy.
  - Default registry remained `legacy`.
- **Next**:
  - Phase 28 Step 8: Plaintext Terminal Authority Closure / Actual Smoke-Profile Routing Flip Candidate.

#### Phase 28 Step 8: Plaintext Terminal Authority Closure / Actual Smoke-Profile Routing Flip Candidate

- **Status**: Done.
- **Goal**: If safe, move from diagnostic-only compiler selection to actual smoke-profile-only local routing use for the clean plaintext terminal-answer branch.
- **Completed Outcome**:
  - Decision:
    - **GO** for the first actual smoke-profile-only routing use of `terminal_answer.plaintext_terminal_answer`.
  - Implemented a local effective plaintext authority value in `_run_post_classification_stage(...)`.
  - The actual local branch consumption now uses the resolver’s effective value only when:
    - switch is `compiler`
    - `authority_source="compiler"`
    - `clean_plaintext_candidate=True`
    - `agreement=True`
    - no `blocking_reasons`
    - `behavior_changed=False`
  - Positive synthetic coverage validates the smoke-profile routing flip for:
    - `Done.`
    - markdown-ish plaintext
    - multi-line plaintext
  - Negative controls remain protected with fallback for:
    - action-only
    - pre-action text plus action
    - checkpoint-with-visible-text
    - leaked system result
    - empty / malformed output
    - dangling short text such as `And.`
  - Important boundary:
    - the default registry remains `legacy`
    - no production authority flip happened
    - runtime behavior under the default registry is unchanged
- **Next**:
  - Phase 28 Step 9: Live Angelica Smoke for Actual Plaintext Terminal Routing Flip under Smoke Profile.

#### Phase 28 Step 9: Live Angelica Smoke for Actual Plaintext Terminal Routing Flip under Smoke Profile

- **Status**: Done.
- **Goal**: Verify with a live Angelica run that the actual smoke-profile-only plaintext terminal routing flip remains healthy when exercised outside the synthetic harness.
- **Completed Outcome**:
  - Live smoke passed from dump `dumps/agent_dump_20260510_035546.txt`.
  - Verified evidence:
    - model output: `Done.`
    - `last_error_code=None`
    - `consecutive_same_error_count=0`
    - `switch_value="compiler"`
    - `authority_source="compiler"`
    - `typed_kind="PLAINTEXT_TERMINAL_ANSWER"`
    - `legacy_kind="plaintext_answer_path"`
    - `agreement=True`
    - `fallback_used=False`
    - `behavior_changed=False`
    - `effective_value=True`
    - `clean_plaintext_candidate=True`
    - no action/checkpoint/leak overlap flags were set
  - Important note:
    - older `terminal_answer_classifier_shadow` mismatches in the dump are not the authority signal for this step
    - the relevant authority evidence is `protocol_shadow / terminal_answer_authority_resolution`
  - Default registry remains `legacy`.
  - No production authority flip happened.
- **Next**:
  - Phase 28 Step 10: Plaintext Terminal Authority Closure / Next Terminal Branch Selection.

#### Phase 28 Step 10: Plaintext Terminal Authority Closure / Next Terminal Branch Selection

- **Status**: Done.
- **Goal**: Close the plaintext terminal-answer smoke-profile authority slice and select the next terminal-answer branch.
- **Completed Outcome**:
  - Closed the plaintext terminal-answer smoke-profile slice.
  - `terminal_answer.plaintext_terminal_answer` now has:
    - synthetic matrix coverage
    - hardened authority diagnostics
    - typed classifier fix for short plaintext like `Done.`
    - smoke-profile compiler authority candidate
    - actual smoke-profile routing use
    - live Angelica smoke pass
  - Smoke profile may keep `terminal_answer.plaintext_terminal_answer = "compiler"` for continued validation.
  - Default production behavior remains `legacy`.
  - No production authority flip happened.
  - Selected next branch:
    - `terminal_answer.checkpoint_only`
  - Deferred branches:
    - `terminal_answer.checkpoint_with_visible_text`
      - still overlaps the legacy plaintext path and needs a dedicated diagnostics/fix slice
    - action-bearing / pre-action branches
      - they cross dispatch/action semantics
    - leaked-system-result cases
      - recovery must remain authoritative
- **Next**:
  - Phase 28 Step 11: Terminal Checkpoint-Only Synthetic Authority Candidate.

#### Phase 28 Step 11: Terminal Checkpoint-Only Synthetic Authority Candidate

- **Status**: Done.
- **Goal**: Add synthetic-first authority diagnostics and a smoke-profile compiler candidate for `terminal_answer.checkpoint_only` without changing production authority.
- **Completed Outcome**:
  - Added `resolve_checkpoint_only_terminal_authority(...)`.
  - Added smoke-profile-only switch configuration:
    - `terminal_answer.checkpoint_only = "compiler"` in `refactor_switches.smoke.toml`
    - default registry remains `legacy`
  - Added `protocol_shadow / terminal_answer_authority_resolution` coverage for branch:
    - `terminal_answer.checkpoint_only`
  - Positive synthetic case validates compiler selection for:
    - `<memory_update_done />`
  - Negative controls validate `legacy_fallback` for:
    - checkpoint-with-visible-text
    - action-only
    - pre-action text plus action
    - plaintext-only
    - leaked system result
    - empty / malformed output
    - checkpoint plus action
  - Important boundary:
    - no production authority flip happened
    - no runtime behavior change under the default registry
    - checkpoint-with-visible-text authority is still deferred
- **Next**:
  - Phase 28 Step 12: Live Angelica Smoke for Terminal Checkpoint-Only under Smoke Profile.

#### Phase 28 Step 12: Live Angelica Smoke for Terminal Checkpoint-Only under Smoke Profile

- **Status**: Not exercised / deferred.
- **Goal**: Verify with live Angelica behavior whether the smoke-profile `terminal_answer.checkpoint_only` candidate is a real terminal-authority runtime path.
- **Completed Outcome**:
  - A clean marker-only checkpoint was produced in dump `dumps/agent_dump_20260510_042059.txt`:
    - model output: `<memory_update_done />`
    - `last_error_code=None`
    - `consecutive_same_error_count=0`
  - Board/memory checkpoint ownership consumed the turn:
    - `stage=memory_board`
    - `decision=continue`
    - `reason=memory_checkpoint_only`
  - Structural parity for the marker-only turn remained aligned:
    - `compiler_shape=CHECKPOINT_ONLY`
    - `compiler_has_checkpoint=True`
    - `compiler_has_action=False`
    - `compiler_has_visible_answer=False`
    - `memory_checkpoint_category=checkpoint_only`
    - `legacy_checkpoint_only=True`
    - `parity_aligned=True`
  - But terminal checkpoint-only authority was not exercised:
    - no positive `terminal_answer.checkpoint_only` compiler-authority log was observed for the clean marker-only turn
    - later terminal authority logs belonged to a different plaintext/memory-text turn and showed `legacy_fallback`
  - Interpretation:
    - checkpoint-only marker generation: pass
    - runtime safety: pass
    - board/memory checkpoint structural behavior: pass
    - terminal checkpoint-only live authority: not exercised
- **Next**:
  - Phase 28 Step 13: Terminal Checkpoint-Only Authority Boundary Review.

#### Phase 28 Step 13: Terminal Checkpoint-Only Authority Boundary Review

- **Status**: Done.
- **Goal**: Decide whether `terminal_answer.checkpoint_only` should remain a terminal-answer authority migration target.
- **Completed Outcome**:
  - Decision: **NO-GO / DEFER** for terminal checkpoint-only authority.
  - Reason:
    - marker-only `<memory_update_done />` turns are practically owned by the board/memory checkpoint stage
    - terminal post-classification does not meaningfully own this runtime branch
    - attempting a terminal authority transfer here would duplicate or conflict with board/memory ownership
  - Synthetic checkpoint-only terminal tests and diagnostics are retained as characterization only.
  - Smoke-profile cleanup:
    - `terminal_answer.checkpoint_only` was reverted back to `legacy` in `refactor_switches.smoke.toml`
    - this avoids implying live terminal-authority validation for a branch that is intercepted earlier
  - Boundaries preserved:
    - default registry remains `legacy`
    - no production authority flip happened
    - no runtime behavior changed
- **Next**:
  - Phase 28 Step 14: Terminal Classifier Shadow Comparator Cleanup.

#### Phase 28 Step 14: Terminal Classifier Shadow Comparator Cleanup

- **Status**: Done.
- **Goal**: Remove confusing stale mismatch artifacts from `terminal_answer_classifier_shadow` without changing runtime authority or behavior.
- **Completed Outcome**:
  - Updated the legacy parity comparator so safe short plaintext such as `Done.` and markdown-ish plaintext no longer report stale `invalid_or_truncated_terminal_text` mismatch after the typed plaintext fix.
  - Added explicit shadow-only clarifiers to the comparator log:
    - `comparator_scope="legacy_parity_only"`
    - `authority_signal="terminal_answer_authority_resolution"`
  - This keeps the review boundary explicit:
    - `terminal_answer_authority_resolution` is the authority signal
    - `terminal_answer_classifier_shadow` is parity/comparator only
  - No runtime behavior changed.
  - Default registry remains `legacy`.
  - No production authority flip happened.
- **Next**:
  - Phase 28 Step 15: Terminal Plaintext Slice Closure / Next Domain Selection.

#### Phase 28 Step 15: Terminal Plaintext Slice Closure / Next Domain Selection

- **Status**: Done.
- **Goal**: Close the terminal plaintext slice cleanly and choose the next migration domain.
- **Completed Outcome**:
  - Closed the plaintext terminal slice for now.
  - `terminal_answer.plaintext_terminal_answer` is now smoke-validated with:
    - typed classifier fix for short plaintext like `Done.`
    - hardened authority diagnostics
    - synthetic smoke coverage
    - smoke-profile compiler authority candidate
    - actual smoke-profile routing use
    - live Angelica smoke pass
  - `terminal_answer_classifier_shadow` is clarified as parity-only, not authority:
    - `comparator_scope="legacy_parity_only"`
    - `authority_signal="terminal_answer_authority_resolution"`
  - Deferred branches remain:
    - `terminal_answer.checkpoint_only`
      - deferred because marker-only `<memory_update_done />` turns are owned by board/memory checkpoint stage
    - `terminal_answer.checkpoint_with_visible_text`
      - deferred because it overlaps the legacy plaintext path and board/memory checkpoint-with-text ownership
  - Boundary preserved:
    - default registry remains `legacy`
    - no production authority flip happened
    - no runtime behavior changed
  - Next domain selected:
    - `Phase 29: Recovery / Invalid-Output Synthetic Matrix`
- **Next**:
  - Phase 29 Step 1: Recovery / Invalid-Output Synthetic Smoke Matrix Preflight.

### Phase 29: Recovery / Invalid-Output Synthetic Matrix

- **Status**: Open.
- **Goal**: Inventory recovery/invalid-output consumers, define a synthetic smoke matrix, and establish authority boundaries before any recovery-domain authority transfer.
- **Allowed**:
  - consumer inventory
  - synthetic matrix design
  - observational diagnostics
  - characterization tests
- **Forbidden**:
  - production authority flips
  - default-registry changes
  - runtime behavior changes during preflight
  - board/memory ownership changes
  - dispatch/action behavior changes
- **Initial matrix should include**:
  - unclosed `<think>`
  - invalid or malformed action JSON
  - leaked system result
  - internal-summary leak/recovery
  - invalid/truncated terminal text
  - checkpoint tag inside think
  - memory tag inside think
  - missing/empty output
  - repeated malformed output / retry limit where easy to characterize
  - mixed visible answer plus invalid protocol
  - action with pre-action text where recovery treats it specially

#### Phase 29 Step 1: Recovery / Invalid-Output Synthetic Smoke Matrix Preflight

- **Status**: Done.
- **Goal**: Inventory recovery/invalid-output consumers, identify current authority sources, and define the synthetic matrix before any authority transfer.
- **Completed Outcome**:
  - Recovery/invalid-output consumer inventory was completed.
  - Current owners and authority patterns:
    - `ResponsePipelinePrevalidationMixin._apply_compiler_diagnosis(...)`
      - compiler-invalid code is mapped through `COMPILER_INVALID_KIND_BY_CODE` and merged into legacy `parsed_output.invalid_kind`
    - `ResponsePipelinePrevalidationMixin._reject_invalid_output_before_transition(...)`
      - legacy invalid-kind plus `output_recovery.decide(...)` still own pre-transition recovery
    - `ResponsePipelineStagesMixin._run_post_classification_stage(...)`
      - mixes typed-primary leaked-system-result handling, `resolve_protocol_authority(...)`, and legacy/typed invalid-kind followups
    - `OutputRecoveryRoutingMixin.decide(...)`
      - remains the main recovery-router owner with legacy invalid-kind branching plus compiler metadata helpers
    - `output_recovery_terminal.py`
      - owns terminal recovery prompt construction
    - `protocol_decision_bridge.resolve_protocol_authority(...)`
      - owns suppression/preservation of legacy invalid-kind in selected compiler-invalid cases
    - `TerminalAnswerClassifier`
      - supplies typed invalid/truncated, leaked-system-result, and internal-summary signals, but recovery-domain branch authority is not yet centralized around it
    - guard paths in `response_pipeline_stages.py`
      - reflection repair, repeated nonproductive thinking, and structural-invalid continuation paths remain runtime-owned
  - Existing switches review:
    - no recovery/invalid-output switch family exists yet
    - current registry only contains:
      - `board_checkpoint.*`
      - `terminal_answer.*`
      - `dispatch.plan_first_single_action`
  - Approved initial synthetic matrix:
    - unclosed `<think>`
    - malformed action JSON / malformed action payload
    - leaked system result
    - internal-summary leak/recovery
    - invalid/truncated terminal text
    - checkpoint tag inside think
    - memory tag inside think
    - empty / whitespace output
    - repeated malformed / repeated no-valid-output guard where harnessable
    - mixed visible answer plus invalid protocol
    - action with pre-action text where recovery treats it specially
  - Key blockers / risk areas:
    - recovery authority is distributed across prevalidation, post-classification, output-recovery routing, and guard state
    - there is not yet a recovery-domain branch authority diagnostic model analogous to terminal/board authority logs
    - retry/streak cases need stateful harness coverage, not only single-turn snapshots
  - No runtime behavior changed.
  - Default registry remains `legacy`.
- **Next**:
  - Phase 29 Step 2: Recovery Invalid-Output Synthetic Harness + Authority Diagnostics.

#### Phase 29 Step 2: Recovery Invalid-Output Synthetic Harness + Authority Diagnostics

- **Status**: Done.
- **Goal**: Add a deterministic recovery synthetic harness and the first observational recovery authority diagnostic path without changing behavior.
- **Completed Outcome**:
  - Added the observational `RecoveryAuthorityDiagnostic` model.
  - Added `protocol_shadow / recovery_authority_resolution` logging for:
    - `recovery.compiler_invalid_kind_mapping`
    - `recovery.prevalidation_reject_invalid_output`
  - Added deterministic synthetic smoke coverage for:
    - unclosed `<think>`
    - malformed action JSON
    - leaked system result
    - invalid/truncated terminal text
    - memory tag inside think
    - checkpoint tag inside think
    - empty / whitespace output
    - pre-action text plus action
  - No recovery/invalid-output switch family was introduced.
  - No runtime behavior changed.
  - Default registry remains `legacy`.
- **Next**:
  - Phase 29 Step 3: Recovery Synthetic Matrix Expansion / First Authority Candidate Decision.

#### Phase 29 Step 3: Recovery Synthetic Matrix Expansion / First Authority Candidate Decision

- **Status**: Done.
- **Goal**: Expand the deterministic recovery synthetic matrix far enough to decide whether any narrow recovery-authority branch is safe to pursue next.
- **Completed Outcome**:
  - Expanded synthetic recovery coverage to include:
    - internal-summary characterization
    - mixed visible answer plus invalid protocol
    - repeated-thinking / no-valid-output guard characterization
    - malformed action payload with visible pre-action text
    - action-only valid control
    - clean plaintext valid control
  - Hardened observational recovery diagnostics with:
    - `parsed_invalid_kind`
    - `recovery_reason`
    - `recovery_prompt_kind`
    - `guard_name`
    - `guard_triggered`
  - First authority-candidate decision:
    - `NO-GO` for authority transfer in this step
    - the cleanest future candidate is `recovery.compiler_invalid_kind_mapping`, not a routed recovery branch
  - Main blockers:
    - recovery ownership is still distributed across prevalidation, output recovery, typed terminal signals, and stateful guards
    - internal-summary typed signals do not currently activate recovery on their own
    - malformed action with visible text currently resolves through mixed visible-text/control recovery
    - repeated-thinking handling is stateful and not a simple invalid-kind branch
  - No recovery switch family was introduced.
  - No runtime behavior changed.
  - Default registry remains `legacy`.
- **Next**:
  - Phase 29 Step 4: Recovery Authority Candidate Design.

#### Phase 29 Step 4: Recovery Authority Candidate Design

- **Status**: Done.
- **Goal**: Turn `recovery.compiler_invalid_kind_mapping` into a real resolver/accessor branch, without changing any current recovery behavior.
- **Completed Outcome**:
  - Added `resolve_compiler_invalid_kind_mapping_authority(...)` in `recovery_authority.py`.
  - The resolver now computes:
    - `effective_invalid_kind`
    - a unified `RecoveryAuthorityDiagnostic`
  - `_apply_compiler_diagnosis(...)` now uses that resolver as the single effectful mapping path.
  - `OutputRecoveryRoutingMixin._resolved_invalid_kind(...)` now uses the same resolver, eliminating duplicate compiler-vs-legacy mapping logic.
  - Added a recovery switch placeholder:
    - `[recovery] compiler_invalid_kind_mapping = "legacy"` in the default registry
    - `[recovery] compiler_invalid_kind_mapping = "legacy"` in the smoke profile
  - Switch decision:
    - Option B selected
    - registry completeness now, smoke enablement deferred
  - Expanded synthetic coverage with direct resolver tests for:
    - compiler-primary agreement
    - legacy-preserving mismatch fallback
    - plain-think-prefix exception fallback
  - No runtime behavior changed.
  - No recovery routing or prompt-selection behavior changed.
  - Default registry remains `legacy`.
- **Next**:
  - Phase 29 Step 5: Recovery Compiler Invalid Mapping Switch + Synthetic Validation.

#### Phase 29 Step 5: Recovery Compiler Invalid Mapping Switch + Synthetic Validation

- **Status**: Done.
- **Goal**: Enable the smoke-only switch path for `recovery.compiler_invalid_kind_mapping` and prove it preserves current behavior.
- **Completed Outcome**:
  - Enabled smoke-only compiler mode:
    - `[recovery] compiler_invalid_kind_mapping = "compiler"` in the smoke registry
  - Kept default production mode:
    - `[recovery] compiler_invalid_kind_mapping = "legacy"` in the default registry
  - Clarified diagnostics:
    - `authority_source` now means switch-controlled authority selection
    - `effective_source` records whether the unchanged effective invalid kind came from compiler or legacy behavior
    - `selected_by_switch` records whether smoke compiler mode actually selected the branch
  - Added behavior-preserving compiler mapping coverage for `E_MEMORY_TAG_INSIDE_THINK` by mapping it to the already-current effective invalid kind `malformed_incomplete_think`.
  - Synthetic smoke validation passed for:
    - unclosed think
    - memory tag inside think
    - checkpoint/subgoal tag inside think
    - malformed action JSON
    - mixed visible answer plus invalid protocol
    - plain-think-prefix exception fallback
    - action-only and clean-plaintext controls
  - Conflict and exception cases still fall back to the current behavior with `behavior_changed=False`.
  - No runtime behavior changed.
  - No recovery routing or prompt-selection behavior changed.
  - Default registry remains `legacy`.
- **Next**:
  - Phase 29 Step 6: Recovery Compiler Invalid Mapping Closure / Next Recovery Branch Selection.

#### Phase 29 Step 6: Recovery Compiler Invalid Mapping Closure / Next Recovery Branch Selection

- **Status**: Done.
- **Goal**: Close the first recovery smoke-authority slice and select the next branch that best advances real recovery authority migration.
- **Completed Outcome**:
  - Closed `recovery.compiler_invalid_kind_mapping` as a validated smoke-profile branch.
  - The branch now has:
    - central resolver/accessor
    - default legacy switch
    - smoke compiler switch
    - synthetic matrix coverage
    - conflict fallback tests
    - behavior-preserving `effective_invalid_kind` outcomes
  - Explicitly recorded:
    - `E_MEMORY_TAG_INSIDE_THINK -> malformed_incomplete_think`
    - this is behavior-preserving compiler coverage for an existing effective outcome, not a behavior change
  - Default registry remains `legacy`.
  - Smoke compiler mode remains enabled only in the smoke profile.
  - No production authority flip happened.
  - No recovery routing or prompt-selection behavior changed.
  - Next branch selected:
    - `recovery.prevalidation_reject_invalid_output`
  - Selection rationale:
    - it continues directly from the existing diagnostics and synthetic harness
    - it owns recovery action selection, which is the next meaningful authority boundary
    - it provides better risk-adjusted progress than jumping immediately to leaked-system-result or stateful guard branches
- **Next**:
  - Phase 29 Step 7: Recovery Prevalidation Reject-Invalid-Output Authority Candidate.

#### Phase 29 Step 7: Recovery Prevalidation Reject-Invalid-Output Authority Candidate

- **Status**: Done.
- **Goal**: Introduce a real resolver/accessor for prevalidation recovery action selection and consume it behavior-preservingly in the prevalidation path.
- **Completed Outcome**:
  - Added `resolve_prevalidation_reject_invalid_output_authority(...)` in `recovery_authority.py`.
  - Added `RecoveryDecisionAuthorityResolution` so the resolver returns:
    - the effective recovery decision
    - a unified `RecoveryAuthorityDiagnostic`
  - `_reject_invalid_intent_followup_before_transition(...)` now computes the current legacy `OutputRecoveryDecision` first, then consumes the resolver’s effective decision without changing behavior.
  - Added recovery switch placeholders:
    - `[recovery] prevalidation_reject_invalid_output = "legacy"` in the default registry
    - `[recovery] prevalidation_reject_invalid_output = "legacy"` in the smoke profile
  - Switch decision:
    - Option A selected
    - smoke compiler mode deferred until there is a distinct compiler-side recovery decision path to validate
  - Expanded deterministic synthetic coverage for:
    - malformed action JSON
    - unclosed think
    - memory tag inside think
    - checkpoint/subgoal tag inside think
    - mixed visible answer plus invalid protocol
    - valid action-only control
    - clean plaintext control
    - empty/whitespace intent-followup characterization
  - Added direct resolver tests for:
    - legacy mode preserving the current decision
    - invalid switch fallback
    - compiler-mode fallback when no compiler decision path exists
    - inactive branch when there is no invalid kind and no recovery decision
  - No production behavior changed.
  - Default registry remains `legacy`.
  - Smoke registry remains `legacy` for this branch.
- **Next**:
  - Phase 29 Step 8: Recovery Prevalidation Reject-Invalid-Output Compiler Decision Candidate.

#### Phase 29 Step 8: Recovery Prevalidation Reject-Invalid-Output Compiler Decision Candidate

- **Status**: Done.
- **Goal**: Create a real compiler-side prevalidation recovery decision candidate path before any smoke switch enablement for this branch.
- **Completed Outcome**:
  - Added `build_compiler_prevalidation_recovery_decision_candidate(...)` in `recovery_authority.py`.
  - The branch now has a real compiler-side decision candidate path for a narrow stateless subset of invalid-output recovery cases.
  - `resolve_prevalidation_reject_invalid_output_authority(...)` now compares:
    - legacy decision
    - compiler candidate availability
    - decision-shape agreement
    - prompt-equivalence proof
  - Added decision-candidate diagnostics:
    - `compiler_recovery_action`
    - `compiler_recovery_reason`
    - `compiler_recovery_prompt_kind`
    - `compiler_decision_available`
    - `decision_agreement`
    - `prompt_equivalent`
    - `candidate_source`
  - Candidate coverage now includes:
    - `malformed_action`
    - `mixed_visible_text_and_control_protocol`
    - `mixed_intent_transition_and_visible_answer`
    - `malformed_incomplete_action`
    - `malformed_incomplete_intent`
    - `malformed_incomplete_file_content`
    - `file_content_must_follow_action`
    - `truncated_internal_response`
    - `action_payload_array`
    - `multiple_actions`
    - `conflicting_intent_transitions`
    - `intent_complete_with_action_not_allowed`
  - Stateful or non-provable branches remain candidate-unavailable for now, especially malformed-think repeat-count recovery.
  - Smoke switch decision:
    - deferred
    - the branch now has a real candidate path, but branch-wide smoke compiler authority would still be misleading until the unsupported cases are either modeled or explicitly fenced
  - No production behavior changed.
  - Default registry remains `legacy`.
  - Smoke registry remains `legacy` for this branch.
- **Next**:
  - Phase 29 Step 9: Recovery Prevalidation Reject-Invalid-Output Smoke Switch Validation.

#### Phase 29 Step 9: Recovery Prevalidation Reject-Invalid-Output Fenced Smoke Switch Validation

- **Status**: Done.
- **Goal**: Enable smoke compiler mode for the prevalidation reject-invalid-output branch, but only for candidate-covered cases where decision agreement and prompt equivalence are proven.
- **Completed Outcome**:
  - Enabled smoke-only compiler mode:
    - `[recovery] prevalidation_reject_invalid_output = "compiler"` in the smoke profile
  - Kept the default registry at:
    - `[recovery] prevalidation_reject_invalid_output = "legacy"`
  - Compiler authority is now synthetically selected only when:
    - `compiler_decision_available=True`
    - `decision_agreement=True`
    - `prompt_equivalent=True`
  - Positive compiler-selected smoke cases now include:
    - `malformed_action`
    - `mixed_visible_text_and_control_protocol`
    - `mixed_intent_transition_and_visible_answer`
  - Unsupported/stateful branches remain legacy-fallback only:
    - malformed-think / unclosed-think recovery
    - memory tag inside think
    - checkpoint/subgoal inside think
    - empty/whitespace followups that do not enter the reject path
  - No recovery routing decisions changed.
  - No output recovery prompt selection changed.
  - `behavior_changed=False` across the synthetic matrix.
  - No production behavior changed.
  - Default registry remains `legacy`.
- **Next**:
  - Phase 29 Step 10: Recovery Prevalidation Reject-Invalid-Output Closure / Next Recovery Branch Selection.

#### Phase 29 Step 10: Recovery Prevalidation Reject-Invalid-Output Closure / Next Recovery Branch Selection

- **Status**: Done.
- **Goal**: Close the prevalidation reject-invalid-output smoke slice and select the next recovery branch with the best safety/value tradeoff.
- **Completed Outcome**:
  - Closed `recovery.prevalidation_reject_invalid_output` as a smoke-validated fenced compiler-authority slice.
  - The branch now has:
    - resolver/accessor coverage
    - effective decision consumption
    - compiler decision candidate builder
    - default `legacy` switch
    - smoke-only `compiler` switch
    - positive compiler-selected synthetic coverage
    - explicit legacy fallback for unsupported/stateful cases
  - Clarified that `mixed_intent_transition_and_visible_answer` is an intent-followup prevalidation recovery case, not ordinary terminal plaintext authority.
  - No production behavior changed.
  - Default registry remains `legacy`.
  - Smoke compiler switch remains smoke-only.
  - No recovery routing decisions changed.
  - No output recovery prompt selection changed.
  - Selected next branch:
    - `recovery.leaked_system_result`
  - Rationale:
    - safety-critical
    - typed signal already exists
    - strong next semantic-policy authority target
    - better next return than lower-value invalid/truncated cleanup or heavier stateful guard migration
- **Next**:
  - Phase 29 Step 11: Leaked-System-Result Recovery Authority Candidate.

#### Phase 29 Step 11: Leaked-System-Result Recovery Authority Candidate

- **Status**: Done.
- **Goal**: Centralize leaked-system-result recovery authority through a typed/legacy resolver without changing current leak recovery behavior.
- **Completed Outcome**:
  - Confirmed runtime ownership sits in the post-classification no-action leak guard.
  - Confirmed current behavior remains:
    - `continue_loop=True`
    - `reason="leaked_system_result_in_assistant_text"`
    - `source="output_recovery"`
    - prompt from `build_leaked_system_result_recovery_prompt()`
  - Added `resolve_leaked_system_result_recovery_authority(...)`.
  - Added `build_typed_leaked_system_result_recovery_decision_candidate(...)`.
  - Routed the leak branch through the resolver’s effective decision behavior-preservingly.
  - Added default/smoke placeholders:
    - `[recovery] leaked_system_result = "legacy"` in the default registry
    - `[recovery] leaked_system_result = "compiler"` in the smoke profile
  - Compiler selection is fenced to cases where:
    - the typed leak signal is present
    - the legacy leak path agrees
    - prompt equivalence is proven
  - Positive compiler-selected synthetic coverage:
    - canonical `SYSTEM RESULT: ...`
  - Fallback-preserved cases:
    - surrounding visible text with embedded leak transcript
    - action-bearing responses
    - internal-summary-like text
    - checkpoint marker only
    - malformed/unclosed think without leak text
  - No production behavior changed.
  - Default registry remains `legacy`.
  - No recovery routing decisions changed.
  - No output recovery prompt selection changed.
  - Leaked system result still cannot become a final answer.
- **Next**:
  - Phase 29 Step 12: Leaked-System-Result Recovery Closure / Next Recovery Branch Selection.

---

#### Phase 29 Step 12: Leaked-System-Result Recovery Closure / Next Recovery Branch Selection

- **Status**: Done.
- **Goal**: Close the `recovery.leaked_system_result` smoke-validated slice and select the next recovery branch.
- **Completed Outcome**:
  - Closed `recovery.leaked_system_result` as a smoke-validated fenced compiler-authority slice.
  - The branch now has:
    - resolver/accessor coverage
    - typed leak recovery decision candidate
    - effective decision consumption
    - default `legacy` switch
    - smoke-only `compiler` switch
    - canonical compiler-selected synthetic coverage
    - strict fallback for legacy-only leak detection
    - negative controls for action, internal-summary, checkpoint, malformed think, and plaintext
  - Default registry remains `legacy`.
  - No production authority flip happened.
  - Leak handling was not weakened.
  - Leaked system result still cannot become a final answer.
  - Action-bearing leak-like responses remain outside this no-action leak guard and keep current action behavior.
  - Selected next recovery branch:
    - `recovery.invalid_truncated_terminal_text`
  - Rationale:
    - typed signal exists
    - high relevance after terminal plaintext work
    - directly connected to recovery/final-answer boundary
    - good next semantic-policy authority target before deeper stateful guard work
    - validates that earlier short-plaintext fixes like `Done.` remain safe
- **Next**:
  - Phase 29 Step 13: Invalid-Truncated Terminal Text Recovery Authority Candidate.

---

#### Phase 29 Step 13: Invalid-Truncated Terminal Text Recovery Authority Candidate

- **Status**: Done.
- **Goal**: Centralize invalid/truncated terminal text recovery authority through a typed/legacy resolver without changing current recovery behavior.
- **Completed Outcome**:
  - Added `resolve_invalid_truncated_terminal_text_recovery_authority(...)` in `recovery_authority.py`.
  - Added a diagnostic-only call to the resolver in `_run_post_classification_stage(...)` to characterize the branch without changing behavior.
  - Added registry placeholders:
    - `recovery.invalid_truncated_terminal_text = "legacy"` in the default registry
    - `recovery.invalid_truncated_terminal_text = "legacy"` in the smoke registry
  - Added synthetic smoke coverage for:
    - positive invalid/truncated cases like `And.`
    - negative controls for clean plaintext, action, checkpoint, leak, and internal-summary
  - No production behavior changed.
  - Default registry remains `legacy`.
  - No recovery routing decisions changed.
  - No output recovery prompt selection changed.
- **Next**:
  - Phase 29 Step 14: Invalid-Truncated Terminal Text Smoke Switch Validation.

---

#### Phase 29 Step 14: Invalid-Truncated Terminal Text Smoke Switch Validation

- **Status**: Done.
- **Goal**: Validate whether `recovery.invalid_truncated_terminal_text` can safely get smoke-profile compiler authority.
- **Completed Outcome**:
  - **NO-GO** for smoke switch enablement.
  - The `INVALID_OR_TRUNCATED_TERMINAL_TEXT` branch is currently diagnostic-only in the post-classification path.
  - It correctly identifies typed invalid/truncated text, but there is no corresponding legacy recovery decision to preserve or replace in this path.
  - Enabling a smoke compiler switch would be misleading, as it would claim authority over a decision that is not being made.
  - The branch remains a typed characterization signal only for now.
  - Added synthetic smoke coverage for incomplete sentences and negative controls.
  - No production behavior changed.
  - Default and smoke registries remain `legacy` for this branch.
- **Next**:
  - Phase 29 Step 15: Recovery Invalid-Truncated Boundary Closure / Remaining Recovery Branch Decision.

---

#### Phase 29 Step 15: Recovery Invalid-Truncated Boundary Closure / Remaining Recovery Branch Decision

- **Status**: Done.
- **Goal**: Close the invalid/truncated terminal text slice and select the next recovery branch.
- **Completed Outcome**:
  - Closed the `recovery.invalid_truncated_terminal_text` branch as a diagnostic-only characterization.
  - The branch has resolver/accessor coverage and synthetic tests, but no recovery decision ownership.
  - The smoke switch remains `legacy` because enabling compiler authority would be misleading.
  - Future work on this branch is deferred until a runtime policy decision is made to actively recover from invalid/truncated terminal text.
  - Decision: Close Phase 29. The core recovery architecture is significantly advanced. Remaining branches (`internal_summary`, stateful guards) are deferred to avoid expanding into deep policy or stateful harness work.
- **Next**:
  - Phase 29 Step 16: Recovery Core Closure / Next Phase Selection.

---

#### Phase 29 Step 16: Recovery Core Closure / Next Phase Selection

- **Status**: Done.
- **Goal**: Close Phase 29 and select the next major refactor phase.
- **Completed Outcome**:
  - Closed Phase 29 (Recovery / Invalid-Output Core).
  - Completed smoke-validated branches:
    - `recovery.compiler_invalid_kind_mapping`
    - `recovery.prevalidation_reject_invalid_output`
    - `recovery.leaked_system_result`
  - Completed diagnostic-only/deferred branch:
    - `recovery.invalid_truncated_terminal_text`
  - Deferred recovery branches:
    - `recovery.internal_summary`
    - stateful malformed-think / repeated invalid-output guards
    - remaining prompt-equivalence hardening
  - Default registry remains `legacy` for all recovery branches.
  - Smoke profile keeps validated recovery compiler switches enabled for continued validation.
  - No production authority was flipped, and no runtime behavior was changed.
  - Selected next phase: `Phase 30: Board/Memory Commit Policy on Compiler-IR Foundation`.
- **Next**:
  - Phase 30 Step 1: Board/Memory Commit Policy Inventory + Commit-Equivalence Harness Plan.

---

### Phase 30: Board/Memory Commit Policy on Compiler-IR Foundation

- **Status**: Not started.
- **Goal**: Migrate remaining board/memory checkpoint commit policy from legacy handler ownership toward compiler IR, typed results, and resolver/accessor authority, while proving commit-equivalence before any authority transfer.
- **Allowed**:
  - Inventory board/memory checkpoint commit paths.
  - Identify current legacy owners.
  - Identify compiler IR / typed signals already available.
  - Design synthetic commit-equivalence harness.
  - Define branch-level switch candidates.
  - Document commit/state invariants.
- **Forbidden**:
  - Behavior changes.
  - Production authority flips.
  - Memory commit behavior changes.
  - Board handler behavior changes.
  - Dispatch/action behavior changes.
  - ActionPolicy changes.
  - Final-answer behavior changes.
- **Done When**:
  - Board/memory commit policy inventory is complete.
  - Commit-equivalence harness plan is documented.
  - First board/memory branch candidate is selected.

---

#### Phase 30 Step 1: Board/Memory Commit Policy Inventory + Commit-Equivalence Harness Plan

- **Status**: Done.
- **Goal**: Inventory current memory-board and board/checkpoint commit paths and design a synthetic commit-equivalence harness.
- **Completed Outcome**:
  - **Inventory**:
    - **Owners**: `MemoryBoardStageHandler` and `PlanBoardStageHandler` are the legacy owners.
    - **Commit Semantics**: `MemoryBoardStageHandler` has embedded side effects (memory-engine commits, state updates) that are not pure classification.
    - **Available Facts**: `board_checkpoint_models.py` and `board_checkpoint_semantics.py` provide typed observational data, but this is not yet sufficient for commit authority.
    - **Blockers**: Memory commit logic is not a pure function, no typed model for a memory commit decision exists, and state effects are computed inside legacy handlers.
  - **Harness Plan**:
    - A future `tests/test_board_memory_commit_equivalence.py` will compare legacy vs. candidate paths.
    - The harness must assert equivalence across `handled`, `reason`, `source`, `response_text`, `next_query`, memory commit effects, and state flags.
  - **First Candidate**: The first implementation target for the commit-equivalence harness is `MEMORY_CHECKPOINT_ONLY`.
  - **Boundary**: This was a docs-only inventory and planning step. No runtime behavior was changed.
- **Next**:
  - Phase 30 Step 2: Board/Memory Synthetic Commit-Equivalence Harness.

---

#### Phase 30 Step 2: Board/Memory Synthetic Commit-Equivalence Harness

- **Status**: Done.
- **Goal**: Implement the first synthetic commit-equivalence harness for the `MEMORY_CHECKPOINT_ONLY` branch.
- **Completed Outcome**:
  - Created `tests/test_board_memory_commit_equivalence.py` to characterize legacy memory commit behavior.
  - Implemented a synthetic harness that runs the `_run_checkpoint_stage` path with a controlled static memory stage, as the real `MemoryBoardStageHandler` has complex dependencies.
  - Added a `LegacyCommitSnapshot` dataclass to capture structured outcomes from the controlled stage.
  - Added positive snapshot coverage for `MEMORY_CHECKPOINT_ONLY`.
  - Added negative controls for plaintext, action-only, and plan-checkpoint-only to ensure they are not treated as memory commits.
  - Added characterization for `MEMORY_CHECKPOINT_WITH_TEXT` and `MEMORY_CHECKPOINT_WITH_ACTION`.
  - No production code was changed. No runtime behavior was changed.
- **Next**:
  - Phase 30 Step 3: Real MemoryBoardStageHandler Commit Snapshot Hardening.

---

#### Phase 30 Step 3: Real MemoryBoardStageHandler Commit Snapshot Hardening

- **Status**: Done.
- **Goal**: Harden the commit-equivalence harness to snapshot the real `MemoryBoardStageHandler`, not just a static mock.
- **Completed Outcome**:
  - The harness in `tests/test_board_memory_commit_equivalence.py` now supports snapshotting the real `MemoryBoardStageHandler`.
  - `LegacyCommitSnapshot` was improved to distinguish `controlled_static` vs. `real_handler` modes and capture more commit details.
  - A new test proves that the real handler's commit behavior for `MEMORY_CHECKPOINT_ONLY` can be captured.
  - The handler's dependencies were mocked, and its state was wired to the harness's state for accurate snapshotting.
  - No production behavior was changed.
- **Next**:
  - Phase 30 Step 4: MEMORY_CHECKPOINT_ONLY Commit Candidate Model / Resolver Design.

---

#### Phase 30 Step 4: MEMORY_CHECKPOINT_ONLY Commit Candidate Model / Resolver Design

- **Status**: Done.
- **Goal**: Design and implement the first typed commit candidate model and resolver for `MEMORY_CHECKPOINT_ONLY` without changing behavior.
- **Completed Outcome**:
  - Added a typed `MemoryCommitCandidate` model and a `resolve_memory_checkpoint_only_commit_authority` resolver.
  - The candidate is intentionally narrow, available only for clean `MEMORY_CHECKPOINT_ONLY` cases, and blocks on commit-count equivalence.
  - The resolver compares the candidate to the legacy snapshot and produces a detailed authority diagnostic.
  - Added a `board_memory.memory_checkpoint_only` switch placeholder to the registries, with both default and smoke profiles set to `legacy`.
  - Added tests for candidate construction, legacy-mode resolution, and compiler-mode fallback.
  - No production authority was transferred, and no runtime behavior was changed.
- **Next**:
  - Phase 30 Step 5: MEMORY_CHECKPOINT_ONLY Commit Equivalence Hardening.

---

#### Phase 30 Step 5: MEMORY_CHECKPOINT_ONLY Commit Equivalence Hardening

- **Status**: Done.
- **Goal**: Harden commit-equivalence validation for `MEMORY_CHECKPOINT_ONLY` to determine if commit counts, `next_query`, and state flags can be proven equivalent.
- **Completed Outcome**:
  - Adopted an "observed-equivalence" model where the typed candidate's structural expectations are compared against the observed legacy commit result.
  - The resolver now proves `commit_equivalent=True` for clean cases by checking if the observed legacy commit result (counts, query, etc.) is consistent with a `MEMORY_CHECKPOINT_ONLY` outcome. The typed candidate itself does not predict memory-engine-dependent values.
  - Added tests to validate full equivalence for the clean case and to confirm fallback on mismatch.
  - The `board_memory.memory_checkpoint_only` switch remains `legacy` in both default and smoke registries.
  - No runtime behavior was changed.
- **Next**:
  - Phase 30 Step 6: MEMORY_CHECKPOINT_ONLY Smoke Switch Validation.

---

#### Phase 30 Step 6: MEMORY_CHECKPOINT_ONLY Smoke Switch Validation

- **Status**: Done.
- **Goal**: Enable the `board_memory.memory_checkpoint_only` switch in the smoke profile and validate it with synthetic tests.
- **Completed Outcome**:
  - Set `board_memory.memory_checkpoint_only = "compiler"` in `refactor_switches.smoke.toml`.
  - Added synthetic tests that run the harness with the smoke profile enabled and confirm that compiler authority is selected for clean, observed-equivalent `MEMORY_CHECKPOINT_ONLY` cases.
  - Fallback controls confirm that mismatched or non-eligible cases still use legacy authority.
  - The default registry remains `legacy`.
  - No production behavior was changed.
- **Next**:
  - Phase 30 Step 7: MEMORY_CHECKPOINT_ONLY Live/Integrated Smoke or Closure Decision.

---

#### Phase 30 Step 7: MEMORY_CHECKPOINT_ONLY Live/Integrated Smoke or Closure Decision

- **Status**: Done.
- **Goal**: Decide whether to run live/integrated smoke tests for the `MEMORY_CHECKPOINT_ONLY` branch or close the slice based on synthetic evidence.
- **Completed Outcome**:
  - **Decision**: **NO-GO** for live/integrated smoke at this time.
  - **Blocker**: The `resolve_memory_checkpoint_only_commit_authority` resolver is not yet integrated into the runtime pipeline, so authority selection cannot be observed in a live run.
  - The slice is closed as an "integrated observability blocker".
  - No runtime behavior was changed.
- **Next**:
  - Phase 30 Step 8: Board/Memory Commit Authority Runtime Diagnostic Integration.

---

#### Phase 30 Step 8: Board/Memory Commit Authority Runtime Diagnostic Integration

- **Status**: Done.
- **Goal**: Integrate the `resolve_memory_checkpoint_only_commit_authority` resolver into the runtime pipeline for diagnostic logging only, without changing behavior.
- **Completed Outcome**:
  - The resolver is now called from `_run_checkpoint_stage`.
  - A new `_log_board_memory_commit_authority_resolution` helper logs the diagnostic output.
  - The resolver's `effective_commit` is not used, and no runtime behavior was changed.
- **Next**:
  - Phase 30 Step 9: MEMORY_CHECKPOINT_ONLY Live Smoke Validation.

---

#### Phase 30 Step 9: Runtime Diagnostic Real-Handler Commit Field Hardening

- **Status**: Done.
- **Goal**: Harden the runtime diagnostic integration to correctly read commit evidence from real-handler state fields.
- **Completed Outcome**:
  - The diagnostic resolver input in `_run_checkpoint_stage` now safely falls back from the memory decision object to agent state fields for commit evidence.
  - This remains a diagnostic-only change. No runtime behavior was changed.
- **Next**:
  - Phase 30 Step 10: MEMORY_CHECKPOINT_ONLY Live Smoke Validation.

---

#### Phase 30 Step 10: MEMORY_CHECKPOINT_ONLY Live Smoke Validation

- **Status**: Done.
- **Goal**: Run a live/integrated smoke test for the `MEMORY_CHECKPOINT_ONLY` branch to confirm that authority selection is now observable in runtime logs.
- **Completed Outcome**:
  - **Result**: NOT A PASS.
  - Live smoke was run for `<memory_update_done />` under the smoke profile.
  - The `board_memory_commit_authority_resolution` diagnostic was observable, but it reported `commit_equivalent=False` and fell back to legacy.
  - **Root Cause**: The live `MemoryBoardStageHandler` correctly reported `accepted_count=0` for a marker-only checkpoint, while the synthetic equivalence model incorrectly expected `accepted_count=1`.
- **Next**:
  - Phase 30 Step 11: MEMORY_CHECKPOINT_ONLY Live Semantics Reconciliation / Closure Decision.

---

#### Phase 30 Step 11: MEMORY_CHECKPOINT_ONLY Live Semantics Reconciliation / Closure Decision

- **Status**: Done.
- **Goal**: Reconcile synthetic `MEMORY_CHECKPOINT_ONLY` equivalence with real live `MemoryBoardStageHandler` behavior.
- **Completed Outcome**:
  - The `resolve_memory_checkpoint_only_commit_authority` resolver was updated to correctly handle marker-only checkpoints (`accepted_count=0`).
  - Live behavior showed `<memory_update_done />` has `accepted_count=0`. The model now treats this zero-count continuation as valid observed equivalence.
  - Synthetic tests in `tests/test_board_memory_commit_equivalence.py` were updated to reflect this live-faithful behavior.
  - Content-bearing memory update authority remains out of scope/deferred until its real protocol syntax and typed classification are identified.
  - No runtime behavior was changed.
- **Next**:
  - Phase 30 Step 12: MEMORY_CHECKPOINT_ONLY Closure / Remaining Board-Memory Branch Selection.

---

#### Phase 30 — Step 12/12: MEMORY_CHECKPOINT_ONLY Closure / Remaining Board-Memory Branch Selection

- **Status**: Done.
- **Goal**: Close the `MEMORY_CHECKPOINT_ONLY` slice and select the next board/memory branch.
- **Completed Outcome**:
  - The `MEMORY_CHECKPOINT_ONLY` slice is now closed.
  - A second live smoke run was not required, as the synthetic reconciliation in Step 11 was sufficient to align the model with observed live behavior.
  - The branch now has: real-handler snapshot coverage, a candidate/resolver model, an observed-equivalence model, runtime diagnostic integration, state-field hardening, a smoke-only compiler switch, synthetic smoke validation, and live semantics reconciliation.
  - All tests are green.
  - The default registry remains `legacy`, and the smoke registry keeps `board_memory.memory_checkpoint_only = "compiler"`.
  - No production behavior was changed.
- **Next**:
  - Phase 31 — Step 1/10: MEMORY_CHECKPOINT_WITH_TEXT Commit Policy Inventory / Harness Plan.

---

### Phase 31: Board/Memory Commit Policy (MEMORY_CHECKPOINT_WITH_TEXT)

- **Status**: Not started.
- **Goal**: Extend the commit-equivalence model to the `MEMORY_CHECKPOINT_WITH_TEXT` branch.
- **Allowed**:
  - Inventory `MEMORY_CHECKPOINT_WITH_TEXT` commit paths.
  - Design and implement synthetic harness coverage.
  - Define a candidate/resolver model.
- **Forbidden**:
  - Behavior changes.
  - Production authority flips.
  - Memory commit behavior changes.
  - Board handler behavior changes.
  - Dispatch/action behavior changes.
- **Done When**:
  - The `MEMORY_CHECKPOINT_WITH_TEXT` branch is smoke-validated with compiler authority.

---

#### Phase 31 — Step 1/10: MEMORY_CHECKPOINT_WITH_TEXT Commit Policy Inventory / Harness Plan

- **Status**: Done.
- **Goal**: Inventory current `MEMORY_CHECKPOINT_WITH_TEXT` commit paths and design a synthetic commit-equivalence harness.
- **Completed Outcome**:
  - **Inventory**:
    - **Owner**: `MemoryBoardStageHandler` owns the initial detection.
    - **Behavior**: It detects `<memory_update_done />` and visible text, strips the marker, and passes the remaining text to the next pipeline stage for final-answer evaluation.
    - **Commit Semantics**: For a marker-only response with text, `accepted_count` is `0`. `last_memory_update_done` is set to `True`.
    - **Blockers**: The primary blocker is ensuring that any future compiler-driven path perfectly preserves the visible text and the `handled=False` pass-through behavior that allows the final-answer path to continue.
  - **Harness Plan**: The commit-equivalence harness will be extended to capture `MEMORY_CHECKPOINT_WITH_TEXT` snapshots, asserting that visible text is preserved and the pipeline continues correctly.
- **Next**:
  - Phase 31 — Step 2/10: MEMORY_CHECKPOINT_WITH_TEXT Synthetic Commit-Equivalence Harness.

---

#### Phase 31 — Step 2/10: MEMORY_CHECKPOINT_WITH_TEXT Synthetic Commit-Equivalence Harness

- **Status**: Done.
- **Goal**: Implement the synthetic commit-equivalence harness for the `MEMORY_CHECKPOINT_WITH_TEXT` branch.
- **Completed Outcome**:
  - The commit-equivalence harness was extended to cover `MEMORY_CHECKPOINT_WITH_TEXT`.
  - A real-handler snapshot test now characterizes the branch's behavior, including:
    - visible text preservation (`Done.`)
    - marker stripping (`<memory_update_done />`)
    - pass-through behavior (`handled=False`) to allow final-answer evaluation
    - zero-count memory commit (`accepted_count=0`)
  - Negative controls were added to ensure other branches are not misclassified.
  - No runtime behavior was changed, and no authority was transferred.
- **Next**:
  - Phase 31 — Step 3/10: MEMORY_CHECKPOINT_WITH_TEXT Candidate Model / Resolver Design.

---

#### Phase 31 — Step 3/10: MEMORY_CHECKPOINT_WITH_TEXT Candidate Model / Resolver Design

- **Status**: Done.
- **Goal**: Design and implement the first typed commit candidate model and resolver for `MEMORY_CHECKPOINT_WITH_TEXT` without changing behavior.
- **Completed Outcome**:
  - Added a typed `MemoryCommitCandidate` model and a `resolve_memory_checkpoint_with_text_commit_authority` resolver.
  - The candidate model and resolver cover visible text preservation, pass-through behavior, and zero-count commit semantics for marker-with-text.
  - The `board_memory.memory_checkpoint_with_text` switch placeholder remains `legacy` in both default and smoke registries.
  - No runtime behavior was changed, and no authority was transferred.
- **Next**:
  - Phase 31 — Step 4/10: MEMORY_CHECKPOINT_WITH_TEXT Commit Equivalence Hardening.

---

#### Phase 31 — Step 4/10: MEMORY_CHECKPOINT_WITH_TEXT Commit Equivalence Hardening

- **Status**: Done.
- **Goal**: Harden commit-equivalence validation for `MEMORY_CHECKPOINT_WITH_TEXT` to determine if all aspects of the legacy behavior can be proven equivalent.
- **Completed Outcome**:
  - The `resolve_memory_checkpoint_with_text_commit_authority` resolver was hardened to prove full commit equivalence.
  - A clean real-handler case for `MEMORY_CHECKPOINT_WITH_TEXT` now proves `commit_equivalent=True`.
  - Mismatches in any agreement field (e.g., `response_text`, `checkpoint_removed`, `visible_text_preserved`, `pass_through`, commit counts) correctly cause a fallback to legacy authority.
  - No runtime behavior was changed, and no authority was transferred.
  - The `board_memory.memory_checkpoint_with_text` switch remains `legacy` in both default and smoke registries.
- **Next**:
  - Phase 31 — Step 5/10: MEMORY_CHECKPOINT_WITH_TEXT Smoke Switch Validation.

---

#### Phase 31 — Step 5/10: MEMORY_CHECKPOINT_WITH_TEXT Smoke Switch Validation

- **Status**: Done.
- **Goal**: Enable smoke-only compiler authority for `board_memory.memory_checkpoint_with_text` and validate it synthetically.
- **Completed Outcome**:
  - Enabled the smoke-only compiler switch for `board_memory.memory_checkpoint_with_text`.
  - The default registry remains `legacy`.
  - Clean real-handler MCT now selects compiler authority under the smoke profile.
  - Fallback controls correctly remain on legacy authority when equivalence mismatches.
  - Negative controls for other branches do not select compiler authority.
  - No production behavior was changed, and no authority was transferred in the default profile.
  - The resolver's `effective_commit` is still not consumed by the runtime.
- **Next**:
  - Phase 31 — Step 6/10: MEMORY_CHECKPOINT_WITH_TEXT Runtime Diagnostic Integration or Live Observability Decision.

---

#### Phase 31 — Step 6/10: MEMORY_CHECKPOINT_WITH_TEXT Runtime Diagnostic Integration or Live Observability Decision

- **Status**: Done.
- **Goal**: Integrate the `MEMORY_CHECKPOINT_WITH_TEXT` commit authority resolver for diagnostic logging to enable live observability.
- **Completed Outcome**:
  - Live observability required runtime diagnostic integration.
  - Added a diagnostic-only call to the `resolve_memory_checkpoint_with_text_commit_authority` resolver in `_run_checkpoint_stage`.
  - Reused the existing `_log_board_memory_commit_authority_resolution` helper for logging.
  - The resolver's `effective_commit` is not consumed, and no runtime behavior was changed.
  - The default registry remains `legacy`, and the smoke registry remains `compiler` for this branch.
- **Next**:
  - Phase 31 — Step 7/10: MEMORY_CHECKPOINT_WITH_TEXT Live Smoke Validation.

---

#### Phase 31 — Step 7/10: MEMORY_CHECKPOINT_WITH_TEXT Live Smoke Validation

- **Status**: Done.
- **Goal**: Run a live/integrated smoke test for the `MEMORY_CHECKPOINT_WITH_TEXT` branch to confirm that authority selection is now observable in runtime logs.
- **Completed Outcome**:
  - **Result**: NOT A PASS.
  - Live smoke was run for `<memory_update_done />\nDone.` under the smoke profile.
  - The `board_memory_commit_authority_resolution` diagnostic was observable, but it reported `commit_equivalent=False` and fell back to legacy.
  - **Root Cause**: The exact agreement mismatch was not visible in the diagnostic log.
- **Next**:
  - Phase 31 — Step 8/10: MEMORY_CHECKPOINT_WITH_TEXT Live Semantics Reconciliation.

---

#### Phase 31 — Step 8/10: MEMORY_CHECKPOINT_WITH_TEXT Live Semantics Reconciliation

- **Status**: Done.
- **Goal**: Reconcile synthetic `MEMORY_CHECKPOINT_WITH_TEXT` equivalence with real live `MemoryBoardStageHandler` behavior.
- **Completed Outcome**:
  - Detailed live diagnostics identified the exact mismatch: only `commit_attempted_agreement` was `False`.
  - Live MCT marker-with-text has zero parsed/accepted/rejected counts.
  - The candidate/resolver model is now live-faithful: marker-with-text is treated as a pass-through, not a content commit attempt (`expected_commit_attempted=False`).
  - No runtime behavior was changed.
  - The resolver's `effective_commit` is still not consumed.
- **Next**:
  - Phase 31 — Step 9/10: MEMORY_CHECKPOINT_WITH_TEXT Live Smoke Re-run / Closure Decision.

---

#### Phase 31 — Step 9/10: MEMORY_CHECKPOINT_WITH_TEXT Live Smoke Re-run / Closure Decision

- **Status**: Done.
- **Goal**: Re-run live/integrated smoke for the `MEMORY_CHECKPOINT_WITH_TEXT` branch to confirm that `commit_equivalent` is now `True` and decide whether to close the slice.
- **Completed Outcome**:
  - Manual live smoke re-run passed.
  - MCT diagnostic showed `switch_value="compiler"`, `authority_source="compiler"`, `selected_by_switch=True`, `candidate_available=True`, and `commit_equivalent=True`.
  - All detailed agreement fields relevant to MCT were `True`.
  - Runtime behavior was preserved: `behavior_changed=False`, `shadow_only=True`.
  - The resolver's `effective_commit` is still not consumed.
- **Next**:
  - Phase 31 — Step 10/10: MEMORY_CHECKPOINT_WITH_TEXT Closure / Next Branch Selection.

---

#### Phase 31 — Step 10/10: MEMORY_CHECKPOINT_WITH_TEXT Closure / Next Branch Selection

- **Status**: Done.
- **Goal**: Close the `MEMORY_CHECKPOINT_WITH_TEXT` slice and select the next board/memory branch.
- **Completed Outcome**:
  - The `MEMORY_CHECKPOINT_WITH_TEXT` slice is closed.
  - The branch now has: real-handler snapshot coverage, a candidate/resolver model, full commit-equivalence hardening, a smoke-only compiler switch, runtime diagnostic integration, detailed agreement-field logging, live semantics reconciliation, and passing manual live smoke validation.
  - Default registry remains `legacy`.
  - Smoke registry keeps `board_memory.memory_checkpoint_with_text = "compiler"`.
  - No production behavior was changed.
  - The resolver's `effective_commit` is still not consumed.
  - Selected next branch: `MEMORY_CHECKPOINT_WITH_ACTION`.
- **Next**:
  - Phase 32 — Step 1/10: MEMORY_CHECKPOINT_WITH_ACTION Commit Policy Inventory / Harness Plan.

---

### Phase 32: Operational Speed / Recovery Protocol Hardening

- **Status**: In Progress.
- **Goal**: Improve agent recovery speed and reliability after recoverable tool failures by hardening the protocol to separate structural validity from action feasibility.
- **Note**: The previously planned `MEMORY_CHECKPOINT_WITH_ACTION` work is deferred.
- **Allowed**:
  - Characterization tests for recovery blockers.
  - Narrow, behavior-preserving protocol fixes.
- **Forbidden**:
  - Broad changes to action validation or intent handling.
  - Changes to search or path normalization logic.
  - Changes to tool execution behavior.
- **Done When**:
  - Valid `intent+single-action` recovery bundles are no longer blocked by the atomic bundle guard.

---

#### Phase 32 — Step 1/8: Invalid Path + Atomic Bundle Recovery Characterization

- **Status**: Done.
- **Goal**: Characterize the root cause of valid recovery bundles being blocked after a recoverable failure.
- **Allowed**:
  - Test-only additions.
- **Forbidden**:
  - Any production code changes.
- **Completed Outcome**:
  - Narrowed root cause from path recovery to failure-mode atomic bundle rejection.
  - Characterized that valid intent+single-action bundles after recoverable failure should be protocol-valid.
  - Updated tests in `tests/test_response_pipeline_stages.py` to distinguish protocol validity from action/tool feasibility.
  - No runtime behavior was changed.
- **Next**:
  - Phase 32 — Step 2/8: Permit Valid Intent+Single-Action Bundles after Recoverable Failure.

---

#### Phase 32 — Step 2/8: Permit Valid Intent+Single-Action Bundles after Recoverable Failure

- **Status**: Done.
- **Goal**: Fix the `intent_atomic_bundle_guard` to allow structurally valid `intent+single-action` bundles after a recoverable failure.
- **Allowed**:
  - Narrow change to the atomic bundle guard.
  - Update tests to confirm the fix.
- **Forbidden**:
  - Broadly disabling the guard.
  - Skipping normal action/tool validation.
- **Completed Outcome**:
  - The `intent_atomic_bundle_guard` in `_reject_invalid_atomic_bundle_before_transition` no longer rejects structurally valid intent+single-action bundles during retry/continuation-after-failure.
  - Mutating actions are not rejected at this layer solely because they are mutating.
  - Normal action/tool policy still applies.
  - Malformed and unsupported multi-action bundles remain blocked.
  - No Angelica/live agent was run.
- **Next**:
  - Phase 32 — Step 3/8: E_ACTION_PAYLOAD_ARRAY / Read-only Multi-action Discovery Bundle Characterization.

---

#### Phase 32 — Step 3/8: E_ACTION_PAYLOAD_ARRAY / Read-only Multi-action Discovery Bundle Characterization

- **Status**: Done.
- **Goal**: Add characterization tests for current multi-action rejection and define the desired future behavior for read-only multi-action discovery bundles.
- **Allowed**:
  - Test-only additions.
- **Forbidden**:
  - Any production code changes.
  - Implementation of read-only multi-action execution.
- **Completed Outcome**:
  - Characterized that the current runtime/compiler treats one-intent multi-action output as invalid (`E_ACTION_PAYLOAD_ARRAY` / `multiple_actions`).
  - Added characterization tests for 3 read-only discovery actions.
  - Added negative controls for >3 actions, mixed read/write, and `run_shell`.
  - The future target is bounded read-only discovery batch support.
  - No tool execution behavior was changed.
  - No Angelica/live agent was run.
- **Next**:
  - Phase 32 — Step 4/8: Read-only Multi-action Discovery Bundle Support.

---

#### Phase 32 — Step 4/8: Read-only Multi-action Discovery Bundle Support

- **Status**: Done.
- **Goal**: Implement protocol support for bounded read-only multi-action discovery bundles to improve operational speed.
- **Allowed**:
  - Narrow changes to protocol validation logic.
  - Update tests to reflect new valid bundles.
- **Forbidden**:
  - Implementation of multi-action tool execution.
  - Changes to tool execution behavior.
  - Changes to search or path normalization logic.
- **Completed Outcome**:
  - Bounded one-intent read-only discovery bundles with 2–3 actions are now protocol-valid.
  - Mutating, `run_shell`, malformed, >3 actions, and unbounded discovery bundles remain blocked.
  - This reduces recovery/discovery round-trips for common “inspect/search docs” model outputs.
  - No tool execution behavior was changed.
  - No Angelica/live agent was run.
- **Next**:
  - Phase 32 — Step 5/8: Structure-only Think Repair Atomicity Characterization.

---

#### Phase 32 — Step 5/8: Structure-only Think Repair Atomicity Characterization

- **Status**: Done.
- **Goal**: Characterize the current behavior where a possible think repair is blocked by atomicity constraints, even if the repair is structure-only.
- **Allowed**:
  - Add characterization tests.
  - Add minimal diagnostic-only seams if needed to observe behavior.
- **Forbidden**:
  - Implementation of structure-only think repair allowance.
  - Changes to tool execution behavior.
  - Changes to search or path normalization logic.
- **Completed Outcome**:
  - Characterized current behavior where possible think repair can be blocked by atomicity constraints (e.g., when an intent payload is present).
  - Added a negative control for unsafe repairs that would alter intent/action semantics.
  - Added a future xfail test for structure-only think repair allowance.
  - No runtime behavior was changed.
  - No tool execution behavior was changed.
  - No search/path normalization was changed.
  - No Angelica/live agent was run.
- **Next**:
  - Phase 32 — Step 6/8: Structure-only Think Repair Allowance.

---

#### Phase 32 — Step 6/8: Structure-only Think Repair Allowance

- **Status**: Done.
- **Goal**: Allow local think-closure repair under atomicity constraints when the repair is provably structure-only.
- **Completed Outcome**:
  - Structure-only trailing `</think>` repair is now allowed under atomicity constraints when protocol-relevant payloads are unchanged.
  - The allowance is intentionally narrow: currently only simple trailing think closure is allowed.
  - Repairs that alter action/intent/file/protocol blocks remain blocked.
  - Think repair inside action JSON remains blocked.
  - Malformed reuse/followup atomicity remains protected.
  - No tool execution behavior changed.
  - No search/path normalization changed.
  - No Angelica/live agent was run.
- **Next**:
  - Phase 32 — Step 7/8: Broad Search Result Shaping.

---

#### Phase 32 — Step 4.5/8: Extracted Intent Payload + Single Action Recovery Bundle Reconciliation

- **Status**: Done.
- **Goal**: Fix a live regression where a valid `intent+action` recovery bundle was blocked because the intent was extracted into `step.intent_payload` before prevalidation.
- **Allowed**:
  - Narrow changes to `_reject_invalid_atomic_bundle_before_transition` to recognize `step.intent_payload` as valid intent context during recoverable failure.
  - Add regression tests.
- **Forbidden**:
  - Broadly disabling guards.
  - Changing tool execution or search/path normalization.
- **Completed Outcome**:
  - `_reject_invalid_atomic_bundle_before_transition` now treats extracted `step.intent_payload` as valid intent context for recoverable-failure recovery bundles.
  - Valid extracted-intent + single-action bundles after recoverable failure are no longer blocked by `retry_or_continuation_after_failure`.
  - Action-only without extracted intent remains blocked.
  - Malformed and unsupported multi-action bundles remain blocked.
  - Mutating single actions are not blocked at this layer solely because they are mutating.
  - Normal action/tool policy still applies.
  - No tool execution behavior changed.
  - No search/path normalization changed.
  - No Angelica/live agent was run.
- **Next**:
  - Phase 32 — Step 4.6/8: Runtime-State Recoverable Failure Detection for Extracted Intent Bundles.

---

#### Phase 32 — Step 4.6/8: Runtime-State Recoverable Failure Detection for Extracted Intent Bundles

- **Status**: Done.
- **Goal**: Make extracted `step.intent_payload` + single valid `ACTION_ONLY` recovery action pass the atomic bundle guard when recoverable failure is recorded in runtime state/context, even if `step.intent_error` is empty.
- **Allowed**:
  - Narrow changes to `_reject_invalid_atomic_bundle_before_transition` to recognize recoverable failure from runtime state.
  - Add regression tests.
- **Forbidden**:
  - Broadly disabling guards.
  - Changing tool execution or search/path normalization.
- **Completed Outcome**:
  - New smoke dump showed `step.intent_error` can be empty while recoverable failure exists in runtime state.
  - `_reject_invalid_atomic_bundle_before_transition` now detects recoverable failure from runtime/context state as well as step intent_error.
  - Extracted intent payload + single valid ACTION_ONLY recovery action now passes atomic bundle guard in this live shape.
  - Malformed and unsupported multi-action bundles remain blocked.
  - No tool execution behavior changed.
  - No search/path normalization changed.
  - No Angelica/live agent was run.
- **Next**:
  - Phase 32 — Step 5/8: Structure-only Think Repair Atomicity Characterization.

---

#### Phase 32 — Step 7/8: Broad Search Result Shaping

- **Status**: Done.
- **Goal**: When a search result is too broad, return a compact path histogram summary instead of only first raw snippets.
- **Completed Outcome**:
  - Broad `search_content` results now return compact path histogram summaries when result volume is too high.
  - Top files are grouped by match count.
  - Broad search output includes non-prescriptive narrowing hints.
  - Small search behavior remains unchanged.
  - No search matching semantics changed.
  - No path normalization changed.
  - No automatic recovery actions were added.
  - No memory-board anchoring was added.
  - No Angelica/live agent was run.
- **Next**:
  - Phase 32 — Step 8/8: Repeat Broad Search Guard / Path Memory Anchoring Decision.

---

#### Phase 32 — Step 7.5/8: Stale Retry Guard Reconciliation

- **Status**: Complete.
- **Goal**: Ensure `retry_or_continuation_after_failure` only triggers when there is an actual active recoverable failure context.
- **Completed Outcome**:
  - `retry_or_continuation_after_failure` now requires an actual active recoverable failure context when `last_error_recoverable` is explicitly available.
  - Stale retry context with `last_error_recoverable=False` no longer blocks valid `ACTION_ONLY` recovery actions.
  - True recoverable failure behavior remains preserved.
  - No search shaping, tool execution, or path normalization was changed.
  - No Angelica/live agent was run.
- **Next**:
  - Phase 32 — Step 8/8: Repeat Broad Search Guard / Path Memory Anchoring Decision.

---

#### Phase 32 — Step 8/8: Repeat Broad Search Guard / Path Memory Anchoring Decision

- **Status**: Complete.
- **Goal**: Decide whether to add a hard repeat broad search guard or automatic path memory anchoring.
- **Completed Outcome**:
  - Decided not to add hard repeat broad search blocking in Phase 32.
  - Decided not to add automatic memory-board path anchoring in Phase 32.
  - Broad search histogram from Step 7 is the primary mitigation for repeated broad search.
  - Path memory anchoring should be considered in a future phase as hint-only/diagnostic-first, not automatic writes.
  - Repeat broad search guard should be considered in a future phase as characterization-first.
  - Refined broad search hint wording to prefer skeleton/chunk before full read.
  - No search matching semantics changed.
  - No path normalization changed.
  - No tool execution behavior changed.
  - No protocol guard behavior changed.
  - No Angelica/live agent was run.


### Phase 34: Protocol Hardening

- **Status**: In Progress.
- **Goal**: Harden runtime protocol parsing and recovery against common, recoverable model errors.
- **Allowed**:
  - Narrow, behavior-preserving protocol normalization and repair.
  - Characterization tests for recovery blockers.
- **Forbidden**:
  - Broad changes to action validation or intent handling.
  - Changes to tool execution behavior.
- **Done When**:
  - Key recovery gaps are closed with narrow, tested fixes.

---

#### Phase 34 — Step 1/N: Think Boundary Auto-Closure Normalization

- **Status**: Complete.
- **Goal**: Make runtime protocol parsing tolerant to common unclosed `<think>` boundary errors by auto-closing open `<think>` blocks before known protocol boundary tags or at EOF.
- **Completed Outcome**:
  - Safe open `<think>` is auto-closed before known top-level protocol boundary tags and at EOF.
  - This intentionally changes prior E_UNCLOSED_THINK recovery behavior for safe boundary-repairable cases.
  - Protected contexts remain safe: action JSON, intent payloads, file_content, quoted strings, fenced code, inline code, comments.
  - Repair is normalization only; compiler/prevalidation/action policy still decide validity/dispatch.
  - Nested think stack semantics remain out of scope.
  - No Angelica/live agent was run.
- **Next**:
  - Phase 33 — Search/Path Recovery UX Hardening.

### Phase 35: Board/Memory Commit Policy (MEMORY_CHECKPOINT_WITH_ACTION)

- **Status**: In Progress.
- **Goal**: Extend the commit-equivalence model to the `MEMORY_CHECKPOINT_WITH_ACTION` branch.
- **Allowed**:
  - Inventory `MEMORY_CHECKPOINT_WITH_ACTION` commit paths.
  - Design and implement synthetic harness coverage.
  - Define a candidate/resolver model.
- **Forbidden**:
  - Behavior changes.
  - Production authority flips.
  - Memory commit behavior changes.
  - Board handler behavior changes.
  - Dispatch/action behavior changes.
- **Done When**:
  - The `MEMORY_CHECKPOINT_WITH_ACTION` branch is smoke-validated with compiler authority.

---

#### Phase 35 — Step 1/10: MEMORY_CHECKPOINT_WITH_ACTION Commit Policy Inventory / Harness Plan

- **Status**: Done.
- **Goal**: Inventory current legacy behavior for `MEMORY_CHECKPOINT_WITH_ACTION` and write a concrete harness plan for the next step.
- **Allowed**:
  - Docs-only inventory and harness plan.
- **Forbidden**:
  - No production code or test changes.
  - No authority transfer.
  - No default registry changes.
  - No smoke switch changes.
  - No runtime diagnostic integration.
- **Completed Outcome**:
  - Inventoried legacy behavior for memory checkpoint + action.
  - The `MemoryBoardStageHandler` detects the marker and action, strips the marker, and returns `handled=True`.
  - The pipeline overrides this to `handled=False` to ensure the action is passed through for dispatch.
  - A commit is attempted for the marker, resulting in `accepted_count=0`.
  - Documented the observation-boundary issue: a raw-response semantic pass may see a memory marker, while a post-handler observation may see `ACTION_ONLY` after the marker is stripped.
  - A harness plan was documented to add a real-handler snapshot test in the next step.
  - No production code or tests were changed.
- **Next**:
  - Phase 35 — Step 2/10: MEMORY_CHECKPOINT_WITH_ACTION Synthetic Commit-Equivalence Harness.

---

#### Phase 35 — Step 2/10: MEMORY_CHECKPOINT_WITH_ACTION Synthetic Commit-Equivalence Harness

- **Status**: Done.
- **Goal**: Extend the commit-equivalence harness to characterize `MEMORY_CHECKPOINT_WITH_ACTION` using synthetic coverage.
- **Allowed**:
  - Test-only changes to `tests/test_board_memory_commit_equivalence.py`.
- **Forbidden**:
  - No production code changes.
  - No authority transfer.
  - No registry/switch changes.
- **Completed Outcome**:
  - Added a real-handler-backed snapshot test to characterize `MEMORY_CHECKPOINT_WITH_ACTION` using `MemoryBoardStageHandler` with a mocked board engine result.
  - The test confirms action preservation, pass-through behavior, and zero-count commit semantics.
  - The test explicitly documents the observation-boundary issue where the compiler shape is `ACTION_ONLY` after the handler strips the memory marker.
  - Added negative controls to prevent misclassification.
  - No production code was changed.
- **Next**:
  - Phase 35 — Step 3/10: MEMORY_CHECKPOINT_WITH_ACTION Candidate Model / Resolver Design.

---

#### Phase 35 — Step 3/10: MEMORY_CHECKPOINT_WITH_ACTION Candidate Model / Resolver Design

- **Status**: Done.
- **Goal**: Add a typed candidate model and resolver for `MEMORY_CHECKPOINT_WITH_ACTION` without changing runtime behavior.
- **Allowed**:
  - Add `build_memory_checkpoint_with_action_commit_candidate`.
  - Add `resolve_memory_checkpoint_with_action_commit_authority`.
  - Add targeted unit tests for the new candidate/resolver.
- **Forbidden**:
  - Wiring the resolver into the runtime pipeline.
  - Consuming `effective_commit`.
  - Changing registry/switch defaults.
  - Adding a smoke switch for this branch.
  - Adding runtime diagnostic integration.
- **Completed Outcome**:
  - Added a candidate builder and resolver for `MEMORY_CHECKPOINT_WITH_ACTION`.
  - The new components model the characterized legacy behavior, including action preservation and pass-through for dispatch.
  - Added targeted unit tests for the new candidate and resolver, including legacy mode and compiler-mode fallback on mismatch.
  - The resolver is not yet consumed by the runtime.
  - No production behavior was changed.
- **Next**:
  - Phase 35 — Step 4/10: MEMORY_CHECKPOINT_WITH_ACTION Commit-Equivalence Hardening.

---

#### Phase 35 — Step 4/10: MEMORY_CHECKPOINT_WITH_ACTION Commit-Equivalence Hardening

- **Status**: Done.
- **Goal**: Harden the MCTA commit-equivalence model and tests to ensure the resolver only reports `commit_equivalent=True` for truly equivalent legacy behavior.
- **Allowed**:
  - Add targeted tests for MCTA equivalence hardening.
  - Add small resolver hardening only if a new test exposes an actual gap.
- **Forbidden**:
  - Wiring the resolver into the runtime pipeline.
  - Consuming `effective_commit`.
  - Adding or flipping registry/switch entries.
  - Adding runtime diagnostic integration.
- **Completed Outcome**:
  - Hardened the candidate builder with negative controls for non-MCTA cases.
  - Hardened the resolver with stricter agreement checks for branch and response text.
  - Added targeted tests for candidate availability and resolver fallback on various mismatches.
  - The resolver is still not wired into the runtime.
  - No production behavior was changed.
- **Next**:
  - Phase 35 — Step 5/10: MEMORY_CHECKPOINT_WITH_ACTION Smoke Switch Validation.

---

#### Phase 35 — Step 5/10: MEMORY_CHECKPOINT_WITH_ACTION Smoke Switch Validation

- **Status**: Done.
- **Goal**: Add smoke-only switch coverage for `MEMORY_CHECKPOINT_WITH_ACTION` candidate/resolver authority validation, without changing default runtime behavior.
- **Allowed**:
  - Add `board_memory.memory_checkpoint_with_action` switch key to registries.
  - Add smoke/test override for `switch_value="compiler"`.
  - Add targeted tests for smoke compiler selection and fallback.
- **Forbidden**:
  - Wiring the resolver into the runtime pipeline.
  - Consuming `effective_commit`.
  - Changing default registry behavior to `compiler`.
  - Adding runtime diagnostic integration.
- **Completed Outcome**:
  - Added `board_memory.memory_checkpoint_with_action` to the switch registries, with `legacy` as default and `compiler` in the smoke profile.
  - Added synthetic tests to validate that compiler authority is selected for clean, observed-equivalent MCTA cases under the smoke profile, with fallback for mismatches and negative controls.
  - The default registry remains `legacy`.
  - The resolver is not yet wired into the runtime, and `effective_commit` is not consumed.
  - No production behavior was changed.
- **Next**:
  - Phase 35 — Step 6/10: MEMORY_CHECKPOINT_WITH_ACTION Runtime Diagnostic Integration.

---

#### Phase 35 — Step 6/10: MEMORY_CHECKPOINT_WITH_ACTION Runtime Diagnostic Integration

- **Status**: Done.
- **Goal**: Integrate the `MEMORY_CHECKPOINT_WITH_ACTION` commit authority resolver into the runtime pipeline for diagnostic logging only, without changing behavior.
- **Allowed**:
  - Call `resolve_memory_checkpoint_with_action_commit_authority` from the pipeline diagnostic path.
  - Add diagnostic logging for MCTA using the existing memory commit authority diagnostic pattern.
  - Add targeted tests proving diagnostics are emitted.
- **Forbidden**:
  - Do not change runtime behavior.
  - Do not consume `decision.effective_commit`.
  - Do not replace legacy outcomes with compiler values.
  - Do not change `MemoryBoardStageHandler` behavior.
  - Do not flip the default registry to `compiler`.
- **Completed Outcome**:
  - The `resolve_memory_checkpoint_with_action_commit_authority` resolver is now called from `_run_checkpoint_stage` for diagnostic logging only.
  - The resolver's `effective_commit` is not consumed, and no runtime behavior was changed.
  - The default registry remains `legacy`, and the smoke registry remains `compiler` for this branch for validation purposes.
  - No dispatch, action, or `MemoryBoardStageHandler` behavior was changed.
- **Next**:
  - Phase 35 — Step 7/10: MEMORY_CHECKPOINT_WITH_ACTION Live Smoke Validation.

---

#### Phase 35 — Step 7/10: MEMORY_CHECKPOINT_WITH_ACTION Live Smoke Validation

- **Status**: Done.
- **Goal**: Validate the MCTA runtime diagnostic integration with a manual/live smoke run.
- **Allowed**:
  - Run smoke tests with the smoke profile.
  - Analyze logs for diagnostic correctness and runtime behavior preservation.
- **Forbidden**:
  - Code changes, unless a concrete mismatch is found and a hotfix is approved.
- **Completed Outcome**:
  - Manual live smoke was run for MCTA under the smoke profile.
  - The `board_memory_commit_authority_resolution` diagnostic was observable.
  - **Result**: NOT A PASS. `commit_equivalent` was `False` due to a mismatch in `commit_attempted_agreement`.
  - Runtime behavior was preserved: action pass-through was correct, and no behavior changed.
  - The resolver's `effective_commit` is not consumed.
- **Next**:
  - Phase 35 — Step 8/10: MEMORY_CHECKPOINT_WITH_ACTION Live Semantics Reconciliation.

---

#### Phase 35 — Step 8/10: MEMORY_CHECKPOINT_WITH_ACTION Live Semantics Reconciliation

- **Status**: Done.
- **Goal**: Reconcile the MCTA candidate/resolver expectations with live smoke behavior observed in logs, without changing runtime behavior.
- **Completed Outcome**:
  - Live smoke confirmed MCTA diagnostic branch is emitted and action/pass-through behavior is preserved.
  - Reconciled MCTA commit semantics: bare marker + action does not count as a durable memory content commit attempt.
  - `expected_commit_attempted` is now `False` for marker-only + action in the candidate model.
  - No runtime behavior was changed.
  - `effective_commit` is still not consumed.
- **Next**:
  - Phase 35 — Step 9/10: MEMORY_CHECKPOINT_WITH_ACTION Live Smoke Re-run / Closure Decision.

---

#### Phase 35 — Step 9/10: MEMORY_CHECKPOINT_WITH_ACTION Live Smoke Re-run / Closure Decision

- **Status**: Done.
- **Goal**: Re-run live/integrated smoke for the `MEMORY_CHECKPOINT_WITH_ACTION` branch to confirm that `commit_equivalent` is now `True` and decide whether to close the slice.
- **Completed Outcome**:
  - Manual live smoke re-run passed.
  - MCTA diagnostic showed `switch_value="compiler"`, `authority_source="compiler"`, `selected_by_switch=True`, `candidate_available=True`, and `commit_equivalent=True`.
  - All detailed agreement fields relevant to MCTA were `True`.
  - Runtime behavior was preserved: `behavior_changed=False`, `shadow_only=True`.
  - The resolver's `effective_commit` is still not consumed.
- **Next**:
  - Phase 35 — Step 10/10: MEMORY_CHECKPOINT_WITH_ACTION Closure / Next Branch Selection.

---

#### Phase 35 — Step 10/10: MEMORY_CHECKPOINT_WITH_ACTION Closure / Next Branch Selection

- **Status**: Done.
- **Goal**: Close Phase 35 for MEMORY_CHECKPOINT_WITH_ACTION and record the final state after successful live smoke re-run.
- **Completed Outcome**:
  - Phase 35 is complete.
  - MCTA branch is validated through live smoke.
  - Clean bare marker + action MCTA reaches compiler authority in smoke profile with `commit_equivalent=True`.
  - Runtime behavior remains legacy/default-safe.
  - `effective_commit` is not consumed.
  - Default registry remains `legacy`.
  - Smoke registry remains `compiler`.
  - Live semantics reconciliation recorded:
    bare marker + action does not count as durable memory content commit attempt.
  - For real memory-content commit + action cases, current model safely falls back unless separately characterized in a future branch.
- **Next**:
  - Phase 36 — MEMORY_CONTENT_WITH_ACTION Commit Policy Characterization.

### Phase 36: MEMORY_CONTENT_WITH_ACTION Commit Policy Characterization

- **Status**: In Progress.
- **Goal**: Characterize the commit policy for checkpoints with a durable memory content tag and an action.
- **Allowed**:
  - Characterization-first.
- **Forbidden**:
  - No production behavior change.
  - No authority transfer.
  - No `effective_commit` consumption.
  - No default registry flip.
- **Done When**:
  - The commit policy for memory content with action is characterized.

---

#### Phase 36 — Step 1/N: MEMORY_CONTENT_WITH_ACTION Commit Policy Characterization / Inventory

- **Status**: Done.
- **Goal**: Characterize the distinct live/runtime case where a checkpoint includes a durable memory content tag and an action.
- **Completed Outcome**:
  - Inventoried the distinct live/runtime case where a checkpoint includes a durable memory content tag and an action.
  - This case is distinct from the Phase 35 bare-marker MCTA because it involves a durable content commit (`accepted_count=1`).
  - Added a characterization test to `tests/test_board_memory_commit_equivalence.py` to snapshot the legacy behavior.
  - No production behavior was changed.
- **Next**:
  - Phase 36 — Step 2/N: Design a candidate/resolver model for memory content + action.

---

#### Phase 36 — Step 2/N: MEMORY_CONTENT_WITH_ACTION Candidate / Resolver Model Design

- **Status**: Done.
- **Goal**: Design and add a typed candidate/resolver model for the distinct memory content tag + action case, without changing runtime behavior.
- **Allowed**:
  - Add a new candidate builder and resolver for memory content + action.
  - Add targeted tests for candidate/resolver behavior.
- **Forbidden**:
  - Do not change runtime behavior.
  - Do not wire the new resolver into the runtime pipeline.
  - Do not consume `effective_commit`.
  - Do not change `MemoryBoardStageHandler`.
  - Do not change switch registry or flip defaults.
- **Done When**:
  - The candidate/resolver model is implemented with tests.
  - No runtime behavior has changed.
- **Completed Outcome**:
  - Added a candidate builder and resolver for the distinct durable memory content + action case.
  - The model is distinct from the Phase 35 bare-marker MCTA model and uses `compiler_has_memory_tags` and the absence of `compiler_has_memory_checkpoint` to distinguish.
  - Added targeted tests for the new candidate/resolver, including negative controls for the bare-marker MCTA case.
  - No runtime behavior was changed.
  - No runtime diagnostic wiring was added, and `effective_commit` is not consumed.
  - No registry or default switch changes were made.
- **Next**:
  - Phase 36 — Step 3/N: Commit-Equivalence Hardening / Smoke Switch Planning.

---

#### Phase 36 — Step 3/N: MEMORY_CONTENT_WITH_ACTION Commit-Equivalence Hardening / Smoke Switch Planning

- **Status**: Done.
- **Goal**: Harden the MEMORY_CONTENT_WITH_ACTION candidate/resolver model and prepare the smoke-switch plan, without changing runtime behavior.
- **Allowed**:
  - Add commit-equivalence hardening tests and negative controls.
  - Document the smoke switch plan.
- **Forbidden**:
  - Do not change runtime behavior.
  - Do not wire the resolver into the runtime pipeline.
  - Do not consume `effective_commit`.
  - Do not change `MemoryBoardStageHandler`.
  - Do not change switch registry or flip defaults.
  - Do not add runtime diagnostic integration.
- **Done When**:
  - Commit-equivalence tests are hardened.
  - The smoke switch plan is documented.
  - No runtime behavior has changed.
- **Completed Outcome**:
  - Strengthened commit-equivalence tests and negative controls for the durable memory content + action case.
  - Documented the smoke switch plan for `board_memory.memory_content_with_action` without adding registry entries.
  - No runtime behavior was changed, no diagnostic wiring was added, and `effective_commit` is not consumed.
  - Phase 35 MCTA semantics remain unchanged.
- **Next**:
  - Phase 36 — Step 4/N: Smoke Switch Registration / Validation.

---

#### Phase 36 — Step 4/N: MEMORY_CONTENT_WITH_ACTION Smoke Switch Registration / Validation

- **Status**: Done.
- **Goal**: Add smoke-switch registration and validation coverage for MEMORY_CONTENT_WITH_ACTION candidate/resolver authority, without changing runtime behavior.
- **Allowed**:
  - Add the `board_memory.memory_content_with_action` switch key to registries.
  - Add smoke validation tests for compiler selection and fallback.
- **Forbidden**:
  - Do not change runtime behavior.
  - Do not wire the resolver into the runtime pipeline.
  - Do not consume `effective_commit`.
  - Do not change `MemoryBoardStageHandler`.
  - Do not change existing switch defaults.
  - Do not add runtime diagnostic integration.
- **Done When**:
  - The switch key is added to registries.
  - Smoke validation tests are implemented and passing.
  - No runtime behavior has changed.
- **Completed Outcome**:
  - Added the `board_memory.memory_content_with_action` switch key to the registries.
  - The default registry remains `legacy`, while the smoke registry uses `compiler`.
  - Added smoke validation tests for compiler selection and fallback.
  - No runtime behavior was changed, no diagnostic wiring was added, and `effective_commit` is not consumed.
  - Phase 35 MCTA semantics remain unchanged.
- **Next**:
  - Phase 36 — Step 5/N: Runtime Diagnostic Integration.

---

#### Phase 36 — Step 5/N: MEMORY_CONTENT_WITH_ACTION Runtime Diagnostic Integration

- **Status**: Done.
- **Goal**: Integrate the MEMORY_CONTENT_WITH_ACTION resolver into `_run_checkpoint_stage` for diagnostic logging only, without changing runtime behavior.
- **Allowed**:
  - Call `resolve_memory_content_with_action_commit_authority` from the pipeline diagnostic path.
  - Log the diagnostic using existing patterns.
  - Add targeted tests proving the diagnostic is emitted.
- **Forbidden**:
  - Do not change runtime behavior.
  - Do not consume `effective_commit`.
  - Do not change `MemoryBoardStageHandler` behavior.
  - Do not flip the default registry to `compiler`.
- **Completed Outcome**:
  - The `resolve_memory_content_with_action_commit_authority` resolver is now called from `_run_checkpoint_stage` for diagnostic logging only.
  - The resolver's `effective_commit` is not consumed, and no runtime behavior was changed.
  - The default registry remains `legacy`, and the smoke registry remains `compiler` for this branch for validation purposes.
  - No dispatch, action, or `MemoryBoardStageHandler` behavior was changed.
  - Phase 35 MCTA semantics remain unchanged.
- **Next**:
  - Phase 36 — Step 6/N: Runtime Diagnostic Smoke Validation.

---

#### Phase 36 — Step 6/N: MEMORY_CONTENT_WITH_ACTION Runtime Diagnostic Smoke Validation

- **Status**: Done.
- **Goal**: Validate the live/runtime diagnostic path for `board_memory.memory_content_with_action` under the smoke profile.
- **Completed Outcome**:
  - Manual/live smoke validated that the `board_memory.memory_content_with_action` diagnostic is emitted.
  - The smoke-profile diagnostic selected compiler authority with `authority_source="compiler"`, `selected_by_switch=True`, and `commit_equivalent=True`.
  - Relevant agreement fields, including commit-attempted and accepted-count agreement, were aligned for the clean durable memory content + action case.
  - Runtime behavior was preserved: response pipeline dispatch, pre-dispatch dispatch-ready, and dispatch outcome evaluation were observed.
  - `behavior_changed=True` is expected here as a diagnostic-only branch-name delta because the compiler candidate branch is `MEMORY_CONTENT_WITH_ACTION` while the legacy branch remains `MEMORY_CHECKPOINT_WITH_ACTION`.
  - The resolver's `effective_commit` is not consumed.
- **Next**:
  - Phase 36 — Step 7/N: Live Smoke Closure / Reconciliation Decision.

---

#### Phase 36 — Step 7/N: MEMORY_CONTENT_WITH_ACTION Live Smoke Closure / Reconciliation Decision

- **Status**: Done.
- **Goal**: Decide whether live smoke requires reconciliation before closing the MEMORY_CONTENT_WITH_ACTION slice.
- **Completed Outcome**:
  - No live semantics reconciliation is required.
  - The clean durable memory content + action case is validated in the smoke profile.
  - Diagnostic compiler selection is observed only as shadow/diagnostic authority; runtime behavior remains legacy/default-safe.
  - The diagnostic-only branch-name delta is documented and expected.
  - `effective_commit` remains unconsumed, and no production authority flip occurred.
  - Phase 35 MCTA semantics remain unchanged.
- **Next**:
  - Phase 36 — Step 8/N: Closure / Next Branch Selection.

---

#### Phase 36 — Step 8/N: MEMORY_CONTENT_WITH_ACTION Closure / Next Branch Selection

- **Status**: Done.
- **Goal**: Close the MEMORY_CONTENT_WITH_ACTION slice and select the next board/memory direction.
- **Completed Outcome**:
  - Phase 36 is complete.
  - Durable memory content + action is characterized, modeled, smoke-switch validated, wired for diagnostic-only runtime logging, and live-smoke validated.
  - Clean durable memory content + action reaches compiler authority in the smoke profile with `commit_equivalent=True`.
  - Runtime behavior remains legacy/default-safe.
  - `effective_commit` is not consumed.
  - Default registry remains `legacy`.
  - Smoke registry remains `compiler`.
  - The diagnostic-only branch-name delta is expected and documented.
  - Phase 35 MCTA semantics remain unchanged.
- **Next**:
  - Phase 37 — Board/Memory Remaining Branch Selection / Next Slice Planning.

---

### Phase 37: Board/Memory Remaining Branch Selection / Next Slice Planning

- **Status**: In Progress.
- **Goal**: Decide whether any board-memory commit-policy branches remain after the Phase 31, Phase 35, and Phase 36 slices, and select the next safe refactor direction.
- **Allowed**:
  - Docs-only inventory and slice-boundary review.
  - Identify whether remaining work belongs to `board_memory`, `board_checkpoint`, `terminal_answer`, `dispatch`, or `recovery`.
  - Select the next branch without changing runtime behavior.
- **Forbidden**:
  - No production behavior change.
  - No runtime diagnostic wiring.
  - No switch registry changes.
  - No `effective_commit` consumption.
  - Do not merge `board_checkpoint.plan_*` authority work into board-memory commit-policy closure.
- **Done When**:
  - The completed board-memory commit-policy branches are listed.
  - The remaining branch boundary is clear.
  - The next slice is selected.

---

#### Phase 37 — Step 1/N: Board/Memory Remaining Branch Selection / Next Slice Planning

- **Status**: Done.
- **Goal**: Inventory the completed board-memory commit-policy branches and decide the next refactor direction.
- **Completed Outcome**:
  - Confirmed that the board-memory commit-policy line now covers:
    - `memory_checkpoint_only` from Phase 31.
    - `memory_checkpoint_with_text` from Phase 31.
    - `memory_checkpoint_with_action` from Phase 35.
    - `memory_content_with_action` from Phase 36.
  - Confirmed that default registry values remain `legacy` while smoke registry values validate compiler authority for the completed board-memory branches.
  - Confirmed that `board_checkpoint.plan_checkpoint_only`, `board_checkpoint.plan_checkpoint_with_text`, and `board_checkpoint.plan_checkpoint_with_action` are separate authority branches and should be handled as a distinct slice.
  - No production behavior was changed.
- **Next**:
  - Phase 37 — Step 2/N: Board/Memory Commit-Policy Closure / Cross-Slice Boundary Review.

---

#### Phase 37 — Step 2/N: Board/Memory Commit-Policy Closure / Cross-Slice Boundary Review

- **Status**: Done.
- **Goal**: Close the board-memory commit-policy line and define the cross-slice boundary before selecting the next refactor slice.
- **Completed Outcome**:
  - Board-memory commit-policy work is closed for the currently characterized branches:
    - `board_memory.memory_checkpoint_only`.
    - `board_memory.memory_checkpoint_with_text`.
    - `board_memory.memory_checkpoint_with_action`.
    - `board_memory.memory_content_with_action`.
  - The completed board-memory branches remain default-legacy and smoke-compiler where validated.
  - Runtime behavior remains legacy/default-safe.
  - `effective_commit` is not consumed by the runtime.
  - No switch registry changes were made.
  - No runtime diagnostic wiring was added in this step.
  - `board_checkpoint.plan_checkpoint_only`, `board_checkpoint.plan_checkpoint_with_text`, and `board_checkpoint.plan_checkpoint_with_action` remain a separate authority slice.
  - The next slice should start with boundary review rather than direct production-code changes.
- **Next**:
  - Phase 38 — Board-Checkpoint Plan Authority Boundary Review / Next Slice Selection.

---

### Phase 38: Board-Checkpoint Plan Authority Boundary Review / Next Slice Selection

- **Status**: In Progress.
- **Goal**: Reconcile the current roadmap state for `board_checkpoint.plan_*` authority branches and decide whether any plan-domain board-checkpoint work remains before selecting the next refactor slice.
- **Allowed**:
  - Docs-only inventory and boundary review.
  - Confirm prior synthetic and live smoke coverage for `board_checkpoint.plan_checkpoint_only`, `board_checkpoint.plan_checkpoint_with_text`, and `board_checkpoint.plan_checkpoint_with_action`.
  - Decide whether this slice is already closed by Phase 27 or needs a narrow follow-up.
- **Forbidden**:
  - No production behavior change.
  - No switch registry changes.
  - No runtime diagnostic wiring.
  - No authority transfer.
  - Do not merge board-checkpoint plan authority with board-memory commit-policy work.
- **Done When**:
  - Prior plan-domain coverage is summarized.
  - The remaining work decision is recorded.
  - The next slice is selected.

---

#### Phase 38 — Step 1/N: Board-Checkpoint Plan Authority Boundary Review / Inventory

- **Status**: Done.
- **Goal**: Inventory the existing `board_checkpoint.plan_*` authority state before deciding whether this slice needs new work.
- **Completed Outcome**:
  - Confirmed that the default registry keeps `board_checkpoint.plan_checkpoint_only`, `board_checkpoint.plan_checkpoint_with_text`, and `board_checkpoint.plan_checkpoint_with_action` on `legacy`.
  - Confirmed that the smoke registry keeps those same plan-domain branches on `compiler` for continued validation.
  - Confirmed that Phase 27 already validated the plan-domain board/checkpoint smoke slice, including synthetic smoke coverage, authority diagnostics, and live Angelica smoke for the plan checkpoint branches.
  - Confirmed that Phase 27 closure explicitly kept default authority on `legacy` and avoided memory checkpoint authority transfer.
  - No production behavior was changed.
- **Next**:
  - Phase 38 — Step 2/N: Board-Checkpoint Plan Authority Closure / Remaining Work Decision.

---

#### Phase 38 — Step 2/N: Board-Checkpoint Plan Authority Closure / Remaining Work Decision

- **Status**: Done.
- **Goal**: Decide whether the `board_checkpoint.plan_*` authority slice requires additional work or can be closed based on prior Phase 27 validation.
- **Completed Outcome**:
  - The plan-domain board-checkpoint authority slice is closed.
  - No new runtime, registry, diagnostic, or test work is required for the currently characterized `board_checkpoint.plan_*` branches.
  - Prior Phase 27 work already validated:
    - `board_checkpoint.plan_checkpoint_only`.
    - `board_checkpoint.plan_checkpoint_with_text`.
    - `board_checkpoint.plan_checkpoint_with_action`.
  - Each plan-domain branch has synthetic smoke coverage, authority diagnostics, and live Angelica smoke validation under the smoke profile.
  - Default registry values remain `legacy`.
  - Smoke registry values remain `compiler` for continued validation.
  - No production authority flip occurred.
  - No memory checkpoint authority transfer occurred.
  - No board-memory commit-policy work was reopened.
- **Next**:
  - Phase 39 — Next Semantic Runtime Slice Selection.

---

### Phase 39: Next Semantic Runtime Slice Selection

- **Status**: In Progress.
- **Goal**: Select the next safe semantic-runtime refactor slice after closing the board/checkpoint plan-authority and board-memory commit-policy lines.
- **Allowed**:
  - Docs-only inventory and decision work.
  - Compare remaining candidate slices by safety, live-agent value, and refactor risk.
  - Select a next active slice without changing runtime behavior.
- **Forbidden**:
  - No production behavior change.
  - No switch registry changes.
  - No runtime diagnostic wiring.
  - No authority transfer.
  - No legacy cleanup or deletion before a consumer map exists.
- **Done When**:
  - Candidate next slices are listed.
  - The selected next active slice is recorded.
  - Stop lines for the selected slice are documented.

---

#### Phase 39 — Step 1/N: Next Semantic Runtime Slice Selection / Candidate Inventory

- **Status**: Done.
- **Goal**: Inventory candidate next slices after closing the board/checkpoint and board-memory authority work.
- **Completed Outcome**:
  - Confirmed that the recently closed slices are:
    - `board_checkpoint.plan_*` authority work.
    - `board_memory` commit-policy work for the characterized memory checkpoint/content branches.
  - Identified candidate next slices:
    - Phase 33 — Search/Path Recovery UX Hardening.
    - Terminal-answer remaining authority/boundary work.
    - Recovery remaining branches and deferred stateful/internal-summary recovery work.
    - Dispatch/action boundary work.
    - Legacy/compatibility cleanup, deferred until a consumer map exists.
  - Preferred near-term candidate is Phase 33 because it is already listed as Not started, targets live-agent search/path failures, and can proceed characterization-first without authority transfer.
  - No production behavior was changed.
- **Next**:
  - Phase 39 — Step 2/N: Select Next Active Slice.

---

#### Phase 39 — Step 2/N: Select Next Active Slice

- **Status**: Done.
- **Goal**: Select the next active semantic-runtime refactor slice after candidate inventory.
- **Decision**: Select Phase 33 — Search/Path Recovery UX Hardening as the next active slice.
- **Rationale**:
  - Phase 33 is already present in the roadmap as Not started.
  - Search/path failures are live-agent pain points and directly affect recovery speed and quality.
  - The slice can proceed safely with characterization-first and diagnostic/hint-first work.
  - The slice does not require production authority transfer, switch default flips, or `effective_commit` consumption.
  - Terminal-answer, recovery-deferred, dispatch/action, and legacy cleanup candidates remain deferred until after the search/path slice or a new selection review.
- **Stop Lines for Phase 33**:
  - No hard repeat broad-search blocking without characterization.
  - No automatic memory-board path anchoring.
  - No tool execution behavior change without explicit characterization and tests.
  - No broad recovery rewrite.
  - No production authority transfer.
  - No legacy cleanup.
- **Next**:
  - Phase 33 — Step 1/N: Search/Path Recovery UX Hardening Inventory.

### Phase 33: Search/Path Recovery UX Hardening

- **Status**: Done.
- **Goal**: Improve user experience and agent recovery from search/path related failures.
- **Allowed**:
  - Characterization tests for repeat broad search.
  - Diagnostic-first or hint-only path memory anchoring.
  - Search/path recovery inventory and current-behavior characterization.
  - Hint wording and diagnostic improvements that do not change search matching, path normalization, tool execution, or recovery authority.
- **Forbidden**:
  - Hard repeat broad search blocking without characterization.
  - Automatic memory-board writes.
  - Automatic path memory anchoring.
  - Broad recovery rewrites.
  - Production authority transfer.
  - Tool execution behavior changes without explicit characterization and tests.
- **Done When**:
  - Search/path recovery behavior is inventoried.
  - Repeat broad search and invalid path recovery behavior are characterized.
  - Any UX/hint hardening is proven behavior-preserving or explicitly documented as a controlled behavior change.

---

#### Phase 33 — Step 1/N: Search/Path Recovery UX Hardening Inventory

- **Status**: Done.
- **Goal**: Inventory existing search/path recovery work and identify the files/tests needed for current-behavior characterization.
- **Completed Outcome**:
  - Confirmed Phase 32 already completed broad `search_content` result shaping with compact path histogram summaries and non-prescriptive narrowing hints.
  - Confirmed Phase 32 deliberately deferred hard repeat broad-search blocking and automatic path memory anchoring.
  - Identified candidate implementation areas:
    - `modules/agent/orchestration/runtime/filesystem_path_failure.py`.
    - `modules/agent/orchestration/runtime/filesystem_path_validation.py`.
    - `modules/agent/orchestration/runtime/search_quality.py`.
    - `modules/agent/orchestration/prompts/recovery_prompt_builder.py`.
    - `modules/agent/orchestration/runtime/recovery_state.py`.
    - `modules/tools/definitions/search.py`.
  - Identified candidate characterization tests:
    - `tests/test_filesystem_path_failure_recovery.py`.
    - `tests/test_search_quality.py`.
    - `tests/test_search_tool_result_shaping.py`.
    - recovery prompt and recoverable-failure tests that mention `search_content`, `search_files`, and path validation.
  - No production behavior was changed.
- **Next**:
  - Phase 33 — Step 2/N: Search/Path Current Behavior Characterization.

---

#### Phase 33 — Step 2/N: Search/Path Current Behavior Characterization

- **Status**: Done.
- **Goal**: Characterize current search/path behavior before deciding whether to add UX hardening.
- **Completed Outcome**:
  - Characterized broad search result shaping:
    - Broad `search_content` results are shaped into `broad_search_summary` with compact per-path histogram output.
    - The summary includes total match/file counts and a non-prescriptive hint to narrow with file skeletons, chunks, listed paths, or exact symbols.
    - Broad `search_files` results intentionally retain the older preview-style “too broad” output rather than the histogram summary.
  - Characterized diagnostic search quality behavior:
    - `classify_search_action_quality(...)` is diagnostic-only and does not block or recover.
    - Weakly bounded search can produce warning-level classification.
    - Exact-anchor unscoped `search_content` is warning-level even when `code_only` is set, because `code_only` does not count as an effective bound for that case.
    - Invalid search roots produce `BLOCK` severity with `invalid_search_root` reason.
    - Non-search filesystem actions can still receive path-validity diagnostics.
  - Characterized path validation behavior:
    - `search_files`, `search_content`, and `list_directory` expect directory paths.
    - `read_file` and `read_chunk` expect file paths.
    - Missing or wrong directory roots use `SEARCH_ROOT_NOT_FOUND`.
    - Missing or wrong file paths use `INVALID_ACTION_PATH`.
    - Empty `search_files` / `search_content` paths normalize to `.` for diagnostics.
  - Characterized filesystem path failure recovery behavior:
    - Tool failure output containing invalid-path markers can be classified as `INVALID_ACTION_PATH_RECOVERY`.
    - The classifier records the invalid path, failed action type, expected/actual kind, failure message, known valid root, and recommended next actions.
    - Recommended next actions currently prefer listing the known valid root and falling back to `search_files` / `search_content` at `.`.
  - Characterized invalid-path recovery prompt behavior:
    - Recovery prompt forbids reusing the failed path.
    - Recovery prompt forbids deriving sibling, child, or package paths from the failed path.
    - Recovery prompt forbids guessing Android/Kotlin package roots.
    - Recovery prompt directs the agent to first establish a valid root, usually with `list_directory` on the known root.
  - No search matching behavior changed.
  - No path normalization behavior changed.
  - No tool execution behavior changed.
  - No recovery authority changed.
  - No memory-board path anchoring was added.
- **Next**:
  - Phase 33 — Step 3/N: Repeat Broad Search / Invalid Path Gap Decision.

---

#### Phase 33 — Step 3/N: Repeat Broad Search / Invalid Path Gap Decision

- **Status**: Done.
- **Goal**: Decide which Phase 33 gap should be handled first after current-behavior characterization.
- **Decision**: Handle repeat broad-search characterization first.
- **Rationale**:
  - Phase 32 explicitly deferred hard repeat broad-search blocking and automatic path memory anchoring.
  - Phase 32 broad-search histogram is already the primary mitigation, so the next safe step is to characterize repeated broad-search behavior before considering any guard.
  - Repeat broad-search characterization is narrower and safer than path anchoring because it does not require memory-board writes or persistent path state.
  - Invalid-path recovery prompt behavior is already partially hardened and characterized, so it can remain a follow-up gap after repeat broad-search behavior is pinned down.
- **Deferred Gaps**:
  - Invalid-path recovery prompt hardening remains available as a later Phase 33 step.
  - Hint-only path anchoring design remains available as a later Phase 33 step.
  - Hard repeat-search blocking remains forbidden until characterization proves the exact failure mode and safe intervention point.
  - Automatic memory-board path anchoring remains forbidden.
- **Next**:
  - Phase 33 — Step 4/N: Repeat Broad Search Characterization.

---

#### Phase 33 — Step 4/N: Repeat Broad Search Characterization

- **Status**: Done.
- **Goal**: Characterize current repeat broad-search recovery behavior without changing runtime behavior.
- **Completed Outcome**:
  - Added a prompt-level characterization test for `low_value_broad_search_repeat`.
  - Confirmed that repeat broad-search recovery is currently UX guidance, not a hard runtime block.
  - Confirmed that the recovery prompt warns that the last search was too broad or a low-value repeat.
  - Confirmed that the prompt allows only a bounded reconnaissance search when exact files are unknown.
  - Confirmed that the prompt requires at least two bounds for bounded reconnaissance: specific path, specific pattern, `include_extensions`, or `exclude_dirs`.
  - Confirmed that if candidate paths are already available, the next step should be a targeted read on those paths, not another broad search.
  - Confirmed that the prompt encourages narrower path/pattern/extension/exclude choices and the shortest path to concrete evidence.
  - No hard repeat-search blocking was added.
  - No automatic memory-board path anchoring was added.
  - No search matching behavior changed.
  - No path normalization behavior changed.
  - No tool execution behavior changed.
  - No recovery authority changed.
- **Next**:
  - Phase 33 — Step 5/N: Repeat Broad Search Guard / Hint Hardening Decision.

---

#### Phase 33 — Step 5/N: Repeat Broad Search Guard / Hint Hardening Decision

- **Status**: Done.
- **Goal**: Decide whether to add a hard repeat broad-search guard or perform prompt-only hint hardening.
- **Decision**: Use prompt-only hint hardening. Do not add a hard guard.
- **Completed Outcome**:
  - Strengthened the existing `too_broad_search` / `low_value_broad_search_repeat` recovery prompt.
  - The prompt now explicitly tells the agent not to repeat the same root-level or weakly bounded `search_content` query.
  - The prompt now says that any next `search_content` action must be materially narrower than the failed search.
  - The existing characterization test now locks this prompt-only behavior.
  - No repeat detector or repeat state was added.
  - No hard repeat-search blocking was added.
  - No automatic memory-board path anchoring was added.
  - No search matching behavior changed.
  - No path normalization behavior changed.
  - No tool execution behavior changed.
  - No recovery authority changed.
- **Next**:
  - Phase 33 — Step 6/N: Invalid-Path Recovery Prompt Hardening Decision.

---

#### Phase 33 — Step 6/N: Invalid-Path Recovery Prompt Hardening Decision

- **Status**: Done.
- **Goal**: Decide whether invalid-path recovery needs additional hardening and keep any change prompt-only.
- **Decision**: Use minimal prompt-only hardening. Do not add automatic path anchoring or runtime behavior changes.
- **Completed Outcome**:
  - Strengthened the existing `INVALID_ACTION_PATH_RECOVERY` prompt.
  - The prompt already forbids reusing the failed path, deriving sibling/child/package paths from it, and guessing Android/Kotlin package roots.
  - The prompt now also forbids substituting another guessed replacement path.
  - The prompt now explicitly requires proving a valid root with an allowed read-only action first.
  - Existing invalid-path prompt tests now lock this prompt-only behavior.
  - No automatic memory-board path anchoring was added.
  - No memory-board writes were added.
  - No path normalization behavior changed.
  - No search matching behavior changed.
  - No tool execution behavior changed.
  - No recovery authority changed.
  - No hard blocking was added.
- **Next**:
  - Phase 33 — Step 7/N: Search/Path Recovery UX Hardening Closure.

---

#### Phase 33 — Step 7/N: Search/Path Recovery UX Hardening Closure

- **Status**: Done.
- **Goal**: Close Phase 33 after characterization and prompt-only UX hardening.
- **Decision**: Close Phase 33. Do not add hint-only path anchoring in this slice.
- **Completed Outcome**:
  - Phase 33 is complete.
  - Search/path recovery behavior was inventoried and characterized.
  - Repeat broad-search behavior was characterized at the prompt level.
  - Repeat broad-search recovery was hardened with prompt-only guidance.
  - Invalid-path recovery was hardened with prompt-only guidance.
  - Hard repeat-search blocking remains forbidden without a future characterization-first slice.
  - Hint-only path anchoring is deferred to a future slice because it risks introducing hidden stateful path memory.
  - Automatic memory-board path anchoring remains forbidden.
  - No memory-board writes were added.
  - No path normalization behavior changed.
  - No search matching behavior changed.
  - No tool execution behavior changed.
  - No recovery authority changed.
  - No production authority transfer occurred.
  - No broad recovery rewrite was added.
- **Next**:
  - Phase 40 — Next Semantic Runtime Slice Selection.

---

### Phase 40: Next Semantic Runtime Slice Selection

- **Status**: In Progress.
- **Goal**: Select the next safe semantic-runtime refactor slice after closing Phase 33 Search/Path Recovery UX Hardening.
- **Allowed**:
  - Docs-only inventory and decision work.
  - Compare remaining candidate slices by safety, live-agent value, and refactor risk.
  - Select the next active slice without changing runtime behavior.
- **Forbidden**:
  - No production behavior change.
  - No switch registry changes.
  - No runtime diagnostic wiring.
  - No authority transfer.
  - No dispatch behavior changes.
  - No recovery behavior changes.
  - No legacy cleanup or deletion before a consumer map exists.
- **Done When**:
  - Candidate next slices are listed.
  - The selected next active slice is recorded.
  - Stop lines for the selected slice are documented.

---

#### Phase 40 — Step 1/N: Next Semantic Runtime Slice Selection / Candidate Inventory

- **Status**: Done.
- **Goal**: Inventory candidate next slices after closing the search/path UX hardening slice.
- **Completed Outcome**:
  - Confirmed that Phase 33 is closed and remained limited to characterization and prompt-only guidance.
  - Identified candidate next slices:
    - Terminal Answer deferred/final-answer migration review.
    - Dispatch/action boundary review.
    - RecoveryStrategy registry expansion or deferred recovery branch review.
    - Consumer map before legacy/compatibility cleanup.
  - Observed that Terminal Answer work already has a long prior migration trail and an explicit deferred final-answer path.
  - Observed that dispatch/action boundary work is high-value but higher risk because dispatch side effects must remain untouched unless a narrow diagnostic/metadata-only slice is selected.
  - Observed that recovery work is useful for live-agent quality but should avoid broad recovery rewrites.
  - Observed that legacy cleanup should remain deferred until a consumer map exists.
  - No production behavior was changed.
- **Next**:
  - Phase 40 — Step 2/N: Select Next Active Slice.

---

#### Phase 40 — Step 2/N: Select Next Active Slice

- **Status**: Done.
- **Goal**: Select the next active semantic-runtime refactor slice after candidate inventory.
- **Decision**: Select Terminal Answer Deferred / Final-Answer Migration Review as the next active slice.
- **Rationale**:
  - Terminal Answer work already has a long prior migration trail and an explicit deferred final-answer path.
  - The slice can start safely with preflight, inventory, and consumer mapping before any implementation.
  - Final-answer behavior is high-value for live-agent quality, but must remain guarded because stop/continue behavior is sensitive.
  - Dispatch/action boundary work remains deferred because dispatch side effects are higher risk.
  - Recovery deferred branch review remains available as a later candidate.
  - Legacy/compatibility cleanup remains deferred until a consumer map exists.
- **Stop Lines for Phase 41**:
  - `TerminalAnswerClassifier` is not sole final-answer authority.
  - No final-answer stop/continue behavior changes.
  - No dispatch behavior changes.
  - No `ActionPolicy` changes.
  - No recovery behavior changes.
  - No production authority transfer.
  - No legacy cleanup or deletion.
  - No migration without a consumer map and characterization tests.
- **Next**:
  - Phase 41 — Terminal Answer Deferred Final-Answer Path Preflight.

---

### Phase 41: Terminal Answer Deferred Final-Answer Path Preflight

- **Status**: Not started.
- **Goal**: Review the deferred terminal-answer final-answer path and decide whether a narrow, behavior-preserving migration candidate exists.
- **Allowed**:
  - Docs-only inventory and preflight.
  - Consumer map for final-answer-related legacy paths.
  - Risk boundary review for stop-gates, policy, dispatch, and recovery.
  - Design-only proposals for narrow behavior-preserving migration candidates.
- **Forbidden**:
  - No final-answer stop/continue behavior changes.
  - No dispatch behavior changes.
  - No `ActionPolicy` changes.
  - No recovery behavior changes.
  - No production authority transfer.
  - No legacy cleanup or deletion.
  - Do not make `TerminalAnswerClassifier` sole final-answer authority.
- **Done When**:
  - Deferred final-answer path state is inventoried.
  - Remaining final-answer-related consumers are mapped.
  - The slice records whether a safe narrow migration candidate exists.

---

#### Phase 41 — Step 1/N: Terminal Answer Deferred Final-Answer Path Preflight / Inventory

- **Status**: Done.
- **Goal**: Inventory the current Terminal Answer deferred final-answer path state and locate remaining final-answer-related legacy consumers before any migration design.
- **Completed Outcome**:
  - Confirmed that Terminal Answer work has a long prior migration trail from Phase 8, Phase 28, and related recovery slices.
  - Confirmed that `TerminalAnswerClassifier` exists and is used as typed/shadow/parity evidence, but must not become sole final-answer authority.
  - Confirmed that Phase 8 Step 4O recorded a NO-GO for `PLAINTEXT_TERMINAL_ANSWER` migration in that slice and deferred final-answer-path migration.
  - Confirmed that Phase 28 later smoke-validated `terminal_answer.plaintext_terminal_answer` under the smoke profile while keeping default production behavior legacy.
  - Confirmed that `terminal_answer.checkpoint_only` was later marked NO-GO / DEFER because marker-only turns are practically owned by board/memory checkpoint handling, not terminal final-answer routing.
  - Confirmed that `terminal_answer.checkpoint_with_visible_text` and other action-bearing or recovery-sensitive branches remain deferred.
  - Confirmed that recovery-adjacent terminal branches such as leaked system result and invalid/truncated terminal text were handled separately and must not be merged into final-answer authority without a new boundary review.
  - Confirmed that remaining final-answer-related work is sensitive because it overlaps stop/continue behavior, intent completion, evidence sufficiency, visible text, and recovery boundaries.
  - No migration candidate is approved yet.
  - No production behavior was changed.
- **Next**:
  - Phase 41 — Step 2/N: Final-Answer Consumer Map.

---

#### Phase 41 — Step 2/N: Final-Answer Consumer Map

- **Status**: Done.
- **Goal**: Map final-answer-related consumers before deciding whether any narrow migration candidate is safe.
- **Completed Outcome**:
  - Mapped classifier/model/shadow consumers:
    - `TerminalAnswerClassifier` and `TerminalAnswerKind` provide typed evidence.
    - `terminal_answer_classifier_shadow` remains parity/comparator diagnostics unless a later slice explicitly approves a narrower consumer migration.
  - Mapped prevalidation and terminal-text consumers:
    - `terminal_plaintext_completion_status(...)` remains relevant for invalid/truncated terminal plaintext handling.
    - `_reject_truncated_terminal_completion_before_transition` remains a sensitive prevalidation boundary because it can affect continue/retry behavior.
  - Mapped response pipeline recovery/final-answer boundaries:
    - leaked-system-result handling already uses typed evidence in a recovery-owned path and must not be merged into final-answer authority.
    - invalid/truncated terminal text remains recovery-adjacent and diagnostic/guard-sensitive.
    - plain final-answer/visible-text paths remain tied to stop/continue and sufficiency policy.
  - Mapped output-recovery/internal-summary consumers:
    - internal-summary-like text remains a recovery/output path, not a final-answer authority transfer target by default.
    - output recovery must not be changed without separate characterization.
  - Mapped prompt-only final-answer guidance:
    - final-answer formatting prompts and build-fix final-answer prompts are user-facing guidance, not authority migration targets.
  - Mapped adjacent board/memory visible-text preservation tests:
    - board/memory visible-text preservation coverage is adjacent evidence only and must not be treated as final-answer authority.
  - Risk classification:
    - Low risk: docs-only inventory, diagnostics, consumer map maintenance.
    - Medium risk: prompt-only final-answer formatting guidance, provided behavior remains unchanged.
    - High risk: any stop/continue decision, final-answer sufficiency policy, `ActionPolicy`, dispatch, output recovery, or legacy deletion.
  - No migration candidate is approved yet.
  - No production behavior was changed.
- **Next**:
  - Phase 41 — Step 3/N: Final-Answer Risk Boundary Review / Migration Candidate Decision.

---

#### Phase 41 — Step 3/N: Final-Answer Risk Boundary Review / Migration Candidate Decision

- **Status**: Done.
- **Goal**: Decide whether any final-answer migration candidate is safe after consumer mapping.
- **Decision**: NO-GO for real final-answer migration in this step. Proceed only to design-only candidate review.
- **Rationale**:
  - `PLAINTEXT_TERMINAL_ANSWER` remains tied to final-answer authority, intent-completion finalization, visible-text handling, evidence sufficiency, and stop/continue behavior.
  - Prevalidation terminal-text consumers can affect retry/continue behavior and therefore are not safe for direct migration without a separate characterization gate.
  - Recovery-adjacent terminal branches such as leaked-system-result, invalid/truncated terminal text, and internal-summary-like text are already recovery/output paths and must not be merged into final-answer authority.
  - Dispatch/action boundaries remain out of scope for this slice.
  - `ActionPolicy` remains out of scope for this slice.
  - Legacy cleanup remains forbidden before a stronger consumer map and migration plan exists.
- **Approved Next Work**:
  - Design-only review of whether a narrow final-answer migration candidate exists.
  - Candidate review may inspect diagnostics, parity evidence, and consumer-map gaps.
  - Candidate review must produce either a narrow design proposal or a renewed NO-GO.
- **Forbidden**:
  - No production behavior change.
  - No final-answer stop/continue behavior change.
  - No final-answer sufficiency policy change.
  - No dispatch behavior change.
  - No `ActionPolicy` change.
  - No recovery behavior change.
  - No production authority transfer.
  - No switch changes.
  - No legacy cleanup or deletion.
  - Do not make `TerminalAnswerClassifier` sole final-answer authority.
- **Next**:
  - Phase 41 — Step 4/N: Design-Only Final-Answer Migration Candidate Review.

---

#### Phase 41 — Step 4/N: Final-Answer Slice Exit / Next Slice Selection

- **Status**: Done.
- **Goal**: Decide whether to continue the final-answer migration review or switch to a safer adjacent semantic-runtime slice.
- **Decision**: Defer final-answer migration and select Semantic Runtime Consumer Map / Legacy Cleanup Preflight as the next active slice.
- **Rationale**:
  - Phase 41 confirmed that final-answer migration remains high risk because it overlaps stop/continue behavior, sufficiency policy, visible text, recovery, dispatch, and `ActionPolicy` boundaries.
  - A stronger global consumer map is a safer prerequisite before any broad legacy cleanup or deletion.
  - Consumer-map work can proceed docs-first and characterization-first without runtime behavior changes.
  - Cleanup remains forbidden until consumers are classified and migration blockers are recorded.
- **Deferred**:
  - Real final-answer migration.
  - `PLAINTEXT_TERMINAL_ANSWER` authority transfer.
  - Final-answer stop/continue behavior changes.
  - Any migration that makes `TerminalAnswerClassifier` sole final-answer authority.
- **Next**:
  - Phase 42 — Semantic Runtime Consumer Map / Legacy Cleanup Preflight.

---

### Phase 42: Semantic Runtime Consumer Map / Legacy Cleanup Preflight

- **Status**: In Progress.
- **Goal**: Build a semantic-runtime consumer map before any legacy or compatibility cleanup.
- **Allowed**:
  - Docs-only inventory and preflight.
  - Search for consumers of legacy semantic helpers, compatibility fields, and transitional accessors.
  - Classify consumers as active, compatibility-only, diagnostic-only, deferred/high-risk, or candidate-for-future-cleanup.
  - Identify missing typed accessors or migration blockers.
- **Forbidden**:
  - No production behavior change.
  - No legacy cleanup or deletion.
  - No compatibility shim removal.
  - No switch registry changes.
  - No authority transfer.
  - No dispatch behavior changes.
  - No final-answer stop/continue behavior changes.
  - No `ActionPolicy` changes.
  - No recovery behavior changes.
- **Done When**:
  - Legacy and compatibility consumers are inventoried.
  - Consumers are classified by risk and ownership boundary.
  - A later cleanup/migration sequence is proposed or explicitly deferred.

---

#### Phase 42 — Step 1/N: Semantic Runtime Consumer Map / Legacy Cleanup Preflight Inventory

- **Status**: Done.
- **Goal**: Inventory semantic-runtime legacy helpers, compatibility fields, transitional accessors, and their consumers before any cleanup decision.
- **Completed Outcome**:
  - Inventoried primary semantic-runtime compatibility surfaces:
    - `ResponseSemantics` remains a legacy semantic helper collection used by tests and selected runtime consumers.
    - `semantic_accessors.py` contains approved transitional accessors such as `get_compiler_metadata`, `has_any_action_proposal_compat`, `is_compiler_invalid`, `is_compiler_invalid_with_legacy_action`, `is_leaked_system_result`, and `has_substantial_think`.
    - `RuntimeProtocolSemantics` provides the compiler-derived read-only snapshot used by semantic accessors and diagnostic paths.
    - `ParsedModelOutput` still carries legacy and compatibility fields such as `has_action_segment`, `invalid_kind`, `action_content`, compiler metadata fields, compiler IR, and attached typed semantic results.
    - `runtime_protocol_semantics.output_recovery_compiler_metadata(...)` remains a deprecated/fallback metadata extraction helper while `semantic_accessors.get_compiler_metadata(...)` is the preferred central accessor.
  - Inventoried visible consumer groups:
    - response pipeline prevalidation and stages;
    - output recovery and recovery routing;
    - terminal-answer classifier and authority diagnostics;
    - action policy and dispatch-adjacent action candidate handling;
    - board/memory and checkpoint equivalence tests;
    - parser/protocol/compiler tests that still construct `ParsedModelOutput` with legacy fields directly.
  - Initial risk observations:
    - `ResponseSemantics.has_any_action_proposal` and `has_any_action_proposal_compat` are protected compatibility/recovery-evidence surfaces and are not dispatch authority.
    - `has_action_segment` remains widely used in tests and compatibility paths and cannot be removed without a migration plan.
    - `ParsedModelOutput` compatibility fields remain active test and runtime construction surfaces.
    - action-policy consumers of compiler IR and action ops are high-risk because dispatch behavior must not change.
    - output recovery metadata consumers are cleanup candidates only if fallback behavior is proven equivalent.
    - terminal-answer and final-answer consumers remain high-risk because they overlap stop/continue behavior and recovery boundaries.
  - No consumer is approved for cleanup yet.
  - No compatibility shim was removed.
  - No production behavior was changed.
- **Next**:
  - Phase 42 — Step 2/N: Consumer Classification / Cleanup Risk Matrix.

---

#### Phase 42 — Step 2/N: Consumer Classification / Cleanup Risk Matrix

- **Status**: Done.
- **Goal**: Classify inventoried semantic-runtime legacy and compatibility consumers by risk and cleanup readiness.
- **Completed Outcome**:
  - Classified protected compatibility / recovery-evidence surfaces:
    - `ResponseSemantics.has_any_action_proposal(...)` and `has_any_action_proposal_compat(...)` remain protected compatibility shims.
    - They provide action-like recovery evidence only and are not dispatch authority.
    - They are not cleanup candidates until all recovery and guard consumers have typed-equivalent coverage.
  - Classified active runtime / high-risk surfaces:
    - `ParsedModelOutput.has_action_segment`, `invalid_kind`, `action_content`, compiler metadata fields, compiler IR, and attached typed semantic results remain active compatibility surfaces.
    - `ActionPolicy` and dispatch-adjacent consumers of compiler IR/action ops are high-risk and must not be simplified without dispatch characterization.
    - final-answer, terminal-answer, and recovery-adjacent consumers remain high-risk because they overlap stop/continue and recovery boundaries.
  - Classified candidate-for-future-cleanup surfaces:
    - `runtime_protocol_semantics.output_recovery_compiler_metadata(...)` is a candidate for later consolidation into `semantic_accessors.get_compiler_metadata(...)` only after explicit parity tests prove fallback behavior is unchanged.
    - direct metadata reads may become future cleanup candidates after a narrower accessor migration plan exists.
  - Classified test-only / fixture construction surfaces:
    - direct `ParsedModelOutput(...)` construction with legacy fields in tests is not production cleanup evidence by itself.
    - tests that intentionally characterize compatibility behavior should remain until the corresponding runtime consumer is migrated or retired.
  - Classified diagnostic/transitional surfaces:
    - `RuntimeProtocolSemantics` and semantic accessor snapshots are diagnostic/transitional read layers, not policy authority.
    - terminal-answer shadow/parity diagnostics remain evidence only unless a later slice explicitly approves a consumer migration.
  - Cleanup readiness matrix:
    - Ready now: none.
    - Candidate after parity proof: output-recovery compiler metadata fallback consolidation.
    - Candidate after consumer migration plan: selected direct compiler metadata reads.
    - Deferred/high-risk: action proposal compatibility shims, `has_action_segment`, final-answer/terminal-answer consumers, dispatch/action policy consumers, recovery behavior consumers.
  - No cleanup was approved.
  - No compatibility shim was removed.
  - No production behavior was changed.
- **Next**:
  - Phase 42 — Step 3/N: Cleanup Candidate Selection / Defer Decision.

---

#### Phase 42 — Step 3/N: Cleanup Candidate Selection / Defer Decision

- **Status**: Done.
- **Goal**: Decide whether any cleanup candidate is safe to advance from the risk matrix.
- **Decision**: Select exactly one narrow candidate for characterization only: output-recovery compiler metadata fallback consolidation.
- **Selected Candidate**:
  - Candidate: consolidate `runtime_protocol_semantics.output_recovery_compiler_metadata(...)` into `semantic_accessors.get_compiler_metadata(...)`.
  - Scope: characterization and parity proof first.
  - Rationale: both helpers serve the same metadata-access concern for compiler error code, recovery id, and invalid kind, but fallback/source behavior must be proven equivalent before any implementation.
- **Deferred**:
  - `ResponseSemantics.has_any_action_proposal(...)` and `has_any_action_proposal_compat(...)` remain protected compatibility/recovery-evidence surfaces.
  - `ParsedModelOutput.has_action_segment`, `invalid_kind`, `action_content`, compiler metadata fields, compiler IR, and attached typed semantic results remain active compatibility surfaces.
  - ActionPolicy and dispatch-adjacent consumers remain high-risk and out of scope.
  - final-answer, terminal-answer, output-recovery behavior, and recovery behavior changes remain out of scope.
  - selected direct compiler metadata reads remain deferred until the helper consolidation candidate is characterized.
- **Forbidden**:
  - No implementation in this step.
  - No cleanup or deletion.
  - No compatibility shim removal.
  - No production behavior change.
  - No authority transfer.
  - No switch changes.
  - No dispatch behavior changes.
  - No final-answer stop/continue behavior changes.
  - No `ActionPolicy` changes.
  - No recovery behavior changes.
- **Next**:
  - Phase 42 — Step 4/N: Output-Recovery Compiler Metadata Fallback Parity Characterization.

---

#### Phase 42 — Step 4/N: Output-Recovery Compiler Metadata Fallback Parity Characterization

- **Status**: Done.
- **Goal**: Prove characterization parity between the deprecated output-recovery metadata helper and the central semantic accessor before any consolidation implementation.
- **Completed Outcome**:
  - Added characterization coverage comparing `runtime_protocol_semantics.output_recovery_compiler_metadata(...)` and `semantic_accessors.get_compiler_metadata(...)`.
  - Covered legacy/fallback metadata cases:
    - legacy `invalid_kind` without compiler metadata;
    - compiler error/recovery metadata with legacy invalid kind fallback;
    - empty metadata.
  - The test locks down exact dictionary parity, including `source`, `error_code`, `recovery_id`, and `invalid_kind`.
  - No production code was changed.
  - No helper was removed.
  - No output recovery behavior changed.
  - No compatibility shim was removed.
- **Next**:
  - Phase 42 — Step 5/N: Output-Recovery Compiler Metadata Consolidation Implementation Decision.

---

#### Phase 42 — Step 5/N: Output-Recovery Compiler Metadata Consolidation Implementation Decision

- **Status**: Done.
- **Goal**: Decide whether the metadata helper consolidation can proceed after parity characterization.
- **Decision**: Proceed only with the already-safe routing import cleanup. Do not remove the deprecated helper yet.
- **Completed Outcome**:
  - Confirmed that `OutputRecoveryRoutingMixin._compiler_strategy_decision(...)` already uses `semantic_accessors.get_compiler_metadata(...)`.
  - Removed the stale unused import of `runtime_protocol_semantics.output_recovery_compiler_metadata(...)` from `output_recovery_routing.py`.
  - Kept `runtime_protocol_semantics.output_recovery_compiler_metadata(...)` in place because tests still use it as an explicit parity oracle and deprecated fallback surface.
  - No output recovery behavior changed.
  - No compatibility shim was removed.
  - No production authority transfer occurred.
  - No switch changed.
  - No dispatch, ActionPolicy, final-answer, or recovery behavior changed.
- **Next**:
  - Phase 42 — Step 6/N: Deprecated Metadata Helper Removal / Retention Decision.

---

#### Phase 42 — Step 6/N: Deprecated Metadata Helper Removal / Retention Decision

- **Status**: Done.
- **Goal**: Decide whether to remove the deprecated `output_recovery_compiler_metadata(...)` helper after routing import cleanup.
- **Decision**: Retain the deprecated helper for now.
- **Rationale**:
  - The active output-recovery routing path already uses `semantic_accessors.get_compiler_metadata(...)`.
  - `output_recovery_compiler_metadata(...)` still serves as an explicit parity oracle in characterization tests.
  - Keeping the helper documents the old fallback contract while broader semantic-runtime cleanup remains in progress.
  - Removing it now would collapse the old-vs-new comparison point too early.
- **Completed Outcome**:
  - Deprecated helper removal is deferred.
  - The helper remains in `runtime_protocol_semantics.py` as a temporary parity/fallback fixture.
  - The narrow metadata consolidation is complete for the active routing path.
  - No production behavior changed.
  - No compatibility shim was removed.
  - No output recovery behavior changed.
  - No recovery, dispatch, ActionPolicy, final-answer, or authority behavior changed.
- **Next**:
  - Phase 42 — Step 7/N: Consumer Map / Metadata Consolidation Closure.

---

#### Phase 42 — Step 7/N: Consumer Map / Metadata Consolidation Closure

- **Status**: Done.
- **Goal**: Close the semantic-runtime consumer map / legacy cleanup preflight slice and select the next refactor direction.
- **Completed Outcome**:
  - Phase 42 is complete.
  - Built the semantic-runtime consumer map for legacy helpers, compatibility fields, transitional accessors, and visible consumer groups.
  - Classified consumers by risk and cleanup readiness.
  - Confirmed that broad legacy cleanup is not yet approved.
  - Selected exactly one narrow cleanup candidate: output-recovery compiler metadata fallback consolidation.
  - Added parity characterization proving `semantic_accessors.get_compiler_metadata(...)` matches `runtime_protocol_semantics.output_recovery_compiler_metadata(...)` for legacy/fallback metadata cases.
  - Confirmed that active output-recovery routing already uses `get_compiler_metadata(...)`.
  - Removed the stale unused import of `output_recovery_compiler_metadata(...)` from `output_recovery_routing.py`.
  - Retained `output_recovery_compiler_metadata(...)` as a temporary parity oracle and fallback-contract fixture.
  - No production behavior changed.
  - No compatibility shim was removed.
  - No recovery, dispatch, ActionPolicy, final-answer, switch, or authority behavior changed.
- **Deferred**:
  - Broad legacy cleanup.
  - `ResponseSemantics` removal.
  - `ParsedModelOutput` compatibility field removal.
  - `has_action_segment` cleanup.
  - `has_any_action_proposal` / `has_any_action_proposal_compat` cleanup.
  - Deprecated metadata helper removal.
  - Any dispatch, ActionPolicy, final-answer, or recovery behavior migration.
- **Next**:
  - Phase 11 — RecoveryStrategy Registry Expansion.

### Phase 11: RecoveryStrategy Registry Expansion

- **Status**: In Progress.
- **Goal**: Expand the `CompilerRecoveryRegistry` to cover more structural errors.
- **Allowed**:
  - Inventory structural compiler recovery strategies and legacy invalid-kind routing.
  - Add new strategies for errors currently handled by legacy `invalid_kind` routing, only after characterization.
  - Keep registry expansion narrow and behavior-preserving.
- **Forbidden**:
  - No runtime-owned policy decisions.
  - No broad recovery rewrite.
  - No recovery behavior change without explicit characterization.
  - No dispatch behavior changes.
  - No ActionPolicy changes.
  - No final-answer stop/continue behavior changes.
  - No authority transfer or switch changes in inventory steps.
- **Done When**:
  - All purely structural `invalid_kind`s are routed through the compiler registry.

---

#### Phase 11 — Step 1/N: RecoveryStrategy Registry Expansion Inventory

- **Status**: Done.
- **Goal**: Inventory current compiler recovery registry coverage, legacy invalid-kind routing, and safe candidate boundaries before adding any strategy.
- **Completed Outcome**:
  - Inventoried `CompilerRecoveryRegistry` and existing strategy coverage.
  - Confirmed registry coverage already includes structural compiler recovery strategies for:
    - unclosed / malformed think family: `unclosed_think`, `action_inside_think`, `intent_inside_think`, `file_content_inside_think`;
    - file-content structure: `file_content_unclosed`, `file_content_requires_action`;
    - mixed visible/control protocol: `mixed_visible_control`;
    - action payload shape: `action_payload_array`, `action_payload_xml_fields`, `action_payload_tool_code`, `action_payload_not_object`;
    - atomic bundle / multiple actions behavior through compiler-routed invalid-kind tests.
  - Inventoried active routing path:
    - `OutputRecoveryRoutingMixin._compiler_strategy_decision(...)` uses compiler metadata via `get_compiler_metadata(...)`.
    - `COMPILER_ROUTED_INVALID_KINDS` gates which invalid kinds may use compiler strategy routing.
    - `resolve_compiler_invalid_kind_mapping_authority(...)` preserves legacy fallback behavior on conflicts.
  - Inventoried test coverage:
    - `tests/test_compiler_recovery_registry.py` covers direct registry resolution.
    - `tests/test_compiler_driven_recovery_routing.py` covers compiler-code routing without legacy `invalid_kind`.
    - `tests/test_recovery_invalid_output_synthetic_smoke.py` covers resolver fallback and legacy-preserving behavior.
  - Initial boundary decision:
    - Purely structural compiler errors are candidate territory.
    - Runtime-owned policy decisions, final-answer/recovery-sensitive branches, dispatch behavior, and ActionPolicy remain out of scope.
  - No registry change was made.
  - No recovery behavior changed.
  - No production behavior changed.
- **Next**:
  - Phase 11 — Step 2/N: Structural Recovery Candidate Selection.

---

#### Phase 11 — Step 2/N: Structural Recovery Candidate Selection

- **Status**: Done.
- **Goal**: Select one structural recovery candidate for characterization before any registry expansion.
- **Decision**: Select `mixed_intent_transition_and_visible_answer` for characterization only.
- **Rationale**:
  - The action-payload family is already covered by `CompilerRecoveryRegistry` and `COMPILER_ROUTED_INVALID_KINDS`, including `action_payload_array`, `action_payload_xml_fields`, `action_payload_tool_code`, and `action_payload_not_object`.
  - `multiple_actions` / atomic bundle behavior is already represented through compiler-routed invalid-kind tests and registry strategies.
  - `mixed_intent_transition_and_visible_answer` is already present in `COMPILER_ROUTED_INVALID_KINDS` but is not represented as a dedicated strategy in the inventoried `CompilerRecoveryRegistry`.
  - The candidate appears structural because it describes a protocol-shape conflict between an intent transition and visible answer text.
  - The candidate remains boundary-sensitive because it touches transition/final-answer territory, so the next step must be characterization only.
- **Forbidden for Next Step**:
  - No registry change.
  - No recovery behavior change.
  - No authority transfer or switch change.
  - No final-answer stop/continue behavior change.
  - No dispatch behavior change.
  - No ActionPolicy change.
  - No broad recovery rewrite.
- **Next**:
  - Phase 11 — Step 3/N: Mixed Intent Transition / Visible Answer Recovery Characterization.

---

#### Phase 11 — Step 3/N: Mixed Intent Transition / Visible Answer Recovery Characterization

- **Status**: Done.
- **Goal**: Characterize current behavior for `mixed_intent_transition_and_visible_answer` before deciding whether a dedicated registry strategy is safe.
- **Completed Outcome**:
  - Confirmed that `mixed_intent_transition_and_visible_answer` is already present in `COMPILER_ROUTED_INVALID_KINDS`.
  - Confirmed that it is not represented as a dedicated strategy in the currently inventoried `CompilerRecoveryRegistry`.
  - Confirmed existing test coverage in `tests/test_mixed_visible_text_and_control_protocol.py` for the `mixed_intent_transition_and_visible_answer` recovery path.
  - Confirmed synthetic smoke coverage references in `tests/test_recovery_invalid_output_synthetic_smoke.py` and related terminal-answer smoke harnesses.
  - Confirmed that this branch is documented as an intent-followup prevalidation recovery case, not ordinary terminal plaintext authority.
  - Confirmed that related transition work previously deferred `FOLLOWUP_PLAINTEXT` because it depends on `get_visible_text` and final-answer/sufficiency boundaries.
  - Boundary conclusion: the candidate is structurally plausible but remains boundary-sensitive because it touches transition/final-answer territory.
  - No registry strategy was added.
  - No recovery behavior changed.
  - No production behavior changed.
- **Next**:
  - Phase 11 — Step 4/N: Mixed Intent Transition / Visible Answer Registry Strategy Design Decision.

---

#### Phase 11 — Step 4/N: Mixed Intent Transition / Visible Answer Registry Strategy Design Decision

- **Status**: Done.
- **Goal**: Decide whether `mixed_intent_transition_and_visible_answer` may advance beyond characterization.
- **Decision**: GO only for design. No registry implementation is approved yet.
- **Rationale**:
  - The branch is already recognized by compiler-routed invalid-kind gating.
  - The branch is structurally plausible because it represents a protocol-shape conflict between an intent transition and visible answer text.
  - The branch is not yet represented as a dedicated `CompilerRecoveryRegistry` strategy.
  - The branch remains boundary-sensitive because it touches transition/final-answer territory and is adjacent to previously deferred `FOLLOWUP_PLAINTEXT` / `get_visible_text` concerns.
  - A dedicated strategy may be safe only if tests prove it preserves current prompt, reason, source, and recovery behavior.
- **Approved Next Work**:
  - Design parity tests for a future dedicated registry strategy.
  - Identify the exact expected `error_code`, `recovery_id`, `invalid_kind`, `handler_key`, prompt, reason, and source behavior.
  - Prove that registry routing would remain behavior-equivalent before implementation.
- **Forbidden**:
  - No registry strategy implementation yet.
  - No recovery behavior change.
  - No authority transfer or switch change.
  - No final-answer stop/continue behavior change.
  - No dispatch behavior change.
  - No ActionPolicy change.
  - No broad recovery rewrite.
  - No legacy cleanup.
- **Next**:
  - Phase 11 — Step 5/N: Mixed Intent Transition / Visible Answer Registry Strategy Parity Test Design.

---

#### Phase 11 — Step 5/N: Mixed Intent Transition / Visible Answer Registry Strategy Parity Test Design

- **Status**: Done.
- **Goal**: Design the parity proof required before implementing a dedicated `CompilerRecoveryRegistry` strategy for `mixed_intent_transition_and_visible_answer`.
- **Designed Strategy Contract**:
  - `error_code`: `E_VISIBLE_TEXT_AFTER_INTENT`.
  - `recovery_id`: `mixed_intent_transition_and_visible_answer`.
  - `invalid_kind`: `mixed_intent_transition_and_visible_answer`.
  - `handler_key`: a dedicated handler key for the mixed intent-transition / visible-answer branch, rather than reusing the ordinary `mixed_visible_control` handler implicitly.
  - Prompt expectation: use `build_mixed_intent_transition_and_visible_answer_prompt()`.
  - Decision reason expectation: `mixed_intent_transition_and_visible_answer`.
  - Source expectation: preserve existing output-recovery / compiler-registry routing source conventions without changing recovery behavior.
- **Required Parity Tests Before Implementation**:
  - Add a registry test proving the future tuple resolves to the intended dedicated strategy contract.
  - Add a routing/contract test proving compiler metadata can route this branch without legacy `invalid_kind` while preserving prompt and decision reason.
  - Add or preserve a current-behavior test proving the existing legacy/prevalidation path still returns `mixed_intent_transition_and_visible_answer` and uses the dedicated prompt.
  - Negative control: do not affect `mixed_visible_text_and_control_protocol` / `mixed_visible_control` routing.
- **Boundary Notes**:
  - This remains boundary-sensitive because it touches transition/final-answer territory.
  - The test design must not approve `FOLLOWUP_PLAINTEXT`, `get_visible_text`, terminal-answer authority, or final-answer stop/continue behavior changes.
  - Registry implementation is still forbidden until the parity characterization step is green.
- **Next**:
  - Phase 11 — Step 6/N: Mixed Intent Transition / Visible Answer Registry Strategy Parity Characterization.

---

#### Phase 11 — Step 6/N: Mixed Intent Transition / Visible Answer Registry Strategy Parity Characterization

- **Status**: Done.
- **Goal**: Add test-only characterization for the current `mixed_intent_transition_and_visible_answer` behavior before any registry implementation.
- **Completed Outcome**:
  - Added a current-behavior contract test for `mixed_intent_transition_and_visible_answer`.
  - The test proves the branch returns decision reason `mixed_intent_transition_and_visible_answer`.
  - The test proves the branch uses the dedicated mixed intent-transition / visible-answer prompt.
  - The test verifies that the branch does not accidentally use ordinary mixed-visible-control or malformed-action prompt language.
  - Existing `mixed_visible_text_and_control_protocol` strategy contract remains the negative-control counterpart.
  - No `CompilerRecoveryRegistry` strategy was added.
  - No compiler metadata routing behavior was changed.
  - No recovery behavior changed.
  - No production behavior changed.
- **Next**:
  - Phase 11 — Step 7/N: Mixed Intent Transition / Visible Answer Registry Strategy Implementation Decision.

---

#### Phase 11 — Step 7/N: Mixed Intent Transition / Visible Answer Registry Strategy Implementation Decision

- **Status**: Done.
- **Goal**: Decide whether the dedicated `mixed_intent_transition_and_visible_answer` registry strategy may be implemented after parity characterization.
- **Decision**: GO for narrow implementation only.
- **Approved Implementation Scope**:
  - Add a dedicated `CompilerRecoveryStrategy` for `mixed_intent_transition_and_visible_answer`.
  - Expected strategy contract:
    - `id`: `mixed_intent_transition_visible_answer`.
    - `error_codes`: `("E_VISIBLE_TEXT_AFTER_INTENT",)`.
    - `recovery_ids`: `("mixed_intent_transition_and_visible_answer",)`.
    - `invalid_kind`: `mixed_intent_transition_and_visible_answer`.
    - `handler_key`: `mixed_intent_transition_visible_answer`.
  - Add a dedicated compiler strategy handler that uses `build_mixed_intent_transition_and_visible_answer_prompt()`.
  - Add registry resolution coverage for the new strategy tuple.
  - Add compiler-driven routing coverage proving this branch can route from compiler metadata without legacy `invalid_kind`.
  - Preserve the existing current-behavior contract test and ordinary `mixed_visible_text_and_control_protocol` negative-control path.
- **Required Behavior Preservation**:
  - Decision reason remains `mixed_intent_transition_and_visible_answer`.
  - Prompt remains the dedicated mixed intent-transition / visible-answer prompt.
  - Recovery source follows existing compiler strategy conventions.
  - Ordinary `mixed_visible_text_and_control_protocol` routing remains unchanged.
- **Forbidden**:
  - No broad recovery rewrite.
  - No final-answer stop/continue behavior change.
  - No transition policy change.
  - No `FOLLOWUP_PLAINTEXT` or `get_visible_text` migration.
  - No dispatch behavior change.
  - No ActionPolicy change.
  - No authority transfer or switch change.
  - No legacy cleanup.
- **Next**:
  - Phase 11 — Step 8/N: Mixed Intent Transition / Visible Answer Registry Strategy Implementation.

---

#### Phase 11 — Step 8/N: Mixed Intent Transition / Visible Answer Registry Strategy Implementation

- **Status**: Done.
- **Goal**: Implement the approved narrow compiler recovery strategy for `mixed_intent_transition_and_visible_answer`.
- **Completed Outcome**:
  - Added a dedicated `CompilerRecoveryStrategy` for `mixed_intent_transition_and_visible_answer`.
  - Added a dedicated compiler strategy handler using `build_mixed_intent_transition_and_visible_answer_prompt()`.
  - Added registry resolution coverage for `E_VISIBLE_TEXT_AFTER_INTENT` / `mixed_intent_transition_and_visible_answer`.
  - Added compiler-driven routing coverage proving the branch routes from compiler metadata without legacy `invalid_kind`.
  - Preserved existing current-behavior contract coverage.
  - Preserved ordinary `mixed_visible_text_and_control_protocol` negative-control behavior.
  - Decision reason remains `mixed_intent_transition_and_visible_answer`.
  - Recovery source follows existing compiler strategy conventions.
  - No broad recovery rewrite was added.
  - No final-answer stop/continue behavior changed.
  - No transition policy changed.
  - No dispatch behavior changed.
  - No ActionPolicy behavior changed.
  - No authority transfer, switch change, or legacy cleanup was added.
- **Next**:
  - Phase 11 — Step 9/N: Mixed Intent Transition / Visible Answer Registry Strategy Closure Review.

---

#### Phase 11 — Step 9/N: Mixed Intent Transition / Visible Answer Registry Strategy Closure Review

- **Status**: Done.
- **Goal**: Close the completed `mixed_intent_transition_and_visible_answer` registry expansion sub-slice and decide how to continue Phase 11 efficiently.
- **Completed Outcome**:
  - The `mixed_intent_transition_and_visible_answer` sub-slice is closed.
  - Green targeted tests confirmed registry resolution, compiler-driven routing, current behavior contract, and mixed-visible negative-control coverage.
  - The completed branch preserves the expected reason, dedicated prompt, and compiler-strategy source conventions.
  - No final-answer stop/continue behavior changed.
  - No transition policy changed.
  - No dispatch behavior changed.
  - No ActionPolicy behavior changed.
  - No authority transfer, switch change, or legacy cleanup was added.
- **Decision**: Keep Phase 11 open and move to a fast multi-candidate structural recovery review instead of selecting only one next candidate.
- **Candidate Batch for Review**:
  - `conflicting_intent_transitions`.
  - `intent_complete_with_action_not_allowed`.
  - `protocol_tag_in_json_string`.
  - `file_content_must_follow_action` / file-content order family, only if inventory shows registry coverage is incomplete.
- **Review Rules for Step 10**:
  - Classify each candidate as already-covered, safe-for-design, characterization-needed, boundary-sensitive, or no-go.
  - Prefer small structural candidates that already have legacy prompt paths and compiler metadata.
  - Do not implement registry strategies during the review step.
  - Do not batch implementation until each candidate has parity expectations for reason, prompt, source, and negative controls.
- **Forbidden for Step 10**:
  - No registry implementation.
  - No broad recovery rewrite.
  - No final-answer stop/continue behavior change.
  - No transition policy change.
  - No `FOLLOWUP_PLAINTEXT` or `get_visible_text` migration.
  - No dispatch behavior change.
  - No ActionPolicy change.
  - No authority transfer or switch change.
  - No legacy cleanup.
- **Next**:
  - Phase 11 — Step 10/N: Multi-Candidate Structural Recovery Review.

---

#### Phase 11 — Step 10/N: Multi-Candidate Structural Recovery Review

- **Status**: Done.
- **Goal**: Review several structural recovery candidates quickly and classify them before choosing the next design batch.
- **Completed Outcome**:
  - Reviewed candidate coverage for:
    - `conflicting_intent_transitions`.
    - `intent_complete_with_action_not_allowed`.
    - `protocol_tag_in_json_string`.
    - `file_content_must_follow_action` / file-content order family.
  - Classified `protocol_tag_in_json_string` as already covered by `CompilerRecoveryRegistry` via `E_PROTOCOL_TAG_IN_JSON_STRING` / `protocol_tag_in_json_string` / `malformed_action`.
  - Classified `file_content_must_follow_action` as already covered for `E_FILE_CONTENT_REQUIRES_ACTION` via the `file_content_requires_action` strategy and `file_content_order` handler.
  - Identified a possible separate coverage-gap review for `E_FILE_CONTENT_ACTION_MISMATCH`, which maps to `file_content_must_follow_action` but is not selected for the next batch.
  - Classified `conflicting_intent_transitions` as a structural transition-conflict candidate with existing compiler mapping `E_MULTIPLE_INTENTS` and legacy prompt path.
  - Classified `intent_complete_with_action_not_allowed` as a structural transition/action-conflict candidate with existing compiler mapping `E_INTENT_COMPLETE_WITH_ACTION` and legacy prompt path.
  - Both selected transition-conflict candidates are boundary-sensitive because they touch transition territory, so the next step is design-only.
  - No registry implementation was added.
  - No recovery behavior changed.
  - No production behavior changed.
- **Decision**: Select a two-candidate design batch for:
  - `conflicting_intent_transitions`.
  - `intent_complete_with_action_not_allowed`.
- **Deferred**:
  - `protocol_tag_in_json_string`, because it is already covered.
  - `file_content_must_follow_action` for `E_FILE_CONTENT_REQUIRES_ACTION`, because it is already covered.
  - `E_FILE_CONTENT_ACTION_MISMATCH` coverage-gap review, which should be handled separately if needed.
- **Forbidden for Next Step**:
  - No registry implementation yet.
  - No broad recovery rewrite.
  - No final-answer stop/continue behavior change.
  - No transition policy change.
  - No `FOLLOWUP_PLAINTEXT` or `get_visible_text` migration.
  - No dispatch behavior change.
  - No ActionPolicy change.
  - No authority transfer or switch change.
  - No legacy cleanup.
- **Next**:
  - Phase 11 — Step 11/N: Transition-Conflict Registry Strategy Batch Design.

---

#### Phase 11 — Step 11/N: Transition-Conflict Registry Strategy Batch Design

- **Status**: Done.
- **Goal**: Design registry strategy contracts for the selected transition-conflict candidates before any implementation.
- **Designed Strategy Contract: `conflicting_intent_transitions`**:
  - `id`: `conflicting_intent_transitions`.
  - `error_codes`: `("E_MULTIPLE_INTENTS",)`.
  - `recovery_ids`: `("conflicting_intent_transitions",)`.
  - `invalid_kind`: `conflicting_intent_transitions`.
  - `handler_key`: `conflicting_intent_transitions`.
  - Prompt expectation: use `build_conflicting_intent_transitions_prompt()`.
  - Decision reason expectation: `conflicting_intent_transitions`.
  - Source expectation: preserve existing compiler strategy source conventions.
- **Designed Strategy Contract: `intent_complete_with_action_not_allowed`**:
  - `id`: `intent_complete_with_action_not_allowed`.
  - `error_codes`: `("E_INTENT_COMPLETE_WITH_ACTION",)`.
  - `recovery_ids`: `("intent_complete_with_action_not_allowed",)`.
  - `invalid_kind`: `intent_complete_with_action_not_allowed`.
  - `handler_key`: `intent_complete_with_action_not_allowed`.
  - Prompt expectation: use `build_completion_with_action_not_allowed_prompt()`.
  - Decision reason expectation: `intent_complete_with_action_not_allowed`.
  - Source expectation: preserve existing compiler strategy source conventions.
- **Required Parity Tests Before Implementation**:
  - Add registry tests proving both future tuples resolve to the intended strategy contracts.
  - Add compiler-driven routing tests proving both branches can route from compiler metadata without legacy `invalid_kind`.
  - Add or preserve current-behavior tests proving existing legacy paths return the same reasons and prompts.
  - Negative control: preserve the already implemented `mixed_intent_transition_and_visible_answer` and `mixed_visible_text_and_control_protocol` paths.
- **Boundary Notes**:
  - Both candidates are boundary-sensitive because they touch transition territory.
  - This design does not approve `FOLLOWUP_PLAINTEXT`, `get_visible_text`, terminal-answer authority, final-answer stop/continue behavior changes, or transition policy changes.
  - `E_INTENT_COMPLETE_WITH_ACTION` remains deferred/UNKNOWN in the bundle semantic validator; this step does not change that validator boundary.
  - Registry implementation is still forbidden until parity characterization is green.
- **Next**:
  - Phase 11 — Step 12/N: Transition-Conflict Registry Strategy Batch Parity Characterization.

---

#### Phase 11 — Step 12/N: Transition-Conflict Registry Strategy Batch Parity Characterization

- **Status**: Done.
- **Goal**: Add test-only characterization for current `conflicting_intent_transitions` and `intent_complete_with_action_not_allowed` behavior before any registry implementation.
- **Completed Outcome**:
  - Added a current-behavior contract test for `conflicting_intent_transitions`.
  - Added a current-behavior contract test for `intent_complete_with_action_not_allowed`.
  - The tests prove both branches preserve their expected decision reasons.
  - The tests prove both branches use their dedicated transition-conflict prompts.
  - The tests verify that `conflicting_intent_transitions` does not accidentally use mixed-visible or mixed-intent/visible-answer prompt language.
  - The tests verify that `intent_complete_with_action_not_allowed` does not accidentally use conflicting-intent or mixed-intent/visible-answer prompt language.
  - Existing `mixed_intent_transition_and_visible_answer` and `mixed_visible_text_and_control_protocol` paths remain negative-control siblings.
  - No `CompilerRecoveryRegistry` strategy was added.
  - No compiler metadata routing behavior was changed.
  - No recovery behavior changed.
  - No production behavior changed.
- **Next**:
  - Phase 11 — Step 13/N: Transition-Conflict Registry Strategy Batch Implementation Decision.

---

#### Phase 11 — Step 13/N: Transition-Conflict Registry Strategy Batch Implementation Decision

- **Status**: Done.
- **Goal**: Decide whether the transition-conflict registry strategy batch may be implemented after parity characterization.
- **Decision**: GO for narrow batch implementation only.
- **Approved Implementation Scope**:
  - Add a dedicated `CompilerRecoveryStrategy` for `conflicting_intent_transitions`.
  - Expected `conflicting_intent_transitions` contract:
    - `id`: `conflicting_intent_transitions`.
    - `error_codes`: `("E_MULTIPLE_INTENTS",)`.
    - `recovery_ids`: `("conflicting_intent_transitions",)`.
    - `invalid_kind`: `conflicting_intent_transitions`.
    - `handler_key`: `conflicting_intent_transitions`.
  - Add a dedicated `CompilerRecoveryStrategy` for `intent_complete_with_action_not_allowed`.
  - Expected `intent_complete_with_action_not_allowed` contract:
    - `id`: `intent_complete_with_action_not_allowed`.
    - `error_codes`: `("E_INTENT_COMPLETE_WITH_ACTION",)`.
    - `recovery_ids`: `("intent_complete_with_action_not_allowed",)`.
    - `invalid_kind`: `intent_complete_with_action_not_allowed`.
    - `handler_key`: `intent_complete_with_action_not_allowed`.
  - Add dedicated compiler strategy handlers that use:
    - `build_conflicting_intent_transitions_prompt()`.
    - `build_completion_with_action_not_allowed_prompt()`.
  - Add registry resolution coverage for both new strategy tuples.
  - Add compiler-driven routing coverage proving both branches route from compiler metadata without legacy `invalid_kind`.
  - Preserve existing current-behavior contract tests.
  - Preserve negative-control separation from `mixed_intent_transition_and_visible_answer` and `mixed_visible_text_and_control_protocol`.
- **Required Behavior Preservation**:
  - Decision reasons remain `conflicting_intent_transitions` and `intent_complete_with_action_not_allowed`.
  - Prompts remain the dedicated transition-conflict prompts.
  - Recovery source follows existing compiler strategy conventions.
  - Existing mixed-visible and mixed-intent/visible-answer routes remain unchanged.
- **Forbidden**:
  - No broad recovery rewrite.
  - No final-answer stop/continue behavior change.
  - No transition policy change.
  - No `FOLLOWUP_PLAINTEXT` or `get_visible_text` migration.
  - No dispatch behavior change.
  - No ActionPolicy change.
  - No bundle semantic validator behavior change.
  - No authority transfer or switch change.
  - No legacy cleanup.
- **Next**:
  - Phase 11 — Step 14/N: Transition-Conflict Registry Strategy Batch Implementation.

---

#### Phase 11 — Step 14/N: Transition-Conflict Registry Strategy Batch Implementation

- **Status**: Done.
- **Goal**: Implement the approved narrow compiler recovery strategies for `conflicting_intent_transitions` and `intent_complete_with_action_not_allowed`.
- **Completed Outcome**:
  - Added a dedicated `CompilerRecoveryStrategy` for `conflicting_intent_transitions`.
  - Added a dedicated `CompilerRecoveryStrategy` for `intent_complete_with_action_not_allowed`.
  - Added dedicated compiler strategy handlers using:
    - `build_conflicting_intent_transitions_prompt()`.
    - `build_completion_with_action_not_allowed_prompt()`.
  - Added registry resolution coverage for both strategy tuples.
  - Added compiler-driven routing coverage proving both branches route from compiler metadata without legacy `invalid_kind`.
  - Preserved existing current-behavior contract tests.
  - Preserved mixed-visible and mixed-intent/visible-answer negative-control separation.
  - Decision reasons remain `conflicting_intent_transitions` and `intent_complete_with_action_not_allowed`.
  - Recovery source follows existing compiler strategy conventions.
  - No broad recovery rewrite was added.
  - No final-answer stop/continue behavior changed.
  - No transition policy changed.
  - No dispatch behavior changed.
  - No ActionPolicy behavior changed.
  - No bundle semantic validator behavior changed.
  - No authority transfer, switch change, or legacy cleanup was added.
- **Next**:
  - Phase 11 — Step 15/N: Transition-Conflict Registry Strategy Batch Closure Review.

---

#### Phase 11 — Step 15/N: Transition-Conflict Registry Strategy Batch Closure Review

- **Status**: Done.
- **Goal**: Close the completed transition-conflict registry strategy batch and choose the next narrow Phase 11 follow-up.
- **Completed Outcome**:
  - The `conflicting_intent_transitions` registry strategy sub-slice is closed.
  - The `intent_complete_with_action_not_allowed` registry strategy sub-slice is closed.
  - Green targeted tests confirmed registry resolution, compiler-driven routing without legacy `invalid_kind`, current behavior contracts, and negative-control separation from mixed-visible and mixed-intent/visible-answer paths.
  - Both completed branches preserve expected reasons, dedicated prompts, and compiler-strategy source conventions.
  - No final-answer stop/continue behavior changed.
  - No transition policy changed.
  - No dispatch behavior changed.
  - No ActionPolicy behavior changed.
  - No bundle semantic validator behavior changed.
  - No authority transfer, switch change, or legacy cleanup was added.
- **Decision**: Keep Phase 11 open for one narrow coverage-gap review before deciding whether to close the phase.
- **Selected Follow-Up**:
  - Review `E_FILE_CONTENT_ACTION_MISMATCH` coverage for the `file_content_must_follow_action` / file-content order family.
- **Rationale**:
  - `file_content_must_follow_action` is already covered for `E_FILE_CONTENT_REQUIRES_ACTION` via the `file_content_requires_action` registry strategy and `file_content_order` handler.
  - `E_FILE_CONTENT_ACTION_MISMATCH` maps to the same invalid kind, `file_content_must_follow_action`, but was previously deferred as a possible separate coverage gap.
  - The review is narrow and structural, and can be completed without changing bundle semantic validator behavior.
- **Forbidden for Step 16**:
  - No registry implementation yet.
  - No broad recovery rewrite.
  - No bundle semantic validator behavior change.
  - No final-answer stop/continue behavior change.
  - No transition policy change.
  - No dispatch behavior change.
  - No ActionPolicy change.
  - No authority transfer or switch change.
  - No legacy cleanup.
- **Next**:
  - Phase 11 — Step 16/N: E_FILE_CONTENT_ACTION_MISMATCH Coverage-Gap Review.

---

#### Phase 11 — Step 16/N: E_FILE_CONTENT_ACTION_MISMATCH Coverage-Gap Review

- **Status**: Done.
- **Goal**: Determine whether `E_FILE_CONTENT_ACTION_MISMATCH` is already sufficiently covered or should receive its own registry strategy design.
- **Completed Outcome**:
  - Confirmed that `E_FILE_CONTENT_REQUIRES_ACTION` is already covered by the `file_content_requires_action` registry strategy.
  - Confirmed that `E_FILE_CONTENT_ACTION_MISMATCH` maps to the same invalid kind: `file_content_must_follow_action`.
  - Confirmed that `BundleSemanticValidator` already classifies both `E_FILE_CONTENT_REQUIRES_ACTION` and `E_FILE_CONTENT_ACTION_MISMATCH` as `INVALID_FILE_CONTENT_PAIRING`.
  - Confirmed golden compiler cases exist for `E_FILE_CONTENT_ACTION_MISMATCH`, including file content with a read action and file content with multiple actions.
  - Confirmed existing compiler-driven routing coverage currently covers `E_FILE_CONTENT_REQUIRES_ACTION`, but not a dedicated `E_FILE_CONTENT_ACTION_MISMATCH` registry route.
  - Confirmed the existing `file_content_order` compiler strategy handler already uses `build_file_content_must_follow_action_prompt()` and can preserve the same reason/prompt behavior if a second strategy is added.
  - No registry implementation was added.
  - No bundle semantic validator behavior changed.
  - No recovery behavior changed.
  - No production behavior changed.
- **Decision**: `E_FILE_CONTENT_ACTION_MISMATCH` is a narrow registry coverage gap and is safe for design-only work.
- **Designed Direction for Next Step**:
  - Add design for a second file-content pairing strategy that reuses the existing `file_content_order` handler.
  - Expected future contract:
    - `id`: `file_content_action_mismatch`.
    - `error_codes`: `("E_FILE_CONTENT_ACTION_MISMATCH",)`.
    - `recovery_ids`: `("file_content_must_follow_action",)`.
    - `invalid_kind`: `file_content_must_follow_action`.
    - `handler_key`: `file_content_order`.
  - Expected prompt: `build_file_content_must_follow_action_prompt()`.
  - Expected reason: `file_content_must_follow_action`.
  - Expected source: existing compiler strategy source conventions.
- **Forbidden for Next Step**:
  - No registry implementation yet.
  - No broad recovery rewrite.
  - No bundle semantic validator behavior change.
  - No file-content parser/compiler behavior change.
  - No final-answer stop/continue behavior change.
  - No transition policy change.
  - No dispatch behavior change.
  - No ActionPolicy change.
  - No authority transfer or switch change.
  - No legacy cleanup.
- **Next**:
  - Phase 11 — Step 17/N: E_FILE_CONTENT_ACTION_MISMATCH Registry Strategy Design.

---

#### Phase 11 — Step 17/N: E_FILE_CONTENT_ACTION_MISMATCH Registry Strategy Design

- **Status**: Done.
- **Goal**: Design the registry strategy contract for `E_FILE_CONTENT_ACTION_MISMATCH` before any implementation.
- **Designed Strategy Contract**:
  - `id`: `file_content_action_mismatch`.
  - `error_codes`: `("E_FILE_CONTENT_ACTION_MISMATCH",)`.
  - `recovery_ids`: `("file_content_must_follow_action",)`.
  - `invalid_kind`: `file_content_must_follow_action`.
  - `handler_key`: `file_content_order`.
  - Prompt expectation: reuse `build_file_content_must_follow_action_prompt()`.
  - Decision reason expectation: `file_content_must_follow_action`.
  - Source expectation: preserve existing compiler strategy source conventions.
- **Required Parity Tests Before Implementation**:
  - Add a current-behavior characterization test for `E_FILE_CONTENT_ACTION_MISMATCH` proving the same reason and file-content-order prompt.
  - Add a registry test proving the future tuple resolves to `file_content_action_mismatch` with handler key `file_content_order`.
  - Add a compiler-driven routing test proving `E_FILE_CONTENT_ACTION_MISMATCH` can route from compiler metadata without legacy `invalid_kind`.
  - Preserve existing `E_FILE_CONTENT_REQUIRES_ACTION` registry/routing behavior as a negative-control sibling.
  - Preserve existing bundle semantic validator tests showing both file-content error codes remain `INVALID_FILE_CONTENT_PAIRING`.
- **Boundary Notes**:
  - This is registry coverage only, not parser/compiler behavior work.
  - This design does not approve any bundle semantic validator behavior change.
  - This design does not approve any file-content parser behavior change.
  - This design does not approve dispatch, ActionPolicy, final-answer, authority, switch, or legacy cleanup changes.
  - Registry implementation is still forbidden until parity characterization is green.
- **Next**:
  - Phase 11 — Step 18/N: E_FILE_CONTENT_ACTION_MISMATCH Registry Strategy Parity Characterization.

---

#### Phase 11 — Step 18/N: E_FILE_CONTENT_ACTION_MISMATCH Registry Strategy Parity Characterization

- **Status**: Done.
- **Goal**: Add test-only characterization for current `E_FILE_CONTENT_ACTION_MISMATCH` behavior before any registry implementation.
- **Completed Outcome**:
  - Added a current-behavior contract test for `E_FILE_CONTENT_ACTION_MISMATCH`.
  - The test proves the branch preserves decision reason `file_content_must_follow_action`.
  - The test proves the branch uses the same file-content-order prompt as `E_FILE_CONTENT_REQUIRES_ACTION`.
  - The test verifies that the branch does not accidentally use action-array or transition-conflict prompt language.
  - Existing `E_FILE_CONTENT_REQUIRES_ACTION` registry/routing behavior remains the sibling control.
  - Existing bundle semantic validator tests continue to own `INVALID_FILE_CONTENT_PAIRING` classification.
  - No `CompilerRecoveryRegistry` strategy was added.
  - No compiler metadata routing behavior was changed.
  - No bundle semantic validator behavior changed.
  - No parser/compiler behavior changed.
  - No recovery behavior changed.
  - No production behavior changed.
- **Next**:
  - Phase 11 — Step 19/N: E_FILE_CONTENT_ACTION_MISMATCH Registry Strategy Implementation Decision.

---

#### Phase 11 — Step 19/N: E_FILE_CONTENT_ACTION_MISMATCH Registry Strategy Implementation Decision

- **Status**: Done.
- **Goal**: Decide whether the `E_FILE_CONTENT_ACTION_MISMATCH` registry strategy may be implemented after parity characterization.
- **Decision**: GO for narrow implementation only.
- **Approved Implementation Scope**:
  - Add one dedicated `CompilerRecoveryStrategy` for `E_FILE_CONTENT_ACTION_MISMATCH`.
  - Expected strategy contract:
    - `id`: `file_content_action_mismatch`.
    - `error_codes`: `("E_FILE_CONTENT_ACTION_MISMATCH",)`.
    - `recovery_ids`: `("file_content_must_follow_action",)`.
    - `invalid_kind`: `file_content_must_follow_action`.
    - `handler_key`: `file_content_order`.
  - Reuse the existing `_compiler_strategy_file_content_order(...)` handler.
  - Add registry resolution coverage for the new strategy tuple.
  - Add compiler-driven routing coverage proving `E_FILE_CONTENT_ACTION_MISMATCH` routes from compiler metadata without legacy `invalid_kind`.
  - Preserve the existing `E_FILE_CONTENT_REQUIRES_ACTION` registry/routing behavior as sibling control.
  - Preserve existing bundle semantic validator tests showing both file-content error codes remain `INVALID_FILE_CONTENT_PAIRING`.
- **Required Behavior Preservation**:
  - Decision reason remains `file_content_must_follow_action`.
  - Prompt remains `build_file_content_must_follow_action_prompt()`.
  - Recovery source follows existing compiler strategy conventions.
  - Existing `E_FILE_CONTENT_REQUIRES_ACTION` strategy remains unchanged.
- **Forbidden**:
  - No broad recovery rewrite.
  - No bundle semantic validator behavior change.
  - No parser/compiler behavior change.
  - No dispatch behavior change.
  - No ActionPolicy change.
  - No final-answer stop/continue behavior change.
  - No transition policy change.
  - No authority transfer or switch change.
  - No legacy cleanup.
- **Next**:
  - Phase 11 — Step 20/N: E_FILE_CONTENT_ACTION_MISMATCH Registry Strategy Implementation.

---

#### Phase 11 — Step 20/N: E_FILE_CONTENT_ACTION_MISMATCH Registry Strategy Implementation

- **Status**: Done.
- **Goal**: Implement the approved narrow compiler recovery strategy for `E_FILE_CONTENT_ACTION_MISMATCH`.
- **Completed Outcome**:
  - Added a dedicated `CompilerRecoveryStrategy` for `E_FILE_CONTENT_ACTION_MISMATCH`.
  - Reused the existing `file_content_order` compiler strategy handler.
  - Added registry resolution coverage for `E_FILE_CONTENT_ACTION_MISMATCH` / `file_content_must_follow_action`.
  - Added compiler-driven routing coverage proving the branch routes from compiler metadata without legacy `invalid_kind`.
  - Preserved existing `E_FILE_CONTENT_REQUIRES_ACTION` registry/routing behavior.
  - Preserved existing current-behavior contract coverage.
  - Preserved existing bundle semantic validator tests owning `INVALID_FILE_CONTENT_PAIRING` classification.
  - Decision reason remains `file_content_must_follow_action`.
  - Recovery source follows existing compiler strategy conventions.
  - No broad recovery rewrite was added.
  - No bundle semantic validator behavior changed.
  - No parser/compiler behavior changed.
  - No dispatch behavior changed.
  - No ActionPolicy behavior changed.
  - No final-answer stop/continue behavior changed.
  - No authority transfer, switch change, or legacy cleanup was added.
- **Next**:
  - Phase 11 — Step 21/N: RecoveryStrategy Registry Expansion Closure Review.

---

#### Phase 11 — Step 21/N: RecoveryStrategy Registry Expansion Closure Review

- **Status**: Done.
- **Goal**: Close Phase 11 after completing the selected narrow RecoveryStrategy registry expansion work.
- **Completed Outcome**:
  - Closed the `mixed_intent_transition_and_visible_answer` registry expansion sub-slice.
  - Closed the transition-conflict registry expansion batch:
    - `conflicting_intent_transitions`.
    - `intent_complete_with_action_not_allowed`.
  - Closed the `E_FILE_CONTENT_ACTION_MISMATCH` registry coverage-gap sub-slice.
  - Added targeted registry resolution coverage for all newly added strategies.
  - Added targeted compiler-driven routing coverage proving the completed branches route from compiler metadata without legacy `invalid_kind`.
  - Preserved current-behavior contract tests for the affected recovery branches.
  - Preserved negative-control separation across mixed-visible, mixed-intent/visible-answer, transition-conflict, action-array, and file-content-order paths.
  - Preserved existing bundle semantic validator ownership for `INVALID_FILE_CONTENT_PAIRING` classification.
  - Preserved parser/compiler behavior.
  - Preserved dispatch behavior.
  - Preserved ActionPolicy behavior.
  - Preserved final-answer stop/continue behavior.
  - No authority transfer, switch change, broad recovery rewrite, or legacy cleanup was added.
- **Closure Decision**: Close Phase 11.
- **Deferred / Not Approved**:
  - Broad recovery rewrite.
  - Cleanup or deletion of legacy recovery paths.
  - Any authority transfer or switch change.
  - Bundle semantic validator behavior changes.
  - Parser/compiler behavior changes.
  - Dispatch, ActionPolicy, or final-answer behavior changes.
- **Next**:
  - Phase 43 — Next Semantic Runtime Slice Selection.

---

### Phase 43: Next Semantic Runtime Slice Selection

- **Status**: In Progress.
- **Goal**: Select the next safe semantic-runtime refactor slice after closing Phase 11 RecoveryStrategy Registry Expansion.
- **Allowed**:
  - Docs-only inventory and decision work.
  - Compare remaining candidate slices by safety, live-agent value, observability value, and refactor risk.
  - Select the next active slice without changing runtime behavior.
- **Forbidden**:
  - No production behavior change.
  - No diagnostic wiring or replay implementation yet.
  - No dispatch behavior change.
  - No recovery behavior change.
  - No ActionPolicy change.
  - No final-answer stop/continue behavior change.
  - No authority transfer or switch change.
  - No legacy cleanup.
- **Done When**:
  - Candidate next slices are listed.
  - The selected next active slice is recorded.
  - Stop lines for the selected slice are documented.

---

#### Phase 43 — Step 1/N: Next Semantic Runtime Slice Selection / Candidate Inventory

- **Status**: Done.
- **Goal**: Inventory candidate next slices after closing Phase 11.
- **Completed Outcome**:
  - Confirmed that Phase 11 closed after narrow, behavior-preserving RecoveryStrategy registry expansion.
  - Identified candidate next slices:
    - Semantic Observability / Replay preflight.
    - Dispatch/action boundary metadata-only follow-up.
    - Legacy cleanup preflight refresh after Phase 11.
    - Recovery prompt / live-agent UX hardening.
    - Terminal-answer deferred boundary review.
  - Observed that Semantic Observability / Replay has high leverage after Phase 11 because registry and compiler-driven recovery routing now cover more branches and need clearer decision tracing.
  - Observed that Dispatch/action boundary work remains high-value but higher-risk because dispatch side effects must remain untouched unless the slice is diagnostic-only.
  - Observed that legacy cleanup should remain deferred until observability and consumer maps make remaining compatibility surfaces safer to classify.
  - Observed that terminal-answer deferred boundaries remain high-risk because they overlap final-answer stop/continue behavior and sufficiency policy.
  - No production behavior was changed.
- **Next**:
  - Phase 43 — Step 2/N: Select Next Active Slice.

---

#### Phase 43 — Step 2/N: Select Next Active Slice

- **Status**: Done.
- **Goal**: Select the next active semantic-runtime slice after candidate inventory.
- **Decision**: Select Semantic Observability / Replay Preflight as the next active slice.
- **Rationale**:
  - Phase 11 expanded compiler-driven recovery routing across several structural branches.
  - The runtime now needs clearer semantic decision tracing before further dispatch, cleanup, or final-answer boundary work.
  - Observability/replay work can start docs-first without production behavior changes.
  - Better observability will improve later debugging for compiler metadata, registry resolution, recovery routing, authority decisions, and compatibility surfaces.
  - Dispatch/action boundary work remains valuable but should wait until decision tracing is clearer.
  - Legacy cleanup remains deferred until observability and consumer maps make compatibility surfaces safer to classify.
  - Terminal-answer deferred boundaries remain high-risk because they overlap final-answer stop/continue behavior and sufficiency policy.
- **Selected Next Phase**:
  - Phase 44 — Semantic Observability / Replay Preflight.
- **Forbidden for Next Phase Start**:
  - No production behavior change.
  - No diagnostic wiring yet.
  - No replay implementation yet.
  - No dispatch behavior change.
  - No recovery behavior change.
  - No ActionPolicy change.
  - No final-answer stop/continue behavior change.
  - No authority transfer or switch change.
  - No legacy cleanup.
- **Next**:
  - Phase 44 — Step 1/N: Semantic Observability / Replay Preflight Inventory.

---

### Phase 44: Semantic Observability / Replay Preflight

- **Status**: In Progress.
- **Goal**: Design a safe observability/replay slice for semantic-runtime decisions before implementing diagnostic wiring or replay tools.
- **Allowed**:
  - Docs-only inventory and design work.
  - Inventory current trace/log surfaces for semantic decisions.
  - Identify semantic decision points that would benefit from structured observation.
  - Define replay inputs/outputs conceptually before implementation.
  - Classify candidate observability surfaces by safety and implementation risk.
- **Forbidden**:
  - No production behavior change.
  - No diagnostic wiring yet.
  - No replay implementation yet.
  - No changes to dispatch, recovery, ActionPolicy, final-answer, parser/compiler, or bundle validator behavior.
  - No authority transfer or switch change.
  - No legacy cleanup.
- **Done When**:
  - Current semantic observability surfaces are inventoried.
  - Candidate replay/diagnostic surfaces are classified.
  - The first safe observability implementation slice is selected or deferred.

---

#### Phase 44 — Step 1/N: Semantic Observability / Replay Preflight Inventory

- **Status**: Done.
- **Goal**: Inventory existing semantic observability, trace, diagnostic, authority-resolution, and replay-adjacent surfaces before any implementation.
- **Completed Outcome**:
  - Confirmed the active slice is observability/replay preflight after Phase 11 registry expansion.
  - Identified existing trace/export surfaces:
    - `modules/agent/orchestration/shared/trace.py`.
    - `modules/agent/orchestration/trace_export.py`.
    - `orchestration_trace` state entries and trace helper tests.
  - Identified existing stage-level logging surfaces:
    - `stage_logger.log(...)` calls in response pipeline and output recovery routing.
    - `output_recovery` continue/terminal diagnostics.
    - `protocol_shadow` diagnostic logs.
  - Identified existing authority/diagnostic resolver surfaces:
    - `recovery_authority.py`.
    - `terminal_answer_authority.py`.
    - `memory_commit_authority.py`.
    - `protocol_decision_bridge.py`.
  - Identified semantic accessor/snapshot surfaces:
    - `runtime_protocol_semantics.py`.
    - `semantic_accessors.py`.
    - compiler metadata helpers and semantic snapshots.
  - Identified replay-adjacent tests and docs:
    - compiler replay trace tests.
    - protocol shadow tests.
    - runtime protocol semantics tests.
    - orchestration trace schema/helper tests.
    - roadmap history of diagnostic-only authority slices.
  - Identified high-value future replay decision points:
    - compiler metadata extraction.
    - compiler error-code to invalid-kind mapping.
    - recovery registry resolution.
    - output recovery decision construction.
    - terminal-answer classifier/shadow results.
    - authority resolver inputs/outputs.
    - dispatch candidate metadata and parity diagnostics.
    - board/memory commit authority diagnostics.
  - Observed that diagnostic and trace surfaces already exist, but are distributed across multiple domains rather than represented by one replayable semantic decision record.
  - Observed that the first implementation slice should be narrow and diagnostic-only, likely centered on collecting already-computed semantic decision facts rather than changing decision flow.
  - No production behavior was changed.
  - No diagnostic wiring was added.
  - No replay implementation was added.
- **Next**:
  - Phase 44 — Step 2/N: Semantic Observability / Replay Surface Classification.

---

#### Phase 44 — Step 2/N: Semantic Observability / Replay Surface Classification

- **Status**: Done.
- **Goal**: Classify existing semantic observability and replay-adjacent surfaces by safety, usefulness, and implementation risk before choosing the first design target.
- **Surface Classification**:
  - **Safe / docs-design first**:
    - A small semantic decision record schema that describes already-computed facts without changing runtime decisions.
    - Compiler metadata extraction facts: `error_code`, `recovery_id`, `invalid_kind`, and metadata source.
    - Invalid-kind mapping facts from `protocol_decision_bridge.py`.
    - Recovery registry resolution facts: selected strategy id, handler key, and whether a strategy was found.
    - Output recovery decision facts: decision reason, source, continue/terminal outcome, and prompt family identity.
  - **Safe but later / diagnostic-only wiring candidate**:
    - Emitting a semantic decision record through existing trace/stage logger surfaces.
    - Adding structured fields to existing `protocol_shadow` diagnostics when the data is already computed.
    - Exporting already-collected semantic decision records via existing trace export paths.
  - **Useful but higher-risk / design later**:
    - End-to-end replay tool execution.
    - Runtime pipeline integration that records every semantic decision across stages.
    - Dispatch/action boundary replay because dispatch side effects must remain untouched.
    - Board/memory commit authority replay because commit equivalence and handler snapshots are domain-specific.
    - Terminal-answer replay because it overlaps final-answer stop/continue and sufficiency policy.
  - **Not approved in this slice**:
    - Any authority selection change.
    - Any switch behavior change.
    - Any new replay execution path that can affect runtime decisions.
    - Any broad production logging expansion without a small schema and tests.
- **Decision**: Select Semantic Decision Record Schema Design as the first safe design target.
- **Rationale**:
  - Existing observability data is useful but scattered across `stage_logger`, `orchestration_trace`, `protocol_shadow`, authority resolvers, semantic accessors, and domain-specific tests.
  - A stable record schema can unify the vocabulary before any wiring or replay implementation.
  - A schema-only step can be validated with tests without changing runtime behavior.
  - The record should initially describe facts already available in recovery routing and compiler metadata paths, especially after Phase 11 expanded registry coverage.
- **Initial Schema Scope for Next Step**:
  - Decision domain, e.g. `output_recovery`, `protocol_authority`, `terminal_answer`, `dispatch_metadata`, `board_memory_commit`.
  - Compiler metadata snapshot: `error_code`, `recovery_id`, `invalid_kind`, source.
  - Registry resolution snapshot: strategy id, handler key, resolved/not resolved.
  - Effective decision: reason, source, outcome kind, and prompt family when applicable.
  - Boundary flags: diagnostic-only, authority-affecting, behavior-affecting.
  - Optional free-form details for future domain-specific fields.
- **Forbidden for Next Step**:
  - No runtime diagnostic wiring yet.
  - No replay tool implementation.
  - No production behavior change.
  - No dispatch behavior change.
  - No recovery behavior change.
  - No ActionPolicy change.
  - No final-answer stop/continue behavior change.
  - No authority transfer or switch change.
  - No legacy cleanup.
- **Next**:
  - Phase 44 — Step 3/N: Semantic Decision Record Schema Design.

---

#### Phase 44 — Step 3/N: Semantic Decision Record Schema Design

- **Status**: Done.
- **Goal**: Design a small, stable semantic decision record schema before any model implementation, diagnostic wiring, or replay tool work.
- **Decision**: Use a minimal generic record that can describe already-computed semantic decisions across domains without becoming runtime authority.
- **Designed Record Name**:
  - `SemanticDecisionRecord`.
- **Designed Core Fields**:
  - `domain`: semantic area, e.g. `output_recovery`, `protocol_authority`, `terminal_answer`, `dispatch_metadata`, `board_memory_commit`.
  - `stage`: pipeline or component stage that produced the record, e.g. `output_recovery`, `prevalidation`, `post_classification`, `checkpoint_stage`.
  - `decision`: short decision label, e.g. `continue`, `terminal`, `legacy_fallback`, `compiler_strategy_resolved`, `strategy_missing`.
  - `reason`: existing runtime reason string when available.
  - `source`: existing runtime source string when available.
  - `diagnostic_only`: boolean. True means the record must not affect runtime behavior.
  - `authority_affecting`: boolean. True only if the decision changes selected authority. Initial records should normally be false.
  - `behavior_affecting`: boolean. True only if the decision changes observable behavior. Initial records should normally be false.
  - `compiler_metadata`: optional compiler metadata snapshot with `error_code`, `recovery_id`, `invalid_kind`, and metadata source.
  - `registry_resolution`: optional recovery registry snapshot with `strategy_id`, `handler_key`, `resolved`, and optional `allowed_next_shapes`.
  - `effective_decision`: optional effective outcome snapshot with `outcome_kind`, `reason`, `source`, and optional `prompt_family`.
  - `authority_resolution`: optional authority resolver snapshot with `branch`, `switch_value`, `authority_source`, `selected_by_switch`, and fallback reason fields when available.
  - `details`: optional dictionary for domain-specific, JSON-serializable details.
- **Initial Domain Scope**:
  - First implementation should target `output_recovery` only, because Phase 11 expanded compiler recovery routing and the relevant data is already computed there.
  - Other domains should remain design-only until the first record model is stable.
- **Replay Concept**:
  - A record is not a replay engine.
  - A record is replay input material: enough structured evidence to later explain why a semantic branch selected a reason/source/outcome.
  - Replay tooling must remain deferred until records can be produced and tested without behavior changes.
- **Schema Rules**:
  - Records must be plain data, deterministic, and JSON-serializable.
  - Records must not call runtime policy or dispatch code.
  - Records must not mutate state.
  - Records must not decide authority.
  - Records must preserve existing runtime strings instead of inventing new behavior labels when a reason/source already exists.
  - Domain-specific fields belong in `details` unless they become stable enough for a future typed sub-record.
- **Testing Expectations for Future Scaffolding**:
  - Unit tests should prove default flags are diagnostic-safe.
  - Unit tests should prove `compiler_metadata`, `registry_resolution`, and `effective_decision` can be represented without requiring runtime objects.
  - Unit tests should prove the record can be converted to a JSON-serializable dictionary.
  - Tests must not require pipeline execution.
- **Forbidden**:
  - No model implementation in this step.
  - No diagnostic wiring.
  - No replay implementation.
  - No production behavior change.
  - No dispatch behavior change.
  - No recovery behavior change.
  - No ActionPolicy change.
  - No final-answer stop/continue behavior change.
  - No authority transfer or switch change.
  - No legacy cleanup.
- **Next**:
  - Phase 44 — Step 4/N: Semantic Decision Record Schema Scaffolding Decision.

---

#### Phase 44 — Step 4/N: Semantic Decision Record Schema Scaffolding Decision

- **Status**: Done.
- **Goal**: Decide whether to implement the designed semantic decision record schema as plain data scaffolding.
- **Decision**: GO for narrow schema scaffolding only.
- **Approved Implementation Scope**:
  - Add a new plain-data semantic decision record module.
  - Suggested module path: `modules/agent/orchestration/responses/semantic_decision_record.py`.
  - Add dataclasses or equivalent plain typed records for:
    - `CompilerMetadataSnapshot`.
    - `RegistryResolutionSnapshot`.
    - `EffectiveDecisionSnapshot`.
    - `AuthorityResolutionSnapshot`.
    - `SemanticDecisionRecord`.
  - Add serialization helper(s) that return JSON-serializable dictionaries.
  - Add unit tests for defaults, nested snapshots, and serialization.
- **Initial Implementation Scope**:
  - Model/scaffold only.
  - No runtime integration.
  - No stage logger integration.
  - No protocol shadow integration.
  - No trace export integration.
  - No replay tool.
- **Required Safety Properties**:
  - Defaults are diagnostic-safe:
    - `diagnostic_only=True`.
    - `authority_affecting=False`.
    - `behavior_affecting=False`.
  - Records are passive data and do not call runtime policy, dispatch, recovery, parser/compiler, or authority code.
  - Records preserve existing reason/source strings when supplied.
  - Serialization omits or safely represents absent optional snapshots.
  - Tests must not require pipeline execution.
- **Forbidden**:
  - No diagnostic wiring.
  - No replay implementation.
  - No production behavior change.
  - No dispatch behavior change.
  - No recovery behavior change.
  - No ActionPolicy change.
  - No final-answer stop/continue behavior change.
  - No authority transfer or switch change.
  - No legacy cleanup.
- **Next**:
  - Phase 44 — Step 5/N: Semantic Decision Record Schema Scaffolding Implementation.

---

#### Phase 44 — Step 5/N: Semantic Decision Record Schema Scaffolding Implementation

- **Status**: Done.
- **Goal**: Implement passive semantic decision record data models and tests without runtime wiring.
- **Completed Outcome**:
  - Added `modules/agent/orchestration/responses/semantic_decision_record.py`.
  - Added passive dataclasses for:
    - `CompilerMetadataSnapshot`.
    - `RegistryResolutionSnapshot`.
    - `EffectiveDecisionSnapshot`.
    - `AuthorityResolutionSnapshot`.
    - `SemanticDecisionRecord`.
  - Added `to_dict()` serialization helpers for JSON-serializable output.
  - Added unit tests for diagnostic-safe defaults.
  - Added unit tests for compiler metadata, registry resolution, effective decision, and authority resolution snapshots.
  - Added a JSON serialization test.
  - Confirmed tests do not require pipeline execution.
  - No runtime integration was added.
  - No stage logger integration was added.
  - No protocol shadow integration was added.
  - No trace export integration was added.
  - No replay tool was added.
  - No production behavior changed.
- **Next**:
  - Phase 44 — Step 6/N: Semantic Decision Record Scaffolding Closure / First Wiring Candidate Review.

---

#### Phase 44 — Step 6/N: Semantic Decision Record Scaffolding Closure / First Implementation Candidate Decision

- **Status**: Done.
- **Goal**: Close semantic decision record scaffolding and choose the first implementation candidate in one pre-code step.
- **Completed Outcome**:
  - Closed the passive `SemanticDecisionRecord` scaffolding sub-slice after green tests.
  - Confirmed the record model remains passive data only.
  - Confirmed there is still no runtime integration, stage logger integration, protocol shadow integration, trace export integration, replay tool, or production behavior change.
  - Reviewed first implementation candidates:
    - Output-recovery compiler strategy decision record builder.
    - Compiler metadata extraction record helper.
    - Protocol-shadow diagnostic record emission.
    - Trace export integration.
  - Selected the output-recovery compiler strategy decision record builder as the first implementation candidate.
- **Decision**: GO for a narrow pure-helper implementation only.
- **Approved Implementation Scope for Step 7**:
  - Add a pure helper that builds a `SemanticDecisionRecord` for output-recovery compiler strategy decisions from already-computed facts.
  - The helper may accept compiler metadata, registry strategy data, effective decision fields, and optional details.
  - The helper must not call runtime policy, dispatch, recovery decision logic, parser/compiler, stage logger, protocol shadow, trace export, or replay code.
  - The helper must not mutate state.
  - The helper must not affect runtime behavior.
  - Add unit tests proving it builds diagnostic-safe records for resolved and unresolved registry-strategy cases.
- **Initial Record Scope**:
  - `domain`: `output_recovery`.
  - `stage`: `output_recovery`.
  - Compiler metadata snapshot.
  - Registry resolution snapshot.
  - Effective decision snapshot when a decision exists.
  - Diagnostic-safe flags.
- **Forbidden for Step 7**:
  - No runtime diagnostic wiring.
  - No stage logger integration.
  - No protocol shadow integration.
  - No trace export integration.
  - No replay implementation.
  - No production behavior change.
  - No dispatch behavior change.
  - No recovery behavior change.
  - No ActionPolicy change.
  - No final-answer stop/continue behavior change.
  - No authority transfer or switch change.
  - No legacy cleanup.
- **Next**:
  - Phase 44 — Step 7/N: Output-Recovery Semantic Decision Record Builder Implementation.

---

#### Phase 44 — Step 7/N: Output-Recovery Semantic Decision Record Builder Implementation

- **Status**: Done.
- **Goal**: Implement a pure output-recovery semantic decision record builder without runtime wiring.
- **Completed Outcome**:
  - Added `modules/agent/orchestration/responses/output_recovery_semantic_record.py`.
  - Added `build_output_recovery_semantic_decision_record(...)`.
  - The helper builds passive `SemanticDecisionRecord` instances for output-recovery decisions from already-computed facts.
  - The helper captures compiler metadata snapshots.
  - The helper captures registry resolution snapshots for resolved and unresolved strategy cases.
  - The helper captures effective decision snapshots when decision fields are supplied.
  - Added unit tests for resolved registry strategy records.
  - Added unit tests for missing strategy records.
  - Added unit tests for dict-like strategy input.
  - No runtime integration was added.
  - No stage logger integration was added.
  - No protocol shadow integration was added.
  - No trace export integration was added.
  - No replay tool was added.
  - No production behavior changed.
- **Next**:
  - Phase 44 — Step 8/N: Output-Recovery Semantic Decision Record Builder Closure / First Diagnostic Wiring Candidate Decision.

---

#### Phase 44 — Step 8/N: Output-Recovery Semantic Decision Record Builder Closure / First Diagnostic Wiring Candidate Decision

- **Status**: Done.
- **Goal**: Close the pure output-recovery semantic record builder sub-slice and choose the first diagnostic wiring candidate in one pre-code step.
- **Completed Outcome**:
  - Closed the pure output-recovery semantic decision record builder sub-slice after green tests.
  - Confirmed the builder remains passive and only packages already-computed facts.
  - Confirmed no runtime integration, stage logger integration, protocol shadow integration, trace export integration, replay tool, or production behavior change was added in Step 7.
  - Reviewed first diagnostic wiring candidates:
    - Diagnostic-only stage logger enrichment in `_compiler_strategy_decision(...)` / compiler strategy path.
    - Protocol-shadow semantic record emission.
    - Trace export integration.
    - State/container storage for semantic records.
  - Rejected state/container storage as a first slice because it risks creating a hidden runtime surface.
  - Deferred protocol-shadow and trace export integration until one narrow stage logger path proves the record shape is useful.
- **Decision**: GO for narrow diagnostic-only stage logger enrichment in the output-recovery compiler strategy path.
- **Approved Implementation Scope for Step 9**:
  - In the compiler strategy path, build an output-recovery `SemanticDecisionRecord` from already-computed compiler metadata, registry strategy data, and effective decision facts.
  - Add the record to existing stage logger output as a JSON-serializable diagnostic field.
  - Preserve existing decision reason, source, prompt, retry counters, and return path.
  - Add tests proving the diagnostic record is emitted for resolved compiler strategies.
  - Add tests proving unresolved or missing strategy paths do not change behavior.
- **Required Safety Properties**:
  - Diagnostic-only only.
  - No replay implementation.
  - No state mutation.
  - No trace export integration.
  - No protocol shadow integration.
  - No production behavior change.
  - No recovery behavior change.
  - No dispatch behavior change.
  - No ActionPolicy change.
  - No final-answer stop/continue behavior change.
  - No authority transfer or switch change.
  - No legacy cleanup.
- **Next**:
  - Phase 44 — Step 9/N: Output-Recovery Compiler Strategy Semantic Record Diagnostic Wiring.

---

#### Phase 44 — Step 9/N: Output-Recovery Compiler Strategy Semantic Record Diagnostic Wiring

- **Status**: Done.
- **Goal**: Wire diagnostic-only semantic decision record emission into the output-recovery compiler strategy path.
- **Completed Outcome**:
  - Added diagnostic-only semantic record construction in the resolved compiler strategy path.
  - Emitted the record as a JSON-serializable field through existing `stage_logger.log(...)` output.
  - Added targeted test coverage proving a resolved compiler strategy emits one semantic decision record.
  - The emitted record captures output-recovery domain/stage, compiler metadata, registry resolution, effective decision, and diagnostic-safe flags.
  - Existing recovery decision reason/source/prompt/return behavior is preserved.
  - No replay implementation was added.
  - No state mutation was added.
  - No trace export integration was added.
  - No protocol shadow integration was added.
  - No production behavior changed.
  - No dispatch behavior changed.
  - No ActionPolicy behavior changed.
  - No final-answer stop/continue behavior changed.
  - No authority transfer, switch change, or legacy cleanup was added.
- **Next**:
  - Phase 44 — Step 10/N: Output-Recovery Semantic Diagnostic Wiring Closure / Replay Preflight Decision.

---

#### Phase 44 — Step 10/N: Semantic Observability / Replay Preflight Closure Review

- **Status**: Done.
- **Goal**: Close Phase 44 after the first safe semantic observability increment and decide whether to continue into replay implementation immediately.
- **Completed Outcome**:
  - Closed the Semantic Observability / Replay Preflight slice after one narrow, behavior-preserving diagnostic integration.
  - Added passive semantic decision record scaffolding:
    - `CompilerMetadataSnapshot`.
    - `RegistryResolutionSnapshot`.
    - `EffectiveDecisionSnapshot`.
    - `AuthorityResolutionSnapshot`.
    - `SemanticDecisionRecord`.
  - Added JSON-serializable `to_dict()` helpers and tests.
  - Added a pure output-recovery semantic decision record builder.
  - Added diagnostic-only stage logger emission for resolved output-recovery compiler strategy paths.
  - Preserved output-recovery decision reason/source/prompt/return behavior.
  - Preserved dispatch behavior.
  - Preserved ActionPolicy behavior.
  - Preserved final-answer stop/continue behavior.
  - Preserved authority and switch behavior.
  - No state/container storage was added.
  - No protocol shadow integration was added.
  - No trace export integration was added.
  - No replay tool was added.
  - No production behavior changed.
- **Decision**: Close Phase 44 now instead of expanding directly into replay tooling.
- **Rationale**:
  - Phase 44 achieved a useful observability increment: semantic decision facts can now be represented and emitted for the output-recovery compiler strategy path.
  - A full replay tool should wait until the next slice selection because trace export, protocol shadow, dispatch metadata, and replay execution each carry different risks.
  - Closing now keeps the slice narrow and prevents observability work from drifting into broad runtime instrumentation.
- **Deferred / Not Approved**:
  - Replay implementation.
  - Trace export integration.
  - Protocol shadow integration.
  - State/container storage for semantic records.
  - Broad production logging expansion.
  - Dispatch/action replay.
  - Terminal-answer replay.
  - Board/memory commit replay.
  - Any authority transfer or switch change.
  - Any production behavior change.
- **Next**:
  - Phase 45 — Next Semantic Runtime Slice Selection.

---

### Phase 45: Next Semantic Runtime Slice Selection

- **Status**: In Progress.
- **Goal**: Select the next safe semantic-runtime refactor slice after closing Phase 44 Semantic Observability / Replay Preflight.
- **Allowed**:
  - Docs-only inventory and decision work.
  - Compare remaining candidate slices by safety, live-agent value, observability value, and refactor risk.
  - Select the next active slice without changing runtime behavior.
- **Forbidden**:
  - No production behavior change.
  - No trace export integration yet.
  - No protocol shadow integration yet.
  - No replay implementation yet.
  - No state mutation or semantic record storage.
  - No dispatch behavior change.
  - No recovery behavior change.
  - No ActionPolicy change.
  - No final-answer stop/continue behavior change.
  - No authority transfer or switch change.
  - No legacy cleanup.
- **Done When**:
  - Candidate next slices are listed.
  - The selected next active slice is recorded.
  - Stop lines for the selected slice are documented.

---

#### Phase 45 — Step 1/N: Next Semantic Runtime Slice Selection / Candidate Inventory

- **Status**: Done.
- **Goal**: Inventory candidate next slices after closing Phase 44.
- **Completed Outcome**:
  - Confirmed that Phase 44 closed after delivering passive semantic decision records, a pure output-recovery record builder, and diagnostic-only stage logger emission in the resolved output-recovery compiler strategy path.
  - Identified candidate next slices:
    - Trace Export Integration Preflight.
    - Protocol Shadow Semantic Record Integration Preflight.
    - Dispatch Metadata Observability Follow-up.
    - Legacy Cleanup Preflight Refresh after Phase 44.
    - Replay Tool Design, without implementation yet.
  - Observed that Trace Export Integration Preflight is a natural next candidate because semantic records now exist in diagnostic logger output but are not yet surfaced through an explicit export/readback path.
  - Observed that Protocol Shadow integration is useful but should wait until record/export shape is clearer.
  - Observed that Dispatch Metadata observability remains valuable but higher-risk because dispatch side effects must remain untouched.
  - Observed that Replay Tool Design should remain design-only until trace/export surfaces are better understood.
  - Observed that Legacy Cleanup remains deferred because new observability surfaces are still young and should not trigger cleanup yet.
  - No production behavior was changed.
- **Next**:
  - Phase 45 — Step 2/N: Select Next Active Slice.

---

#### Phase 45 — Step 2/N: Select Next Active Slice

- **Status**: Done.
- **Goal**: Select the next active semantic-runtime slice after candidate inventory.
- **Decision**: Select Trace Export Integration Preflight as the next active slice.
- **Rationale**:
  - Phase 44 introduced passive semantic decision records and diagnostic-only output-recovery compiler-strategy record emission.
  - Semantic decision records now exist in diagnostic logger output, but there is no explicit export/readback path for analyzing them as artifacts.
  - Trace Export Integration Preflight can start docs-first and inventory-only without changing production behavior.
  - Trace/export work is lower risk than protocol-shadow integration, dispatch observability, or replay tooling because it can first classify existing export/readback surfaces before any wiring.
  - Replay Tool Design remains deferred until trace/export surfaces are understood.
  - Protocol Shadow integration remains deferred until record shape and export/readback needs are clearer.
  - Dispatch Metadata observability remains deferred because dispatch side effects must remain untouched.
  - Legacy Cleanup remains deferred because new observability surfaces are still young.
- **Selected Next Phase**:
  - Phase 46 — Trace Export Integration Preflight.
- **Forbidden for Next Phase Start**:
  - No production behavior change.
  - No trace export integration yet.
  - No protocol shadow integration.
  - No replay implementation.
  - No state mutation or semantic record storage.
  - No dispatch behavior change.
  - No recovery behavior change.
  - No ActionPolicy change.
  - No final-answer stop/continue behavior change.
  - No authority transfer or switch change.
  - No legacy cleanup.
- **Next**:
  - Phase 46 — Step 1/N: Trace Export Integration Preflight Inventory.

---

### Phase 46: Trace Export Integration Preflight

- **Status**: In Progress.
- **Goal**: Design a safe path for exporting or reading back semantic decision records from existing trace/log surfaces before implementing trace export integration.
- **Allowed**:
  - Docs-only inventory and design work.
  - Inventory existing trace export code and tests.
  - Inventory how `stage_logger` output is represented in traces or logs.
  - Identify whether semantic decision records can be exported from existing diagnostic output without new runtime state.
  - Classify candidate export/readback surfaces by safety and implementation risk.
- **Forbidden**:
  - No production behavior change.
  - No trace export integration yet.
  - No protocol shadow integration.
  - No replay implementation.
  - No state mutation or semantic record storage.
  - No dispatch behavior change.
  - No recovery behavior change.
  - No ActionPolicy change.
  - No final-answer stop/continue behavior change.
  - No authority transfer or switch change.
  - No legacy cleanup.
- **Done When**:
  - Existing trace export/readback surfaces are inventoried.
  - Candidate semantic decision record export paths are classified.
  - The first safe export/readback implementation slice is selected or deferred.

---

#### Phase 46 — Step 1/N: Trace Export Integration Preflight Inventory / Export Surface Decision

- **Status**: Done.
- **Goal**: Inventory trace/export/readback surfaces and choose the first safe semantic decision record export characterization target in one pre-code step.
- **Completed Outcome**:
  - Confirmed the active slice is Trace Export Integration Preflight after Phase 44.
  - Identified current trace/export files:
    - `modules/agent/orchestration/shared/trace.py`.
    - `modules/agent/orchestration/trace_export.py`.
  - Confirmed `trace_export.py` is an export adapter over the shared trace layer.
  - Confirmed `trace_export.py` already exposes structured trace via `snapshot_trace(state)` and rendered trace text.
  - Confirmed stage logger usage is widespread and stage logger entries are represented through `orchestration_trace` state entries.
  - Confirmed semantic decision record emission currently happens through existing `stage_logger.log(...)` output in the resolved output-recovery compiler strategy path.
  - Confirmed no explicit semantic record state/container storage currently exists or is desired as a first export slice.
  - Confirmed no protocol-shadow integration or replay tool exists for semantic decision records yet.
  - Observed that semantic decision records already traverse the existing trace surface as stage logger fields, so the first safe code step should characterize existing export/readback behavior rather than add new integration.
- **Surface Classification**:
  - **Safe first code target / test-only**:
    - Characterize that a stage logger entry containing `semantic_decision_record` is preserved by the existing trace snapshot/export path.
    - Use existing trace/state/export helpers only.
    - Do not add new runtime wiring.
  - **Safe later / small implementation candidate**:
    - Add a tiny extractor/filter helper for semantic decision records from exported trace snapshots, if characterization proves the field is already present.
  - **Defer**:
    - Protocol-shadow semantic record integration.
    - Trace export schema changes.
    - New semantic record state/container storage.
    - Replay tool implementation.
    - Broad production logging expansion.
  - **No-go in this slice**:
    - Any trace/export path that mutates runtime behavior or changes decision flow.
- **Decision**: Select test-only trace export characterization as the first safe code step.
- **Approved Implementation Scope for Step 2**:
  - Add characterization tests proving a `semantic_decision_record` field emitted through `OrchestrationStageLogger` is preserved in `orchestration_trace` and `trace_export` structured output.
  - Use existing trace/export APIs only.
  - Do not modify `trace_export.py` yet.
  - Do not modify `shared/trace.py` yet.
  - Do not add semantic record storage.
  - Do not add replay tooling.
- **Required Safety Properties**:
  - Test-only characterization.
  - No production behavior change.
  - No trace export implementation change.
  - No protocol shadow integration.
  - No replay implementation.
  - No state mutation or semantic record storage.
  - No dispatch behavior change.
  - No recovery behavior change.
  - No ActionPolicy change.
  - No final-answer stop/continue behavior change.
  - No authority transfer or switch change.
  - No legacy cleanup.
- **Next**:
  - Phase 46 — Step 2/N: Semantic Decision Record Trace Export Characterization.

---

#### Phase 46 — Step 2/N: Semantic Decision Record Trace Export Characterization

- **Status**: Done.
- **Goal**: Characterize whether semantic decision record fields already survive existing stage logger, orchestration trace, and trace export surfaces without implementation changes.
- **Completed Outcome**:
  - Added test-only characterization proving `OrchestrationStageLogger` preserves a `semantic_decision_record` field in `orchestration_trace` entry fields.
  - Added test-only characterization proving existing `OrchestrationTraceExporter` structured output preserves the same `semantic_decision_record` field through `runtime_artifacts(...)["orchestration_trace"]`.
  - Confirmed the existing trace/export path can surface semantic decision records as ordinary stage logger fields.
  - Confirmed no `trace_export.py` implementation change was required.
  - Confirmed no `shared/trace.py` implementation change was required.
  - Confirmed no semantic record state/container storage was required.
  - Confirmed no replay tooling was required.
  - No production behavior changed.
- **Next**:
  - Phase 46 — Step 3/N: Trace Export Surface Closure / Export Helper Decision.

---

#### Phase 46 — Step 3/N: Trace Export Surface Closure / Export Helper Decision

- **Status**: Done.
- **Goal**: Close the Trace Export Integration Preflight slice and decide whether an export helper should be implemented immediately.
- **Completed Outcome**:
  - Reviewed the Step 2 characterization results.
  - Confirmed semantic decision records emitted through existing stage logger output are preserved in `orchestration_trace` entry fields.
  - Confirmed existing `OrchestrationTraceExporter.runtime_artifacts(...)` already exposes those fields through structured trace output.
  - Confirmed the useful export/readback path exists without adding new runtime state, trace export schema changes, or replay tooling.
  - Confirmed no additional export helper is required for the current slice.
  - Confirmed protocol-shadow integration, replay implementation, trace export schema changes, semantic record storage, and broad production logging remain deferred.
- **Decision**: Close Phase 46 without implementing an export helper.
- **Rationale**:
  - The first export/readback question was answered by characterization: existing trace export already preserves `semantic_decision_record` fields.
  - A new extractor/filter helper would be premature until a concrete consumer or replay workflow needs it.
  - Closing now keeps the slice narrow and avoids turning trace export preflight into replay tooling.
- **Deferred / Not Approved**:
  - Export helper implementation.
  - Trace export schema changes.
  - Protocol-shadow semantic record integration.
  - Replay implementation.
  - Semantic record state/container storage.
  - Broad production logging expansion.
  - Dispatch/action replay.
  - Terminal-answer replay.
  - Board/memory commit replay.
  - Any authority transfer or switch change.
  - Any production behavior change.
  - Legacy cleanup.
- **Next**:
  - Phase 47 — Next Semantic Runtime Slice Selection.

---

#### Phase 46 — Step 1/N: Trace Export Integration Preflight Inventory / Export Surface Decision

- **Status**: Done.
- **Goal**: Inventory trace/export/readback surfaces and choose the first safe semantic decision record export characterization target in one pre-code step.
- **Completed Outcome**:
  - Confirmed the active slice is Trace Export Integration Preflight after Phase 44.
  - Identified current trace/export files:
    - `modules/agent/orchestration/shared/trace.py`.
    - `modules/agent/orchestration/trace_export.py`.
  - Confirmed `trace_export.py` is an export adapter over the shared trace layer.
  - Confirmed `trace_export.py` already exposes structured trace via `snapshot_trace(state)` and rendered trace text.
  - Confirmed stage logger usage is widespread and stage logger entries are represented through `orchestration_trace` state entries.
  - Confirmed semantic decision record emission currently happens through existing `stage_logger.log(...)` output in the resolved output-recovery compiler strategy path.
  - Confirmed no explicit semantic record state/container storage currently exists or is desired as a first export slice.
  - Confirmed no protocol-shadow integration or replay tool exists for semantic decision records yet.
  - Observed that semantic decision records likely already traverse the existing trace surface as stage logger fields, so the first safe code step should characterize existing export/readback behavior rather than add new integration.
- **Surface Classification**:
  - **Safe first code target / test-only**:
    - Characterize that a stage logger entry containing `semantic_decision_record` is preserved by the existing trace snapshot/export path.
    - Use existing trace/state/export helpers only.
    - Do not add new runtime wiring.
  - **Safe later / small implementation candidate**:
    - Add a tiny extractor/filter helper for semantic decision records from exported trace snapshots, if characterization proves the field is already present.
  - **Defer**:
    - Protocol-shadow semantic record integration.
    - Trace export schema changes.
    - New semantic record state/container storage.
    - Replay tool implementation.
    - Broad production logging expansion.
  - **No-go in this slice**:
    - Any trace/export path that mutates runtime behavior or changes decision flow.
- **Decision**: Select test-only trace export characterization as the first safe code step.
- **Approved Implementation Scope for Step 2**:
  - Add characterization tests proving a `semantic_decision_record` field emitted through `OrchestrationStageLogger` is preserved in `orchestration_trace` and `trace_export` structured output.
  - Use existing trace/export APIs only.
  - Do not modify `trace_export.py` yet.
  - Do not modify `shared/trace.py` yet.
  - Do not add semantic record storage.
  - Do not add replay tooling.
- **Required Safety Properties**:
  - Test-only characterization.
  - No production behavior change.
  - No trace export implementation change.
  - No protocol shadow integration.
  - No replay implementation.
  - No state mutation or semantic record storage.
  - No dispatch behavior change.
  - No recovery behavior change.
  - No ActionPolicy change.
  - No final-answer stop/continue behavior change.
  - No authority transfer or switch change.
  - No legacy cleanup.
- **Next**:
  - Phase 46 — Step 2/N: Semantic Decision Record Trace Export Characterization.

---

### Phase 12: Observability/Replay

- **Goal**: Improve debugging by enabling replay of semantic decisions.
- **Allowed**: Log the inputs and outputs of semantic accessors. Create a debug tool to replay a response through the semantic layer.
- **Forbidden**: Adding complexity to the production path.
- **Done When**: A given production response can be re-evaluated offline.

---

### Phase 13: Legacy Cleanup

- **Goal**: Remove deprecated legacy fields and helpers.
- **Allowed**: Remove `ResponseSemantics`, `has_action_segment`, and other legacy fields from `ParsedModelOutput`.
- **Forbidden**: Removing anything that still has a consumer.
- **Done When**: `ResponseSemantics` is deleted.

---

### Phase 14: Compatibility Cleanup (Deferred)

- **Goal**: Remove legacy compatibility fields and branching logic from refactored components.
- **Scope**: `ActionPolicyHandler` `reason`/`details` fields, `ResponsePipelinePrevalidationMixin` fallback logic.
- **Forbidden**: Implementation before a new design is approved.
- **Done When**: The legacy compatibility shims from Phase 7 are removed.
