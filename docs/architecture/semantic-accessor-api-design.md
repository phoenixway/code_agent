# Semantic Accessor API Design (Phase 3)

- **Status**: Reviewed / Approved for initial implementation.
- **Scope approved only for**:
  - `get_compiler_metadata`
  - `has_any_action_proposal_compat`
  - `is_compiler_invalid`
  - `is_compiler_invalid_with_legacy_action`
- **Approval does not authorize**:
  - consumer migration
  - runtime policy changes
  - dispatch behavior changes
  - final-answer/sufficiency changes
  - intent transition changes
  - memory/plan board changes

---

This document defines the API for the `semantic_accessors` module, which is the core of the Semantic Runtime Migration.

## 1. Purpose and Guiding Principles

The `semantic_accessors` module will provide a single, testable access point for selected behavior-preserving semantic reads. It acts as a translation layer between the raw `ParsedModelOutput` (with its mix of legacy and compiler fields) and the rest of the runtime for specific, approved use cases.

- **Single Access Point**: For an approved set of use cases (initially compatibility shims and recovery metadata), consumers should use this module instead of direct field access.
- **Narrow Scope**: This module is **not** a universal replacement for all semantic checks. Runtime policy, dispatch authority, intent transition policy, final-answer/sufficiency, and board/checkpoint policy require separate design approval before being delegated to an accessor.
- **Behavior Preservation**: The initial accessors are designed to be behavior-preserving wrappers around existing logic. They centralize logic, but do not change it.
- **Compiler-First, Legacy-Aware**: Accessors prioritize data from `RuntimeProtocolSemantics` (the compiler's view) but maintain careful, explicit fallbacks to legacy fields to ensure backward compatibility during the migration.
- **Strict Authority Boundaries**: Accessors provide **structural facts**, not **policy decisions**. For example, an accessor can state `has_action`, but it cannot state `is_dispatch_allowed`. Dispatch authority remains with the runtime (`ActionPolicy`, `ResponsePipeline`).

## 2. Initial Accessor API

The initial implementation phase will focus on a small, safe set of accessors that support recovery and compatibility.

---

### `get_compiler_metadata(parsed_output)`

- **Purpose**: To provide a stable, centralized way to access compiler-derived metadata (`error_code`, `recovery_id`, `invalid_kind`) for recovery and diagnostic purposes. This accessor formalizes the logic currently in `output_recovery_compiler_metadata`.
- **Inputs**:
    - `parsed_output: ParsedModelOutput`
- **Output**: `dict[str, str]` containing `source`, `error_code`, `recovery_id`, and `invalid_kind`.
- **Source Priority**:
    1. Reads from `parsed_output.runtime_protocol_semantics` if it exists.
    2. Falls back to direct reads of `parsed_output.compiler_error_code`, `compiler_recovery_id`, and `invalid_kind`.
    3. If no compiler data is present, returns empty strings for compiler fields but preserves the legacy `invalid_kind`.
- **Fallback Behavior**: If `runtime_protocol_semantics` is missing, it gracefully falls back to raw `parsed_output` fields. If those are also missing, it returns a dictionary indicating the data is missing.
- **Authority Boundary**: **Structural Fact**. Provides compiler diagnostic metadata. It is **not** dispatch authority.
- **Non-Goals**: This function does not interpret the metadata or decide on a recovery strategy. That is the role of `OutputRecoveryRoutingMixin`.
- **Future Tests**:
    - **Source Priority**: Test that it correctly reads from `RuntimeProtocolSemantics` when present (source: `compiler`).
    - **Fallback**: Test that it falls back to `parsed_output.compiler_*` fields when `RuntimeProtocolSemantics` is absent (source: `parsed_output_compiler_fields`).
    - **`invalid_kind` Precedence**: Test that `invalid_kind` from `RuntimeProtocolSemantics` takes precedence over the legacy `invalid_kind` on `parsed_output`.
    - **Missing Data**: Test that it returns an empty structure (preserving legacy `invalid_kind`) when no compiler data is available (source: `missing`).

---

### `has_any_action_proposal_compat(parsed_output, parsed_action_count=0)`

- **Purpose**: To act as a behavior-preserving, backward-compatible replacement for `ResponseSemantics.has_any_action_proposal`. Its purpose is to detect any "action-like" content for **recovery and guardrail purposes only**.
- **Inputs**:
    - `parsed_output: ParsedModelOutput`
    - `parsed_action_count: int` (from legacy segment parsing)
- **Output**: `bool`
- **Source Priority**: Returns `True` if any of the following are true, checked in order:
    1. `parsed_action_count > 0`.
    2. The protected fallback: `parsed_output.compiler_ir.action_ops` is a non-empty list.
    3. `parsed_output.has_action_segment` is `True`.
- **Fallback Behavior**: If `compiler_ir` is missing, it relies solely on the legacy `parsed_action_count` and `has_action_segment` fields.
- **Authority Boundary**: **Compatibility Shim / Recovery Evidence**. This is a broad, non-authoritative check. A `True` result is **not** dispatch permission. It is used by guards like `is_nonproductive_thinking_turn` to see if the model *attempted* an action.
- **Non-Goals**: This function must **not** be used for dispatch decisions. It must **not** be replaced by a stricter check like `RuntimeProtocolSemantics.has_action` until all consumers are migrated and the compatibility shim is no longer needed.
- **Future Tests**:
    - **Legacy Action Count**: Test that it returns `True` if `parsed_action_count > 0`.
    - **Compiler IR Fallback**: Test that it returns `True` if `compiler_ir.action_ops` is a non-empty list, even if legacy checks are `False`. This protects the critical compatibility shim.
    - **Legacy Segment**: Test that it returns `True` if `parsed_output.has_action_segment` is `True`.
    - **No Action**: Test that it returns `False` if all checks are negative.

---

### `is_compiler_invalid(parsed_output)`

- **Purpose**: To provide a single, unambiguous signal of whether the protocol compiler found the response to be structurally invalid.
- **Inputs**:
    - `parsed_output: ParsedModelOutput`
- **Output**: `bool`
- **Source Priority**:
    1. Returns `not parsed_output.runtime_protocol_semantics.is_valid` if `RuntimeProtocolSemantics` is present.
    2. Falls back to checking if `parsed_output.compiler_shape == "INVALID"` or if `parsed_output.compiler_error_code` is a non-empty structural error code.
- **Fallback Behavior**: If no compiler information is available, it must return `False` to avoid incorrectly blocking a response that the compiler never analyzed.
- **Authority Boundary**: **Supreme Structural Fact**. A `True` result means the response is structurally invalid. Per the constitution, this response **must never be dispatched**.
- **Non-Goals**: This function does not provide the *reason* for the invalidity. Use `get_compiler_metadata` for that.
- **Future Tests**:
    - **RPS Source**: Test that it returns `True` if `RuntimeProtocolSemantics.is_valid` is `False`.
    - **Fallback Sources**: Test that it returns `True` if `compiler_shape` is `INVALID` or if `compiler_error_code` is set.
    - **Valid Case**: Test that it returns `False` if compiler analysis was successful (`is_valid` is `True` and no error code).
    - **No Compiler Data**: Test that it returns `False` if no compiler information is present at all, preventing incorrect blocking.

---

### `is_compiler_invalid_with_legacy_action(parsed_output, parsed_action_count=0)`

- **Purpose**: To detect the specific, high-risk condition where the compiler deems a response structurally invalid, but the broad compatibility check (`has_any_action_proposal_compat`) detects action-like content. This content can come from legacy parsers (`parsed_action_count`, `has_action_segment`) or the compiler's IR (`compiler_ir.action_ops`). This is the primary scenario the "Compiler `INVALID` Is Final" invariant is designed to protect against.
- **Inputs**:
    - `parsed_output: ParsedModelOutput`
    - `parsed_action_count: int`
- **Output**: `bool`
- **Logic**: This is a composition of other accessors:
    - `return is_compiler_invalid(parsed_output) and has_any_action_proposal_compat(parsed_output, parsed_action_count)`
- **Authority Boundary**: **Safety Check / Recovery Trigger**. A `True` result indicates that a dispatch would violate the constitution. The action-like content should be treated as **recovery evidence only**.
- **Non-Goals**: This is not a general-purpose validity check. It is a highly specific safety guard.
- **Future Tests**:
    - **Core Invariant**: Test that it returns `True` when `is_compiler_invalid` is `True` AND `has_any_action_proposal_compat` is `True`. This is the "recovery evidence only" case.
    - **Compiler Valid**: Test that it returns `False` if `is_compiler_invalid` is `False`.
    - **No Action Proposal**: Test that it returns `False` if `has_any_action_proposal_compat` is `False`.

## 3. Rejected Initial Accessors

The following accessors are **explicitly not part of the initial API design** because they touch on frozen runtime policies or require more complex design that is deferred to later phases.

- **`is_dispatch_allowed`**: Forbidden. Dispatch is a complex runtime policy owned by `ActionPolicy` and the response pipeline, not a simple semantic fact.
- **`is_valid_atomic_bundle`**: Forbidden. Bundle validation is a high-risk dispatch authority boundary that is frozen. It will be refactored in a later, dedicated phase.
- **`is_valid_terminal_answer` / `is_final_answer_sufficient`**: Forbidden. Final-answer and sufficiency logic is frozen by the constitution.
- **`get_followup_surface`**: Forbidden. Intent transition logic is complex and frozen.
- **`get_visible_text`**: Deferred. While seemingly simple, this is part of the final-answer guard logic, which is frozen. It will be migrated later.
- **`has_subgoal_tags` / `has_memory_tags`**: Deferred. These are part of the memory/plan checkpoint policy, which will be migrated in a later phase.

## 4. Implementation Phase Test Requirements

The implementation of the `semantic_accessors` module must be accompanied by a comprehensive test suite that validates not only the logic of each accessor but also the core invariants of the semantic runtime migration.

- **Unit Tests**: Each accessor function must have dedicated unit tests covering all logic paths, including source priority, fallbacks, and edge cases (e.g., `None` inputs, missing fields).
- **Parity Tests**: Where an accessor replaces existing logic (e.g., from `ResponseSemantics`), parity tests should be created to run both the old and new logic against a corpus of real-world responses, logging any disagreements. This ensures the migration is behavior-preserving.
- **Invariant Protection**: The test suite must include explicit tests that map to the `test-contracts.md` document. For example, tests must prove that a compiler-`INVALID` response with legacy action content is correctly identified as `is_compiler_invalid_with_legacy_action` and that `has_any_action_proposal_compat` correctly uses its fallbacks.
- **No Authority Creep**: Tests must confirm that no accessor returns a policy decision. For example, `has_any_action_proposal_compat` must not be a simple alias for a dispatch-authoritative check.

---

## Phase 4 Migration Design: `has_any_action_proposal`

- **Status**: Reviewed / Approved for implementation.
- **Scope approved only for**:
  - `ResponseSemantics.has_any_action_proposal` delegating to `semantic_accessors.has_any_action_proposal_compat`.
- **Approval does not authorize**:
  - Any other consumer migration.
- **Candidate**: `ResponseSemantics.has_any_action_proposal`
- **Target Accessor**: `semantic_accessors.has_any_action_proposal_compat`

### 1. Goal

To perform the first behavior-preserving migration of a consumer to the new `semantic_accessors` module. This task migrates the implementation of `ResponseSemantics.has_any_action_proposal` to delegate directly to `semantic_accessors.has_any_action_proposal_compat`.

### 2. Analysis of Current Behavior

The intended migration is behavior-preserving if the current implementation checks the same three sources with equivalent OR semantics. Both the accessor and the current implementation must check for an action proposal from any of these sources:
1.  A non-zero `parsed_action_count` (from legacy segment parsing).
2.  The presence of `action_ops` in `compiler_ir` (the critical compatibility shim).
3.  A `True` value for the legacy `has_action_segment` flag.

### 3. Proposed Change

The implementation of `ResponseSemantics.has_any_action_proposal` will be replaced with a direct call to the accessor. This is a pure delegation.

**Implementation (for Phase 4 Implementation step):**
```python
# at top of modules/agent/orchestration/responses/response_semantics.py
from .semantic_accessors import has_any_action_proposal_compat

# in ResponseSemantics class
def has_any_action_proposal(self, parsed_output, parsed_action_count: int) -> bool:
    return has_any_action_proposal_compat(parsed_output, parsed_action_count)
```

### 4. Behavior Preservation and Invariant Protection

- **Behavior Preservation**: The migration is behavior-preserving because the accessor's logic is designed to be identical to the logic it replaces.
- **`parsed_action_count`**: The `parsed_action_count` argument is passed directly through to the accessor.
- **`compiler_ir.action_ops` Fallback**: The critical compatibility shim that checks `compiler_ir.action_ops` is preserved, satisfying a key constitutional requirement.
- **Authority Boundary**: This change does not alter the authority model. The function's output remains **recovery evidence only**, not dispatch permission.

### 5. Test Plan

1.  **Run All Existing Tests**: The full test suite will be run to ensure no regressions.
2.  **Verify Key Consumer Tests**: The existing tests in `tests/test_response_guards.py` and `tests/test_response_semantics.py` that consume this function will be used to verify behavior preservation.
3.  **Add Behavior and Delegation Tests**: New tests will be added to `tests/test_response_semantics.py`:
    -   Verify that `ResponseSemantics.has_any_action_proposal` continues to return `True` when `parsed_action_count > 0`.
    -   Verify it returns `True` when `compiler_ir.action_ops` is non-empty (the critical shim).
    -   Verify it returns `True` when `has_action_segment` is `True`.
    -   Verify it returns `False` when there is no action proposal.
    -   Add a mock-based test to explicitly verify that it delegates its call to `semantic_accessors.has_any_action_proposal_compat`.

### 6. Explicit Non-Goals

This design is strictly limited to the delegation described above. It does **not** include changes to `ActionPolicy`, dispatch behavior, output recovery, final-answer/sufficiency, intent transitions, or memory/plan boards.

---

## Phase 4 Batch Migration Planning

- **Status**: Reviewed / Approved for implementation.
- **Approval Scope**: This approval applies *only* to the two call sites listed in this batch. It does not authorize any other consumer migration or helper function deletion.

### 1. Goal

To identify the next safe, behavior-preserving consumer migrations that can use the existing, approved `semantic_accessors`.

### 2. Consumer Analysis

An analysis of the `Consumer Inventory` table reveals the following categories of remaining consumers:

-   **A. Safe Immediate Wrapper Candidates**: Low-risk consumers whose current logic can be replaced by a direct call to an existing accessor.
-   **B. Needs New Accessor Design**: Consumers whose logic is a good candidate for centralization but requires a new accessor not yet in the approved API.
-   **C. Later Validator/Policy Phase**: High-risk consumers tied to dispatch authority, runtime policy, or other frozen areas.
-   **D. Do Not Touch**: Consumers that are already migrated, diagnostic-only, or explicitly blocked.

### 3. Proposed Migration Batch 1

Based on the analysis, the following two consumers are identified as safe, high-value candidates for a batch migration. They are pure wrappers and do not change any runtime behavior.

1.  **`OutputRecoveryRoutingMixin._compiler_strategy_decision`**
    -   **Source**: `runtime_protocol_semantics.output_recovery_compiler_metadata`
    -   **Target Accessor**: `semantic_accessors.get_compiler_metadata`
    -   **Proposed Change**: In `_compiler_strategy_decision`, replace the call to `output_recovery_compiler_metadata` with a direct call to `semantic_accessors.get_compiler_metadata`.
    -   **Justification**: `get_compiler_metadata` was designed as a direct, behavior-preserving replacement for this helper.
    -   **Constraint**: Batch 1 may update only the selected call site. The existing helper function must remain in place. Deprecation/removal requires a later cleanup design.

2.  **`ModelOutputRecoveryHandler._has_any_action_proposal`**
    -   **Consumer**: `ModelOutputRecoveryHandler.decide`
    -   **Current Implementation**: A method on `ModelOutputRecoveryHandler` that delegates to `ResponseSemantics.has_any_action_proposal`.
    -   **Proposed Change**: Replace the internal call to `self.semantics.has_any_action_proposal` with a direct call to `semantic_accessors.has_any_action_proposal_compat`.
    -   **Justification**: This continues the migration of `has_any_action_proposal` consumers, moving one step closer to the source and further isolating `ResponseSemantics`.
    -   **Constraints**:
        - The change may only replace the internal compatibility-action-proposal read.
        - It must preserve the forwarding of `parsed_action_count`.
        - The result must remain recovery evidence only, not dispatch permission.

### 4. Next Step

-   Review and approve this batch migration plan.
-   Implementation is blocked until approval is granted.

---

## Phase 4 Batch 2 Planning: Fast-Lane Exhausted

- **Status**: Planning complete. Awaiting review and approval for next design phase.

### 1. Goal

To identify if any remaining consumers in the inventory can be safely migrated using only the existing approved accessors.

### 2. Conclusion: Fast-Lane Exhausted

A review of the `Consumer Inventory` confirms that all remaining safe, low-risk "fast-lane" migration candidates have been addressed in Step 1 and Batch 1.

All other consumers fall into one of these categories:
- They are part of a frozen, high-risk policy domain (e.g., `ActionPolicy`, dispatch authority, intent transitions).
- They require new accessor functions that have not yet been designed or approved.

**Therefore, the fast-lane for behavior-preserving wrapper migrations with the current accessor set is exhausted.**

### 3. Recommendation: Design Next Accessor Batch

The next logical step is to begin the API design for the next batch of semantic accessors. The following are proposed as candidates for the next design phase, as they represent useful, lower-risk semantic reads that can unblock further migrations:

- **`has_substantial_think`**: For migrating `ResponseGuardPolicy.is_nonproductive_thinking_turn`.
- **`get_visible_text`**: For migrating plaintext/final-answer guards in `IntentTransitionHandler` and `DispatchOutcomeHandler`.
- **`is_leaked_system_result`**: For migrating the guard in `ResponsePipelineStagesMixin`.

Implementation of these accessors is blocked until a formal API design is documented and approved.

---

## Next Accessor Batch Design (Proposed)

- **Status**: Design Proposed. Awaiting review and approval for implementation.
- **Scope**: This design covers two new, low-risk accessors.
- **Implementation**: Not approved.

### `is_leaked_system_result(text: str) -> bool`

- **Purpose**: To centralize the detection of "leaked" internal `SYSTEM RESULT` transcripts in the model's final answer.
- **Inputs**: `text: str` (The text to check, typically the final visible answer).
- **Output**: `bool`.
- **Current Source**: `ResponseSemantics.looks_like_leaked_system_result`.
- **Behavior Preservation**: Must be a pure, behavior-preserving replacement of the existing regex-based check.
- **Authority Boundary**: **Final-Answer Guard**. A `True` result is a signal that the response is likely malformed and should be recovered. It is not a final policy decision.
- **Non-Goals**: Does not determine if the response is a valid final answer. Does not parse or extract any text.
- **Future Tests**:
    - Test that it matches the canonical `SYSTEM RESULT` prefix.
    - Test that it does not match ordinary prose like "the system result was...".
    - Parity tests against `ResponseSemantics.looks_like_leaked_system_result`.
- **Allowed Consumers**: `ResponsePipelineStagesMixin` (leaked system result check).
- **Forbidden Consumers**: Any consumer related to dispatch authority or intent transitions.

### `has_substantial_think(raw_response: str) -> bool`

- **Purpose**: To centralize the detection of a `<think>` block with a meaningful amount of content (>= 5 words).
- **Inputs**: `raw_response: str`.
- **Output**: `bool`.
- **Current Source**: `ResponseSemantics.has_substantial_think`.
- **Behavior Preservation**: Must be a pure, behavior-preserving replacement of the existing logic.
- **Authority Boundary**: **Loop-Detection Guard**. A `True` result is an input to the `is_nonproductive_thinking_turn` policy, not a policy decision itself.
- **Non-Goals**: Does not change the non-productive thinking policy. Does not parse the content of the think block.
- **Future Tests**:
    - Test that it returns `True` for think blocks with >= 5 words.
    - Test that it returns `False` for think blocks with < 5 words.
    - Test that it handles multiple think blocks correctly.
    - Parity tests against `ResponseSemantics.has_substantial_think`.
- **Allowed Consumers**: `ResponseGuardPolicy.is_nonproductive_thinking_turn`.
- **Forbidden Consumers**: Any consumer outside of the non-productive thinking guard.

### Deferred Accessors

- **`get_visible_text`**: Deferred. Visible text extraction touches final-answer/plaintext guards, `IntentTransitionHandler`, `DispatchOutcomeHandler`, and user-facing stop decisions. It requires a separate, dedicated design and must not be included in this batch.
