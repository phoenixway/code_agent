# Current Refactor State: Semantic Runtime Migration

This document is the single source of truth for the current state of the Semantic Runtime Migration refactor.

## Current Phase

- **Phase**: Phase 10 Step 18: First True Authority Candidate — Legacy-Derived Typed Result Primary With Legacy Fallback
- **Status**: Complete.
- **Next Step**: Phase 10 Step 19: Extend Typed Primary to Remaining Legacy-Derived Memory Branches.
- **Boundary**: The checkpoint parity bridge remains diagnostic-only. Legacy board handlers still own commit behavior, the prepass compiler analysis remains observational, and `_apply_compiler_diagnosis` remains the effectful classification-stage path that recomputes on normalized response.

## Step 4I Parity Matrix

| `TerminalAnswerKind` | Implemented in classifier? | Source type | Legacy parity logging available? | Consumer migration status | Remaining risk / deferred notes |
|---|---|---|---|---|---|
| `LEAKED_SYSTEM_RESULT` | Yes | `legacy_compatible_rule` | Yes | Narrow consumer migrated | Typed primary signal with legacy fallback remains in place. |
| `INVALID_OR_TRUNCATED_TERMINAL_TEXT` | Yes | `legacy_compatible_rule` | Yes | First narrow consumer migrated | Legacy fallback remains required because the classifier uses `candidate_text` / `PURE_PLAINTEXT`, while the legacy guard uses `raw_response`. |
| `INTERNAL_SUMMARY_LIKE_TEXT` | Yes | `runtime_policy` | Yes | Narrow consumer migrated | Typed result is a primary hint only; legacy runtime-policy helper remains the confirmation/fallback path. |
| `PRE_ACTION_VISIBLE_TEXT_WITH_ACTION` | Yes | `compiler_fact` | No dedicated legacy parity kind | Blocked | Compiler-fact classification exists, but no consumer migration is approved. |
| `INTENT_COMPLETE_WITH_VISIBLE_TEXT` | Yes | `compiler_fact` | No dedicated legacy parity kind | Blocked | Structural fact only; runtime final-answer policy remains separate. |
| `CHECKPOINT_WITH_VISIBLE_TEXT` | Yes | `compiler_fact` | No dedicated legacy parity kind | Blocked | Board/checkpoint consumers are not migrated. |
| `CHECKPOINT_ONLY` | Yes | `compiler_fact` | No dedicated legacy parity kind | Blocked | Shadow signal only; no board consumer migration. |
| `PLAINTEXT_TERMINAL_ANSWER` | Yes | `compiler_fact` | Yes | No-go for current migration | Remaining consumers sit on final-answer, intent-completion, visible-text, and stop-gate authority boundaries. |
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
  - The design specifies a behavior-preserving migration: typed result primary signal plus legacy fallback.
  - A strict replacement of `is_leaked_system_result(response)` with `TerminalAnswerKind.LEAKED_SYSTEM_RESULT` is explicitly forbidden for Step 4L.
  - The existing outer guard `not self.semantics.has_any_action_proposal(parsed_output, parsed_action_count)` must be preserved.
  - The legacy accessor remains the production fallback when the typed result is absent or when the typed result is present but not `LEAKED_SYSTEM_RESULT`.
  - The classifier is not yet sole authority for leaked-system-result detection.
  - A future implementation step, `Phase 8 Step 4L`, was proposed.
  - This was a design-only step. No production code was changed, and consumer migration remains blocked.
- **Phase 8 Step 4L: First Consumer Migration (Implementation) (Complete)**
  - The first narrow consumer migration is now complete.
  - Migrated consumer: the leaked-system-result guard in `ResponsePipelineStagesMixin`.
  - The implementation uses the typed `TerminalAnswerClassifier` result as the primary signal.
  - The legacy `is_leaked_system_result(response)` accessor remains the production fallback.
  - The fallback applies both when the typed result is absent and when it is present but not `LEAKED_SYSTEM_RESULT`.
  - The existing outer guard `not self.semantics.has_any_action_proposal(parsed_output, parsed_action_count)` is preserved.
  - `_run_terminal_answer_classifier_shadow` was not renamed.
  - No other consumers were migrated.
  - `TerminalAnswerClassifier` is still not sole authority.
  - Production behavior is intended to remain equivalent.
  - Tests passed.
## Known Authority Boundaries

- **Compiler**: Authoritative for precise, structural diagnostics. A compiler-`INVALID` response must never be dispatched.
- **Runtime**: Authoritative for all semantic and policy decisions (e.g., `ActionPolicy`, evidence sufficiency, final answer correctness).
- **Compatibility Shim**: `ResponseSemantics.has_any_action_proposal` is a protected compatibility helper for detecting action-like content for recovery purposes. It is not dispatch authority.

## Current Known Risks

- **Mixed Authority**: The response pipeline still consumes a mix of legacy parser fields and new compiler-derived data.
- **Implicit Semantics**: Many runtime decisions still rely on fragile regex-based helpers.
- **Scope Creep**: The `history.py` refactor is explicitly blocked.

## Next Intended Step

- **Phase 10 Step 5: First Board/Checkpoint Consumer Migration (Design)**
  - Design the first narrow, behavior-preserving migration of a board/checkpoint consumer to use the newly available compiler facts.
  - This is a design-only step.

## Phase 9 Step 1 Outcome

- **Conclusion**
  - The next safe refactor slice is bundle/action execution, not final-answer semantics.
  - The current runtime is already partially plan-shaped, but not truly plan-first end to end.
  - The design gate is complete and the current inventory is documented in `docs/architecture/plan-first-bundle-execution-design.md`.

- **Current execution path**
  - `ResponsePipelinePrevalidationMixin._apply_compiler_diagnosis(...)` populates compiler metadata and IR on `ParsedModelOutput`.
  - `ResponsePipelineStagesMixin._run_post_classification_stage(...)` still owns orchestration, policy handoff, and late `ExecutionPlan` creation.
  - `DispatchPipeline.run_iteration(...)` consumes `execution_plan` only for metadata and pre-action text, but still dispatches raw `segments`.

- **Authority split to preserve**
  - Compiler / IR owns structure.
  - `ActionPolicyHandler` owns permission and runtime-policy validation.
  - `DispatchPipeline` owns side effects.
  - `ResponsePipeline` orchestrates, but should not remain the long-term source of dispatch semantics.

- **Existing Phase 6 / 7 decisions to preserve**
  - Only validated execution plans may authorize runtime mutation or dispatch.
  - Compiler-owned bundle structure must stay separate from runtime-owned permission checks.
  - Legacy compatibility shims remain acceptable where parity is not yet proven.

- **Remaining legacy execution dependencies**
  - `DispatchPipeline` still executes raw `segments`.
  - `ActionPolicyHandler` still retains `segments` fallback when IR action ops are absent.
  - `ResponsePipelineOutcome.dispatch_ready(...)` still carries both `segments` and `execution_plan`.
  - `DispatchOutcomeHandler` still infers committed actions from processed segments rather than from a fully authoritative plan/commit contract.

## Phase 9 Step 2 Outcome

- **Current producer / consumer flow**
  - `ResponsePipelineStagesMixin._build_execution_plan(...)` is the current producer.
  - It is invoked late, only on `dispatch_ready`, after recovery and `ActionPolicy`.
  - `ParsedModelOutput.compiler_ir` is already available earlier from
    `ResponsePipelinePrevalidationMixin._apply_compiler_diagnosis(...)`.
  - `DispatchPipeline.run_iteration(...)` consumes the plan only for pre-action text
    and trace metadata; raw `segments` still drive actual dispatch side effects.

- **Minimal contract**
  - Required `ExecutionPlan` fields for the first migrated slice:
    `shape`, `transaction_kind`, `action_effects`, `output_effects`,
    `bundle_validated`, `transition_applied`,
    `before_active_intent_id`, `after_active_intent_id`.
  - Compatibility-only / observational fields remain allowed:
    `state_effects`, `active_intent_unchanged`, `action_dispatched`.
  - Compiler IR is the source of action payload summaries and pre-action text.
  - Runtime state remains the source of before/after intent ids.

- **First migration candidate**
  - One narrow single-action dispatch-ready slice:
    atomic intent+action bundle and equivalent single-action dispatch-ready flow
    where compiler IR already provides exactly one authoritative `ActionOpIR`.
  - This is the lowest-risk path because:
    - IR already carries the action payload
    - `ActionPolicy` already consumes IR first
    - current `ExecutionPlan` already models this path
    - multi-action readonly batches remain out of scope

- **Fallback strategy**
  - `ExecutionPlan` becomes the primary producer-side contract only for the migrated
    slice.
  - `segments` fallback remains required whenever IR action ops are absent, the path
    is outside the migrated slice, or parity is not yet proven.
  - No path may dispatch different actions just because a plan exists.

- **Tests required before implementation**
  - characterization tests for current `ExecutionPlan` fields
  - plan-vs-segment parity tests for the first migrated slice
  - fallback coverage for non-migrated paths
  - no-dispatch-on-invalid coverage
  - pre-action-text parity coverage

## Phase 9 Step 3 Outcome

- **Characterization coverage added**
  - current `ExecutionPlan` field population is now locked down in tests
  - compiler IR plan-first candidate fields are characterized
  - plan-vs-segment action-summary parity is covered for the first migrated single-action bundle path
  - segment-based fallback behavior is covered when no authoritative plan exists
  - no-dispatch-plan expansion on invalid paths remains covered

- **Boundary**
  - No production behavior changed.
  - No dispatch behavior changed.
  - No `ActionPolicy` authority changed.

## Phase 9 Step 4 Outcome

- **Decision**
  - Step 5 should implement a narrow dispatch bridge/helper first, not a broad
    producer rewrite and not a full consumer replacement.

- **Chosen first migrated slice**
  - single-action dispatch-ready path only
  - compiler IR contains exactly one authoritative `ActionOpIR`
  - `ActionPolicy` has already allowed the action
  - `ExecutionPlan` is present and matches the current characterized slice

- **Why this is the safest slice**
  - current producer behavior is already characterized
  - plan-vs-segment parity exists for this path
  - `ActionPolicy` already consumes compiler IR first
  - side-effect behavior can stay behind explicit segment fallback

- **Where fallback must remain**
  - when `execution_plan` is absent
  - when `compiler_ir` is absent
  - when IR action count is not exactly one
  - when dispatch input cannot be derived losslessly
  - on all non-migrated paths

- **Behavior drift definition**
  - different action count, order, payload, path, command, or file content
  - any bypass of `ActionPolicy`
  - changed pre-action-text emission
  - changed post-dispatch reconstruction/outcome behavior
  - dispatch on a path that currently falls back or rejects

- **Step 5 scope**
  - add a narrow bridge/helper at the dispatch boundary
  - keep `ResponsePipelineStagesMixin._build_execution_plan(...)` as the current producer
  - keep `ResponsePipelineOutcome.dispatch_ready(...)` carrying both `segments`
    and `execution_plan`
  - keep segment dispatch as the compatibility fallback

## Phase 9 Step 5A Outcome

- **Implemented**
  - A narrow dispatch-boundary parity probe was added for the eligible
    single-action dispatch-ready slice.
  - The probe inspects:
    - `iteration.execution_plan`
    - `iteration.parsed_output.compiler_ir`
    - current `segments`
  - The probe only marks the path eligible when:
    - `execution_plan` is present
    - `compiler_ir` is present
    - IR has exactly one authoritative `ActionOpIR`
    - payload parity with the segment-derived action is exact
    - action-effect summary parity is exact
    - no unsupported action shape is present

- **What it does not do**
  - It does not produce a new plan-authoritative dispatch input.
  - It returns the existing `segments`.
  - Actual dispatch remains segment-driven.
  - It is an instrumentation/parity bridge, not yet a plan-authoritative
    dispatch bridge.

- **Fallback preserved**
  - `segments` remain the explicit production fallback for:
    - no `execution_plan`
    - no `compiler_ir`
    - zero or multiple IR action ops
    - payload mismatch
    - unsupported action shape
    - any uncertainty

- **Behavior boundary**
  - No dispatch side effects changed.
  - No `ActionPolicy` authority changed.
  - No pre-action text emission changed.
  - No post-dispatch reconstruction or outcome handling changed.
  - The existing segment dispatcher contract remains intact.

## Phase 9 Step 5B Outcome

- **Current segment dispatch contract documented**
  - `DispatchPipeline._dispatch_segments(...)` still calls
    `dispatcher.dispatch_segments(segments, state)`.
  - The dispatcher expects an ordered segment list with:
    - `thought` segments
    - `text` segments
    - `action` segments where `content` is a dict payload
  - Processed-segment expectations in dispatch outcome handling remain unchanged.

- **IR-derived candidate contract chosen**
  - Proposed internal type:
    `PlanDispatchCandidate`
  - Required fields:
    - `action_type`
    - `payload`
    - `action_summary`
    - `source="compiler_ir"`
    - `matched_segment_index`
  - Optional compatibility fields may include compiler shape, transaction kind,
    and pre-action text.

- **Losslessness rules**
  - Candidate payload must equal the segment action payload exactly.
  - Candidate summary must equal `ExecutionPlan.action_effects[0]`.
  - Exactly one IR action op and exactly one segment action are required.
  - File-content-backed shapes and multi-action paths remain excluded.
  - Unsupported shapes must fall back.

- **Step 5C shape**
  - Build the candidate from IR/plan for the eligible slice.
  - Compare it against the current segment-derived action.
  - If the match is exact, keep routing through the existing dispatcher contract.
  - Keep segment fallback explicit and intact.

## Phase 9 Step 5C Outcome

- **Implemented**
  - The first internal IR-derived dispatch candidate surface is now implemented.
  - Working internal type:
    `PlanDispatchCandidate`
  - Implemented candidate fields:
    - `action_type`
    - `payload`
    - `action_summary`
    - `source="compiler_ir"`
    - `matched_segment_index`
    - optional compatibility fields:
      `compiler_shape`, `transaction_kind`, `pre_action_text`

- **Eligibility remains narrow**
  - Candidate builds only for the eligible single-action slice.
  - File-content-backed and multi-action paths still produce no candidate.
  - Payload mismatch, summary mismatch, and unsupported shapes still fall back.

- **Behavior boundary**
  - Actual dispatch remains segment-driven.
  - No dispatch side effects changed.
  - No `ActionPolicy` authority changed.
  - No pre-action text behavior changed.
  - No post-dispatch outcome handling changed.

## Phase 9 Step 5D Outcome

- **Decision**
  - It is not yet safe to pass `PlanDispatchCandidate` directly into the
    dispatcher path.

- **Why**
  - `ActionDispatcher.dispatch_segments(...)` still expects concrete segment objects.
  - `DispatchOutcomeHandler` still reconstructs and interprets `processed_segs`.
  - `ExecutionCommit` still derives committed action counts from processed action segments.
  - A direct candidate-driven dispatch path would widen the migration beyond the
    current narrow slice.

- **Option review**
  - Option A: candidate as metadata/diagnostic only while dispatch stays
    segment-driven: recommended.
  - Option B: candidate-derived synthetic segment adapter: deferred.
  - Option C: direct dispatcher candidate input: no-go for now.

- **Recommended next step**
  - `Phase 9 Step 5E: Candidate Metadata Bridge Implementation`
  - Keep actual dispatch segment-driven.
  - Preserve `processed_segs` / dispatch-outcome expectations.
  - Preserve all existing fallback points.

## Phase 9 Step 5E Outcome

- **Implemented**
  - `PlanDispatchCandidate` is now surfaced as metadata/bridge evidence on the
    eligible single-action path.
  - Candidate metadata remains diagnostic only.
  - Actual dispatcher input remains the original `segments` list/object.

- **Coverage**
  - Eligible single-action path surfaces candidate metadata.
  - Non-eligible paths surface no candidate metadata.
  - Dispatcher still receives the original segment list/object.
  - Existing processed-segment and outcome behavior is unchanged.

- **Behavior boundary**
  - No dispatch side effects changed.
  - No `ActionPolicy` authority changed.
  - No fallback was removed or narrowed.
  - Actual dispatch remains segment-driven.

## Phase 9 Step 5F Outcome

- **Conclusion**
  - **NO-GO** for a synthetic segment adapter in the immediate next step.
  - `PlanDispatchCandidate` metadata bridge is complete and safe.
  - Actual dispatch should remain segment-driven for now.
  - Candidate-driven dispatcher input is not approved.
  - Synthetic segments are not approved.

- **Rationale**
  - Dispatcher input identity and concrete segment objects still matter.
  - `processed_segs`, `DispatchOutcomeHandler`, and `ExecutionCommit` remain segment-shaped.
  - The metadata bridge already provides plan-first evidence without side-effect risk.
  - Adapter work would be a separate higher-risk migration requiring its own design/test slice.

- **Slice status**
  - Phase 9 Step 5A-5F bridge sub-slice is complete.

- **Recommended next step**
  - `Phase 10 Step 1: Board/Checkpoint Consumer Slice Preflight`

## Phase 9 Step 7 Outcome

- **Conclusion**
  - The review of the Phase 9 plan-first dispatch boundary work is complete.
  - The current slice (Steps 5A-6D) successfully introduced a diagnostic metadata bridge for the single-action dispatch path.
  - However, the evidence is not sufficient to safely proceed with candidate-driven dispatch or a synthetic segment adapter. The side-effect boundary remains high-risk.
  - The plan-first dispatch boundary slice is now closed for now. Actual dispatch remains segment-driven.
  - The next safest slice is to address the deferred board/checkpoint consumers, which is a narrower and lower-risk area than dispatch side effects or final-answer authority.

## Phase 10 Step 1: Board/Checkpoint Consumer Slice Preflight (Complete)

- **Conclusion**
  - The preflight review of board/checkpoint consumers is complete and documented in `docs/architecture/board-checkpoint-consumer-slice-design.md`.
  - The review identified a major architectural blocker: the `ResponsePipeline` executes the board/checkpoint stage (`_run_checkpoint_stage`) *before* the main classification stage (`_run_classification_stage`).
  - This pipeline ordering prevents the primary consumers (`MemoryBoardStageHandler`, `PlanBoardStageHandler`) from accessing typed semantic results (e.g., from the `TerminalAnswerClassifier`) and other post-classification runtime facts, as they have not been computed yet.
  - **NO-GO** for immediate consumer migration. Any migration is blocked until the pipeline is safely reordered.
- **Recommendation**
  - The next step is `Phase 10 Step 2: Board/Checkpoint Characterization Tests`. This is a test-only step to lock down the behavior of the board handlers and their pipeline interaction before any reordering is designed.
  - After characterization, a new `Phase 10 Step 3: Pipeline Reordering Design` will be required.

## Phase 10 Step 2: Board/Checkpoint Characterization Tests (Complete)

- **Conclusion**
  - Added orchestration characterization tests to `tests/test_response_pipeline_stages.py` to lock down the orchestration behavior of `_run_checkpoint_stage`.
  - The tests cover how the pipeline behaves for `memory_checkpoint_only`, `memory_checkpoint_and_text`, and `plan_checkpoint_only` outcomes from mocked board handlers.
  - This was a test-only step. No production code was changed.
  - Characterization of the internal parsing and commit logic of the board handlers themselves is deferred until after the pipeline is reordered, as their migration is blocked.

## Phase 10 Step 3: Pipeline Reordering Design (Complete)

- **Conclusion**
  - The design for unblocking the board/checkpoint consumer migration is complete.
  - A full pipeline reordering was rejected as too high-risk.
  - The chosen design is a lower-risk **Early Structural Diagnosis Prepass**. This involves extracting a pure, side-effect-free helper for structural analysis and then using it in a new prepass before the checkpoint stage.
  - The prepass is strictly structural and must not include side effects like terminal-answer classification or `invalid_kind` mutation.
  - This makes `RuntimeProtocolSemantics` available to the checkpoint stage for future migration, without changing the behavior of any existing stage.
  - This was a design-only step. No production code was changed.

## Phase 10 Step 4: Pure Structural Diagnosis Extraction + Early Prepass (Complete)

- **Conclusion**
  - The Early Structural Diagnosis Prepass has been implemented as a behavior-preserving refactor.
  - A pure `_run_structural_diagnosis_prepass` helper now runs before `_run_checkpoint_stage`.
  - The resulting `compiler_analysis` is attached to `CheckpointStageState` for observation and future migration only.
  - `_apply_compiler_diagnosis` was not refactored into a wrapper around the pure helper. It remains the existing effectful classification-stage path and recomputes its own diagnosis on the normalized response.
  - For safety, `_run_classification_stage` does *not* reuse the prepass analysis. Reuse is deferred to a future parity/reuse step.
  - Compiler-derived structural facts are now available to the checkpoint stage for future migration.
  - No board handlers were migrated, and no production behavior was changed.

## Phase 10 Step 4B: Structural Prepass Parity / Reuse Decision (Complete)

- **Conclusion**
  - A design-only review was conducted to assess the safety of reusing the prepass analysis (from the raw response) in the classification stage (which uses a normalized response).
  - **NO-GO** for reuse at this time. The potential mismatch between raw and normalized responses creates a risk of behavior drift.
  - The prepass analysis remains observational only.
  - `_run_classification_stage` will continue to recompute its own diagnosis on the normalized response.
  - The next step is to design the first consumer migration.

## Phase 10 Step 5: First Board/Checkpoint Consumer Migration (Design) (Complete)

- **Conclusion**
  - The safest first consumer migration is a **structural parity / diagnostic bridge** in the checkpoint stage, not a board commit migration.
  - The chosen first target is prepass-vs-legacy checkpoint parity logging attached to `_run_checkpoint_stage` / `CheckpointStageState` observations.
  - This keeps `MemoryBoardStageHandler` and `PlanBoardStageHandler` fully authoritative for commit behavior, continuation prompts, and checkpoint-only vs checkpoint-and-text/action outcomes.
  - A dedicated board/checkpoint semantic model is **not** required before this first step because the initial implementation should remain observational only.
- **Chosen first implementation shape**
  - Use prepass compiler facts as a secondary signal for checkpoint structure only.
  - Compare compiler/prepass facts against legacy checkpoint observations such as:
    - checkpoint tags present
    - checkpoint marker present
    - checkpoint with visible text
    - checkpoint with action
  - Log parity/mismatch information without changing board commit logic, routing, dispatch, or stop behavior.
  - Keep `_apply_compiler_diagnosis` unchanged and keep classification-stage recomputation on normalized response.
- **No-go items**
  - No authority transfer to `MemoryBoardStageHandler` or `PlanBoardStageHandler`.
  - No board commit parsing replacement.
  - No direct use of prepass analysis to change `memory_checkpoint_only`, `memory_checkpoint_and_text`, `plan_checkpoint_only`, or related flags.
  - No reuse of prepass analysis inside `_run_classification_stage`.
  - No dispatch, final-answer, stop-gate, `ActionPolicy`, parser, or `history.py` changes.
- **Required characterization before later authority transfer**
  - Direct characterization of board handler parsing and commit behavior.
  - Parity tests for checkpoint-only / checkpoint-with-text / checkpoint-with-action observations.
  - Evidence that compiler/prepass facts and handler-visible cleaned response semantics stay aligned across normalization boundaries.
- **Next step**
  - Phase 10 Step 6 should implement **Board/Checkpoint Structural Parity Logging** only.

## Phase 10 Step 6: Board/Checkpoint Structural Parity Logging Implementation (Complete)

- **Conclusion**
  - Diagnostic-only parity logging has been added in `_run_checkpoint_stage`.
  - The new parity bridge compares prepass compiler facts from `CheckpointStageState.compiler_analysis` against legacy board/checkpoint handler outcomes.
  - Logged information includes compiler shape/error metadata, visible-text source when available, action presence/count, checkpoint-like structural facts, legacy outcome categories, parity alignment, and mismatch reason when obvious.
  - Missing compiler analysis is tolerated, and logging failures are swallowed.
- **Authority / fallback**
  - No authority transfer happened.
  - `MemoryBoardStageHandler` and `PlanBoardStageHandler` remain authoritative for parsing, commits, and checkpoint outcome flags.
  - `_run_classification_stage` still recomputes analysis on normalized response and does not reuse prepass analysis.
- **Behavior boundary**
  - No board commit behavior changed.
  - No checkpoint routing behavior changed.
  - No dispatch, final-answer, stop-gate, `ActionPolicy`, parser, or `history.py` behavior changed.
- **Next step**
  - Phase 10 Step 7: Board/Checkpoint Parity Review / First Authority Migration Decision.

## Phase 10 Step 7: Board/Checkpoint Parity Review / First Authority Migration Decision (Complete)

- **Conclusion**
  - **NO-GO** for a first authority migration at this time.
  - The Step 6 parity bridge is sufficient for observability, but not sufficient to replace handler parsing or commit logic.
  - Mismatch reasons from Step 6 must be treated as diagnostic hints only, not as authoritative parity failures.
- **Why authority migration is blocked**
  - `MemoryBoardStageHandler` contains commit-aware logic that is not reduced to structural tag recognition:
    - memory-engine apply results
    - `clean_text` dependence
    - raw-vs-clean visible-text fallback
    - marker-only checkpoint handling
    - checkpoint-only streak behavior
  - `PlanBoardStageHandler` contains planner- and cleanup-aware logic that is not reduced to structural tag recognition:
    - planner extraction/mutation behavior
    - raw-vs-clean action detection
    - visible-text stripping outcomes
    - checkpoint-only vs checkpoint-with-text routing
  - The prepass compiler analysis is on raw response, while handler decisions depend on handler-local cleaned/committed state.
- **Authority boundary**
  - Legacy board handlers remain authoritative.
  - The parity bridge remains diagnostic-only.
  - Compiler/prepass facts remain structural-only observations.
  - `_run_classification_stage` still recomputes diagnosis on normalized response and does not reuse prepass analysis.
- **Next step**
  - Phase 10 Step 8: Direct Board Handler Parsing/Commit Characterization Tests.

## Phase 10 Step 8: Direct Board Handler Parsing/Commit Characterization Tests (Complete)

- **Conclusion**
  - Direct unit-level characterization now exists for both `MemoryBoardStageHandler` and `PlanBoardStageHandler`.
  - The handler tests lock down parsing, cleanup, commit-aware behavior, and checkpoint outcome decisions sufficiently to design a semantic model without guessing.
- **Characterized memory-handler behavior**
  - accepted memory mutations with `clean_text` pass-through
  - rejected/no-op memory result pass-through
  - raw-vs-clean visible-text fallback
  - marker-only checkpoint behavior
  - checkpoint-with-text and checkpoint-with-action outcomes
  - engine-failure fallback behavior
- **Characterized plan-handler behavior**
  - planner unavailable fallback
  - planner extract-error continuation path
  - no-update pass-through and create-count reset
  - checkpoint-with-text and checkpoint-with-action outcomes
  - checkpoint-only continuation path
  - summary print side effect when planner reports applied changes
- **Surprising current behavior**
  - `MemoryBoardStageHandler.apply()` resets the local checkpoint-only streak before incrementing it, so handler-local streak accumulation does not happen across calls by itself.
  - This is now encoded as current behavior, not corrected behavior.
- **Authority boundary unchanged**
  - No production code changed.
  - Legacy board handlers remain authoritative.
  - Compiler/prepass facts remain structural-only observations.
  - The parity bridge remains diagnostic-only.
- **Next step**
  - Phase 10 Step 9: Board/Checkpoint Semantic Model Design.

## Phase 10 Step 9: Board/Checkpoint Semantic Model Design (Complete)

- **Conclusion**
  - The smallest safe typed model is a new observational result layer for board/checkpoint outcomes, separate from `TerminalAnswerClassifier`.
  - Working design name: `BoardCheckpointSemanticResult`.
  - It should represent both:
    - legacy handler outcomes
    - compiler/prepass structural facts
  - It must not transfer authority.
- **Proposed model shape**
  - Companion types:
    - `BoardCheckpointKind`
    - `BoardCheckpointSource`
    - `BoardCheckpointEvidence`
  - Candidate kinds:
    - `NONE`
    - `MEMORY_CHECKPOINT_ONLY`
    - `MEMORY_CHECKPOINT_WITH_TEXT`
    - `MEMORY_CHECKPOINT_WITH_ACTION`
    - `PLAN_CHECKPOINT_ONLY`
    - `PLAN_CHECKPOINT_WITH_TEXT`
    - `PLAN_CHECKPOINT_WITH_ACTION`
    - `MIXED_BOARD_CHECKPOINT`
    - `UNKNOWN`
  - Core fields:
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
    - optional compiler/prepass summary fields
    - optional parity/mismatch fields
- **Authority boundary**
  - The model is not:
    - commit authority
    - planner mutation authority
    - memory-engine authority
    - routing authority
    - dispatch authority
  - It must not replace commit results, mutate checkpoint flags, or drive routing in its first implementation.
- **Next step**
  - Phase 10 Step 10: Board/Checkpoint Semantic Model Skeleton + Shadow Population.

## Phase 10 Step 10: Board/Checkpoint Semantic Model Skeleton + Shadow Population (Complete)

- **Implementation outcome**
  - Added a new observational model file:
    - `modules/agent/orchestration/responses/board_checkpoint_models.py`
  - Added typed model components:
    - `BoardCheckpointKind`
    - `BoardCheckpointSource`
    - `BoardCheckpointSemanticResult`
  - `CheckpointStageState` now carries `board_checkpoint_semantic_result`.
  - `_run_checkpoint_stage(...)` now populates the semantic result after legacy handler outcomes are known.
  - Population combines:
    - legacy plan-board outcome category
    - legacy memory-board outcome category
    - prepass compiler analysis / IR structural facts when available
- **Observed result shape**
  - The model records:
    - typed checkpoint kind
    - source / reason / evidence
    - visible-text and action presence
    - clean-vs-raw text presence
    - legacy plan and memory outcomes
    - compiler shape / error / recovery metadata
    - checkpoint-related compiler facts
    - parity availability / alignment / mismatch reason
- **Behavior boundary**
  - No routing behavior changed.
  - No board commit behavior changed.
  - No checkpoint flags are driven by the new model.
  - No authority transfer happened.
  - Legacy board handlers remain authoritative.
  - `_run_classification_stage` still recomputes diagnosis on normalized response.
- **Test coverage**
  - Semantic result attachment is now characterized for:
    - `memory_checkpoint_only`
    - `memory_checkpoint_and_text`
    - `plan_checkpoint_only`
    - mixed plan + memory outcomes
  - Missing compiler/prepass analysis yields safe fallback semantics.
  - Existing checkpoint routing behavior remains unchanged.
- **Next step**
  - Phase 10 Step 11: Board/Checkpoint Semantic Model Parity Review / First Consumer Migration Decision.

## Phase 10 Step 11: Board/Checkpoint Semantic Model Parity Review / First Consumer Migration Decision (Complete)

- **Decision**
  - **NO-GO** for a first authority migration.
  - `BoardCheckpointSemanticResult` is useful, but it is not yet strong enough to drive any production board/checkpoint consumer.
- **Why**
  - The semantic model currently captures checkpoint presence and broad outcome categories, but parity is still too coarse to prove:
    - commit-equivalence
    - cleanup-equivalence
    - routing-equivalence
  - Remaining risk areas include:
    - visible-text parity vs handler-local cleaned-text behavior
    - action parity vs checkpoint-with-action handler behavior
    - plan-vs-memory distinction in mixed outcomes
    - compiler-invalid framing vs handler-local cleanup/continuation behavior
  - `_build_board_checkpoint_semantic_result(...)` is still a large embedded builder in `ResponsePipelineStagesMixin`, which makes future refinement and direct characterization harder than a dedicated pure helper would.
- **Authority boundary remains unchanged**
  - Legacy board handlers remain authoritative.
  - `BoardCheckpointSemanticResult` remains observational only.
  - Compiler/prepass facts remain structural-only observations.
  - `_run_classification_stage` still recomputes diagnosis on normalized response and does not reuse prepass analysis.
- **Next step**
  - Phase 10 Step 12: BoardCheckpoint Semantic Model Refinement + Pure Builder Extraction.

## Phase 10 Step 12: BoardCheckpoint Semantic Model Refinement + Pure Builder Extraction (Complete)

- **Implementation outcome**
  - Extracted the board/checkpoint semantic-result construction into a new pure helper module:
    - `modules/agent/orchestration/responses/board_checkpoint_semantics.py`
  - `ResponsePipelineStagesMixin._run_checkpoint_stage(...)` now delegates semantic-result construction to the extracted pure helper.
  - The helper is side-effect-free:
    - no logging
    - no state mutation
    - no handler calls
    - no pipeline calls
- **Observational refinement**
  - Added low-risk observational parity fields:
    - `legacy_has_checkpoint`
    - `compiler_has_checkpoint_like`
    - `legacy_has_visible_text`
    - `compiler_has_visible_text`
    - `legacy_has_action`
    - `compiler_has_action`
  - These remain diagnostic-only and do not drive routing.
- **Characterization**
  - Direct unit tests now cover the pure helper across:
    - memory checkpoint only
    - memory checkpoint with text
    - plan checkpoint only
    - mixed outcomes
    - no checkpoint
    - missing compiler/prepass analysis
    - checkpoint-presence mismatch
  - `_run_checkpoint_stage(...)` is also characterized to attach the same result as the pure helper.
- **Boundary remains unchanged**
  - No board commit behavior changed.
  - No checkpoint routing behavior changed.
  - No checkpoint flags are mutated from the semantic model.
  - No authority transfer happened.
  - Legacy board handlers remain authoritative.
- **Next step**
  - Phase 10 Step 13: BoardCheckpoint Pure Builder Parity Review / First Safe Consumer Candidate.

## Phase 10 Step 13: First Narrow BoardCheckpoint Consumer Migration (Complete)

- **Implementation outcome**
  - `_run_checkpoint_stage(...)` now performs a first narrow typed read-through for memory checkpoint routing.
  - Migrated typed read-through cases:
    - `MEMORY_CHECKPOINT_ONLY`
    - `MEMORY_CHECKPOINT_WITH_TEXT`
  - The typed result is only consulted when it is legacy-derived and confirms the same legacy bool.
- **Authority boundary**
  - This is not compiler/prepass authority.
  - This is not board commit migration.
  - Legacy board handlers remain authoritative.
  - Legacy flags still win on disagreement.
  - Compiler/prepass-only checkpoint facts cannot trigger routing.
- **Behavior boundary**
  - No board commit behavior changed.
  - No checkpoint routing behavior changed.
  - No checkpoint flags are mutated from compiler/prepass facts.
  - No dispatch, final-answer, stop-gate, `ActionPolicy`, parser, or `history.py` behavior changed.
- **Test coverage**
  - typed read-through path for `memory_checkpoint_only`
  - typed read-through path for `memory_checkpoint_and_text`
  - disagreement tests proving legacy flags win
  - continued coverage that compiler/prepass-only checkpoint facts do not trigger routing
- **Next step**
  - Phase 10 Step 14: Plan Checkpoint Typed Read-Through or Memory Branch Fallback Tightening.

## Phase 10 Step 14: Complete Legacy-Derived Typed Read-Through for Board Checkpoint Routing (Complete)

- **Implementation outcome**
  - `_run_checkpoint_stage(...)` now completes the safe legacy-derived typed read-through micro-slice for checkpoint-routing branches backed by legacy handler bools.
  - Migrated branches:
    - `MEMORY_CHECKPOINT_ONLY`
    - `MEMORY_CHECKPOINT_WITH_TEXT`
    - `MEMORY_CHECKPOINT_WITH_ACTION`
    - `PLAN_CHECKPOINT_ONLY`
    - `PLAN_CHECKPOINT_WITH_TEXT`
    - `PLAN_CHECKPOINT_WITH_ACTION`
  - The typed result is only used when it is legacy-derived and confirms the same legacy bool.
- **Authority boundary**
  - This is not compiler/prepass authority.
  - This is not board commit migration.
  - Legacy board handlers remain authoritative.
  - Legacy flags still win on disagreement.
  - Compiler/prepass-only checkpoint facts cannot trigger routing.
- **Behavior boundary**
  - No observable checkpoint routing behavior changed.
  - No board commit behavior changed.
  - No checkpoint flags are mutated from compiler/prepass facts.
  - No dispatch, final-answer, stop-gate, `ActionPolicy`, parser, or `history.py` behavior changed.
- **Test coverage**
  - typed read-through paths for all migrated branches above
  - disagreement tests proving legacy flags win
  - continued coverage that compiler/prepass-only plan and memory checkpoint facts do not trigger routing
- **Deferred branches**
  - No additional safe legacy-bool-backed checkpoint-routing branches remain in this micro-slice.
  - Any next migration requires a new authority/design step rather than more typed mirroring.
- **Phase 10 Step 16: BoardCheckpoint Legacy-Derived Authority Candidate Implementation (Complete)**
  - effective checkpoint-flag resolution is now centralized in a pure helper, `_run_checkpoint_stage(...)` uses it instead of scattered inline bool resolution, and `CheckpointStageState(...)` construction consistently carries effective checkpoint flags. No compiler/prepass authority was introduced, and no observable routing or commit behavior changed.
- **Phase 10 Step 17: Use EffectiveCheckpointFlags as the Single Local Checkpoint Routing Surface (Complete)**
  - `_run_checkpoint_stage(...)` now uses `EffectiveCheckpointFlags` as the single local checkpoint routing/state surface after resolution.
  - No compiler/prepass authority was introduced.
  - No observable routing or commit behavior changed.
  - Legacy board handlers remain authoritative.
- **Phase 10 Step 18: First True Authority Candidate — Legacy-Derived Typed Result Primary With Legacy Fallback (Complete)**
  - The first true authority narrowing was attempted for the `memory_checkpoint_only` branch.
  - A new pure helper was introduced as a typed-primary candidate, but it remains behavior-preserving with a legacy disagreement guard; the typed result cannot change the memory branch category.
  - Legacy fallback remains fully in place, and no observable routing or commit behavior changed.
  - No compiler/prepass authority was introduced.

## Phase 9 Step 6D Outcome

- **Conclusion**
  - The review of the diagnostic parity evidence from Step 6C is complete.
  - The producer-side `ExecutionPlan` metadata and consumer-side `DispatchPipeline` diagnostics are sufficiently aligned for observability.
  - The metadata is not yet strong enough to simplify candidate construction or remove `compiler_ir`/`segments` checks.
  - Candidate-driven dispatch and synthetic segment adapters remain deferred.
  - The Phase 9 Step 6A-6D producer/metadata alignment mini-slice is now complete.

## Phase 9 Step 6C Outcome

- **Conclusion**
  - The `DispatchPipeline` now reads the new `ExecutionPlan` observational metadata for diagnostic purposes only.
  - A new diagnostic log field, `dispatch_bridge_metadata_parity`, records the alignment between the producer's `ExecutionPlan` metadata and the consumer's direct `compiler_ir` checks.
  - No dispatch behavior was changed.
  - The `DispatchPipeline` candidate builder still uses `compiler_ir` and `segments` as its source of truth.

## Phase 9 Step 6B Outcome

- **Conclusion**
  - The review of the enriched `ExecutionPlan` from Step 6A is complete.
  - The new observational metadata (`action_payload_snapshot`, `action_op_count`, etc.) is not yet sufficient to replace the `DispatchPipeline`'s direct `compiler_ir` and `segments` checks.
  - `candidate_eligibility_status` is a coarse producer-side hint and must not be used for dispatch authority.
  - The safest next step is to use the new metadata as diagnostic-only input to the `DispatchPipeline` candidate builder, logging any parity mismatches without changing behavior.
  - A new Step 6C is proposed for this diagnostic alignment.

## Phase 9 Step 6A Outcome

- **Conclusion**
  - `ExecutionPlan` was enriched with non-authoritative observational metadata fields (`action_payload_snapshot`, `action_op_count`, `plan_source`, `candidate_eligibility_status`, `pre_action_text_source`).
  - The producer (`ResponsePipelineStagesMixin._build_execution_plan`) now populates these fields from `compiler_ir`.
  - Characterization tests were added to lock down the new field population.
  - No consumer logic was changed, and no dispatch behavior was changed.
  - Actual dispatch remains segment-driven.

## Phase 9 Step 6 Outcome

- **Conclusion**
  - The producer-side `ExecutionPlan` creation path in `ResponsePipelineStagesMixin._build_execution_plan` was reviewed.
  - The review concluded that the current `ExecutionPlan` is not rich enough to be the sole source for a plan-first dispatch consumer.
  - The consumer (`DispatchPipeline`) currently has to re-access `compiler_ir` and `segments` to build its internal `PlanDispatchCandidate` because `ExecutionPlan` only contains action summaries (`action_effects`), not the full payloads needed for dispatch.
  - The safest next step is to enrich `ExecutionPlan` with new observational-only metadata fields (e.g., `action_payload_snapshot`, `action_op_count`, `plan_source`).
  - This enrichment must not authorize dispatch, replace segments, bypass `ActionPolicy`, or change side effects.
  - A new Step 6A was proposed to implement this enrichment.

## Step 4M Batch Plan

- **Conclusion**
  - The Terminal Answers slice was kept open through Steps 4M.1, 4M.2, 4N.1, and 4N.2 to address the remaining low-risk legacy consumers first.

- **Remaining TerminalAnswer-related legacy consumers**
  - `INVALID_OR_TRUNCATED_TERMINAL_TEXT` consumer:
    `ResponsePipelinePrevalidationMixin._reject_truncated_terminal_completion_before_transition`
  - `INTERNAL_SUMMARY_LIKE_TEXT` consumer:
    output-recovery routing that handles `internal_summary_instead_of_final_answer`
  - `PLAINTEXT_TERMINAL_ANSWER` / final-answer path consumers:
    final-answer and stop-gate-adjacent logic remain deferred pending separate preflight
  - `CHECKPOINT_WITH_VISIBLE_TEXT` / `CHECKPOINT_ONLY` consumers:
    board/checkpoint handlers remain deferred to a separate slice

- **Ranking**
  - `INVALID_OR_TRUNCATED_TERMINAL_TEXT`
    - Bug impact: High
    - Migration risk: Medium
    - Classifier readiness: High
    - Policy/authority risk: Medium
  - `INTERNAL_SUMMARY_LIKE_TEXT`
    - Bug impact: Medium
    - Migration risk: Medium
    - Classifier readiness: Medium
    - Policy/authority risk: High
  - `PLAINTEXT_TERMINAL_ANSWER`
    - Bug impact: High
    - Migration risk: High
    - Classifier readiness: Medium
    - Policy/authority risk: High
  - `CHECKPOINT_WITH_VISIBLE_TEXT` / `CHECKPOINT_ONLY`
    - Bug impact: Medium
    - Migration risk: Medium
    - Classifier readiness: Medium
    - Policy/authority risk: Medium

- **Recommended ordered migration sequence**
  - `Phase 8 Step 4M.1`: `INVALID_OR_TRUNCATED_TERMINAL_TEXT` consumer migration design
  - `Phase 8 Step 4M.2`: `INVALID_OR_TRUNCATED_TERMINAL_TEXT` implementation
  - `Phase 8 Step 4N.1`: `INTERNAL_SUMMARY_LIKE_TEXT` consumer migration design
  - `Phase 8 Step 4N.2`: `INTERNAL_SUMMARY_LIKE_TEXT` implementation
  - Later: `PLAINTEXT_TERMINAL_ANSWER` / final-answer path only after separate preflight
  - Checkpoint/board consumers deferred to a separate board/checkpoint slice

## Step 4M.1 Design

- **Current consumer path**
  - Exact function:
    `ResponsePipelinePrevalidationMixin._reject_truncated_terminal_completion_before_transition`
  - Current helper used:
    `terminal_plaintext_completion_status(raw_response)`
  - Current behavior on invalid/truncated terminal plaintext:
    - only runs when `step.intent_payload` is a dict with `mode == "complete"`
    - calls the legacy helper on the raw response text
    - if the helper reports invalid/truncated text, clears terminal plaintext completion state
    - logs `reason="truncated_terminal_plaintext_answer"` and `source="intent_completion_atomicity_guard"`
    - returns `ResponsePipelineOutcome.continue_with(...)` using `_terminal_completion_recovery_prompt(...)`

- **Current classifier readiness**
  - `TerminalAnswerClassifier` already classifies `INVALID_OR_TRUNCATED_TERMINAL_TEXT`
    using `terminal_plaintext_completion_status(candidate_text)` when
    `runtime_semantics.visible_text_source == "PURE_PLAINTEXT"` and the text is not a complete leaked-system marker.
  - Inputs used by the classifier:
    - `runtime_semantics`
    - `raw_response_text`
    - internally derived `candidate_text = visible_text or raw_response_text`
  - After Step 4L, the classifier result is attached to `ParsedModelOutput` as
    `parsed_output.terminal_answer_semantic_result`.
  - The classifier already runs early enough:
    it executes in `_apply_compiler_diagnosis(...)`, before later prevalidation and stage consumers can inspect `parsed_output`.

- **Parity / risk analysis**
  - Similarity:
    - both the legacy consumer and the classifier rely on the same legacy helper family:
      `terminal_plaintext_completion_status(...)`
  - Mismatch:
    - the current consumer evaluates `terminal_plaintext_completion_status(raw_response)`
    - the classifier evaluates the helper on `candidate_text`, and only on the `PURE_PLAINTEXT` classifier path
    - this means the classifier is structurally narrower than the legacy guard
  - Design conclusion:
    - legacy fallback is required for Step 4M.2
    - typed result can be the primary hint only inside the existing intent-completion guard
    - if the typed result is absent, or present but not `INVALID_OR_TRUNCATED_TERMINAL_TEXT`, the legacy helper must still run
  - Policy / intent-completion risk:
    - this consumer is tied to `intent_payload.mode == "complete"`
    - it is part of an intent-completion atomicity/policy path, not a free-standing terminal-answer authority
    - Step 4M.2 must preserve all existing intent-completion preconditions and recovery behavior

- **Proposed Step 4M.2 implementation**
  - Scope only:
    `ResponsePipelinePrevalidationMixin._reject_truncated_terminal_completion_before_transition`
  - Proposed shape:
    - preserve the existing `intent_payload` and `mode == "complete"` preconditions
    - read `parsed_output.terminal_answer_semantic_result` if available at the call site
    - treat `TerminalAnswerKind.INVALID_OR_TRUNCATED_TERMINAL_TEXT` as the primary hint
    - always confirm the final rejection decision with `terminal_plaintext_completion_status(raw_response)`
    - preserve the same state clearing, logging, recovery prompt, reason, and source
  - Explicit non-goals:
    - no stop-gate authority change
    - no final-answer authority change
    - no migration of any other consumer
    - no classifier logic changes in Step 4M.2 unless a separate design step proves parity is insufficient

- **Tests required for Step 4M.2**
  - typed result path:
    typed `INVALID_OR_TRUNCATED_TERMINAL_TEXT` triggers the same recovery outcome
  - legacy fallback when typed result is absent
  - legacy fallback when typed result is present but differs
  - existing policy / preconditions preserved:
    no rejection unless `intent_payload.mode == "complete"`
  - no-behavior-change cases:
    valid completion still passes through unchanged

## Step 4M.2 Implementation

- **Outcome**
  - Migrated consumer:
    `ResponsePipelinePrevalidationMixin._reject_truncated_terminal_completion_before_transition`
  - Typed `INVALID_OR_TRUNCATED_TERMINAL_TEXT` is now the primary hint for this guard, with legacy confirmation.
  - Legacy `terminal_plaintext_completion_status(raw_response)` remains the production fallback.
  - The fallback applies when the typed result is absent or present but differs.
  - Existing `intent_payload.mode == "complete"` precondition is preserved.
  - Existing recovery behavior is preserved:
    terminal completion state clearing, recovery prompt behavior, logging fields, `reason`, and `source`.
  - No stop-gate, final-answer, policy, dispatch, UI, or parser behavior was changed.
  - No other consumers were migrated.
  - Tests passed.

## Step 4N.1 Design

- **Current internal-summary consumer path**
  - Exact functions:
    - `OutputRecoveryRoutingMixin.decide(...)`
    - `OutputRecoveryRoutingMixin._resolved_invalid_kind(...)` / the local invalid-kind resolution flow inside `decide(...)`
  - Current helper / policy used:
    `ModelOutputRecoveryHandler._is_internal_summary_instead_of_final_answer(parsed_output)`
  - Current behavior when internal summary is detected:
    - if no earlier `invalid_kind` has already been selected, `decide(...)` sets
      `invalid_kind = "internal_summary_instead_of_final_answer"`
    - the routing branch logs `reason="internal_summary_instead_of_final_answer"`
    - it returns `OutputRecoveryDecision.continue_with(...)`
      using `build_internal_summary_instead_of_final_answer_prompt()`
      with `source="output_recovery"`

- **Current classifier readiness**
  - `TerminalAnswerClassifier` classifies `INTERNAL_SUMMARY_LIKE_TEXT` when
    `TerminalAnswerClassifierInput.is_internal_summary` is `True`.
  - `is_internal_summary` is computed in
    `ResponsePipelinePrevalidationMixin._run_terminal_answer_classifier_shadow(...)`
    by calling the existing legacy helper
    `_is_internal_summary_instead_of_final_answer(parsed_output)`.
  - The typed result is attached to `ParsedModelOutput` as
    `parsed_output.terminal_answer_semantic_result`.
  - The consumer can access that typed result without reclassifying because
    `parsed_output` is already handed into output-recovery routing.

- **Parity / risk analysis**
  - The typed classifier result and the existing consumer both depend on the same
    runtime-policy helper family:
    `_is_internal_summary_instead_of_final_answer(parsed_output)`.
  - However, exact parity is still not proven for this consumer path because:
    - the helper is runtime-policy logic, not a compiler fact
    - the output-recovery flow is invalid-kind routing, where earlier invalid kinds
      may take precedence before the internal-summary check runs
    - this branch is part of recovery policy, not a free-standing terminal-answer authority
  - Design conclusion:
    - typed result may be a primary hint only
    - legacy helper / existing invalid-kind logic remains the confirmation and fallback path
    - typed result alone must not create a new internal-summary recovery if the
      legacy policy helper would not do so

- **Proposed Step 4N.2 implementation**
  - Scope only:
    the existing internal-summary recovery consumer in output-recovery routing
  - Proposed shape:
    - keep the current invalid-kind ordering in `decide(...)`
    - inspect `parsed_output.terminal_answer_semantic_result` as a primary hint
      for the internal-summary branch
    - confirm with `_is_internal_summary_instead_of_final_answer(parsed_output)`
      unless exact parity is proven
    - preserve current recovery behavior, `reason`, `source`, logging, and prompt
      `build_internal_summary_instead_of_final_answer_prompt()`
  - Explicit non-goals:
    - no stop-gate or final-answer authority change
    - no migration of any other consumer
    - no classifier logic changes in Step 4N.2

- **Tests required for Step 4N.2**
  - typed result path with legacy confirmation
  - typed result alone must not expand behavior if parity is not exact
  - fallback when typed result is absent
  - fallback when typed result differs
  - current non-summary cases pass through unchanged

## Step 4N.2 Implementation

- **Outcome**
  - Migrated consumer:
    internal-summary recovery in `OutputRecoveryRoutingMixin.decide(...)`
  - Typed `INTERNAL_SUMMARY_LIKE_TEXT` is now a primary hint for this consumer.
  - `_is_internal_summary_instead_of_final_answer(parsed_output)` remains the confirmation/fallback path.
  - Typed result alone does not create a new recovery decision.
  - Existing invalid-kind ordering and earlier invalid-kind precedence are preserved.
  - Existing recovery behavior is preserved:
    `invalid_kind="internal_summary_instead_of_final_answer"`,
    `reason="internal_summary_instead_of_final_answer"`,
    `source="output_recovery"`,
    `build_internal_summary_instead_of_final_answer_prompt()`,
    and existing logging behavior.
  - No stop-gate, final-answer, policy, dispatch, UI, parser, or history behavior was changed.
  - No other consumers were migrated.
  - Tests passed.

## Step 4O Review

- **Remaining consumers**
  - `ResponseSemantics.is_plaintext_answer_path(...)`
    in `modules/agent/orchestration/responses/response_semantics.py`
    - helper/surface:
      `parsed_output.visible_text`, `_strip_non_plaintext_control_blocks(raw_response)`,
      `has_any_action_proposal(...)`, `invalid_kind`
    - role:
      plaintext/final-answer path detection
  - `IntentTransitionRoutingMixin.handle_model_step(...)`
    in `modules/agent/orchestration/transitions/intent_transition_routing.py`
    - helpers/surfaces:
      `_remaining_has_plaintext_answer_only(response_text)`,
      `_mark_terminal_plaintext_completion(response_text)`,
      `_finalize_completed_intent()`
    - role:
      intent-completion finalization and transition handling
  - `ResponsePipelineStagesMixin._run_post_classification_stage(...)`
    in `modules/agent/orchestration/responses/response_pipeline_stages.py`
    - helpers/state:
      `terminal_plaintext_completion_pending`,
      `output_recovery.decide(...)`,
      `action_policy.decide(...)`
    - role:
      stop/continue behavior after recovery/policy decisions
  - `OutputRecoveryRoutingMixin.decide(...)`
    in `modules/agent/orchestration/responses/output_recovery_routing.py`
    - helper:
      `missing_action_or_answer` routing / `build_missing_action_or_answer_prompt()`
    - role:
      recovery for missing action or missing final answer

- **Classifier readiness**
  - `TerminalAnswerClassifier` produces `PLAINTEXT_TERMINAL_ANSWER` from the structural fact
    `runtime_semantics.visible_text_source == "PURE_PLAINTEXT"`.
  - The typed result is attached to `ParsedModelOutput` early enough for later consumers.
  - However, the classifier provides structural classification only. It does not
    decide final-answer correctness, sufficiency, transition completion, or stop behavior.

- **Risk analysis**
  - Final-answer authority risk:
    remaining consumers decide whether a response is an acceptable final answer,
    not just whether plaintext is structurally present.
  - Stop-gate risk:
    `terminal_plaintext_completion_pending` influences later stop vs continue
    behavior in `ResponsePipelineStagesMixin`.
  - Intent completion risk:
    `handle_model_step(...)` finalizes intents and marks terminal completion state.
  - Visible-text mismatch risk:
    legacy consumers use a mix of `visible_text`, sanitized raw response text,
    `_remaining_has_plaintext_answer_only(...)`, and `_strip_non_plaintext_control_blocks(...)`,
    while the classifier uses `PURE_PLAINTEXT` structural facts.
  - Policy vs structure boundary:
    `PLAINTEXT_TERMINAL_ANSWER` is structural. The remaining consumers are policy
    and authority decisions.

- **Recommendation**
  - **NO-GO** for a `PLAINTEXT_TERMINAL_ANSWER` migration in the current slice.
  - No remaining narrow consumer was identified that avoids final-answer authority,
    stop-gate authority, and intent-completion policy.
  - Recommendation:
    defer `PLAINTEXT_TERMINAL_ANSWER` migration and close the Terminal Answers
    consumer-migration slice for now.

## Step 4P Closure

- **Terminal Answers consumer-migration slice**
  - Complete for now.
  - Completed migrations:
    - `LEAKED_SYSTEM_RESULT`
    - `INVALID_OR_TRUNCATED_TERMINAL_TEXT`
    - `INTERNAL_SUMMARY_LIKE_TEXT`
- **Deferred**
  - `PLAINTEXT_TERMINAL_ANSWER` / final-answer-path migration
  - checkpoint/board consumers to a separate board/checkpoint slice
- **Deferred rationale**
  - final-answer authority risk
  - stop-gate risk
  - intent-completion risk
  - visible-text extraction/sanitization mismatch risk
  - remaining consumers are policy/authority decisions, not structural reads

## Test Status

- All tests are currently passing.
- Key test contracts are documented in `test-contracts.md`.
