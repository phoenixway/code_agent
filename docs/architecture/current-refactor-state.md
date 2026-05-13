# Current Refactor State: Semantic Runtime Migration

This document is the single source of truth for the current state of the Semantic Runtime Migration refactor.

## Current Phase

- **Phase**: Phase 45 — Step 2/N: Select Next Active Slice
- **Status**: Complete.
- **Next Step**: Phase 46 — Step 1/N: Trace Export Integration Preflight Inventory.
- **Boundary**: Trace Export Integration Preflight is selected as the next active slice. The next work is docs-only inventory. No production behavior change, trace export integration, protocol shadow integration, replay implementation, dispatch behavior change, recovery behavior change, ActionPolicy change, final-answer stop/continue behavior change, authority transfer, switch change, state mutation, or legacy cleanup is allowed yet.

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
- **Phase 10 Step 19: Extend Typed Primary to Remaining Legacy-Derived Memory Branches (Complete)**
  - The typed-primary candidate pattern was extended to `MEMORY_CHECKPOINT_WITH_TEXT` and `MEMORY_CHECKPOINT_WITH_ACTION`.
  - The new pure helpers remain behavior-preserving with legacy disagreement guards.
  - The typed result cannot change the memory branch category, and no observable routing or commit behavior changed.
- **Phase 10 Step 20: Typed-Primary Candidate for Legacy-Derived Plan Branches (Complete)**
  - The typed-primary candidate pattern was extended to all legacy-derived plan checkpoint branches.
  - The new pure helpers remain behavior-preserving with legacy disagreement guards.
  - The typed result cannot change the plan branch category, and no observable routing or commit behavior changed.
- **Phase 10 Step 21: Consolidate BoardCheckpoint Typed-Primary Candidate Helpers / Reduce Boilerplate (Complete)**
  - The typed-primary candidate helpers were consolidated to reduce boilerplate.
  - No authority was expanded, and no observable routing or commit behavior changed.
- **Phase 10 Step 22: First Compiler-Authority Switch for BoardCheckpoint Routing (Complete)**
  - The first default-off compiler-authority switch was introduced for the `PLAN_CHECKPOINT_ONLY` branch.
  - When enabled, a clean compiler-only signal can now trigger the plan checkpoint continuation path.
  - Default behavior remains unchanged. Legacy fallback is preserved. No other branches were migrated.
- **Phase 10 Step 23: PLAN_CHECKPOINT_ONLY Compiler Authority Guard Tightening + Angelica Smoke Run (Complete)**
  - The authority-switch predicate for `PLAN_CHECKPOINT_ONLY` was hardened to require `compiler_has_checkpoint`.
  - Additional fallback tests were added.
  - Smoke tests with the switch enabled showed no regressions, so the switch is considered safe to keep (but default-off).
  - The board/checkpoint slice is now considered complete.
- **Phase 10 Step 24: Central Refactor Switch Registry TOML (Complete)**
  - A central TOML registry for refactor authority switches was introduced in `modules/agent/orchestration/config/refactor_switches.toml`.
  - A loader was added to read switch defaults from the registry.
  - The existing `PLAN_CHECKPOINT_ONLY` switch was wired to the registry.
  - No authority was expanded, and default behavior remains unchanged.

- **Phase 10 Step 25: Refactor Switch Registry Smoke Profile (Complete)**
  - The switch registry loader now supports an `ANGELICA_REFACTOR_SWITCH_REGISTRY` environment variable to override the default TOML file.
  - A smoke-test profile, `refactor_switches.smoke.toml`, was added to enable the `PLAN_CHECKPOINT_ONLY` compiler-authority switch for validation runs.
  - The default `refactor_switches.toml` remains unchanged, with all switches set to `legacy`.
  - No new authority branches were added, and no runtime behavior was changed unless the smoke override is used.
- **Phase 10 Step 26B: Synthetic Smoke Harness + Self-Closing Subgoal Compiler Fix (Complete)**
  - A targeted Angelica smoke run exposed a real compiler coverage gap: self-closing `<subgoal ... />` tags were treated as plaintext by the compiler/prepass while the legacy `PlanBoardStageHandler` correctly handled them as `plan_checkpoint_only`.
  - The compiler/parser path now recognizes both `<subgoal .../>` and `<subgoal ... />` as structural subgoal checkpoints instead of `PURE_PLAINTEXT`.
  - Safe board-only checkpoint protocol now compiles to a valid `CHECKPOINT_ONLY` shape instead of falling back to ambiguous invalid classification.
  - Deterministic synthetic smoke coverage was added for the smoke-authority `PLAN_CHECKPOINT_ONLY` branch, including negative controls for checkpoint-with-text, checkpoint-with-action, and action-only responses.
  - No default authority expansion occurred. The default switch registry remains `legacy`; compiler authority is still exercised only under the smoke-profile override.
- **Phase 10 Step 26D: BoardCheckpoint Authority-Source Logging (Complete)**
  - Explicit authority-resolution diagnostics were added for `board_checkpoint.plan_checkpoint_only`.
  - The new diagnostics distinguish:
    - shadow parity only
    - legacy-selected routing
    - compiler-selected routing
    - legacy fallback under compiler switch mode
  - No routing or behavior changed.
  - The default switch registry remains `legacy`.
- **Phase 27 Step 1: Board/Checkpoint Synthetic Smoke Matrix Expansion (Complete)**
  - Deterministic synthetic smoke coverage now includes plan, memory, mixed, action-only, plaintext-only, and invalid checkpoint controls.
  - Covered branches include:
    - `PLAN_CHECKPOINT_ONLY`
    - `PLAN_CHECKPOINT_WITH_TEXT`
    - `PLAN_CHECKPOINT_WITH_ACTION`
    - `MEMORY_CHECKPOINT_ONLY`
    - `MEMORY_CHECKPOINT_WITH_TEXT`
    - `MEMORY_CHECKPOINT_WITH_ACTION`
    - mixed plan+memory checkpoint
    - action-only negative control
    - plaintext-only negative control
    - invalid open-`<think>` checkpoint negative control
  - No default authority expansion happened. The default switch registry remains `legacy`.
  - No runtime behavior changed.
- **Phase 27 Step 2: `PLAN_CHECKPOINT_WITH_TEXT` Smoke-Profile Compiler Authority (Complete)**
  - Added branch-specific authority resolution and diagnostics for `board_checkpoint.plan_checkpoint_with_text`.
  - Default registry remains `legacy`; smoke profile now enables:
    - `board_checkpoint.plan_checkpoint_only = "compiler"`
    - `board_checkpoint.plan_checkpoint_with_text = "compiler"`
  - Synthetic smoke now validates:
    - default-registry legacy behavior for `PLAN_CHECKPOINT_WITH_TEXT`
    - smoke-profile compiler authority for clean `PLAN_CHECKPOINT_WITH_TEXT`
    - negative controls for checkpoint-only, checkpoint-with-action, memory-checkpoint-with-text, and invalid open-`<think>` cases
  - No runtime behavior changed under the default registry.
- **Phase 27 Step 3: `PLAN_CHECKPOINT_WITH_TEXT` Live Angelica Smoke (Complete)**
  - Targeted live Angelica smoke passed under the smoke profile.
  - Observed raw output:
    - `<subgoal action="mark_in_progress" id="sg_1" />`
    - `Plan board updated.`
  - Authority diagnostics showed:
    - `branch = board_checkpoint.plan_checkpoint_with_text`
    - `switch_value = compiler`
    - `authority_source = compiler`
    - `agreement = True`
    - `fallback_used = False`
    - `behavior_changed = False`
  - Structural parity remained aligned and the runtime did not crash.
  - Default registry remains `legacy`.
- **Phase 27 Step 4: `PLAN_CHECKPOINT_WITH_ACTION` Smoke-Profile Compiler Authority (Complete)**
  - Added branch-specific authority resolution and diagnostics for `board_checkpoint.plan_checkpoint_with_action`.
  - Smoke profile now enables:
    - `board_checkpoint.plan_checkpoint_only = "compiler"`
    - `board_checkpoint.plan_checkpoint_with_text = "compiler"`
    - `board_checkpoint.plan_checkpoint_with_action = "compiler"`
  - Synthetic smoke now validates:
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
  - No runtime behavior changed under the default registry.
- **Phase 27 Step 5: `PLAN_CHECKPOINT_WITH_ACTION` Live Angelica Smoke (Complete)**
  - Targeted live Angelica smoke passed under the smoke profile.
  - Compiler authority was selected for `board_checkpoint.plan_checkpoint_with_action`.
  - No fallback was used.
  - The action/dispatch path remained preserved:
    - `action_policy` passed with `action_count = 1`
    - `response_pipeline` reached `dispatch`
    - `pre_dispatch_pipeline` reached `dispatch_ready`
  - Structural parity remained aligned and the runtime did not crash.
  - Default registry remains `legacy`.
- **Phase 27 Step 6: Plan-Domain Board/Checkpoint Smoke Closure (Complete)**
  - The plan-domain board/checkpoint compiler-authority smoke slice is now complete for:
    - `PLAN_CHECKPOINT_ONLY`
    - `PLAN_CHECKPOINT_WITH_TEXT`
    - `PLAN_CHECKPOINT_WITH_ACTION`
  - Each validated branch now has:
    - synthetic smoke coverage
    - branch-specific authority diagnostics
    - live Angelica smoke pass under the smoke profile
  - Smoke profile may keep the validated plan-checkpoint compiler switches enabled for continued validation.
  - The default registry remains `legacy`; no production authority flip happened.
  - No memory checkpoint authority transfer happened.
  - No board commit logic changed.
  - No dispatch/action behavior changed.
  - Memory checkpoint branches remain deferred because they include memory-engine commit semantics and should not be bundled with the plan-domain slice.
- **Phase 28 Step 1: Terminal Answer Synthetic Smoke Matrix Preflight (Complete)**
  - Terminal/final-answer consumers were inventoried across:
    - `TerminalAnswerClassifier`
    - `response_pipeline_prevalidation`
    - `response_pipeline_stages`
    - `output_recovery_routing`
    - `response_semantics.is_plaintext_answer_path`
    - legacy malformed-output helpers such as `is_leaked_system_result`
  - Current authority shape:
    - typed terminal-answer result exists and is attached to `ParsedModelOutput`
    - some narrow consumers already use it as a hint or primary signal with legacy fallback
    - final-answer / plaintext-answer authority is still largely legacy/runtime-policy driven
  - Existing switch placeholders already exist and remain `legacy`:
    - `terminal_answer.plaintext_terminal_answer`
    - `terminal_answer.checkpoint_only`
    - `terminal_answer.checkpoint_with_visible_text`
  - Proposed first synthetic smoke matrix rows:
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
- **Phase 28 Step 2: Terminal Answer Synthetic Smoke Harness Skeleton + Authority Diagnostics (Complete)**
  - Added observational terminal-answer authority diagnostics for:
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
  - Current characterizations now explicitly show:
    - clean plaintext can align typed and legacy signals
    - `CHECKPOINT_WITH_VISIBLE_TEXT` currently disagrees with the legacy plaintext path
    - leaked system result can still appear on the legacy plaintext path even though leak recovery takes authority later
  - No authority transfer happened.
  - No runtime behavior changed.
- **Phase 28 Step 3: Terminal Answer Synthetic Matrix Expansion / First Authority Candidate Decision (Complete)**
  - Expanded synthetic smoke coverage for `terminal_answer.plaintext_terminal_answer` to characterize:
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
  - Observational diagnostics were hardened with non-authoritative fields for:
    - `legacy_active`
    - `has_action`
    - `has_checkpoint`
    - `is_leaked_system_result`
    - more specific `mismatch_reason` values
  - First authority-candidate decision:
    - `terminal_answer.plaintext_terminal_answer` is **NO-GO** for smoke-profile authority transfer in the current state.
  - Blocking findings:
    - `Done.` is still a legacy plaintext-answer path but typed classification currently marks it `INVALID_OR_TRUNCATED_TERMINAL_TEXT`.
    - markdown-ish plaintext currently shares the same truncated-text overlap.
    - `CHECKPOINT_WITH_VISIBLE_TEXT` still overlaps the legacy plaintext path.
    - leaked system result can still overlap the legacy plaintext path even though leak recovery later takes authority.
  - Safe characterization retained:
    - explicit multi-line plaintext and plain explanatory plaintext without actions can align typed and legacy signals.
  - Default registry remains `legacy`.
  - No authority transfer happened.
  - No runtime behavior changed.
- **Phase 28 Step 4: Terminal Answer Diagnostics Hardening (Complete)**
  - Hardened `TerminalAnswerAuthorityDiagnostic` with explicit observational bucket fields for:
    - `typed_plaintext_eligible`
    - `legacy_active`
    - `invalid_or_truncated_terminal_text`
    - `checkpoint_with_visible_text_overlap`
    - `leaked_system_result_overlap`
    - `action_or_pre_action_overlap`
    - `clean_plaintext_candidate`
    - `blocking_reasons`
  - Refined `resolve_plaintext_terminal_answer_authority(...)` so the diagnostic output now cleanly distinguishes:
    - clean plaintext candidate
    - invalid/truncated plaintext overlap
    - checkpoint-with-visible-text overlap
    - leaked-system-result overlap
    - action/pre-action overlap
    - empty / malformed inactive cases
  - Expanded synthetic smoke assertions and added a direct helper-level characterization test for the resolver buckets.
  - No authority transfer happened.
  - Default registry remains `legacy`.
  - No runtime behavior changed.
  - Remaining blocker:
    - typed plaintext classification for short answers like `Done.` and markdown-ish plaintext still needs review/fix before any authority transfer can be reconsidered.
- **Phase 28 Step 5: Typed Plaintext Classification Review / Fix Candidate (Complete)**
  - Reviewed the typed plaintext classifier and identified the root cause:
    - `TerminalAnswerClassifier` was applying `terminal_plaintext_completion_status(...)` to all `PURE_PLAINTEXT` candidates.
    - That helper is intentionally strict for intent-completion final answers and was over-classifying short but complete plaintext like `Done.` and markdown-ish plaintext as invalid/truncated.
  - Implemented a narrow classifier-only fix:
    - short `PURE_PLAINTEXT` answers that are punctuated and do not end in a dangling word now remain typed `PLAINTEXT_TERMINAL_ANSWER`
    - the fix applies only in the typed/shadow classifier path
    - runtime routing, recovery, and authority remain unchanged
  - Post-fix synthetic characterization now shows:
    - `Done.` aligns as a clean plaintext candidate
    - markdown-ish plaintext aligns as a clean plaintext candidate
    - multi-line plaintext remains aligned
    - checkpoint-with-visible-text remains blocked as a checkpoint overlap
    - leaked system result remains blocked as a leak overlap
    - action-bearing and malformed cases remain non-plaintext
  - No authority transfer happened.
  - Default registry remains `legacy`.
  - No runtime behavior changed.
- **Phase 28 Step 6: Plaintext Terminal Authority Re-review / Smoke-Profile Candidate (Complete)**
  - Re-reviewed `terminal_answer.plaintext_terminal_answer` after the typed plaintext classifier fix.
  - Decision:
    - **GO** for a smoke-profile-only compiler/typed authority candidate for clean plaintext terminal answers.
  - Implemented smoke-profile-only switch configuration:
    - `modules/agent/orchestration/config/refactor_switches.smoke.toml`
      - `terminal_answer.plaintext_terminal_answer = "compiler"`
  - Refined `resolve_plaintext_terminal_answer_authority(...)` so that when the switch is `compiler`:
    - `authority_source="compiler"` is selected only for clean, agreement-gated plaintext candidates
    - `authority_source="legacy_fallback"` is used for every overlap or uncertain case
    - `behavior_changed=False` remains preserved
  - Positive synthetic smoke now validates compiler selection for:
    - `Done.`
    - markdown-ish plaintext
    - multi-line plaintext
  - Negative controls remain protected with fallback for:
    - action-only
    - pre-action text plus action
    - checkpoint-with-visible-text
    - leaked system result
    - empty / malformed output
    - dangling/incomplete plaintext like `And.`
  - Important boundary:
    - actual post-classification routing still remained legacy in this step
    - compiler authority was selected diagnostically under the smoke profile only
    - no production authority flip happened
  - Default registry remains `legacy`.
  - No runtime behavior changed under the default registry.
- **Phase 28 Step 7: Live Angelica Smoke for Plaintext Terminal Answer under Smoke Profile (Complete)**
  - Live smoke passed for `terminal_answer.plaintext_terminal_answer` under the smoke profile.
  - Observed authority diagnostics:
    - `switch_value="compiler"`
    - `authority_source="compiler"`
    - `typed_kind="PLAINTEXT_TERMINAL_ANSWER"`
    - `legacy_kind="plaintext_answer_path"`
    - `agreement=True`
    - `fallback_used=False`
    - `clean_plaintext_candidate=True`
    - no action/checkpoint/leak overlap
  - Runtime remained stable:
    - `last_error_code=None`
    - `consecutive_same_error_count=0`
  - Up to this step, actual routing was still legacy.
  - Default registry remained `legacy`.
- **Phase 28 Step 8: Plaintext Terminal Authority Closure / Actual Smoke-Profile Routing Flip Candidate (Complete)**
  - Decision:
    - **GO** for the first actual smoke-profile-only routing use of `terminal_answer.plaintext_terminal_answer`.
  - Implemented an agreement-gated local effective variable in `_run_post_classification_stage(...)`:
    - `legacy_plaintext_answer_path`
    - `terminal_answer_authority`
    - `effective_plaintext_answer_path`
  - Actual routing use is enabled only when all are true:
    - switch is `compiler`
    - `authority_source="compiler"`
    - `clean_plaintext_candidate=True`
    - `agreement=True`
    - no `blocking_reasons`
    - `behavior_changed=False`
  - The first local consumer now uses `effective_plaintext_answer_path` instead of the raw legacy value:
    - the nonproductive-thinking guard call inside `_run_post_classification_stage(...)`
  - Positive smoke coverage:
    - `Done.`
    - markdown-ish plaintext
    - multi-line plaintext
  - Negative controls remain protected:
    - action-only
    - pre-action text plus action
    - checkpoint-with-visible-text
    - leaked system result
    - empty / malformed output
    - dangling short text such as `And.`
  - Behavior boundary:
    - default registry remains `legacy`
    - no production authority flip happened
    - runtime behavior under the default registry is unchanged
- **Phase 28 Step 9: Live Angelica Smoke for Actual Plaintext Terminal Routing Flip under Smoke Profile (Complete)**
  - Live smoke passed for the actual smoke-profile plaintext terminal routing flip.
  - Verified from dump:
    - model output was exactly `Done.`
    - `last_error_code=None`
    - `consecutive_same_error_count=0`
    - `stage=protocol_shadow`
    - `decision=terminal_answer_authority_resolution`
    - `branch=terminal_answer.plaintext_terminal_answer`
    - `switch_value=compiler`
    - `authority_source=compiler`
    - `typed_kind=PLAINTEXT_TERMINAL_ANSWER`
    - `legacy_kind=plaintext_answer_path`
    - `agreement=True`
    - `fallback_used=False`
    - `behavior_changed=False`
    - `effective_value=True`
    - `clean_plaintext_candidate=True`
    - no action/checkpoint/leak overlap flags were set
  - Important note:
    - older `terminal_answer_classifier_shadow` mismatches in the same dump are not the authority signal for this step
    - the relevant authority evidence is `protocol_shadow / terminal_answer_authority_resolution`
  - Default registry remains `legacy`.
  - No production authority flip happened.
- **Phase 28 Step 10: Plaintext Terminal Authority Closure / Next Terminal Branch Selection (Complete)**
  - Closed the plaintext terminal-answer smoke-profile authority slice.
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
  - Next branch decision:
    - selected: `terminal_answer.checkpoint_only`
    - deferred: `terminal_answer.checkpoint_with_visible_text`
      - because it still overlaps the legacy plaintext path and needs a dedicated diagnostics/fix slice
    - deferred: action-bearing / pre-action branches
      - because they cross dispatch/action semantics
    - deferred: leaked-system-result cases
      - because recovery must remain authoritative
  - Rationale for `terminal_answer.checkpoint_only`:
    - narrower than checkpoint-with-visible-text
    - no visible-text ambiguity
    - no action dispatch
    - switch placeholder already exists
    - synthetic-first validation is straightforward
- **Phase 28 Step 11: Terminal Checkpoint-Only Synthetic Authority Candidate (Complete)**
  - Added `terminal_answer.checkpoint_only` authority diagnostics/resolver.
  - Added smoke-profile-only switch configuration for synthetic validation:
    - `modules/agent/orchestration/config/refactor_switches.smoke.toml`
      - `terminal_answer.checkpoint_only = "compiler"` during Step 28.11 validation
  - Synthetic positives validate compiler selection for:
    - `<memory_update_done />`
  - Negative controls validate `legacy_fallback` for:
    - checkpoint-with-visible-text
    - action-only
    - pre-action text plus action
    - plaintext-only
    - leaked system result
    - empty / malformed output
    - checkpoint plus action
  - Default registry remains `legacy`.
  - No production authority flip happened.
  - No behavior change under the default registry.
- **Phase 28 Step 12: Live Angelica Smoke for Terminal Checkpoint-Only under Smoke Profile (Not Exercised / Deferred)**
  - Live smoke produced a clean checkpoint-only marker from dump `dumps/agent_dump_20260510_042059.txt`:
    - model output: `<memory_update_done />`
    - `last_error_code=None`
    - `consecutive_same_error_count=0`
  - Board/memory checkpoint ownership consumed the marker-only turn before terminal post-classification authority could own it:
    - `stage=memory_board`
    - `decision=continue`
    - `reason=memory_checkpoint_only`
  - Structural parity stayed aligned for the checkpoint-only marker:
    - `compiler_shape=CHECKPOINT_ONLY`
    - `compiler_has_checkpoint=True`
    - `compiler_has_action=False`
    - `compiler_has_visible_answer=False`
    - `memory_checkpoint_category=checkpoint_only`
    - `legacy_checkpoint_only=True`
    - `parity_aligned=True`
  - Terminal checkpoint-only authority was **not exercised**:
    - no positive `terminal_answer.checkpoint_only` compiler-authority log was observed for the clean marker-only turn
    - later terminal authority logs belonged to a different plaintext/memory-text turn and showed `legacy_fallback`
  - Result:
    - checkpoint-only marker generation: pass
    - runtime safety: pass
    - board/memory checkpoint structural handling: pass
    - terminal checkpoint-only live authority: not exercised
- **Phase 28 Step 13: Terminal Checkpoint-Only Authority Boundary Review (Complete)**
  - Decision: **NO-GO / DEFER** for `terminal_answer.checkpoint_only` as a live terminal-authority migration target.
  - Reason:
    - marker-only `<memory_update_done />` turns are practically owned by the board/memory checkpoint stage, not by the terminal final-answer path
    - forcing terminal authority here would duplicate or conflict with board/memory ownership
    - synthetic terminal checkpoint-only coverage remains useful as characterization, but it is not a sound runtime authority-transfer target right now
  - Smoke-profile cleanup:
    - `terminal_answer.checkpoint_only` was reverted back to `legacy` in `refactor_switches.smoke.toml`
    - this avoids implying live-authority validation where runtime ownership never reaches terminal post-classification
  - Boundaries preserved:
    - default registry remains `legacy`
    - no production authority flip happened
    - no runtime behavior changed
  - Next domain decision:
    - defer terminal checkpoint branches for now
    - prefer `Phase 28 Step 14: Terminal Classifier Shadow Comparator Cleanup`
- **Phase 28 Step 14: Terminal Classifier Shadow Comparator Cleanup (Complete)**
  - Cleaned up the `terminal_answer_classifier_shadow` comparator so it no longer reports stale mismatch for safe short plaintext such as `Done.` and markdown-ish plaintext.
  - Chosen cleanup:
    - align the legacy parity comparator with the existing short-plaintext acceptance used by the typed shadow classifier
    - add clarifying shadow-only fields so live dumps do not confuse classifier parity with branch authority
  - New shadow log fields:
    - `comparator_scope="legacy_parity_only"`
    - `authority_signal="terminal_answer_authority_resolution"`
  - Important boundary:
    - `protocol_shadow / terminal_answer_authority_resolution` remains the branch-authority signal
    - `terminal_answer_classifier_shadow` remains parity/comparator diagnostics only
  - No runtime behavior changed.
  - Default registry remains `legacy`.
  - No production authority flip happened.
- **Phase 28 Step 15: Terminal Plaintext Slice Closure / Next Domain Selection (Complete)**
  - Closed the terminal plaintext slice for now.
  - `terminal_answer.plaintext_terminal_answer` is now validated under smoke profile with:
    - typed classifier fix for short plaintext like `Done.`
    - hardened authority diagnostics
    - synthetic smoke matrix coverage
    - smoke-profile compiler authority candidate
    - actual smoke-profile routing use
    - live Angelica smoke pass
  - `terminal_answer_classifier_shadow` is now explicitly parity-only:
    - `comparator_scope="legacy_parity_only"`
    - `authority_signal="terminal_answer_authority_resolution"`
  - Deferred terminal branches remain:
    - `terminal_answer.checkpoint_only`
      - deferred because marker-only checkpoint turns are owned by board/memory checkpoint stage
    - `terminal_answer.checkpoint_with_visible_text`
      - deferred because it overlaps the legacy plaintext path and board/memory checkpoint-with-text ownership
  - Closure boundary:
    - default registry remains `legacy`
    - no production authority flip happened
    - no runtime behavior changed
  - Next domain selected:
    - `Phase 29: Recovery / Invalid-Output Synthetic Matrix`
  - Recommended next step:
    - `Phase 29 Step 1: Recovery / Invalid-Output Synthetic Smoke Matrix Preflight`
- **Phase 29 Step 1: Recovery / Invalid-Output Synthetic Smoke Matrix Preflight (Complete)**
  - Completed the first recovery-domain preflight inventory without changing runtime behavior.
  - Current recovery/invalid-output consumers:
    - `ResponsePipelinePrevalidationMixin._apply_compiler_diagnosis(...)`
      - owner: classification/prevalidation
      - authority mix: compiler-invalid code mapped via `COMPILER_INVALID_KIND_BY_CODE`, then merged into legacy `parsed_output.invalid_kind`
      - branch type: invalid-kind stamping before recovery routing
      - synthetic-safe: yes
    - `ResponsePipelinePrevalidationMixin._reject_invalid_output_before_transition(...)`
      - owner: prevalidation
      - authority mix: legacy `parsed_output.invalid_kind` plus `output_recovery.decide(...)`
      - branch type: continue/retry recovery
      - synthetic-safe: yes
    - `ResponsePipelineStagesMixin._run_post_classification_stage(...)`
      - owner: post-classification runtime
      - authority mix:
        - typed-primary for `TerminalAnswerKind.LEAKED_SYSTEM_RESULT`
        - `resolve_protocol_authority(...)` for compiler-invalid suppression decisions
        - legacy/typed mixed `parsed_output.invalid_kind` for structural invalid followups
      - branch type: continue/recovery, stop, dispatch-safe suppression, retry guards
      - synthetic-safe: yes
    - `OutputRecoveryRoutingMixin.decide(...)` in `output_recovery_routing.py`
      - owner: recovery routing
      - authority mix: mostly legacy `invalid_kind` routing with compiler metadata helpers and some typed structural parity
      - branch type: recovery prompt selection / retry continuation
      - synthetic-safe: yes
    - `output_recovery_terminal.py`
      - owner: terminal-recovery helpers
      - authority mix: terminal guard / invalid-kind driven
      - branch type: recovery prompt construction only
      - synthetic-safe: yes
    - `protocol_decision_bridge.resolve_protocol_authority(...)`
      - owner: invalid-kind authority bridge
      - authority mix: compiler-invalid and parsed-action-count facts
      - branch type: suppress or preserve legacy invalid-kind before recovery
      - synthetic-safe: yes
    - `protocol_decision_bridge.compiler_invalid_kind_for_output(...)`
      - owner: compiler invalid-kind mapping
      - authority mix: compiler code -> legacy invalid kind
      - branch type: invalid-kind derivation only
      - synthetic-safe: yes
    - `TerminalAnswerClassifier`
      - owner: typed terminal semantics
      - authority mix: typed/shadow only in this domain, except leaked-system-result and internal-summary consumers already wired elsewhere
      - branch type: typed invalid/truncated, leaked, internal-summary signals
      - synthetic-safe: yes
    - guards in `response_pipeline_stages.py`
      - `reflection_repair_pending`
      - repeated/nonproductive thinking
      - structural invalid hard-stop continuation
      - branch type: retry/continue/stop safety
      - synthetic-safe: yes, though some streak/repeat cases need harness support
  - Existing refactor switches:
    - no recovery/invalid-output switch family exists yet
    - current registry only has:
      - `board_checkpoint.*`
      - `terminal_answer.*`
      - `dispatch.plan_first_single_action`
    - therefore Phase 29 should not assume branch switches already exist
  - Proposed synthetic smoke matrix for Phase 29:
    - unclosed `<think>`
    - malformed action JSON / malformed action payload
    - leaked system result
    - internal-summary recovery
    - invalid/truncated terminal text
    - checkpoint tag inside think
    - memory tag inside think
    - empty / whitespace output
    - repeated malformed or repeated no-valid-output guard if harnessable
    - mixed visible answer plus invalid protocol
    - action with pre-action text where recovery or invalid-kind routing treats it specially
  - Current blockers / risk areas:
    - recovery authority is spread across prevalidation, post-classification, and output-recovery routing rather than a single branch resolver
    - several branches already mix typed-primary and legacy-primary logic, especially leaked-system-result and compiler-invalid suppression
    - retry/streak behavior depends on guard state, so some synthetic cases need a stateful harness rather than a single-turn fixture
    - no recovery-domain authority diagnostics analogous to `terminal_answer_authority_resolution` exist yet
  - Recommended next step:
    - `Phase 29 Step 2: Recovery Invalid-Output Synthetic Harness + Authority Diagnostics`
  - Boundary:
    - default registry remains `legacy`
    - no runtime behavior changed
    - no new authority switches were added
- **Phase 29 Step 2: Recovery Invalid-Output Synthetic Harness + Authority Diagnostics (Complete)**
  - Added [recovery_authority.py](/home/romankozak/studio/public/it/angelica-ai/modules/agent/orchestration/responses/recovery_authority.py) with the observational `RecoveryAuthorityDiagnostic` model.
  - Added `protocol_shadow / recovery_authority_resolution` logging for the first two recovery instrumentation points:
    - `recovery.compiler_invalid_kind_mapping`
      - emitted from `_apply_compiler_diagnosis(...)`
      - characterizes compiler-invalid mapping vs legacy/effective invalid kind
    - `recovery.prevalidation_reject_invalid_output`
      - emitted from `_reject_invalid_intent_followup_before_transition(...)`
      - characterizes effective invalid kind plus the selected recovery action before the prevalidation continuation result is returned
  - Added deterministic synthetic recovery harness coverage in [test_recovery_invalid_output_synthetic_smoke.py](/home/romankozak/studio/public/it/angelica-ai/tests/test_recovery_invalid_output_synthetic_smoke.py) for:
    - unclosed `<think>`
    - malformed action JSON
    - leaked system result
    - invalid/truncated terminal text
    - memory tag inside think
    - checkpoint tag inside think
    - empty / whitespace output
    - pre-action text plus action
  - Important boundary:
    - diagnostics are observational only
    - no recovery authority switches were added
    - no runtime behavior changed
    - default registry remains `legacy`
  - Recommended next step:
    - `Phase 29 Step 3: Recovery Synthetic Matrix Expansion / First Authority Candidate Decision`
- **Phase 29 Step 3: Recovery Synthetic Matrix Expansion / First Authority Candidate Decision (Complete)**
  - Expanded deterministic synthetic recovery coverage in [test_recovery_invalid_output_synthetic_smoke.py](/home/romankozak/studio/public/it/angelica-ai/tests/test_recovery_invalid_output_synthetic_smoke.py) to include:
    - internal-summary characterization
    - mixed visible answer plus invalid protocol
    - repeated-thinking/no-valid-output guard characterization
    - malformed action payload with visible pre-action text
    - action-only valid control
    - clean plaintext valid control
  - Hardened observational recovery diagnostics with additional clarifying fields:
    - `parsed_invalid_kind`
    - `recovery_reason`
    - `recovery_prompt_kind`
    - `guard_name`
    - `guard_triggered`
  - First authority candidate decision:
    - `NO-GO` for recovery authority transfer in this step
    - recovery ownership remains too distributed across compiler-invalid mapping, output-recovery routing, typed terminal signals, and stateful guards
    - the best future narrow candidate is `recovery.compiler_invalid_kind_mapping`, because it is the cleanest behavior-preserving observational slice and already tracks compiler/legacy agreement without owning downstream routing
  - Current blockers / risk areas:
    - internal-summary typed signals do not activate recovery on their own
    - malformed action plus visible text currently resolves through `mixed_visible_text_and_control_protocol`
    - repeated-thinking / no-valid-output handling is stateful and not a pure invalid-kind branch
    - leaked-system-result and recovery/dispatch/final-answer boundaries still overlap
  - Boundary:
    - no recovery switches were added
    - no runtime behavior changed
    - default registry remains `legacy`
  - Recommended next step:
    - `Phase 29 Step 4: Recovery Authority Candidate Design`
- **Phase 29 Step 4: Recovery Authority Candidate Design (Complete)**
  - Added `resolve_compiler_invalid_kind_mapping_authority(...)` in [recovery_authority.py](/home/romankozak/studio/public/it/angelica-ai/modules/agent/orchestration/responses/recovery_authority.py).
  - The resolver now centralizes compiler-invalid-kind mapping and returns both:
    - a behavior-preserving `effective_invalid_kind`
    - `RecoveryAuthorityDiagnostic`
  - `_apply_compiler_diagnosis(...)` now consumes the resolver directly.
  - `OutputRecoveryRoutingMixin._resolved_invalid_kind(...)` now uses the same resolver, removing duplicated mapping logic while preserving current recovery outcomes.
  - Added a new registry placeholder:
    - `recovery.compiler_invalid_kind_mapping = "legacy"` in the default registry
    - `recovery.compiler_invalid_kind_mapping = "legacy"` in the smoke registry
  - Switch decision:
    - Option B selected
    - add the branch key now for registry completeness, but keep both default and smoke on `legacy` until the next validation step
  - Expanded tests with direct resolver characterization for:
    - compiler-primary agreement
    - legacy-preserving mismatch fallback
    - plain-think-prefix exception fallback
  - Boundary:
    - no runtime behavior changed
    - no recovery routing or prompt-selection behavior changed
    - default registry remains `legacy`
  - Recommended next step:
    - `Phase 29 Step 5: Recovery Compiler Invalid Mapping Switch + Synthetic Validation`
- **Phase 29 Step 5: Recovery Compiler Invalid Mapping Switch + Synthetic Validation (Complete)**
  - Enabled the smoke-profile switch:
    - `recovery.compiler_invalid_kind_mapping = "compiler"` in [refactor_switches.smoke.toml](/home/romankozak/studio/public/it/angelica-ai/modules/agent/orchestration/config/refactor_switches.smoke.toml)
  - Kept the default registry at:
    - `recovery.compiler_invalid_kind_mapping = "legacy"`
  - Clarified resolver semantics in [recovery_authority.py](/home/romankozak/studio/public/it/angelica-ai/modules/agent/orchestration/responses/recovery_authority.py):
    - `authority_source` now reflects switch-controlled authority selection
    - `effective_source` records where the unchanged effective invalid kind came from
    - `selected_by_switch` makes it explicit when smoke compiler mode actually selected the branch
  - Added behavior-preserving compiler mapping coverage for `E_MEMORY_TAG_INSIDE_THINK` by mapping it to the current effective invalid kind `malformed_incomplete_think`.
  - Synthetic smoke validation passed for:
    - unclosed think
    - memory tag inside think
    - checkpoint/subgoal tag inside think
    - malformed action JSON
    - mixed visible answer plus invalid protocol
    - plain-think-prefix exception fallback
    - action-only and clean-plaintext controls
  - Fallback behavior remains preserved on conflicts and exceptions:
    - malformed action conflict stays on legacy/current behavior
    - plain-think-prefix exception stays on fallback/current behavior
  - Boundary:
    - no runtime behavior changed
    - no recovery routing or prompt-selection behavior changed
    - default registry remains `legacy`
    - no production behavior changed
  - Recommended next step:
    - `Phase 29 Step 6: Recovery Compiler Invalid Mapping Closure / Next Recovery Branch Selection`
- **Phase 29 Step 6: Recovery Compiler Invalid Mapping Closure / Next Recovery Branch Selection (Complete)**
  - Closed the `recovery.compiler_invalid_kind_mapping` smoke-profile authority slice.
  - Validated under smoke profile:
    - central resolver/accessor
    - default legacy switch
    - smoke compiler switch
    - synthetic matrix coverage
    - conflict fallback tests
    - behavior-preserving `effective_invalid_kind` outcomes
  - Explicitly recorded behavior-preserving compiler coverage:
    - `E_MEMORY_TAG_INSIDE_THINK -> malformed_incomplete_think`
    - this was added to cover an already-current effective invalid-kind outcome, not to change runtime behavior
  - Boundary:
    - default registry remains `legacy`
    - smoke compiler switch remains enabled only in the smoke profile
    - no production authority flip happened
    - no recovery routing or prompt-selection behavior changed
  - Next recovery branch decision:
    - selected `recovery.prevalidation_reject_invalid_output`
  - Rationale:
    - it is the strongest architecture continuation from the Step 29.2/29.3 diagnostics work
    - it already has observational diagnostics and sits directly at recovery action selection
    - it is lower-risk than jumping straight into the safety-sensitive leaked-system-result branch, while still advancing the actual recovery authority boundary instead of staying in pure invalid-kind mapping
    - it is a better immediate progression target than stateful retry/guard branches, which need heavier harness/state modeling
  - Recommended next step:
    - `Phase 29 Step 7: Recovery Prevalidation Reject-Invalid-Output Authority Candidate`
- **Phase 29 Step 7: Recovery Prevalidation Reject-Invalid-Output Authority Candidate (Complete)**
  - Added `resolve_prevalidation_reject_invalid_output_authority(...)` in [recovery_authority.py](/home/romankozak/studio/public/it/angelica-ai/modules/agent/orchestration/responses/recovery_authority.py).
  - Added a small `RecoveryDecisionAuthorityResolution` wrapper so the resolver can return:
    - the effective recovery decision
    - `RecoveryAuthorityDiagnostic`
  - `_reject_invalid_intent_followup_before_transition(...)` now computes the legacy recovery decision as before, then consumes the resolver’s effective decision behavior-preservingly.
  - Added registry placeholders:
    - `recovery.prevalidation_reject_invalid_output = "legacy"` in the default registry
    - `recovery.prevalidation_reject_invalid_output = "legacy"` in the smoke registry
  - Switch decision:
    - Option A selected
    - no smoke compiler enablement yet, because this branch does not yet have an independent compiler decision producer to validate against legacy recovery action selection
  - Expanded synthetic coverage for the prevalidation reject path to include:
    - malformed action JSON
    - unclosed think
    - memory tag inside think
    - checkpoint/subgoal tag inside think
    - mixed visible answer plus invalid protocol
    - valid action-only control
    - clean plaintext control
    - empty/whitespace intent followup characterization
  - Added direct resolver tests for:
    - legacy mode preserving the current decision
    - invalid switch fallback
    - compiler-mode fallback when no compiler decision path exists
    - inactive branch when there is no invalid kind and no recovery decision
  - Boundary:
    - no production behavior changed
    - default registry remains `legacy`
    - smoke registry remains `legacy` for this branch
    - effective decision is now consumed, but remains behavior-preserving and test-locked
  - Recommended next step:
    - `Phase 29 Step 8: Recovery Prevalidation Reject-Invalid-Output Compiler Decision Candidate`
- **Phase 29 Step 8: Recovery Prevalidation Reject-Invalid-Output Compiler Decision Candidate (Complete)**
  - Added `build_compiler_prevalidation_recovery_decision_candidate(...)` in [recovery_authority.py](/home/romankozak/studio/public/it/angelica-ai/modules/agent/orchestration/responses/recovery_authority.py).
  - The branch now has a real compiler-side recovery decision candidate path for a narrow subset of stateless invalid-output cases.
  - Current compiler candidate coverage includes:
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
  - Stateful or otherwise non-provable branches remain candidate-unavailable for now, including:
    - malformed-think family driven by repeat-count state
    - empty/whitespace followups that do not enter the reject path
  - `resolve_prevalidation_reject_invalid_output_authority(...)` now compares:
    - legacy decision
    - compiler candidate availability
    - decision-shape agreement
    - prompt-equivalence proof
  - Added diagnostic fields for this comparison:
    - `compiler_recovery_action`
    - `compiler_recovery_reason`
    - `compiler_recovery_prompt_kind`
    - `compiler_decision_available`
    - `decision_agreement`
    - `prompt_equivalent`
    - `candidate_source`
  - Smoke switch decision:
    - deferred
    - reason: the branch now has a real candidate path, but coverage is still partial and branch-wide compiler authority would be misleading until the remaining unsupported cases are either modeled or explicitly fenced
  - Boundary:
    - no production behavior changed
    - default registry remains `legacy`
    - smoke registry remains `legacy` for this branch
    - effective recovery decision remains legacy-owned
  - Recommended next step:
    - `Phase 29 Step 9: Recovery Prevalidation Reject-Invalid-Output Smoke Switch Validation`
- **Phase 29 Step 9: Recovery Prevalidation Reject-Invalid-Output Fenced Smoke Switch Validation (Complete)**
  - Enabled the smoke-only switch:
    - `recovery.prevalidation_reject_invalid_output = "compiler"` in [refactor_switches.smoke.toml](/home/romankozak/studio/public/it/angelica-ai/modules/agent/orchestration/config/refactor_switches.smoke.toml)
  - Default registry remains:
    - `recovery.prevalidation_reject_invalid_output = "legacy"` in [refactor_switches.toml](/home/romankozak/studio/public/it/angelica-ai/modules/agent/orchestration/config/refactor_switches.toml)
  - Fenced compiler selection is now synthetically validated for candidate-covered, agreement-proven cases only.
  - Positive smoke compiler-selected cases:
    - `malformed_action`
    - `mixed_visible_text_and_control_protocol`
    - `mixed_intent_transition_and_visible_answer`
  - Unsupported or stateful branches remain fenced behind legacy fallback:
    - malformed-think / unclosed-think family
    - memory tag inside think
    - checkpoint/subgoal inside think
    - empty/whitespace followups that never enter the reject path
  - Selection fence remains:
    - `compiler_decision_available=True`
    - `decision_agreement=True`
    - `prompt_equivalent=True`
    - otherwise `authority_source="legacy_fallback"`
  - Boundary:
    - no production behavior changed
    - no recovery routing decisions changed
    - no output recovery prompt selection changed
    - default registry remains `legacy`
    - runtime outcomes remain behavior-preserving with `behavior_changed=False`
  - Recommended next step:
    - `Phase 29 Step 10: Recovery Prevalidation Reject-Invalid-Output Closure / Next Recovery Branch Selection`
- **Phase 29 Step 10: Recovery Prevalidation Reject-Invalid-Output Closure / Next Recovery Branch Selection (Complete)**
  - Closed `recovery.prevalidation_reject_invalid_output` as a smoke-validated fenced compiler-authority slice.
  - The branch now has:
    - resolver/accessor coverage
    - effective decision consumption
    - compiler decision candidate builder
    - default `legacy` switch
    - smoke-only `compiler` switch
    - positive compiler-selected synthetic cases
    - explicit legacy fallback for unsupported/stateful cases
    - behavior-preserving outcomes
  - Clarification:
    - `mixed_intent_transition_and_visible_answer` is a recovery-active intent-followup prevalidation case.
    - It is not normal terminal plaintext authority.
  - Default registry remains `legacy`.
  - Smoke compiler mode remains enabled only in the smoke profile for this branch.
  - No production authority flip happened.
  - No recovery routing decisions changed.
  - No output recovery prompt selection changed.
  - Selected next recovery branch:
    - `recovery.leaked_system_result`
  - Selection rationale:
    - safety-critical branch
    - typed signal already exists
    - high-value semantic policy authority target
    - better next return than lower-value invalid/truncated cleanup or heavier stateful guard migration
  - Recommended next step:
    - `Phase 29 Step 11: Leaked-System-Result Recovery Authority Candidate`
- **Phase 29 Step 11: Leaked-System-Result Recovery Authority Candidate (Complete)**
  - Inventory outcome:
    - runtime owner is the post-classification no-action leak guard in [response_pipeline_stages.py](/home/romankozak/studio/public/it/angelica-ai/modules/agent/orchestration/responses/response_pipeline_stages.py)
    - typed leak signal comes from `TerminalAnswerKind.LEAKED_SYSTEM_RESULT`
    - legacy fallback remains `is_leaked_system_result(response)`
    - current recovery outcome remains:
      - `continue_loop=True`
      - `reason="leaked_system_result_in_assistant_text"`
      - `source="output_recovery"`
      - leak recovery prompt from `build_leaked_system_result_recovery_prompt()`
  - Added `resolve_leaked_system_result_recovery_authority(...)` in [recovery_authority.py](/home/romankozak/studio/public/it/angelica-ai/modules/agent/orchestration/responses/recovery_authority.py).
  - Added `build_typed_leaked_system_result_recovery_decision_candidate(...)` for the typed leak path.
  - The branch now has:
    - resolver/accessor coverage
    - behavior-preserving effective decision consumption
    - default `legacy` switch
    - smoke-only `compiler` switch
    - canonical compiler-selected synthetic coverage
    - explicit legacy fallback when only the legacy accessor detects the leak
  - Smoke switch decision:
    - enabled
    - reason: the branch already had a real typed-primary signal and a fixed recovery outcome, so fenced compiler selection can be validated without changing behavior
  - Positive compiler-selected cases:
    - canonical `SYSTEM RESULT: ...`
  - Fallback-preserved cases:
    - surrounding visible text with embedded `SYSTEM RESULT: ...`
    - action-bearing responses
    - internal-summary-like text
    - checkpoint marker only
    - malformed/unclosed think without leak text
  - Boundary:
    - no production behavior changed
    - default registry remains `legacy`
    - smoke registry enables `recovery.leaked_system_result = "compiler"`
    - no recovery routing decisions changed
    - no output recovery prompt selection changed
    - leaked system result still cannot become a final answer
- **Phase 29 Step 12: Leaked-System-Result Recovery Closure / Next Recovery Branch Selection (Complete)**
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
- **Phase 29 Step 13: Invalid-Truncated Terminal Text Recovery Authority Candidate (Complete)**
  - Added `resolve_invalid_truncated_terminal_text_recovery_authority(...)` in [recovery_authority.py](/home/romankozak/studio/public/it/angelica-ai/modules/agent/orchestration/responses/recovery_authority.py).
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
- **Phase 29 Step 14: Invalid-Truncated Terminal Text Smoke Switch Validation (Complete)**
  - **NO-GO** for smoke switch enablement.
  - The `INVALID_OR_TRUNCATED_TERMINAL_TEXT` branch is currently diagnostic-only in the post-classification path.
  - It correctly identifies typed invalid/truncated text, but there is no corresponding legacy recovery decision to preserve or replace in this path.
  - Enabling a smoke compiler switch would be misleading, as it would claim authority over a decision that is not being made.
  - The branch remains a typed characterization signal only for now.
  - Added synthetic smoke coverage for incomplete sentences and negative controls.
  - No production behavior changed.
  - Default and smoke registries remain `legacy` for this branch.
- **Phase 29 Step 15: Recovery Invalid-Truncated Boundary Closure / Remaining Recovery Branch Decision (Complete)**
  - Closed the `recovery.invalid_truncated_terminal_text` branch as a diagnostic-only characterization.
  - The branch has resolver/accessor coverage and synthetic tests, but no recovery decision ownership.
  - The smoke switch remains `legacy` because enabling compiler authority would be misleading.
  - Future work on this branch is deferred until a runtime policy decision is made to actively recover from invalid/truncated terminal text.
  - Decision: Close Phase 29. The core recovery architecture is significantly advanced. Remaining branches (`internal_summary`, stateful guards) are deferred to avoid expanding into deep policy or stateful harness work.
- **Phase 29 Step 16: Recovery Core Closure / Next Phase Selection (Complete)**
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
  - Recommended next step: `Phase 30 Step 1: Board/Memory Commit Policy Inventory + Commit-Equivalence Harness Plan`.
- **Phase 30 Step 1: Board/Memory Commit Policy Inventory + Commit-Equivalence Harness Plan (Complete)**
  - **Inventory Outcome**:
    - **Owners**: `MemoryBoardStageHandler` and `PlanBoardStageHandler` are the legacy owners, orchestrated by `_run_checkpoint_stage`.
    - **Commit Semantics**: `MemoryBoardStageHandler` has embedded side effects, including memory-engine commits and state updates (`accepted_count`, `next_query`). This is more than classification; it is stateful commit policy.
    - **Available Facts**: `board_checkpoint_models.py` and `board_checkpoint_semantics.py` provide typed observational data, but this is not yet sufficient for commit authority.
    - **Blockers**:
      - Memory commit logic is not a pure function.
      - No typed model for a memory commit *decision* exists.
      - State effects (`accepted_count`, `next_query`) are computed inside legacy handlers.
      - Insufficient synthetic test coverage for commit equivalence.
  - **Harness Plan**:
    - A future `tests/test_board_memory_commit_equivalence.py` will compare legacy vs. candidate paths.
    - The harness must assert equivalence across multiple dimensions: `handled`, `reason`, `source`, `response_text`, `next_query`, memory commit effects, and state flags.
    - The first step is to build a harness that captures a structured snapshot of the legacy path's behavior.
  - **First Candidate**:
    - The first implementation target for the commit-equivalence harness is `MEMORY_CHECKPOINT_ONLY`. It is the narrowest memory branch with no action or visible text, making it the best first target.
  - **Boundary**: This was a docs-only inventory and planning step. No runtime behavior was changed.
- **Phase 30 Step 2: Board/Memory Synthetic Commit-Equivalence Harness (Complete)**
  - Created `tests/test_board_memory_commit_equivalence.py` to characterize legacy memory commit behavior.
  - Implemented a synthetic harness that runs the `_run_checkpoint_stage` path with a controlled static memory stage, as the real `MemoryBoardStageHandler` has complex dependencies.
  - Added a `LegacyCommitSnapshot` dataclass to capture structured outcomes from the controlled stage.
  - Added positive snapshot coverage for `MEMORY_CHECKPOINT_ONLY`.
  - Added negative controls for plaintext, action-only, and plan-checkpoint-only to ensure they are not treated as memory commits.
  - Added characterization for `MEMORY_CHECKPOINT_WITH_TEXT` and `MEMORY_CHECKPOINT_WITH_ACTION`.
  - No production code was changed. No runtime behavior was changed.
- **Phase 30 Step 3: Real MemoryBoardStageHandler Commit Snapshot Hardening (Complete)**
  - The commit-equivalence harness in `tests/test_board_memory_commit_equivalence.py` was hardened to support snapshotting the real `MemoryBoardStageHandler`.
  - The `LegacyCommitSnapshot` model was improved to distinguish between `controlled_static` and `real_handler` modes and to capture `rejected_count`.
  - A new test, `test_memory_checkpoint_only_real_handler_snapshot`, now proves that the real handler can be instantiated and its commit behavior for `MEMORY_CHECKPOINT_ONLY` can be captured.
  - The real handler's dependencies (`agent`, `prompt_builder`, `memory_board_engine`) were mocked, and its `state` was wired to the harness's state to ensure accurate snapshotting.
  - No production behavior was changed.
- **Phase 30 Step 4: MEMORY_CHECKPOINT_ONLY Commit Candidate Model / Resolver Design (Complete)**
  - Added a typed `MemoryCommitCandidate` model and a `resolve_memory_checkpoint_only_commit_authority` resolver.
  - The candidate is intentionally narrow, available only for clean `MEMORY_CHECKPOINT_ONLY` cases, and blocks on commit-count equivalence.
  - The resolver compares the candidate to the legacy snapshot and produces a detailed authority diagnostic.
  - Added a `board_memory.memory_checkpoint_only` switch placeholder to the registries, with both default and smoke profiles set to `legacy`.
  - Added tests for candidate construction, legacy-mode resolution, and compiler-mode fallback.
  - No production authority was transferred, and no runtime behavior was changed.
- **Phase 30 Step 5: MEMORY_CHECKPOINT_ONLY Commit Equivalence Hardening (Complete)**
  - Hardened commit-equivalence validation for `MEMORY_CHECKPOINT_ONLY` using an "observed-equivalence" model.
  - The resolver now proves `commit_equivalent=True` for clean cases by checking if the observed legacy commit result (counts, query, etc.) is consistent with a `MEMORY_CHECKPOINT_ONLY` outcome. The typed candidate itself does not predict memory-engine-dependent values.
  - Added tests to validate full equivalence for the clean case and to confirm fallback on mismatch.
  - The `board_memory.memory_checkpoint_only` switch remains `legacy` in both default and smoke registries, as this step only proves equivalence, it does not enable the switch.
  - No runtime behavior was changed.
- **Phase 30 Step 6: MEMORY_CHECKPOINT_ONLY Smoke Switch Validation (Complete)**
  - Enabled the `board_memory.memory_checkpoint_only` switch in the smoke-test profile only.
  - Added synthetic tests to `tests/test_board_memory_commit_equivalence.py` that validate compiler authority is selected for clean, observed-equivalent `MEMORY_CHECKPOINT_ONLY` cases under the smoke profile.
  - Fallback controls confirm that mismatched or non-eligible cases still use legacy authority.
  - The default registry remains `legacy`, and no production behavior was changed.
- **Phase 30 Step 7: MEMORY_CHECKPOINT_ONLY Live/Integrated Smoke or Closure Decision (Complete)**
  - **Decision**: **NO-GO** for live/integrated smoke at this time.
  - **Blocker**: The `resolve_memory_checkpoint_only_commit_authority` resolver is not yet integrated into the runtime pipeline (`_run_checkpoint_stage`), so authority selection cannot be observed in a live run.
  - The slice is closed as an "integrated observability blocker".
  - No runtime behavior was changed.
- **Phase 30 Step 8: Board/Memory Commit Authority Runtime Diagnostic Integration (Complete)**
  - The `resolve_memory_checkpoint_only_commit_authority` resolver is now integrated into `_run_checkpoint_stage` for diagnostic logging only.
  - A new `_log_board_memory_commit_authority_resolution` helper was added to log the diagnostic output.
  - The resolver's `effective_commit` is not used, and no runtime behavior was changed.
- **Phase 30 Step 9: Runtime Diagnostic Real-Handler Commit Field Hardening (Complete)**
  - Hardened the diagnostic integration to correctly read commit evidence from real-handler state fields (`last_memory_board_accepted_count`, etc.).
  - The diagnostic resolver input now safely falls back from the memory decision object to the agent state fields.
  - This remains a diagnostic-only change. No runtime behavior was changed.
- **Phase 30 Step 10: MEMORY_CHECKPOINT_ONLY Live Smoke Validation (Complete)**
  - Live smoke was run for `<memory_update_done />` under the smoke profile.
  - **Result**: NOT A PASS. `commit_equivalent` was `False`, causing a fallback to legacy.
  - **Root Cause**: The live `MemoryBoardStageHandler` correctly reported `accepted_count=0` for a marker-only checkpoint, but the synthetic equivalence model expected `accepted_count=1`.
  - **Next Step**: `Phase 30 — Step 11/11: MEMORY_CHECKPOINT_ONLY Live Semantics Reconciliation / Closure Decision`.
- **Phase 30 Step 11: MEMORY_CHECKPOINT_ONLY Live Semantics Reconciliation (Complete)**
  - The `resolve_memory_checkpoint_only_commit_authority` resolver was updated to correctly handle marker-only checkpoints (`accepted_count=0`).
  - Live behavior showed `<memory_update_done />` has `accepted_count=0`. The model now treats this zero-count continuation as valid observed equivalence.
  - Synthetic tests in `tests/test_board_memory_commit_equivalence.py` were updated to reflect this live-faithful behavior.
  - Content-bearing memory update authority remains out of scope/deferred until its real protocol syntax and typed classification are identified.
  - No runtime behavior was changed.
- **Phase 30 — Step 12/12: MEMORY_CHECKPOINT_ONLY Closure / Remaining Board-Memory Branch Selection (Complete)**
  - The `MEMORY_CHECKPOINT_ONLY` slice is now closed.
  - A second live smoke run was not required, as the synthetic reconciliation in Step 11 was sufficient to align the model with observed live behavior.
  - The branch now has: real-handler snapshot coverage, a candidate/resolver model, an observed-equivalence model, runtime diagnostic integration, state-field hardening, a smoke-only compiler switch, synthetic smoke validation, and live semantics reconciliation.
  - All tests are green.
  - The default registry remains `legacy`, and the smoke registry keeps `board_memory.memory_checkpoint_only = "compiler"`.
  - No production behavior was changed.
  - **Next Phase**: `Phase 31 — Step 1/10: MEMORY_CHECKPOINT_WITH_TEXT Commit Policy Inventory / Harness Plan`.
- **Phase 31 — Step 1/10: MEMORY_CHECKPOINT_WITH_TEXT Commit Policy Inventory / Harness Plan (Complete)**
  - **Inventory Outcome**:
    - **Owner**: `MemoryBoardStageHandler` owns the initial detection of `MEMORY_CHECKPOINT_WITH_TEXT`.
    - **Behavior**: It detects `<memory_update_done />` and visible text, strips the marker, and passes the remaining text to the next pipeline stage for final-answer evaluation.
    - **Commit Semantics**: For a marker-only response with text, `accepted_count` is `0`. `last_memory_update_done` is set to `True`.
    - **Blockers**: The primary blocker is ensuring that any future compiler-driven path perfectly preserves the visible text and the `handled=False` pass-through behavior that allows the final-answer path to continue.
  - **Harness Plan**: The commit-equivalence harness will be extended to capture `MEMORY_CHECKPOINT_WITH_TEXT` snapshots, asserting that visible text is preserved and the pipeline continues correctly.
  - **Boundary**: This was a docs-only inventory and planning step. No runtime behavior was changed.
- **Phase 31 — Step 2/10: MEMORY_CHECKPOINT_WITH_TEXT Synthetic Commit-Equivalence Harness (Complete)**
  - The commit-equivalence harness was extended to cover `MEMORY_CHECKPOINT_WITH_TEXT`.
  - A real-handler snapshot test now characterizes the branch's behavior, including:
    - visible text preservation (`Done.`)
    - marker stripping (`<memory_update_done />`)
    - pass-through behavior (`handled=False`) to allow final-answer evaluation
    - zero-count memory commit (`accepted_count=0`)
  - Negative controls were added to ensure other branches are not misclassified.
  - No runtime behavior was changed, and no authority was transferred.
- **Phase 31 — Step 3/10: MEMORY_CHECKPOINT_WITH_TEXT Candidate Model / Resolver Design (Complete)**
  - Added a typed `MemoryCommitCandidate` model and a `resolve_memory_checkpoint_with_text_commit_authority` resolver.
  - The candidate model and resolver cover visible text preservation, pass-through behavior, and zero-count commit semantics for marker-with-text.
  - The `board_memory.memory_checkpoint_with_text` switch placeholder remains `legacy` in both default and smoke registries.
  - No runtime behavior was changed, and no authority was transferred.
- **Phase 31 — Step 4/10: MEMORY_CHECKPOINT_WITH_TEXT Commit Equivalence Hardening (Complete)**
  - Hardened commit-equivalence validation for `MEMORY_CHECKPOINT_WITH_TEXT`.
  - A clean real-handler case now proves full `commit_equivalent=True`, while any mismatch correctly falls back to legacy.
  - No runtime behavior was changed, and no authority was transferred.
  - The smoke switch remains `legacy`.
- **Phase 31 — Step 5/10: MEMORY_CHECKPOINT_WITH_TEXT Smoke Switch Validation (Complete)**
  - Enabled the smoke-only compiler switch for `board_memory.memory_checkpoint_with_text`.
  - The default registry remains `legacy`.
  - Clean real-handler MCT now selects compiler authority under the smoke profile.
  - Fallback controls correctly remain on legacy authority when equivalence mismatches.
  - Negative controls for other branches do not select compiler authority.
  - No production behavior was changed, and no authority was transferred in the default profile.
  - The resolver's `effective_commit` is still not consumed by the runtime.
- **Phase 31 — Step 6/10: MEMORY_CHECKPOINT_WITH_TEXT Runtime Diagnostic Integration or Live Observability Decision (Complete)**
  - Live observability required runtime diagnostic integration.
  - Added a diagnostic-only call to the `resolve_memory_checkpoint_with_text_commit_authority` resolver in `_run_checkpoint_stage`.
  - Reused the existing `_log_board_memory_commit_authority_resolution` helper for logging.
  - The resolver's `effective_commit` is not consumed, and no runtime behavior was changed.
  - The default registry remains `legacy`, and the smoke registry remains `compiler` for this branch.
- **Phase 31 — Step 7/10: MEMORY_CHECKPOINT_WITH_TEXT Live Smoke Validation (Complete)**
  - **Result**: NOT A PASS.
  - Live smoke was run for `<memory_update_done />\nDone.` under the smoke profile.
  - The `board_memory_commit_authority_resolution` diagnostic was observable, but it reported `commit_equivalent=False` and fell back to legacy.
  - **Root Cause**: The exact agreement mismatch was not visible in the diagnostic log.
  - **Next Step**: `Phase 31 — Step 8/10: MEMORY_CHECKPOINT_WITH_TEXT Live Semantics Reconciliation`.
- **Phase 31 — Step 8/10: MEMORY_CHECKPOINT_WITH_TEXT Live Semantics Reconciliation (Complete)**
  - **Completed Outcome**:
    - Detailed live diagnostics identified the exact mismatch: only `commit_attempted_agreement` was `False`.
    - Live MCT marker-with-text has zero parsed/accepted/rejected counts.
    - The candidate/resolver model is now live-faithful: marker-with-text is treated as a pass-through, not a content commit attempt (`expected_commit_attempted=False`).
    - No runtime behavior was changed.
    - The resolver's `effective_commit` is still not consumed.
- **Phase 31 — Step 9/10: MEMORY_CHECKPOINT_WITH_TEXT Live Smoke Re-run / Closure Decision (Complete)**
  - **Completed Outcome**:
    - Manual live smoke re-run passed.
    - MCT diagnostic showed `switch_value="compiler"`, `authority_source="compiler"`, `selected_by_switch=True`, `candidate_available=True`, and `commit_equivalent=True`.
    - All detailed agreement fields relevant to MCT were `True`.
    - Runtime behavior was preserved: `behavior_changed=False`, `shadow_only=True`.
    - The resolver's `effective_commit` is still not consumed.
- **Phase 31 — Step 10/10: MEMORY_CHECKPOINT_WITH_TEXT Closure / Next Branch Selection (Complete)**
  - **Completed Outcome**:
    - The `MEMORY_CHECKPOINT_WITH_TEXT` slice is closed.
    - The branch now has: real-handler snapshot coverage, a candidate/resolver model, full commit-equivalence hardening, a smoke-only compiler switch, runtime diagnostic integration, detailed agreement-field logging, live semantics reconciliation, and passing manual live smoke validation.
    - Default registry remains `legacy`.
    - Smoke registry keeps `board_memory.memory_checkpoint_with_text = "compiler"`.
    - No production behavior was changed.
    - The resolver's `effective_commit` is still not consumed.
    - Selected next branch: `MEMORY_CHECKPOINT_WITH_ACTION`.
- **Phase 32 — Step 1/8: Invalid Path + Atomic Bundle Recovery Characterization (Complete)**
  - **Completed Outcome**:
    - Narrowed root cause from path recovery to failure-mode atomic bundle rejection.
    - Characterized that valid intent+single-action bundles after recoverable failure should be protocol-valid.
    - Updated tests in `tests/test_response_pipeline_stages.py` to distinguish protocol validity from action/tool feasibility.
    - No runtime behavior was changed.
    - No search or path normalization logic was changed.
- **Phase 32 — Step 2/8: Permit Valid Intent+Single-Action Bundles after Recoverable Failure (Complete)**
  - **Completed Outcome**:
    - The `intent_atomic_bundle_guard` in `_reject_invalid_atomic_bundle_before_transition` no longer rejects structurally valid intent+single-action bundles during retry/continuation-after-failure.
    - Mutating actions are not rejected at this layer solely because they are mutating.
    - Normal action/tool policy still applies.
    - Malformed and unsupported multi-action bundles remain blocked.
    - No Angelica/live agent was run.
- **Phase 32 — Step 3/8: E_ACTION_PAYLOAD_ARRAY / Read-only Multi-action Discovery Bundle Characterization (Complete)**
  - **Completed Outcome**:
    - Characterized that the current runtime/compiler treats one-intent multi-action output as invalid (`E_ACTION_PAYLOAD_ARRAY` / `multiple_actions`).
    - Added characterization tests for 3 read-only discovery actions.
    - Added negative controls for >3 actions, mixed read/write, and `run_shell`.
    - The future target is bounded read-only discovery batch support.
    - No tool execution behavior was changed.
    - No Angelica/live agent was run.
- **Phase 32 — Step 4/8: Read-only Multi-action Discovery Bundle Support (Complete)**
  - **Completed Outcome**:
    - Bounded one-intent read-only discovery bundles with 2–3 actions are now protocol-valid.
    - No tool execution behavior changed.
    - Mutating, run_shell, malformed, >3 actions, and unbounded discovery bundles remain blocked.
    - This reduces recovery/discovery round-trips for common “inspect/search docs” model outputs.
    - No Angelica/live agent was run.
- **Phase 32 — Step 4.5/8: Extracted Intent Payload + Single Action Recovery Bundle Reconciliation (Complete)**
  - **Completed Outcome**:
    - Smoke dump showed live path extracted intent payload before prevalidation, leaving compiler shape as ACTION_ONLY.
    - `_reject_invalid_atomic_bundle_before_transition` now treats extracted `step.intent_payload` as valid intent context for recoverable-failure recovery bundles.
    - Valid extracted-intent + single-action bundles after recoverable failure are no longer blocked by `retry_or_continuation_after_failure`.
    - Action-only without extracted intent remains blocked.
    - Malformed and unsupported multi-action bundles remain blocked.
    - Mutating single actions are not blocked at this layer solely because they are mutating.
    - Normal action/tool policy still applies.
    - No tool execution behavior changed.
    - No search/path normalization changed.
    - No Angelica/live agent was run.
- **Phase 32 — Step 5/8: Structure-only Think Repair Atomicity Characterization (Complete)**
  - **Completed Outcome**:
    - Characterized current behavior where possible think repair can be blocked by atomicity constraints (e.g., when an intent payload is present).
    - Added a negative control for unsafe repairs that would alter intent/action semantics.
    - Added a future xfail test for structure-only think repair allowance.
    - No runtime behavior was changed.
    - No tool execution behavior was changed.
    - No search/path normalization was changed.
    - No Angelica/live agent was run.
- **Phase 32 — Step 4.6/8: Runtime-State Recoverable Failure Detection for Extracted Intent Bundles (Complete)**
  - **Completed Outcome**:
    - New smoke dump showed `step.intent_error` can be empty while recoverable failure exists in runtime state.
    - `_reject_invalid_atomic_bundle_before_transition` now detects recoverable failure from runtime/context state as well as step intent_error.
    - Extracted intent payload + single valid ACTION_ONLY recovery action now passes atomic bundle guard in this live shape.
    - Malformed and unsupported multi-action bundles remain blocked.
    - No tool execution behavior changed.
    - No search/path normalization changed.
    - No Angelica/live agent was run.
- **Phase 32 — Step 6/8: Structure-only Think Repair Allowance (Complete)**
  - **Completed Outcome**:
    - Structure-only trailing `</think>` repair is now allowed under atomicity constraints when protocol-relevant payloads are unchanged.
    - The allowance is intentionally narrow: currently only simple trailing think closure is allowed.
    - Repairs that alter action/intent/file/protocol blocks remain blocked.
    - Think repair inside action JSON remains blocked.
    - Malformed reuse/followup atomicity remains protected.
    - No tool execution behavior changed.
    - No search/path normalization changed.
    - No Angelica/live agent was run.
- **Phase 32 — Step 7/8: Broad Search Result Shaping (Complete)**
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
- **Phase 32 — Step 7.5/8: Stale Retry Guard Reconciliation (Complete)**
  - **Completed Outcome**:
    - `retry_or_continuation_after_failure` now requires an actual active recoverable failure context when `last_error_recoverable` is explicitly available.
    - Stale retry context with `last_error_recoverable=False` no longer blocks valid `ACTION_ONLY` recovery actions.
    - True recoverable failure behavior remains preserved.
    - No search shaping, tool execution, or path normalization was changed.
    - No Angelica/live agent was run.
- **Phase 32 — Step 8/8: Repeat Broad Search Guard / Path Memory Anchoring Decision (Complete)**
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
- **Phase 34 — Step 1/N: Think Boundary Auto-Closure Normalization (Complete)**
  - **Completed Outcome**:
    - Safe open `<think>` is auto-closed before known top-level protocol boundary tags and at EOF.
    - This intentionally changes prior E_UNCLOSED_THINK recovery behavior for safe boundary-repairable cases.
    - Protected contexts remain safe: action JSON, intent payloads, file_content, quoted strings, fenced code, inline code, comments.
    - Repair is normalization only; compiler/prevalidation/action policy still decide validity/dispatch.
    - Nested think stack semantics remain out of scope.
    - No Angelica/live agent was run.

- **Phase 35 — Step 1/10: MEMORY_CHECKPOINT_WITH_ACTION Commit Policy Inventory / Harness Plan (Complete)**
  - **Inventory Outcome**:
    - **Owner**: `MemoryBoardStageHandler` owns the initial detection of `MEMORY_CHECKPOINT_WITH_ACTION`.
    - **Behavior**: It detects `<memory_update_done />` and an action, strips the marker, and returns `handled=True`. The pipeline in `_run_checkpoint_stage` then overrides this to `handled=False` to ensure the action is passed through for dispatch.
    - **Commit Semantics**: A commit is attempted for the marker, resulting in `accepted_count=0` (similar to MCT). `last_memory_update_done` is set to `True`.
    - **Observation-Boundary Note**: A raw-response semantic pass may retain evidence that a memory checkpoint marker was present, while a post-handler / cleaned-response observation may classify the remaining payload as `ACTION_ONLY` after `MemoryBoardStageHandler` strips the marker. This distinction is critical for proving equivalence.
    - **Blockers**: The primary blocker is ensuring that any future compiler-driven path perfectly preserves the action and the `handled=False` pass-through behavior that allows dispatch to continue.
  - **Harness Plan**: The commit-equivalence harness will be extended to capture `MEMORY_CHECKPOINT_WITH_ACTION` snapshots, asserting that the action is preserved and the pipeline continues correctly to dispatch.
  - **Boundary**: This was a docs-only inventory and planning step. No production code or tests were changed.

- **Phase 35 — Step 2/10: MEMORY_CHECKPOINT_WITH_ACTION Synthetic Commit-Equivalence Harness (Complete)**
  - **Completed Outcome**:
    - The commit-equivalence harness was extended to cover `MEMORY_CHECKPOINT_WITH_ACTION`.
    - A real-handler-backed snapshot test using `MemoryBoardStageHandler` with a mocked board engine result now characterizes the branch's behavior, including:
      - action preservation and pass-through for dispatch (`handled=False`).
      - marker stripping.
      - zero-count memory commit (`accepted_count=0`).
    - The test explicitly documents the observation-boundary issue where the compiler shape is `ACTION_ONLY` even though a memory marker was present in the raw response.
    - Negative controls were added to ensure other branches are not misclassified.
    - No production code was changed, and no authority was transferred. Full real-handler / board-engine equivalence proof remains for later hardening steps if needed.

- **Phase 35 — Step 3/10: MEMORY_CHECKPOINT_WITH_ACTION Candidate Model / Resolver Design (Complete)**
  - **Completed Outcome**:
    - Added a typed `MemoryCommitCandidate` model and a `resolve_memory_checkpoint_with_action_commit_authority` resolver.
    - The candidate model and resolver cover action preservation, pass-through behavior, and zero-count commit semantics for marker-with-action.
    - The resolver is not yet wired into the runtime pipeline, and its `effective_commit` is not consumed.
    - The `board_memory.memory_checkpoint_with_action` switch placeholder was not added yet.
    - No runtime behavior was changed, and no authority was transferred.

- **Phase 35 — Step 4/10: MEMORY_CHECKPOINT_WITH_ACTION Commit-Equivalence Hardening (Complete)**
  - **Completed Outcome**:
    - Hardened the `MEMORY_CHECKPOINT_WITH_ACTION` candidate builder and resolver with more negative controls and stricter agreement checks.
    - Added tests for candidate availability negative controls and resolver fallback on various mismatches.
    - The resolver is still not wired into the runtime, and its `effective_commit` is not consumed.
    - No registry/switch changes were made.
    - No runtime behavior was changed.

- **Phase 35 — Step 5/10: MEMORY_CHECKPOINT_WITH_ACTION Smoke Switch Validation (Complete)**
  - **Completed Outcome**:
    - Added `board_memory.memory_checkpoint_with_action` to the switch registries, with `legacy` as default and `compiler` in the smoke profile.
    - Added synthetic tests to validate that compiler authority is selected for clean, observed-equivalent MCTA cases under the smoke profile, with fallback for mismatches and negative controls.
    - The default registry remains `legacy`.
    - The resolver is not yet wired into the runtime, and `effective_commit` is not consumed.
    - No production behavior was changed.

- **Phase 35 — Step 6/10: MEMORY_CHECKPOINT_WITH_ACTION Runtime Diagnostic Integration (Complete)**
  - **Completed Outcome**:
    - The `resolve_memory_checkpoint_with_action_commit_authority` resolver is now called from `_run_checkpoint_stage` for diagnostic logging only.
    - The resolver's `effective_commit` is not consumed, and no runtime behavior was changed.
    - The default registry remains `legacy`, and the smoke registry remains `compiler` for this branch for validation purposes.
    - No dispatch, action, or `MemoryBoardStageHandler` behavior was changed.

- **Phase 35 — Step 7/10: MEMORY_CHECKPOINT_WITH_ACTION Live Smoke Validation (Complete)**
  - **Completed Outcome**:
    - Manual live smoke was run for MCTA under the smoke profile.
    - The `board_memory_commit_authority_resolution` diagnostic was observable.
    - **Result**: NOT A PASS. `commit_equivalent` was `False` due to a mismatch in `commit_attempted_agreement`.
    - Runtime behavior was preserved: action pass-through was correct, and no behavior changed.
    - The resolver's `effective_commit` is not consumed.
- **Phase 35 — Step 8/10: MEMORY_CHECKPOINT_WITH_ACTION Live Semantics Reconciliation (Complete)**
  - **Completed Outcome**:
    - Live smoke confirmed MCTA diagnostic branch is emitted and action/pass-through behavior is preserved.
    - Reconciled MCTA commit semantics: bare marker + action does not count as a durable memory content commit attempt.
    - `expected_commit_attempted` is now `False` for marker-only + action in the candidate model.
    - No runtime behavior was changed.
    - `effective_commit` is still not consumed.
- **Phase 35 — Step 9/10: MEMORY_CHECKPOINT_WITH_ACTION Live Smoke Re-run / Closure Decision (Complete)**
  - **Completed Outcome**:
    - Manual live smoke re-run passed.
    - MCTA diagnostic showed `switch_value="compiler"`, `authority_source="compiler"`, `selected_by_switch=True`, `candidate_available=True`, and `commit_equivalent=True`.
    - All detailed agreement fields relevant to MCTA were `True`.
    - Runtime behavior was preserved: `behavior_changed=False`, `shadow_only=True`.
    - The resolver's `effective_commit` is still not consumed.
- **Phase 35 — Step 10/10: MEMORY_CHECKPOINT_WITH_ACTION Closure (Complete)**
  - Phase 35 is complete.
  - Clean bare marker + action reaches compiler authority in smoke profile with `commit_equivalent=True`.
  - Live semantics reconciliation recorded: bare marker + action does not count as durable memory content commit attempt.
  - Real memory-content commit + action remains separate future characterization.
  - No production behavior changed.
- **Phase 36 — Step 1/N: MEMORY_CONTENT_WITH_ACTION Commit Policy Characterization / Inventory (Complete)**
  - Inventoried the distinct live/runtime case where a checkpoint includes a durable memory content tag and an action.
  - This case is distinct from the Phase 35 bare-marker MCTA because it involves a durable content commit (`accepted_count=1`).
  - Added a characterization test to `tests/test_board_memory_commit_equivalence.py` to snapshot the legacy behavior.
  - No production behavior was changed.
- **Phase 36 — Step 2/N: MEMORY_CONTENT_WITH_ACTION Candidate / Resolver Model Design (Complete)**
  - Added a candidate builder and resolver for the distinct durable memory content + action case.
  - The model is distinct from the Phase 35 bare-marker MCTA model and uses `compiler_has_memory_tags` and the absence of `compiler_has_memory_checkpoint` to distinguish.
  - Added targeted tests for the new candidate/resolver, including negative controls for the bare-marker MCTA case.
  - No runtime behavior was changed.
  - No runtime diagnostic wiring was added, and `effective_commit` is not consumed.
  - No registry or default switch changes were made.

- **Phase 36 — Step 3/N: MEMORY_CONTENT_WITH_ACTION Commit-Equivalence Hardening / Smoke Switch Planning (Complete)**
  - Strengthened commit-equivalence tests and negative controls for the durable memory content + action case.
  - Documented the smoke switch plan for `board_memory.memory_content_with_action` without adding registry entries.
  - No runtime behavior was changed, no diagnostic wiring was added, and `effective_commit` is not consumed.
  - Phase 35 MCTA semantics remain unchanged.

- **Phase 36 — Step 5/N: MEMORY_CONTENT_WITH_ACTION Runtime Diagnostic Integration (Complete)**
  - The `resolve_memory_content_with_action_commit_authority` resolver is now called from `_run_checkpoint_stage` for diagnostic logging only.
  - The resolver's `effective_commit` is not consumed, and no runtime behavior was changed.
  - The default registry remains `legacy`, and the smoke registry remains `compiler` for this branch for validation purposes.
  - No dispatch, action, or `MemoryBoardStageHandler` behavior was changed.
  - Phase 35 MCTA semantics remain unchanged.

- **Phase 36 — Step 6/N: MEMORY_CONTENT_WITH_ACTION Runtime Diagnostic Smoke Validation (Complete)**
  - Manual/live smoke validated that the `board_memory.memory_content_with_action` diagnostic is emitted under the smoke profile.
  - The diagnostic selected compiler authority with `authority_source="compiler"`, `selected_by_switch=True`, and `commit_equivalent=True`.
  - Runtime behavior was preserved: the response pipeline reached dispatch, pre-dispatch reached dispatch-ready, and dispatch outcome evaluation proceeded.
  - `behavior_changed=True` was observed as a diagnostic-only branch-name delta, not runtime behavior transfer.
  - The resolver's `effective_commit` is not consumed.

- **Phase 36 — Step 7/N: MEMORY_CONTENT_WITH_ACTION Live Smoke Closure / Reconciliation Decision (Complete)**
  - No live semantics reconciliation is required.
  - The clean durable memory content + action case is validated in the smoke profile.
  - The diagnostic branch-name delta is documented and expected for compiler-selected `MEMORY_CONTENT_WITH_ACTION` because the legacy branch remains `MEMORY_CHECKPOINT_WITH_ACTION`.
  - Runtime behavior remains legacy/default-safe, and no production authority flip occurred.
  - Phase 35 MCTA semantics remain unchanged.

- **Phase 36 — Step 8/N: MEMORY_CONTENT_WITH_ACTION Closure / Next Branch Selection (Complete)**
  - Phase 36 is complete.
  - Durable memory content + action is characterized, modeled, smoke-switch validated, wired for diagnostic-only runtime logging, and live-smoke validated.
  - Clean durable memory content + action reaches compiler authority in the smoke profile with `commit_equivalent=True`.
  - The diagnostic-only branch-name delta remains expected and documented.
  - Runtime behavior remains legacy/default-safe, and `effective_commit` is not consumed.
  - Default registry remains `legacy`; smoke registry remains `compiler`.
  - Phase 35 MCTA semantics remain unchanged.
  - Next work should select the remaining board/memory branch or decide whether to close the board/memory commit-policy slice.

- **Phase 36 — Step 4/N: MEMORY_CONTENT_WITH_ACTION Smoke Switch Registration / Validation (Complete)**
  - Added the `board_memory.memory_content_with_action` switch key to the registries.
  - The default registry remains `legacy`, while the smoke registry uses `compiler`.
  - Added smoke validation tests for compiler selection and fallback.
  - No runtime behavior was changed, no diagnostic wiring was added, and `effective_commit` is not consumed.
  - Phase 35 MCTA semantics remain unchanged.

## Guiding Principles: Typed Accessors and Branch Authority Switches

As of Phase 10, the semantic runtime refactor adopts a new guiding principle for managing the transition from legacy to compiler-driven authority. The model is:

- **Accessors/Resolvers are the Common Consumption Path**: All consumption of compiler/typed semantic results must go through approved accessors or resolvers. Pipeline code must not read raw compiler facts directly for routing decisions.
- **Branch-Specific Authority Switches**: The authority for a specific semantic decision is controlled by an explicit, named switch. This switch determines whether the legacy implementation or the new compiler/typed implementation is authoritative.
- **Centralized Switch Registry**: All authority switches must be centrally registered and documented.
- **Validation Through Controlled Authority Transfer**: During development, compiler authority may be enabled for selected branches to force real-world validation via smoke tests.
- **Fix-Forward on Regressions**: If enabling compiler authority reveals regressions, the preferred path is to fix the underlying compiler or semantic extraction logic.

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
