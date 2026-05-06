# Response Protocol Invariants

This document outlines key invariants of the model response protocol, particularly after the `PRE_ACTION_TEXT_AND_ACTION` refactor. These rules are critical for runtime stability and predictable behavior. Future changes must not accidentally revert these invariants.

## 1. Final Answer Semantics

- **`PLAINTEXT_ONLY` shape**: A response containing only user-visible text (without any control protocol tags like `<action>` or `<intent>`) is considered a final answer.
- **Loop Termination**: When the model produces a valid final answer, the execution loop may terminate, and the text is presented to the user.

## 2. Pre-Action Text Semantics

- **`PRE_ACTION_TEXT_AND_ACTION` shape**: This shape represents a response with leading visible text that appears before the first `<action>` tag.
- **User-Visible Preamble**: This text is treated as a user-visible status update or preamble, not a final answer. For example: "Okay, I will read the file first."
- **Runtime Behavior**: The runtime should emit this pre-action text to the user before dispatching the subsequent action.
- **No Loop Termination**: The runtime must not stop after emitting pre-action text; it must proceed to execute the action.

## 3. Invalid Post-Action Text

- **Visible text after `<action>` is invalid**: Any user-visible text that appears after an `<action>` tag is considered a protocol violation.
- **Reasoning**: This text would be describing the results of an action before that action has actually executed, which is a logical paradox.
- **Normalization**: This invalid post-action text must not be normalized or re-interpreted as pre-action text.

## 4. Action Payload Safety

- **Valid Action Form**: The only valid form for a single action is `<action>{...}</action>`, where the payload is a single JSON object.
- **Invalid Action Array**: An action payload containing a JSON array, like `<action>[...]</action>`, is invalid (`E_ACTION_PAYLOAD_ARRAY`).
- **Dispatch Prevention**: Responses with action arrays must never be dispatched.
- **No Fallback**: Action arrays must not be misinterpreted as a different valid construct, such as an intent being accepted without a follow-up action.

## 5. Legacy Migration Rule for Pre-Action Text

- **Legacy Disagreement**: The legacy response parser may still classify a valid `PRE_ACTION_TEXT_AND_ACTION` response as `mixed_visible_text_and_control_protocol`.
- **Compiler Override**: If the protocol compiler identifies the shape as `PRE_ACTION_TEXT_AND_ACTION` with no errors, the runtime is permitted to apply a narrow override. This bypasses the legacy recovery logic and allows the action to be dispatched.
- **Narrow Scope**: This override must *only* apply to this specific migration case. It must not apply to responses with visible text *after* an action or any other response that the compiler deems invalid.

## 6. Compiler Authority Boundary

The `ProtocolDecisionBridge` centralizes compiler-vs-legacy authority. Its rules are intentionally narrow to prevent regressions during migration.

- **`PLAINTEXT_ONLY` is not compiler-authoritative**: Legacy recovery policies for cases like `missing_action_or_answer` or plain-think recovery still apply to plaintext-like responses. The compiler does not yet override these.
- **`PRE_ACTION_TEXT_AND_ACTION` authority is narrow**: The compiler is only authoritative for simple pre-action status text followed by an action. If the response also contains `<think>` or other control blocks, it falls back to legacy `mixed_visible_text_and_control_protocol` recovery.
- **Action payload errors are compiler-authoritative**: The compiler is the authority for structural action payload errors (e.g., `E_ACTION_PAYLOAD_ARRAY`), preventing dispatch.
- **File Content Pairing Diagnostics**: The compiler is authoritative for structural errors related to `write_file_block` and `<file_content>` pairing, such as `E_FILE_CONTENT_REQUIRES_ACTION`.

## 8. Compiler Authority Migration Backlog

This section outlines the process and backlog for migrating response protocol decisions from legacy semantics to compiler authority.

### Current State

#### Compiler-Authoritative

The `ProtocolDecisionBridge` currently grants authority to the compiler for a narrow set of well-defined cases:

- **Simple `PRE_ACTION_TEXT_AND_ACTION`**: A response containing only leading visible text before a single action, without any other control blocks like `<think>`.
- **Action Payload Diagnostics**: Structural errors in the action payload, such as `E_ACTION_PAYLOAD_ARRAY`.
- **File Content Pairing Diagnostics**: Structural errors related to `write_file_block` and `<file_content>` pairing.

#### Legacy-Governed

Most semantic and policy-level decisions remain under legacy control. The compiler may correctly identify the shape, but legacy recovery logic is still authoritative. These include:

- **`PLAINTEXT_ONLY` responses**: These often overlap with legacy recovery policies for `missing_action_or_answer` or plain-think recovery. The compiler cannot yet safely override these.
- **Mixed `PRE_ACTION_TEXT_AND_ACTION`**: If the response contains `<think>` or other control blocks mixed with visible prose and an action, it falls back to legacy `mixed_visible_text_and_control_protocol` recovery.
- **Plain-think recovery**: Responses containing only a `<think>` block without an action.
- **Missing action/answer policy**: General cases where the model fails to produce a required action or final answer.
- **Evidence sufficiency**: Policies that guard against premature final answers without sufficient evidence (e.g., `modify_completion_claim_without_state_change_proof`).
- **Subgoal validation**: Policies around `mark_done` usage.
- **Search narrowing**: Policies that detect repeated low-value or broad searches.

### Migration Process

Migrating a category from legacy to compiler authority requires a careful, test-driven process.

#### Entry Criteria

Before adding a new rule to `ProtocolDecisionBridge`, the following criteria must be met:

1.  **Compiler Golden Coverage**: The compiler must have golden test cases (`tests/golden/responses/compiler/cases/`) that correctly identify the shape and any relevant errors for the target category.
2.  **Semantic Shadow Coverage**: Semantic shadow tests (`tests/golden/responses/test_semantic_shadow.py`) should be run to compare compiler semantics against legacy helpers, with any disagreements documented.
3.  **Runtime Integration Coverage**: A runtime integration test (e.g., in `tests/test_protocol_compiler_runtime_integration.py`) must exist to prove the compiler's decision correctly flows through the pipeline.
4.  **Negative Legacy-Regression Case**: A test must exist that proves the new rule does *not* incorrectly suppress a valid legacy recovery path (e.g., `test_mixed_visible_text_recovery_happens_before_action_policy`).
5.  **Real-World Evidence**: Where possible, the decision should be supported by evidence from real model outputs (e.g., smoke test logs or production dumps).

#### Steps

1.  Add or verify compiler golden test coverage for the specific response shape.
2.  Add or verify semantic shadow tests to understand any gaps between compiler and legacy views.
3.  Add a new, narrow rule to `ProtocolDecisionBridge`.
4.  Add a runtime integration test that asserts the new authority rule leads to the correct pipeline outcome (e.g., `dispatch_ready` or a specific recovery).
5.  Keep the legacy logic as a fallback until the new compiler-driven category is fully proven.

### Important Warnings

- **Do not make `compiler_shape` alone authoritative.** The policy boundary must be clear and tested. A correct shape from the compiler does not automatically mean legacy recovery policies are wrong.
- **`PLAINTEXT_ONLY` is a prime example.** While the compiler can identify this shape, it does not have the context to decide whether the response is a valid final answer or a case that requires `missing_action_or_answer` recovery. Authority must be granted based on more than just the shape.

### ACTION_ONLY Migration Audit

This audit assesses the feasibility of making `ACTION_ONLY` a compiler-authoritative shape.

#### Current Flow

A response classified as `ACTION_ONLY` by the compiler still passes through the full legacy pipeline:

1.  **Output Recovery**: It is checked for legacy `invalid_kind`s like `missing_memory_update_done`.
2.  **Action Policy**: It is checked against the active intent's `allowed_actions`.
3.  **Dispatch**: If it passes all checks, it is dispatched.

#### Coexisting Invalid Kinds

A response can have `compiler_shape="ACTION_ONLY"` but still be invalid due to legacy or runtime policies.

**Compiler-Authoritative Diagnostics within `ACTION_ONLY`:**

- Malformed action payload (e.g., not a JSON object).
- `write_file_block` missing its `<file_content>` block or being unclosed.

**Unsafe Candidates (must remain legacy/runtime governed for now):**

- **Missing memory checkpoint**: Policies like `missing_memory_update_done` or `state_changing_action_requires_think_reflection` are runtime-dependent and not purely structural.
- **Action not allowed by intent**: This is a core `ActionPolicy` check based on the active intent's contract.
- **No-op edits**: A runtime check to prevent actions that have no effect.
- **Edit retries requiring fresh reads**: A runtime policy to ensure data consistency.

#### Path to Migration

Before `ACTION_ONLY` can become compiler-authoritative, even for a subset of cases, the following tests are required:

1.  A test proving that a valid `ACTION_ONLY` response with a legacy `invalid_kind` (e.g., `missing_memory_update_done`) is **not** overridden by the compiler and still triggers recovery.
2.  A test proving that a valid `ACTION_ONLY` response that is disallowed by `ActionPolicy` is **not** dispatched.

#### Warning

`compiler_shape == "ACTION_ONLY"` alone is insufficient to grant authority. It must not suppress legacy `invalid_kind`s related to runtime policy, such as missing checkpoints or disallowed actions. Any future authority rule must be extremely narrow, likely combined with other compiler diagnostics.

## 9. Regression Testing Checklist

To ensure these invariants are maintained, the following test suites must remain green after any related changes:

- Compiler golden tests (`tests/golden/responses/compiler/test_compiler_golden.py`)
- Semantic shadow tests (`tests/golden/responses/test_semantic_shadow.py`)
- Compiler gap matrix (if applicable)
- Protocol runtime integration tests (`tests/test_protocol_compiler_runtime_integration.py`)
- Pre-action text flow tests (`tests/agent/orchestration/test_pre_action_text_flow.py`)
- Mixed visible text and control protocol tests (`tests/test_mixed_visible_text_and_control_protocol.py`)
- Action array and atomic bundle tests
