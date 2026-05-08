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

- **Status**: In Progress (Part 1 Complete).
- **Goal**: Analyze shadow logs and begin integrating legacy helper branches into the classifier.
- **Prerequisite**: Step 4H must be complete.
- **Forbidden**: Consumer migration. Any changes to runtime behavior.
- **Done When (Part 1)**: The shadow logging was updated to compute and record `legacy_kind` and `is_match`, enabling parity analysis.
- **Done When (Full)**: A parity matrix is documented, and at least one legacy helper branch is integrated into the classifier with passing tests.

---

### Phase 9: Plan-First Bundle Execution

- **Goal**: Refactor `DispatchPipeline` to execute from a plan derived from semantic accessors, not from reparsed segments.
- **Allowed**: Modify `ResponsePipeline` to build an `ExecutionPlan` using semantic accessors. Modify `DispatchPipeline` to execute this plan.
- **Forbidden**: Changing dispatch side effects.
- **Done When**: `DispatchPipeline` no longer receives raw segments.

---

### Phase 10: RecoveryStrategy Registry Expansion

- **Goal**: Expand the `CompilerRecoveryRegistry` to cover more structural errors.
- **Allowed**: Add new strategies for errors currently handled by legacy `invalid_kind` routing.
- **Forbidden**: Adding strategies for runtime-owned policy decisions.
- **Done When**: All purely structural `invalid_kind`s are routed through the compiler registry.

---

### Phase 11: Observability/Replay

- **Goal**: Improve debugging by enabling replay of semantic decisions.
- **Allowed**: Log the inputs and outputs of semantic accessors. Create a debug tool to replay a response through the semantic layer.
- **Forbidden**: Adding complexity to the production path.
- **Done When**: A given production response can be re-evaluated offline.

---

### Phase 12: Legacy Cleanup

- **Goal**: Remove deprecated legacy fields and helpers.
- **Allowed**: Remove `ResponseSemantics`, `has_action_segment`, and other legacy fields from `ParsedModelOutput`.
- **Forbidden**: Removing anything that still has a consumer.
- **Done When**: `ResponseSemantics` is deleted.

---

### Phase 13: Compatibility Cleanup (Deferred)

- **Goal**: Remove legacy compatibility fields and branching logic from refactored components.
- **Scope**: `ActionPolicyHandler` `reason`/`details` fields, `ResponsePipelinePrevalidationMixin` fallback logic.
- **Forbidden**: Implementation before a new design is approved.
- **Done When**: The legacy compatibility shims from Phase 7 are removed.
