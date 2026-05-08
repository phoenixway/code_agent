# Current Refactor State: Semantic Runtime Migration

This document is the single source of truth for the current state of the Semantic Runtime Migration refactor.

## Current Phase

- **Phase**: Phase 8 Step 4K: First Consumer Migration (Design)
- **Status**: Complete.
- **Next Step**: Phase 8 Step 4L: First Consumer Migration (Implementation), pending explicit approval.
- **Boundary**: Consumer migration remains blocked. Production behavior remains unchanged.

## Step 4I Parity Matrix

| `TerminalAnswerKind` | Implemented in classifier? | Source type | Legacy parity logging available? | Consumer migration status | Remaining risk / deferred notes |
|---|---|---|---|---|---|
| `LEAKED_SYSTEM_RESULT` | Yes | `legacy_compatible_rule` | Yes | Blocked | Regex-compatible rule only; classifier remains shadow-only. |
| `INVALID_OR_TRUNCATED_TERMINAL_TEXT` | Yes | `legacy_compatible_rule` | Yes | Blocked | Depends on legacy plaintext-completion heuristic; no policy migration. |
| `INTERNAL_SUMMARY_LIKE_TEXT` | Yes | `runtime_policy` | Yes | Blocked | Caller-computed boolean flag; no stateful runtime objects enter classifier. |
| `PRE_ACTION_VISIBLE_TEXT_WITH_ACTION` | Yes | `compiler_fact` | No dedicated legacy parity kind | Blocked | Compiler-fact classification exists, but no consumer migration is approved. |
| `INTENT_COMPLETE_WITH_VISIBLE_TEXT` | Yes | `compiler_fact` | No dedicated legacy parity kind | Blocked | Structural fact only; runtime final-answer policy remains separate. |
| `CHECKPOINT_WITH_VISIBLE_TEXT` | Yes | `compiler_fact` | No dedicated legacy parity kind | Blocked | Board/checkpoint consumers are not migrated. |
| `CHECKPOINT_ONLY` | Yes | `compiler_fact` | No dedicated legacy parity kind | Blocked | Shadow signal only; no board consumer migration. |
| `PLAINTEXT_TERMINAL_ANSWER` | Yes | `compiler_fact` | Yes | Blocked | Classifier output is not dispatch or stop authority. |
| `NO_VISIBLE_TEXT` | Yes | `compiler_fact` | Indirectly | Blocked | Fallback structural case only; no consumer authority changes. |
| `UNKNOWN` | Yes | `fallback` | Indirectly | Blocked | Safe shadow fallback for non-matching cases. |

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
- **Phase 7: ActionPolicy-Dependent Bundle Validation (Complete)**
  - The refactor of `ActionPolicy`-dependent bundle validation logic is complete.
  - **Step 2**: Added characterization tests to lock down existing behavior.
  - **Step 3A**: Created typed result scaffolding (`AtomicBundlePolicyResultKind`, `AtomicBundleActionValidationResult`).
  - **Step 3B**: Refactored `ActionPolicyHandler` producer to return the typed result while preserving legacy `ok`/`reason`/`details` fields.
  - **Step 4**: Migrated `ResponsePipelinePrevalidationMixin` consumer to use `result.kind` for branching, with a fallback for legacy `reason` strings.
  - The closure review concluded that cleanup of legacy `reason`/`details` fields is deferred.
  - Runtime behavior is unchanged.
- **Phase 8: Visible Text & Terminal Answer Semantics (Design)**
  - This phase has been opened to clarify authority for visible text and terminal answer semantics.
  - **Step 1 (Inventory)**: The design-only inventory of current behaviors is complete.
  - The scope includes terminal plaintext completion, intent completion with visible answer, and memory/subgoal checkpoint + text combinations.
  - Implementation is not authorized until a design is approved.
- **Phase 8 Step 2: Characterization Tests (Implementation)**
  - Added characterization tests to lock down the exact behavior of all identified components and scenarios related to visible text and terminal answers.
  - Key behaviors characterized include compiler shape analysis, `ResponseSemantics.is_plaintext_answer_path`, `looks_like_leaked_system_result`, `terminal_plaintext_completion_status`, and `_is_internal_summary_instead_of_final_answer`.
  - Tests were added/expanded in `tests/test_visible_text_terminal_answer_semantics.py`, `tests/test_output_recovery.py`, and `tests/test_terminal_plaintext_completion_guard.py`.
  - All tests passed, and no production code was changed. Runtime behavior is unchanged.
- **Phase 8 Step 3: Typed Model Scaffolding (Design)**
  - The design review of characterization test results is complete.
  - The review concluded that the ambiguity of current signals (e.g., `compiler_shape=PLAINTEXT_ONLY` for multiple distinct scenarios) justifies introducing a typed result model.
  - The design for a `TerminalAnswerKind` enum and `TerminalAnswerSemanticResult` dataclass is approved for scaffolding only.
  - Implementation of the classifier logic and migration of consumers is not authorized.
- **Phase 8 Step 3A: Typed Model Scaffolding (Implementation)**
  - Created `modules/agent/orchestration/responses/terminal_answer_models.py` with `TerminalAnswerKind` enum and `TerminalAnswerSemanticResult` dataclass.
  - Created `tests/test_terminal_answer_models.py` with unit tests for the new types.
  - All tests passed.
  - No `TerminalAnswerClassifier` was created, no classification logic was implemented, and no consumers were migrated.
  - Runtime behavior is unchanged.
- **Phase 8 Step 4A: Compiler/Runtime Semantics Tag Coverage Review (Design-Only)**
  - The design-only review of compiler/runtime semantics tag coverage is complete.
  - The review concluded that `RuntimeProtocolSemantics` lacks sufficient structural facts to reliably build the `TerminalAnswerClassifier`.
  - Key gaps include ambiguous shapes (`PLAINTEXT_ONLY`) and missing recognition of subgoal tags with visible text.
  - Recommendation: Defer classifier implementation and proceed with a design phase to add the missing structural facts.
- **Phase 8 Step 4C: Compiler Fact Scaffolding (Design)**
  - The design for adding new structural facts to the compiler and `RuntimeProtocolSemantics` is complete.
  - The design proposes new facts (`has_subgoal_tags`, `has_memory_tags`, etc.) and compiler shape improvements to provide unambiguous signals for the future `TerminalAnswerClassifier`.
  - Implementation is not authorized.
- **Phase 8 Step 4D: New Fact Characterization Tests (Design)**
  - The design for characterization tests for the new structural facts and shape improvements is complete.
  - The design specifies tests for `has_subgoal_tags`, `has_memory_tags`, `has_memory_checkpoint`, and improved compiler shapes (`PURE_PLAINTEXT`, `SUBGOAL_WITH_TEXT`, `PRE_ACTION_TEXT_AND_ACTION`).
  - Implementation is not authorized until Step 4D.1.
- **Phase 8 Step 4D.1: New Fact Characterization Test Implementation**
  - Implemented golden characterization tests in `tests/test_compiler_structural_facts.py` to specify the target behavior for new compiler facts and shapes.
  - The tests were marked `xfail` and were expected to fail until Step 4E was complete.
  - No production code was changed. Runtime behavior is unchanged.
- **Phase 8 Step 4E: Compiler/Runtime Fact Implementation (Complete)**
  - Implemented compiler, parser, and IR changes to support new structural facts (`has_memory_tags`, `has_subgoal_tags`, `has_memory_checkpoint`, `visible_text_source`) and improved shapes (`PURE_PLAINTEXT`, `SUBGOAL_WITH_TEXT`, `PRE_ACTION_TEXT_AND_ACTION`, `INTENT_COMPLETE_WITH_TEXT`).
  - The work was confined to the compiler/parser/IR layer. No consumers were migrated, no `TerminalAnswerClassifier` was implemented, and no new runtime regex fact detection was added.
- **Phase 8 Step 4F: Shadow Sufficiency / Parity Review (Complete)**
  - A design-only review concluded that the structural facts from Step 4E are sufficient to proceed with the design of a shadow-mode `TerminalAnswerClassifier`.
  - A new test file, `tests/test_terminal_answer_fact_sufficiency.py`, was added to prove sufficiency without changing production code.
  - The design of the classifier is now unblocked, but implementation and consumer migration remain blocked.
- **Phase 8 Step 4B (Redux): TerminalAnswerClassifier Shadow Mode Design (Complete)**
  - The design for the `TerminalAnswerClassifier` and its shadow-mode validation plan is complete and documented in `docs/architecture/visible-text-terminal-answer-semantics-design.md`.
  - This is a design-only step. No production code was changed.
  - Implementation of the classifier is not authorized until Step 4G is approved.
  - No runtime consumers were migrated, and no dispatch or policy behavior was intentionally changed.
- **Phase 8 Step 4G: TerminalAnswerClassifier Shadow Implementation (Complete)**
  - Implemented the `TerminalAnswerClassifier` as an isolated, shadow-safe component in `modules/agent/orchestration/responses/terminal_answer_classifier.py`.
  - The implementation follows the design from Step 4B Redux, but defers branches that depend on legacy helpers.
  - Unit tests were added in `tests/test_terminal_answer_classifier.py` to cover the implemented compiler-fact branches.
  - No runtime shadow execution hook was added, and no consumers were migrated.
  - No dispatch, policy, or user-visible behavior was changed.
- **Phase 8 Step 4H: Shadow Wiring / Diagnostic Logging (Complete)**
  - The `TerminalAnswerClassifier` is now wired into the `ResponsePipelinePrevalidationMixin` in shadow mode.
  - It runs after the `RuntimeProtocolSemantics` snapshot is created and logs its classification as a shadow signal.
  - The actual comparison against legacy logic is deferred to a later step.
  - The call is protected by an exception handler to prevent it from affecting runtime behavior.
  - No consumers were migrated, and no production behavior was changed.
- **Phase 8 Step 4I: Parity Matrix / Legacy Helper Integration (Complete)**
  - **Part 1 (Complete)**: Implemented a diagnostic helper in `ResponsePipelinePrevalidationMixin` to compute a `legacy_kind` for terminal answers. The shadow logging now records both `classifier_kind` and `legacy_kind`, and computes `is_match`.
  - **Part 2 (Complete)**: Integrated the `LEAKED_SYSTEM_RESULT` legacy rule into the `TerminalAnswerClassifier`.
  - **Part 3 (Complete)**: Integrated the `INVALID_OR_TRUNCATED_TERMINAL_TEXT` legacy rule into the `TerminalAnswerClassifier`.
  - **Part 4 (Complete)**: Integrated the `INTERNAL_SUMMARY_LIKE_TEXT` legacy rule into the `TerminalAnswerClassifier` using a caller-computed boolean flag in shadow mode.
  - A Step 4I parity matrix is now documented for all `TerminalAnswerKind` classifications.
  - All approved Step 4I legacy helper branches are now integrated in shadow mode.
  - No production behavior was changed.
- **Phase 8 Step 4J: Consumer Migration Design Gate (Complete)**
  - A design-only review of the Step 4I parity matrix and shadow-log evidence was completed.
  - The review concluded that `LEAKED_SYSTEM_RESULT` is a safe candidate for a first, narrow consumer migration.
  - A new design-only step, `Phase 8 Step 4K`, was proposed to formally design this migration.
  - Consumer migration remains blocked, and no production behavior was changed.
- **Phase 8 Step 4K: First Consumer Migration (Design) (Complete)**
  - The design for migrating the `is_leaked_system_result` check in `ResponsePipelineStagesMixin` to use the `TerminalAnswerClassifier` is complete.
  - The design specifies how to attach the classifier's result to `parsed_output` and migrate the consumer to read the typed `kind`.
  - A future implementation step, `Phase 8 Step 4L`, was proposed.
  - This was a design-only step. No production code was changed, and consumer migration remains blocked.
## Known Authority Boundaries

- **Compiler**: Authoritative for precise, structural diagnostics. A compiler-`INVALID` response must never be dispatched.
- **Runtime**: Authoritative for all semantic and policy decisions (e.g., `ActionPolicy`, evidence sufficiency, final answer correctness).
- **Compatibility Shim**: `ResponseSemantics.has_any_action_proposal` is a protected compatibility helper for detecting action-like content for recovery purposes. It is not dispatch authority.

## Current Known Risks

- **Mixed Authority**: The response pipeline still consumes a mix of legacy parser fields and new compiler-derived data.
- **Implicit Semantics**: Many runtime decisions still rely on fragile regex-based helpers.
- **Scope Creep**: The `history.py` refactor is explicitly blocked.

## Next Intended Step

- **Phase 8 Step 4L: First Consumer Migration (Implementation)**: Implement the approved design from Step 4K to migrate the `is_leaked_system_result` check in `ResponsePipelineStagesMixin`. This step is not yet authorized and requires explicit approval to begin.

## Test Status

- All tests are currently passing.
- Key test contracts are documented in `test-contracts.md`.
