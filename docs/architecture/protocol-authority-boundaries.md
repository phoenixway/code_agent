# Protocol Authority Boundaries

This document defines the strict separation of concerns between the Protocol Compiler and the Orchestration Runtime.

| Authority | Owner | Description |
|---|---|---|
| **Compiler Metadata** | Compiler | Purely structural facts derived from the compiler's analysis. Includes `error_code`, `recovery_id`, and structurally-derived `invalid_kind`. |
| **Compatibility Action Proposal** | Runtime | A broad, backward-compatible check for any "action-like" content. Used for recovery evidence. **Not** dispatch proof. Implemented by `ResponseSemantics.has_any_action_proposal`. |
| **Dispatch-Authoritative Action** | Runtime | The final decision that an action is structurally valid and allowed to proceed to dispatch. Owned by the `ResponsePipeline` and `ActionPolicy`. |
| **Compiler-Invalid Safety State** | Runtime | A state where `compiler_shape` is `INVALID`. In this state, any action-like content is considered recovery evidence, **never** dispatch evidence. |
| **Runtime Policy** | Runtime | All semantic and policy decisions, including `ActionPolicy`, evidence sufficiency, final answer correctness, and intent completion. |

## Critical Invariant

A response that the compiler deems structurally `INVALID` must **never** be dispatched, even if legacy parsing detects action-like segments. Such segments are considered **recovery evidence**, not dispatch evidence. This is a critical safety invariant.

---

## Consumer Inventory

This table documents every major consumer of response semantics, their current data sources, and their migration path. It is the primary artifact of the "Phase 2: Consumer Inventory" audit.

| Consumer | Current Source(s) | Semantic Meaning | Future Accessor | Risk | Next Phase? |
|---|---|---|---|---|---|
| **`ResponseSemantics.has_any_action_proposal`** | `parsed_output.has_action_segment`, `parsed_action_count`, `compiler_ir.action_ops` | Compatibility action proposal, recovery evidence | `accessors.has_any_action_proposal` | High | No |
| **`ResponsePipelinePrevalidationMixin._apply_compiler_diagnosis`** | `ProtocolCompiler.analyze()`, `compiler_analysis` fields | Compiler metadata, populates `RuntimeProtocolSemantics` | `accessors.analyze_and_populate_semantics` | High | No |
| **`OutputRecoveryRoutingMixin.decide`** | `parsed_output.invalid_kind`, `RuntimeProtocolSemantics`, `ResponseSemantics` | Recovery policy, routing | `accessors.get_recovery_strategy`, `accessors.is_unproven_modify_claim` | High | No |
| **`protocol_decision_bridge.resolve_protocol_authority`** | `parsed_output` (compiler fields, `invalid_kind`), `parsed_action_count` | Dispatch authority arbitration (compiler vs. legacy) | N/A authority bridge / later dedicated authority resolver | High | No |
| **`ModelOutputRecoveryHandler._has_any_action_proposal`** | `ResponseSemantics.has_any_action_proposal` | Compatibility action proposal | `accessors.has_any_action_proposal_compat` | Medium | Yes |
| **`ResponsePipelineStagesMixin._build_execution_plan`** | `compiler_ir`, runtime state | Execution commit | `accessors.get_action_ops`, `accessors.get_pre_action_text` | High | No |
| **`ResponseGuardPolicy.is_nonproductive_thinking_turn`** | `ResponseSemantics` helpers | Runtime policy (loop detection) | `accessors.has_substantial_think`, `accessors.has_any_action_proposal` | Medium | No |
| **`ActionPolicyHandler` bundle/command helpers** | `compiler_ir`, legacy `segments` | Dispatch authority, runtime policy | `accessors.get_action_ops` | High | No |
| **`TransitionFollowupSemantics`** | `ProtocolCompiler.analyze()` on fragments | Intent transition/followup policy | `accessors.get_followup_surface` | High | No |
| **`IntentTransitionHandler` followup helpers** | `TransitionFollowupSemantics`, regex | Intent transition/followup policy | `accessors.get_followup_surface` | High | No |
| **`IntentTransitionHandler` (plaintext completion)** | `sanitize_visible_text_for_user` (regex) | Final-answer/plaintext guard | `accessors.get_visible_text` | Medium | No/Later |
| **`PlanBoardStageHandler`** | Regex on raw response | Memory/subgoal/checkpoint policy | `accessors.has_action`, `accessors.has_subgoal_tags` | Medium | No/Later |
| **`MemoryBoardStageHandler`** | Regex on raw response | Memory/subgoal/checkpoint policy | `accessors.has_action`, `accessors.has_memory_tags` | Medium | No/Later |
| **`DispatchPipeline._build_execution_commit`** | `iteration.execution_plan` | Execution commit | N/A (already uses plan) | N/A | N/A |
| **`protocol_decision_bridge.compiler_invalid_kind_for_output`** | `parsed_output` compiler fields | Compiler metadata | `accessors.get_compiler_error` | Low | No |
| **`output_recovery_routing._resolved_invalid_kind`** | `parsed_output` fields, `compiler_invalid_kind_for_output` | Compiler metadata, recovery routing | `accessors.get_invalid_kind` | High | No |
| **`output_recovery_routing._compiler_strategy_decision`** | `output_recovery_compiler_metadata` | Compiler metadata, recovery routing | `accessors.get_recovery_strategy` | High | No |
| **`runtime_protocol_semantics.output_recovery_compiler_metadata`** | `RuntimeProtocolSemantics` or `parsed_output` | Compiler metadata | `accessors.get_compiler_metadata` | Low | Yes |
| **`ActionPolicyHandler._formal_intent_required_for_multi_write_flow`** | `compiler_ir`, `action_segments`, runtime state | Runtime policy (intent requirement) | `accessors.get_action_ops` | High | No |
| **`ResponsePipelinePrevalidationMixin._reject_compiler_invalid_atomic_bundle_before_transition`** | `compiler_error_code`, `invalid_kind` from `parsed_output` | Atomic bundle validation / dispatch authority boundary (compiler path) | N/A / later dedicated bundle validator | High | No |
| **`ResponsePipelinePrevalidationMixin._reject_invalid_atomic_bundle_before_transition`** | `compiler_error_code`, `invalid_kind`, `compiler_ir`, `segments`, `ActionPolicyHandler.validate_atomic_bundle_action` | Atomic bundle validation / dispatch authority boundary | N/A / later dedicated bundle validator | High | No |
| **`ResponsePipelinePrevalidationMixin._reject_truncated_terminal_completion_before_transition`** | `step.intent_payload`, `terminal_plaintext_completion_status(raw_response)` | Final-answer/plaintext guard | N/A / later terminal-answer validator | Medium | No |
| **`ResponsePipelineStagesMixin` (leaked system result check)** | `ResponseSemantics.looks_like_leaked_system_result` | Final-answer/plaintext guard | `accessors.is_leaked_system_result` | Medium | No |
| **`ResponsePipelineStagesMixin._log_semantic_shadow_disagreements`** | `compiler_analysis`, `ResponseSemantics` | Diagnostic-only semantic shadow logging | N/A (diagnostic) | do-not-migrate-yet | No |
| **`output_recovery_routing.output_recovery_structural_parity`** | `RuntimeProtocolSemantics`, `parsed_output` | Diagnostic-only structural parity check | N/A (diagnostic) | do-not-migrate-yet | No |
| **`search_quality.classify_search_action_quality`** | `action_payload` dict | Diagnostic-only | N/A (diagnostic) | do-not-migrate-yet | No |
| **`DispatchOutcomeHandler._extract_visible_text`** | `extract_visible_text_for_user` (regex) | Final-answer/plaintext guard | `accessors.get_visible_text` | Medium | No/Later |
| **`DispatchOutcomeHandler._strip_leaked_system_results_from_ui_text`** | Regex on raw response | Final-answer/plaintext guard | `accessors.get_visible_text` | Medium | No/Later |
| **`history.py`** | Various | History management (refactor blocked by constitution) | N/A | do-not-migrate-yet | No |

### Next Safe Implementation Candidates

Based on this inventory, the next safe and productive implementation steps for **Phase 3 (Accessor Module)** are:

1.  **Create `semantic_accessors.py`**: Implement a new module for semantic accessors with full test coverage.
2.  **Implement Compatibility and Recovery Helpers**: The first accessors to implement should be those that support recovery and compatibility, not dispatch authority. The only candidates for the initial implementation are:
    -   `get_compiler_metadata`
    -   `has_any_action_proposal_compat`
    -   `is_compiler_invalid`
    -   `is_compiler_invalid_with_legacy_action`
3.  **Behavior-Preserving Migration**: Once tested, low-risk consumers can be migrated to use these new accessors.

High-risk consumers related to dispatch authority, atomic bundle validation, and intent transition policy must **not** be migrated until the accessor module is stable and a new design is approved for those specific migrations.
