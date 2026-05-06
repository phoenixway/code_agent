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

## 6. Regression Testing Checklist

To ensure these invariants are maintained, the following test suites must remain green after any related changes:

- Compiler golden tests (`tests/golden/responses/compiler/test_compiler_golden.py`)
- Semantic shadow tests (`tests/golden/responses/test_semantic_shadow.py`)
- Compiler gap matrix (if applicable)
- Protocol runtime integration tests (`tests/test_protocol_compiler_runtime_integration.py`)
- Pre-action text flow tests (`tests/agent/orchestration/test_pre_action_text_flow.py`)
- Mixed visible text and control protocol tests (`tests/test_mixed_visible_text_and_control_protocol.py`)
- Action array and atomic bundle tests
