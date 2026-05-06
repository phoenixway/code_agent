# Shadow Disagreement Triage Report

This document analyzes disagreements found in runtime shadow logs between the legacy `ResponseSemantics` (regex-based) and the new `ProtocolCompiler`.

## Case 1: Protocol Tags in Think Block Text

-   **Disagreement**:
    -   `legacy_invalid_kind`: `intent_inside_think`, `nested_think`
    -   `compiler_shape`: `ACTION_ONLY`
    -   `compiler_code`: `null`
-   **Raw Response Excerpt**:
    ```xml
    <think>
    I am thinking about what an intent is. It looks like `<intent mode="activate">`.
    </think>
    <action>{"type":"read_file","path":"x.py"}</action>
    ```
-   **Structural Analysis**: The raw response is structurally valid. It contains a closed `<think>` block followed by an `<action>` block. The text inside the `<think>` block contains something that looks like a protocol tag, but it is not intended as one.
-   **Verdict**: `legacy_false_positive`
-   **Reason**: The legacy `ResponseSemantics` uses simple string-matching on the content of `<think>` blocks. It cannot distinguish between a real protocol tag and a plain-text example of one. The `ProtocolCompiler`'s lexer and parser correctly identify this as plain text within the think block, leading to a valid `ACTION_ONLY` shape.
-   **Recommended Action**: Do not change the compiler. The legacy behavior is incorrect and should not be preserved during migration. New regression tests have been added to the `compiler_gaps` suite to protect the correct compiler behavior.

---

## Case 2: Protocol Tags in Intent Goal String

-   **Disagreement**:
    -   `legacy_invalid_kind`: `intent_body_contains_action`
    -   `compiler_shape`: `INTENT_ONLY`
    -   `compiler_code`: `null`
-   **Raw Response Excerpt**:
    ```xml
    <intent mode="activate">{"goal": "User wants to do <action>something</action>"}</intent>
    ```
-   **Structural Analysis**: The raw response contains an `<action>` tag inside a JSON string value. This is a structural violation that can confuse downstream systems.
-   **Verdict**: `compiler_false_negative`
-   **Reason**: The legacy system correctly identifies this as a problem. The `ProtocolCompiler` currently does not parse inside JSON string values, so it misses this violation and incorrectly classifies the response as a valid `INTENT_ONLY` shape.
-   **Recommended Action**: This is a known gap that must be fixed in the compiler. The issue is already tracked in `tests/golden/responses/compiler_gaps/cases/intent_body_contains_action_gap.yaml`. The migration to a compiler-driven system must address this.

---
