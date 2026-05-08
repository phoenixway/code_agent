# Current Refactor State: Semantic Runtime Migration

This document is the single source of truth for the current state of the Semantic Runtime Migration refactor.

## Current Phase

- **Phase 4: Behavior-Preserving Wrapper Migration (Complete)**
- **Status**: All planned wrapper migrations are complete. The remaining migration review is also complete.

## Completed Governance

- **Governance Phase 1: Governance Alignment**
  - All governance documents (`constitution`, `roadmap`, `stop-lines`, etc.) are aligned with the actual completed work and established boundaries.

## Completed Work

- **Phase 0: Boundary Freeze**
  - `RuntimeProtocolSemantics` adapter created for compiler-derived data.
  - Adapter populated in response pipeline for diagnostic use.
- **Phase 2: Consumer Inventory**
  - A detailed inventory of all locations that consume response semantics was created and approved.
  - The inventory lives in `docs/architecture/protocol-authority-boundaries.md`.
- **Phase 3A: Compiler Metadata Migration (in `output_recovery`)**
  - Centralized helper for reading `error_code`, `recovery_id`, and `invalid_kind` from `RuntimeProtocolSemantics` with legacy fallbacks.
  - All compiler strategy handlers and `_compiler_repeat_fingerprint` now use the centralized helper.
  - Parity diagnostics added to log differences between legacy and new semantic sources.
  - **Boundary**: This work is complete and closed.
- **Phase 3: Accessor Module (Implementation)**
  - `modules/agent/orchestration/responses/semantic_accessors.py` created with four approved accessors (`get_compiler_metadata`, `has_any_action_proposal_compat`, `is_compiler_invalid`, `is_compiler_invalid_with_legacy_action`).
  - Dedicated unit tests created in `tests/test_semantic_accessors.py`.
  - No consumers were migrated, and no runtime behavior was changed.
- **Phase 4 (Step 1): `has_any_action_proposal` Migration**
  - `ResponseSemantics.has_any_action_proposal` now delegates to `semantic_accessors.has_any_action_proposal_compat`.
  - Behavior was preserved, and all relevant tests passed.
  - No other consumers were migrated.
- **Phase 4 (Batch 1): Call-Site Migrations**
  - Migrated `OutputRecoveryRoutingMixin._compiler_strategy_decision` to use `get_compiler_metadata`.
  - Migrated `ModelOutputRecoveryHandler._has_any_action_proposal` to use `has_any_action_proposal_compat`.
  - The `output_recovery_compiler_metadata` helper was preserved.
  - No other consumers were migrated, and runtime behavior was unchanged.
- **Next Accessor Batch (Implementation)**
  - Implemented `is_leaked_system_result` and `has_substantial_think` in `semantic_accessors.py`.
  - Added dedicated unit tests, which passed.
  - `get_visible_text` was not implemented and remains deferred.
  - No consumers were migrated, and no runtime behavior was changed.
- **Phase 4 (Batch 2): Consumer Migrations**
  - Migrated `ResponsePipelineStagesMixin` leaked system result check to `is_leaked_system_result`.
  - Migrated `ResponseGuardPolicy.is_nonproductive_thinking_turn` to `has_substantial_think`.
  - Tests passed.
  - No `get_visible_text` implementation.
  - No other consumers migrated.
  - Runtime behavior unchanged.
- **Phase 4: Remaining Migration Review**
  - Reviewed all remaining un-migrated consumers in the inventory.
  - Conclusion: The "fast-lane" of simple, safe wrapper migrations is exhausted.
  - All remaining consumers are either high-risk policy/dispatch boundaries or require new accessors tied to those same frozen domains.
  - Recommendation: Conclude Phase 4 and begin planning for a later policy-focused phase (e.g., Phase 5).
- **Phase 5: TransitionSemanticValidator (Design)**
  - The design for the `TransitionSemanticValidator` is approved.
  - The validator will centralize and replace the complex followup-handling logic in `IntentTransitionHandler` with a single, testable component that returns a strongly-typed classification.
  - Implementation is authorized for Step 1 (scaffolding) only.
- **Phase 5 Step 1: TransitionSemanticValidator Scaffolding**
  - Created `modules/agent/orchestration/transitions/transition_semantic_validator.py` and `tests/test_transition_semantic_validator.py`.
  - Added `TransitionResultKind` enum, `TransitionValidationResult` dataclass, and `TransitionSemanticValidator` class scaffold.
  - The `validate` method returns `UNKNOWN` by default.
  - Tests passed.
  - No logic was migrated, and no runtime behavior was changed.
- **Phase 5 Step 2A: Core Structural Logic Migration (Design)**
  - The design for migrating the core structural classification logic (`NO_FOLLOWUP`, `FOLLOWUP_ACTION`, `FOLLOWUP_CONFLICT`) into the `TransitionSemanticValidator` is approved.
  - Implementation is authorized for Step 2A only.
- **Phase 5 Step 2A: Core Structural Logic Migration (Implementation)**
  - Implemented core structural classifications (`NO_FOLLOWUP`, `FOLLOWUP_ACTION`, `FOLLOWUP_CONFLICT`) inside `TransitionSemanticValidator`.
  - Added unit and parity tests, which passed.
  - No consumers were migrated, and no old helpers were modified.
  - `get_visible_text` and context-sensitive violations were not implemented.
  - Runtime behavior is unchanged.
- **Phase 5 Step 2B: Context-Sensitive Logic Migration (Design)**
  - The design for migrating context-sensitive violation classifications (`TRANSITION_ONLY_VIOLATION`, etc.) into the `TransitionSemanticValidator` is approved.
  - Implementation is authorized for Step 2B only.
- **Phase 5 Step 2B: Context-Sensitive Logic Migration (Implementation)**
  - Implemented context-sensitive classifications (`TRANSITION_ONLY_VIOLATION`, `REUSE_ONLY_VIOLATION`, `COMPLETE_WITH_ACTION_VIOLATION`) inside `TransitionSemanticValidator`.
  - Added unit and parity tests, which passed.
  - No consumers were migrated, and no old helpers were modified.
  - `get_visible_text` and `FOLLOWUP_PLAINTEXT` were not implemented.
  - Runtime behavior is unchanged.
- **Phase 5 Step 3: Consumer Migration (Design)**
  - The design for migrating the first narrow slice of `IntentTransitionRoutingMixin` (recovery/violation classifications) to use the `TransitionSemanticValidator` is approved.
  - The design uses a fallback to legacy logic for all other cases to ensure behavior preservation and defer `get_visible_text`.
  - Implementation is authorized for the first narrow slice only.
- **Phase 5 Step 3: Consumer Migration (Implementation)**
  - Migrated the first narrow slice of `IntentTransitionRoutingMixin` to use the `TransitionSemanticValidator` for recovery/violation classifications.
  - Migrated kinds: `TRANSITION_ONLY_VIOLATION`, `REUSE_ONLY_VIOLATION`, `COMPLETE_WITH_ACTION_VIOLATION`, `FOLLOWUP_CONFLICT`.
  - Fallback to legacy logic preserved for `NO_FOLLOWUP`, `FOLLOWUP_ACTION`, `FOLLOWUP_PLAINTEXT`, and `UNKNOWN`.
  - Tests passed, and runtime behavior is unchanged.
- **Phase 5 Review: Next Migration Slice**
  - Reviewed the remaining fallback paths (`NO_FOLLOWUP`, `FOLLOWUP_ACTION`, `FOLLOWUP_PLAINTEXT`, `UNKNOWN`).
  - Conclusion: `NO_FOLLOWUP` and `FOLLOWUP_ACTION` are safe candidates for a second narrow migration slice.
  - `FOLLOWUP_PLAINTEXT` remains deferred due to the `get_visible_text` dependency.
  - `UNKNOWN` must remain a fallback to preserve behavior for unhandled cases.
  - Recommendation: Proceed with designing the second migration slice for `NO_FOLLOWUP` and `FOLLOWUP_ACTION`.
- **Phase 5 Step 4: Second Consumer Migration (Design)**
  - The design for migrating the second narrow slice of `IntentTransitionRoutingMixin` (`NO_FOLLOWUP`, `FOLLOWUP_ACTION`) to use the `TransitionSemanticValidator` is approved.
  - The design uses a fallback to legacy logic for `FOLLOWUP_PLAINTEXT` and `UNKNOWN`.
  - Implementation is authorized for the second narrow slice only.
- **Phase 5 Step 4: Second Consumer Migration (Implementation)**
  - Migrated the second narrow slice of `IntentTransitionRoutingMixin` (`NO_FOLLOWUP`, `FOLLOWUP_ACTION`) to use the `TransitionSemanticValidator`.
  - Fallback to legacy logic preserved for `FOLLOWUP_PLAINTEXT` and `UNKNOWN`.
  - Tests passed, and runtime behavior is unchanged.
- **Phase 5 Boundary Review**
  - Reviewed the remaining fallback paths (`FOLLOWUP_PLAINTEXT`, `UNKNOWN`).
  - Conclusion: The `FOLLOWUP_PLAINTEXT` path is deeply tied to final-answer/sufficiency policy and the `get_visible_text` accessor. Migrating it would significantly expand the scope of Phase 5.
  - Recommendation: Conclude Phase 5. The `TransitionSemanticValidator` has successfully migrated the vast majority of transition classifications. The remaining `FOLLOWUP_PLAINTEXT` and `UNKNOWN` paths will be kept on the legacy fallback, and the old helpers will be preserved. `get_visible_text` will be deferred to a potential future phase.
- **Phase 6: Bundle Semantic Validation Pass (Design)**
  - The design for the `BundleSemanticValidator` is approved.
  - The validator will centralize classification of action bundle structure and safety.
  - Implementation is authorized for Step 1 (scaffolding) only.
- **Phase 6 Step 1: BundleSemanticValidator Scaffolding**
  - Created `modules/agent/orchestration/responses/bundle_semantic_validator.py` and `tests/test_bundle_semantic_validator.py`.
  - Added `BundleResultKind` enum, `BundleValidationResult` dataclass, and `BundleSemanticValidator` class scaffold.
  - The `validate` method returns `UNKNOWN` by default.
  - Tests passed.
  - No classification logic was implemented, and no runtime behavior was changed.
- **Phase 6 Step 2A: Compiler-Only Logic (Implementation)**
  - Implemented the first slice of compiler-driven error classifications (`INVALID_ACTION_ARRAY`, `INVALID_MULTIPLE_ACTIONS`, `INVALID_FILE_CONTENT_PAIRING`) inside `BundleSemanticValidator`.
  - Added unit tests, which passed.
  - No consumers were migrated, and no old helpers were modified.
  - Shape-driven classification was not implemented.
  - Runtime behavior is unchanged.
- **Phase 6 Step 2B.1: Shape-Driven Logic (Implementation)**
  - Implemented the `INTENT_ACTION_BUNDLE` shape classification in `BundleSemanticValidator`.
  - Added unit tests, which passed.
  - No consumers were migrated, and no other shape logic was implemented.
  - Runtime behavior is unchanged.
- **Phase 6 Step 2B.2: Shape-Driven Logic (Implementation)**
  - Implemented the `READONLY_ACTION_BATCH_CANDIDATE` shape classification in `BundleSemanticValidator`.
  - Added unit tests, which passed.
  - No consumers were migrated, and no other shape logic was implemented.
  - Runtime behavior is unchanged.
- **Phase 6 Step 2B.3: Shape-Driven Logic (Implementation)**
  - Implemented the `NO_BUNDLE_SHAPE` classification for the `INTENT_ONLY` shape in `BundleSemanticValidator`.
  - Added unit tests, which passed.
  - No consumers were migrated, and no other shape logic was implemented.
  - Runtime behavior is unchanged.
- **Phase 6 Step 2C: Parity Testing (Implementation)**
  - Created `tests/test_bundle_semantic_validator_parity.py` to prove behavioral equivalence for all implemented classifications.
  - Parity tests cover Step 2A (error-code) and Step 2B (shape) mappings, including precedence and fallback cases.
  - All tests passed.
  - No production code was changed, and no consumers were migrated.
  - Runtime behavior is unchanged.
- **Phase 6 Step 3: First Consumer Migration (Implementation)**
  - Migrated `ResponsePipelinePrevalidationMixin._reject_compiler_invalid_atomic_bundle_before_transition` to use `BundleSemanticValidator`.
  - Added `tests/test_response_pipeline_prevalidation.py` to prove exact behavior preservation.
  - All tests passed, and runtime behavior is unchanged.
  - No other consumers were migrated.
- **Phase 6: Bundle Semantic Validation Pass (Complete)**
  - The `BundleSemanticValidator` was created, implemented with compiler-only logic (error-code and shape-driven), and verified with parity tests.
  - The first, lowest-risk consumer was migrated.
  - The review of the next consumer concluded that `ActionPolicy`/`segments`-dependent logic should be deferred, and Phase 6 is now complete.
- **Post-Phase 6 Planning Review**
  - A review of next phase candidates was conducted, comparing `ActionPolicy`-dependent bundle validation, plan-first execution, and visible text semantics.
  - **Recommendation**: Proceed with a new phase focused on `ActionPolicy`-dependent bundle validation as the most logical continuation of the bundle validation thread.
  - The old "Phase 7: Plan-First Bundle Execution" will be deferred and re-numbered to Phase 8.
- **Phase 7: ActionPolicy-Dependent Bundle Validation (Design)**
  - The design for refactoring `ActionPolicy`-dependent bundle validation logic is approved.
  - Implementation is authorized for Step 2 (characterization tests) only.
- **Phase 7 Step 2: Characterization Tests (Implementation)**
  - Added characterization tests to `tests/test_action_policy.py` and `tests/test_response_pipeline_prevalidation.py`.
  - The tests lock down the existing behavior of `ActionPolicyHandler.validate_atomic_bundle_action` and `ResponsePipelinePrevalidationMixin._reject_invalid_atomic_bundle_before_transition`.
  - All tests passed.
  - No production code was changed, and no runtime behavior was changed.

## Known Authority Boundaries

- **Compiler**: Authoritative for precise, structural diagnostics. A compiler-`INVALID` response must never be dispatched.
- **Runtime**: Authoritative for all semantic and policy decisions (e.g., `ActionPolicy`, evidence sufficiency, final answer correctness).
- **Compatibility Shim**: `ResponseSemantics.has_any_action_proposal` is a protected compatibility helper for detecting action-like content for recovery purposes. It is not dispatch authority.

## Current Known Risks

- **Mixed Authority**: The response pipeline still consumes a mix of legacy parser fields and new compiler-derived data.
- **Implicit Semantics**: Many runtime decisions still rely on fragile regex-based helpers.
- **Scope Creep**: The `history.py` refactor is explicitly blocked.

## Next Intended Step

- Review characterization test results and decide whether to approve Phase 7 Step 3 (Typed Result Introduction).

## Test Status

- All tests are currently passing.
- Key test contracts are documented in `test-contracts.md`.
