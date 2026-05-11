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

- **Status**: In Progress.
- **Goal**: Reconcile synthetic `MEMORY_CHECKPOINT_WITH_TEXT` equivalence with real live `MemoryBoardStageHandler` behavior by improving diagnostic logging.
- **Allowed**:
  - Add per-agreement diagnostic fields to `_log_board_memory_commit_authority_resolution`.
  - Update tests to assert on the new diagnostic fields.
- **Forbidden**:
  - Changing runtime behavior.
  - Consuming the `effective_commit` from the resolver.
  - Changing memory/board handler behavior.
  - Flipping the default registry.
- **Done When**:
  - The diagnostic log includes detailed agreement fields.
  - A manual re-run of live smoke can identify the exact cause of `commit_equivalent=False`.

---

### Phase 11: RecoveryStrategy Registry Expansion

- **Goal**: Expand the `CompilerRecoveryRegistry` to cover more structural errors.
- **Allowed**: Add new strategies for errors currently handled by legacy `invalid_kind` routing.
- **Forbidden**: Adding strategies for runtime-owned policy decisions.
- **Done When**: All purely structural `invalid_kind`s are routed through the compiler registry.

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
