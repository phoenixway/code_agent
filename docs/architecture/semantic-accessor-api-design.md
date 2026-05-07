# Semantic Accessor API Design (Phase 3)

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
