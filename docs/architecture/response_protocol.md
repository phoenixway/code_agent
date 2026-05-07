# Response Protocol Invariants

This document outlines key invariants of the model response protocol, particularly after the `PRE_ACTION_TEXT_AND_ACTION` refactor. These rules are critical for runtime stability and predictable behavior. Future changes must not accidentally revert these invariants.

## Current Migration Boundary

This section summarizes the current state of the protocol migration, defining the boundary between compiler and runtime authority.

-   **Compiler is authoritative for precise protocol-structural diagnostics only.** This includes malformed payloads, incorrect tag nesting (e.g., `<action>` inside `<think>`), and contradictory structures (e.g., `<intent mode="complete">` with an `<action>`).

-   **Runtime remains authoritative for all semantic and policy decisions.** The compiler does not have the context to make these judgments. Runtime authority includes:
    -   `ActionPolicy` enforcement (is an action allowed by the current intent?).
    -   Evidence sufficiency and final answer correctness.
    -   Active intent completion and subgoal validation.
    -   Search narrowing and low-value tool use detection.
    -   Dispatch decisions for valid `ACTION_ONLY` and `INTENT_ACTION_BUNDLE` shapes.
    -   Completion decisions for `PLAINTEXT_ONLY` shapes.

-   **Broad shape authority is explicitly forbidden.** The compiler identifying a shape is not sufficient to grant dispatch authority or bypass runtime checks. This applies to:
    -   `ACTION_ONLY` by shape.
    -   `PLAINTEXT_ONLY` by shape.
    -   `INTENT_ACTION_BUNDLE` by shape.
    -   Broad `E_MIXED_VISIBLE_TEXT_AND_CONTROL` errors.

-   **Future compiler migration must follow a strict, incremental process:**
    1.  Add a precise diagnostic for a narrow, well-defined error case.
    2.  Add a corresponding entry to `protocol/spec.py`.
    3.  Add golden and semantic shadow tests to verify compiler behavior.
    4.  Add a `ProtocolDecisionBridge` test to confirm authority.
    5.  Add a shared `invalid_kind` mapping if the error is non-dispatchable.
    6.  Confirm that `output_recovery` and `prevalidation` can route the new `invalid_kind`.
    7.  Update the documentation matrix.
    8.  Run the full test suite to check for regressions.

## 1. Final Answer Semantics

- **`PLAINTEXT_ONLY` shape**: A response containing only user-visible text (without any control protocol tags like `<action>` or `<intent>`) is considered a final answer.
- **Loop Termination**: When the model produces a valid final answer, the execution loop may terminate, and the text is presented to the user.

## 2. Pre-Action Text Semantics

- **`PRE_ACTION_TEXT_AND_ACTION` shape**: This shape represents a response with leading visible text that appears before the first `<action>` tag.
- **User-Visible Preamble**: This text is treated as a user-visible status update or preamble, not a final answer. For example: "Okay, I will read the file first."
- **Runtime Behavior**: The runtime should emit this pre-action text to the user before dispatching the subsequent action.
- **No Loop Termination**: The runtime must not stop after emitting pre-action text; it must proceed to execute the action.

## 3. Invalid Post-Action Text

- **Visible text after `<action>` is invalid**: Any user-visible text that appears after an `<action>` tag is considered a protocol violation. This rule applies even if the action is part of an atomic `<intent>`+`<action>` bundle.
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

## 7. Compiler Authority Migration Backlog

This section outlines the process and backlog for migrating response protocol decisions from legacy semantics to compiler authority.

### Current State

#### Compiler-Authoritative

The `ProtocolDecisionBridge` currently grants authority to the compiler for a narrow set of well-defined cases:

- **Simple `PRE_ACTION_TEXT_AND_ACTION`**: A response containing only leading visible text before a single action, without any other control blocks like `<think>`.
- **Action Payload Diagnostics**: Structural errors in the action payload, such as `E_ACTION_PAYLOAD_ARRAY`.
- **File Content Pairing Diagnostics**: Structural errors related to `write_file_block` and `<file_content>` pairing (e.g., missing action, wrong order, action mismatch).

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

### ACTION_ONLY Safe-Subset Audit

This audit assesses which parts of `ACTION_ONLY` validation can be safely owned by the compiler versus which must remain governed by the runtime.

**Conclusion**: `compiler_shape == "ACTION_ONLY"` alone is **never** sufficient to grant dispatch authority. The shape only describes the protocol structure (e.g., a single action with optional think/file_content). The final decision to dispatch, recover, or block the action depends on runtime policies that the compiler does not have access to.

- **Compiler Authority**: The compiler is authoritative for *precise structural diagnostics* that can occur within an `ACTION_ONLY` shape, such as a malformed payload (`E_ACTION_PAYLOAD_ARRAY`) or an action inside a think block (`E_ACTION_INSIDE_THINK`). These are invalid regardless of runtime state.
- **Runtime Authority**: The runtime remains the final authority for all other checks, including:
  - **ActionPolicy**: Is the action allowed by the current intent contract?
  - **Checkpoint Policy**: Does a state-changing action have the required `<think>` and memory tags?
  - **Dispatch Effects**: Does the action result in a no-op edit or violate other dispatch-time rules?

The following table inventories various `ACTION_ONLY` cases and their authority path:

| Case | Example | Compiler Shape | Legacy `invalid_kind` | Bridge Authority | Runtime Outcome | Safe for Compiler? |
|---|---|---|---|---|---|---|
| **A. Valid read-only action** | `<action>{"type":"read_file"}</action>` | `ACTION_ONLY` | `null` | Legacy | Runtime Dispatch | No (ActionPolicy) |
| **B. Action with checkpoint** | `<think>...</think><memory_update_done/><action>...</action>` | `ACTION_ONLY` | `null` | Legacy | Runtime Dispatch | No (ActionPolicy) |
| **C. Action missing checkpoint** | `<think>...</think><action>...</action>` | `ACTION_ONLY` | `missing_memory_update_done` | Legacy | Recovery | No (Runtime policy) |
| **D. Disallowed action** | `<action>{"type":"delete_file"}</action>` | `ACTION_ONLY` | `null` | Legacy | ActionPolicy Block | No (ActionPolicy) |
| **E. Action not in intent** | `<action>{"type":"read_file"}</action>` | `ACTION_ONLY` | `null` | Legacy | ActionPolicy Block | No (ActionPolicy) |
| **F. Valid `write_file_block`** | `<action>...</action><file_content>...</file_content>` | `ACTION_ONLY` | `null` | Legacy | Runtime Dispatch | No (ActionPolicy) |
| **G. Malformed payload** | `<action>[...]</action>` | `INVALID` | `action_payload_array` | **Compiler** | Recovery | Yes (already done) |
| **H. Action inside think** | `<think><action>...</action></think>` | `INVALID` | `action_inside_think` | **Compiler** | Recovery | Yes (already done) |
| **I. From `PRE_ACTION_TEXT`** | `OK<action>...</action>` | `PRE_ACTION_TEXT_AND_ACTION` | `mixed_...` | **Compiler (Valid)** | Runtime Dispatch | Yes (already done) |
| **J. In atomic bundle** | `<intent>...</intent><action>...</action>` | `INTENT_ACTION_BUNDLE` | `null` | Legacy | Runtime Dispatch | No (ActionPolicy) |

### PLAINTEXT_ONLY Final-Answer Boundary Audit

This audit assesses whether `compiler_shape == "PLAINTEXT_ONLY"` can ever be sufficient to determine that a response is a valid final answer.

**Conclusion**: `compiler_shape == "PLAINTEXT_ONLY"` is **never** sufficient to prove answer correctness or intent completion. The shape only indicates the absence of protocol control blocks. The runtime remains the final authority for deciding if a plaintext response is a valid final answer, a premature conclusion requiring recovery, or a non-sequitur.

- **Compiler Authority**: The compiler's role is purely structural. It identifies that the response contains only visible text (and possibly non-structural elements like think blocks that are stripped).
- **Runtime Authority**: The runtime is responsible for all semantic and policy-level validation, including:
  - **Evidence Sufficiency**: Does the agent have enough information to answer the user's question? (e.g., `modify_completion_claim_without_state_change_proof` recovery).
  - **Intent Completion**: Does the plaintext answer satisfy the goal of the active intent?
  - **Contextual Appropriateness**: Is a plaintext answer appropriate at this stage of the task, or is an action required? (e.g., `missing_action_or_answer` recovery).

The following table inventories various `PLAINTEXT_ONLY` cases and their authority path, demonstrating why runtime governance is essential.

| Case | Example | Compiler Shape | Legacy/Runtime Decision | Bridge Authority | Safe for Compiler? |
|---|---|---|---|---|---|
| **A. Valid answer, no intent** | `Hello world.` | `PLAINTEXT_ONLY` | Dispatch as final answer | Legacy | No (Runtime policy) |
| **B. Valid answer, sufficient evidence** | `The answer is 42.` | `PLAINTEXT_ONLY` | Dispatch as final answer | Legacy | No (Runtime policy) |
| **C. Answer, missing evidence** | `The answer is 42.` | `PLAINTEXT_ONLY` | Recover (`modify_completion_claim_without_state_change_proof`) | Legacy | No (Runtime policy) |
| **D. Answer after noisy tool result** | `The search was noisy.` | `PLAINTEXT_ONLY` | Recover (`missing_action_or_answer`) | Legacy | No (Runtime policy) |
| **E. Answer after recovery prompt** | `OK.` | `PLAINTEXT_ONLY` | Recover (`missing_action_or_answer`) | Legacy | No (Runtime policy) |
| **F. Protocol-like literal** | `Use \`<action>\`` | `PLAINTEXT_ONLY` | Dispatch as final answer | Legacy | No (Runtime policy) |
| **G. `complete` intent + visible text** | `<intent mode="complete"/>OK` | `PLAINTEXT_ONLY` | Dispatch as final answer (legacy path) | Legacy | No (Runtime policy) |
| **H. Terminal fallback** | `I am stuck.` | `PLAINTEXT_ONLY` | Dispatch as final answer | Legacy | No (Runtime policy) |
| **I. Plaintext after malformed step** | `OK.` | `PLAINTEXT_ONLY` | Recover (`missing_action_or_answer`) | Legacy | No (Runtime policy) |
| **J. User-forced final answer** | `The answer is 42.` | `PLAINTEXT_ONLY` | Dispatch as final answer | Legacy | No (Runtime policy) |

### Mixed Visible/Control Migration Split

This audit inventories the different cases of mixed visible text and control protocol to guide future migration.

| Case | Example | Compiler | Legacy `invalid_kind` | Bridge Authority | Future Authority | Risk |
|---|---|---|---|---|---|---|
| **Simple Pre-Action Text** | `OK<action>...</action>` | `PRE_ACTION_TEXT_AND_ACTION` | `mixed_visible_text_and_control_protocol` | **Compiler (Valid)** | Compiler | Low |
| **Visible + Think + Action** | `OK<think>...</think><action>...</action>` | `E_MIXED_VISIBLE_TEXT_AND_CONTROL` | `mixed_visible_text_and_control_protocol` | Legacy | Compiler | Medium |
| **Visible + Checkpoint + Action** | `OK<progress>...</progress><action>...</action>` | `E_MIXED_VISIBLE_TEXT_AND_CONTROL` | `mixed_visible_text_and_control_protocol` | Legacy | Compiler | Medium |
| **Visible Text After Action** | `<action>...</action>OK` | `E_VISIBLE_TEXT_AFTER_ACTION` | `mixed_visible_text_and_control_protocol` | **Compiler** | Compiler | Low |
| **Visible Text After Intent** | `<intent>...</intent>OK` | `E_VISIBLE_TEXT_AFTER_INTENT` | `mixed_intent_transition_and_visible_answer` | **Compiler** | Compiler | Low |
| **Literal Tag in Code** | `<think>Use \`<action>\`</think><action>...</action>` | `ACTION_ONLY` | `null` or `action_inside_think` | Legacy | Compiler | Medium |

### Atomic Bundle Migration Audit

This audit assesses the feasibility of making atomic intent/action bundle diagnostics compiler-authoritative.

| Case | Example | Compiler | Legacy `invalid_kind` | Bridge Authority | Notes |
|---|---|---|---|---|---|
| **Valid Bundle** | `<intent>...</intent><action>...</action>` | `INTENT_ACTION_BUNDLE` | `null` | Legacy | Valid bundle, but remains legacy-governed to allow `ActionPolicy` checks. |
| **Multiple Actions** | `<intent>...</intent><action>...</action><action>...</action>` | `E_ATOMIC_BUNDLE_REQUIRES_EXACTLY_ONE_ACTION` | `multiple_actions` | **Compiler** | Precise structural error. |
| **Action Array** | `<intent>...</intent><action>[...]</action>` | `E_ATOMIC_BUNDLE_REQUIRES_EXACTLY_ONE_ACTION` | `action_payload_array` | **Compiler** | Precise structural error. Covered by atomic bundle authority. |
| **Multiple Intents** | `<intent>...</intent><intent>...</intent><action>...</action>` | `E_MULTIPLE_INTENTS` | `conflicting_intent_transitions` | **Compiler** | Precise structural error. |
| **Complete + Action** | `<intent mode="complete">...</intent><action>...</action>` | `E_INTENT_COMPLETE_WITH_ACTION` | `intent_complete_with_action_not_allowed` | **Compiler** | Contradictory structure. |
| **Bundle + Visible Text** | `<intent>...</intent><action>...</action>OK` | `E_VISIBLE_TEXT_AFTER_ACTION` | `mixed_visible_text_and_control_protocol` | **Compiler** | Covered by existing visible-text-after-action authority. |

**Conclusion**: Precise structural errors related to atomic bundles, such as multiple actions or multiple intents, are now compiler-authoritative. The valid `INTENT_ACTION_BUNDLE` shape remains legacy-governed to ensure runtime policy checks (e.g., `ActionPolicy`) are not bypassed.

### Intent + Visible Text Migration Audit

This audit assesses the feasibility of making intent-plus-visible-text cases compiler-authoritative.

| Case | Example | Compiler | Legacy `invalid_kind` | Bridge Authority | Notes |
|---|---|---|---|---|---|
| **Activate + Visible** | `<intent mode="activate">...</intent>OK` | `E_VISIBLE_TEXT_AFTER_INTENT` | `mixed_intent_transition_and_visible_answer` | **Compiler** | Invalid. Should recover. |
| **Complete + Visible** | `<intent mode="complete">...</intent>OK` | `PLAINTEXT_ONLY` | `mixed_intent_transition_and_visible_answer` | Legacy | Current compiler behavior treats complete-intent + visible answer as plaintext/final-answer path; this remains legacy/runtime governed. |
| **Activate + Action** | `<intent mode="activate">...</intent><action>...</action>` | `INTENT_ACTION_BUNDLE` | `null` | Legacy | Valid atomic bundle. |

**Conclusion**: The compiler now emits a precise `E_VISIBLE_TEXT_AFTER_INTENT` error for invalid mixes of non-`complete` intent transitions and visible text. This error code is compiler-authoritative. The broad `E_MIXED_VISIBLE_TEXT_AND_CONTROL` error is still not safe to make compiler-authoritative, as it covers other cases like `Visible + Think + Action` that have different recovery paths and risks.

**Path to Migration**: The `E_VISIBLE_TEXT_AFTER_INTENT` diagnostic is now compiler-authoritative. Other mixed content cases remain legacy-governed until they also have precise, tested diagnostics.

## Search Narrowing Runtime Policy

To maintain performance and guide the model toward efficient investigation, the runtime enforces several policies to discourage broad, low-value, or repetitive searches.

-   **Broad Searches are Expensive**: Searches on the root directory (`.`) with vague patterns can be very slow and consume a large token budget for results that are often not useful. The runtime monitors for these patterns.

-   **Repeated Low-Value Searches are Blocked**: If the model repeatedly issues broad searches that yield no useful results, the runtime will intervene. After a certain number of repeats (a runtime-configurable policy), a `low_value_broad_search_repeat` recovery is triggered.

-   **Recovery Guides Toward Narrowing**: The recovery prompt explicitly instructs the model to narrow its next search by improving at least one of the following:
    -   **Path**: Use a more specific subdirectory instead of the root.
    -   **Pattern**: Use a more specific search pattern (e.g., an exact symbol, class name, or function name).
    -   **Extensions**: Use `include_extensions` to limit the search to relevant file types (e.g., `.py`, `.kt`).
    -   **Exclusions**: Use `exclude_dirs` to avoid noisy directories like `build`, `dist`, or `.git`.

-   **Exact Reads are Preferred After Broad Search**: After a broad search result exposes exact candidate paths, the next preferred step is an exact file read (`read_file`, `read_chunk`, `read_file_skeleton`), not another broad content search.

-   **Docs and Logs are Secondary Evidence**: The recovery prompt guides the model to treat `docs/` and log files as noisy or secondary evidence unless they are the explicit target of the user's request.

-   **Self-Referential Hits are Filtered**: The runtime detects when a search's results come only from its own artifacts (e.g., `debug.log`, `communication.log`). These are not considered valid source code evidence. A `history_self_reference_hit` recovery prompts the model to issue a new search that excludes these artifact files.

### Compiler IR Semantic Migration Plan

This section outlines the plan to migrate runtime semantic extraction from legacy `ParsedModelOutput` fields to the compiler's more reliable Intermediate Representation (IR).

**Current State**: The runtime currently consumes a mix of legacy fields (e.g., `has_action_segment`, `visible_text`) and compiler-derived fields (`compiler_shape`, `compiler_error_code`). Many stages still use `ResponseSemantics` helpers that operate on raw response strings, which is inefficient and less precise than using the compiler's structured output.

**Goal**: Systematically replace legacy semantic extraction with a new `RuntimeProtocolSemantics` adapter, populated directly from the compiler's IR. This will make the runtime more robust, efficient, and easier to maintain.

#### Proposed Adapter Shape

A new `RuntimeProtocolSemantics` class will be introduced to provide a stable, read-only view of the response's semantics, derived from the compiler's `CompilerAnalysis`.

```python
@dataclass(frozen=True)
class RuntimeProtocolSemantics:
    source: str  # "compiler" | "legacy_fallback"
    shape: ResponseShape
    is_valid: bool
    error_code: str | None
    recovery_id: str | None
    action_count: int
    has_action: bool
    action_ops: list[ActionOpIR]
    intent_ops: list[IntentOpIR]
    visible_text: str
    has_visible_answer: bool
    pre_action_text: str
    memory_ops: list[BoardOpIR]
    subgoal_ops: list[BoardOpIR]
    has_file_content: bool
    file_content: str
    effects_preview: EffectPreview | None
```

#### Consumer Inventory

-   **`response_pipeline_stages.py`**
    -   **Current Source**: `ParsedModelOutput` fields, `ResponseSemantics` helpers.
    -   **IR Equivalent**: `RuntimeProtocolSemantics` adapter.
    -   **Risk**: Medium. Core logic.
    -   **Recommendation**: Migrate after validation in read-only contexts.

-   **`output_recovery_routing.py`**
    -   **Current Source**: `ParsedModelOutput` fields, `ResponseSemantics` helpers.
    -   **IR Equivalent**: `RuntimeProtocolSemantics` adapter.
    -   **Risk**: Medium. Critical for recovery.
    -   **Recommendation**: Phase 3. Migrate structural checks first.

-   **`response_pipeline_prevalidation.py`**
    -   **Current Source**: `ParsedModelOutput` fields, `ResponseSemantics` helpers.
    -   **IR Equivalent**: `RuntimeProtocolSemantics` adapter.
    -   **Risk**: Medium. Core pipeline logic.
    -   **Recommendation**: Migrate alongside `response_pipeline_stages`.

-   **`intent_transition_routing.py`**
    -   **Current Source**: `ParsedModelOutput` fields, `ResponseSemantics` helpers, and its own regex parsing.
    -   **IR Equivalent**: `RuntimeProtocolSemantics` adapter.
    -   **Risk**: High. Complex logic with its own parsing.
    -   **Recommendation**: Phase 4.

-   **`plan_board` / `memory_board` stages**
    -   **Current Source**: Raw response text, `ResponseSemantics` helpers.
    -   **IR Equivalent**: `RuntimeProtocolSemantics` adapter.
    -   **Risk**: High. Stateful and complex.
    -   **Recommendation**: Phase 4.

-   **`dispatch_pipeline.py`**
    -   **Current Source**: `ExecutionPlan` (derived from `ParsedModelOutput` and `compiler_ir`).
    -   **IR Equivalent**: `RuntimeProtocolSemantics` adapter would be used to create the `ExecutionPlan`.
    -   **Risk**: Low. The interface is already abstracted.
    -   **Recommendation**: Update plan creation logic to use the adapter.

-   **`semantic shadow tests`**
    -   **Current Source**: `ResponseSemantics` helpers vs. `CompilerAnalysis`.
    -   **IR Equivalent**: `RuntimeProtocolSemantics` adapter.
    -   **Risk**: Low. Test-only consumer.
    -   **Recommendation**: Phase 2. Use to validate the adapter.

#### Phased Migration Plan

1.  **Phase 1: Introduce Adapter (No Behavior Change)**
    -   **Status: Done.** This phase introduces the `RuntimeProtocolSemantics` adapter as an additive, read-only snapshot of compiler IR semantics. It is populated in the response pipeline but not yet consumed by any runtime logic. Existing consumers still use legacy fields or direct `compiler_ir` reads. No behavior or authority boundaries have changed.

2.  **Phase 2: Adopt in Read-Only Diagnostics**
    -   **Status: In Progress.** This phase uses the `RuntimeProtocolSemantics` adapter for read-only diagnostics and test-time validation. A compact snapshot of the adapter's state is now logged to the orchestration trace. Parity tests have been added to confirm the adapter's fields are consistent with the raw compiler output. No runtime consumers have been switched to use the adapter yet.

#### Output Recovery Migration Audit

This audit inventories the dependencies of the `output_recovery` stage to determine which parts can be safely migrated to use the `RuntimeProtocolSemantics` adapter.

**Conclusion**: A significant portion of output recovery logic depends on runtime state (e.g., retry counters, active intent type) and semantic interpretation (e.g., evidence sufficiency). These must remain runtime-owned. However, many foundational structural checks currently rely on regex-based helpers in `ResponseSemantics` or direct reads from `ParsedModelOutput`. These are excellent candidates for migration to the more reliable `RuntimeProtocolSemantics` adapter.

| Check | Location | Current Source | RPS Equivalent | Risk | Phase | Reason |
|---|---|---|---|---|---|---|
| **Resolve `invalid_kind`** | `output_recovery_routing.py` | `parsed_output.invalid_kind`, `compiler_error_code` | `snapshot.invalid_kind` | Low | 3A | `invalid_kind` is pre-computed and stored on the snapshot. Pure structural fact. |
| **Compiler Strategy Routing** | `output_recovery_routing.py` | `compiler_error_code`, `compiler_recovery_id` | `snapshot.error_code`, `snapshot.recovery_id` | Low | 3A | Pure structural facts from the compiler. |
| **Action Presence** | `response_semantics.py` | `parsed_action_count`, `compiler_ir`, `has_action_segment` | `snapshot.has_action`, `snapshot.action_count` | Low | 3A | Core structural fact, directly available from IR. |
| **State-Changing Action** | `output_recovery.py` | `parsed_output.segments`, regex | `any(op.write_like for op in snapshot.action_ops)` | Medium | 3B | RuntimeProtocolSemantics can provide action_ops/write_like as a structural input, but the recovery decision depends on runtime modify context, checkpoint/reflection policy, and state. |
| **Malformed Think Recovery** | `output_recovery_routing.py` | `invalid_kind`, `raw_chars`, retry counters (state) | `snapshot.invalid_kind`, `len(response)` | Medium | 3B | Combines structural `invalid_kind` with runtime retry state. |
| **Missing `memory_update_done`** | `output_recovery.py` | `response` (raw text), `semantics` helpers | `any(op.kind == 'memory_update_done' for op in snapshot.memory_ops)` | Medium | 3B | The check is structural, but the decision to recover depends on runtime context (`_is_modify_context`). |
| **Unproven Modify Claim** | `output_recovery.py` | `semantics`, `_is_modify_context` (state), `visible_text` | `snapshot.has_action`, `snapshot.visible_text` + runtime state | High | Runtime-owned | Core semantic policy. Depends heavily on runtime state. |
| **Internal Summary** | `output_recovery.py` | `semantics`, `visible_text`, regex | `snapshot.has_action`, `snapshot.visible_text` + regex | High | Runtime-owned | Semantic interpretation of visible text. Not purely structural. |
| **Build/Fix Status** | `output_recovery.py` | `state` | N/A | High | Runtime-owned | Purely runtime state-dependent. |
| **Retry/Terminal Logic** | `output_recovery_terminal.py` | `state` (retry counters, etc.) | N/A | High | Runtime-owned | Core runtime policy for loop control. |

##### Phase 3A-pre: Read-Only Parity Checks

-   **Status: Done.** This phase adds read-only diagnostics to the `output_recovery` stage.
-   A new `output_recovery_semantics_parity` trace entry now logs a comparison between legacy structural fields (`invalid_kind`, `has_action_segment`) and the equivalent fields from `RuntimeProtocolSemantics`.
-   The parity diagnostics now label expected mismatches (e.g., `legacy_action_in_compiler_invalid_response`) where the legacy parser sees an action in a response that the compiler correctly identifies as structurally invalid.
-   This is a diagnostics-only change. Output recovery decisions are not yet using the new adapter. All behavior and authority boundaries remain unchanged.
-   Legacy action presence is not yet migrated to `RuntimeProtocolSemantics`. Invalid compiler responses must not dispatch actions, even if legacy parsing detects an action-like segment. Compiler-invalid responses remain recovery-owned even when legacy parsing detects action-like content; this protects against dispatch from malformed responses.

##### Phase 3A-1: Read-Only Compiler Metadata Migration

-   **Status: Done.** This phase migrates the read-side of compiler strategy routing metadata (`error_code`, `recovery_id`) to use `RuntimeProtocolSemantics` with a fallback to legacy `ParsedModelOutput` fields.
-   This is a behavior-preserving refactor. Output recovery decisions, `invalid_kind` resolution, and authority boundaries remain unchanged.
-   Runtime-owned checks and other structural checks (e.g., `action_count`) are not yet migrated.

##### Phase 3A-2: Read-Only `invalid_kind` Metadata Migration

-   **Status: Done.** This phase extends the `output_recovery_compiler_metadata` helper to include `invalid_kind`.
-   The helper prefers `invalid_kind` from `RuntimeProtocolSemantics` when available, falling back to the legacy `ParsedModelOutput.invalid_kind` field.
-   The `_compiler_strategy_decision` router now uses this metadata-driven `invalid_kind` when resolving a recovery strategy, but this is a behavior-preserving change due to the fallback logic.
-   The top-level `_resolved_invalid_kind` helper and overall output recovery decisions remain unchanged.
-   Action presence, `action_count`, checkpoint, and state-changing checks are not migrated.

##### Proposed Phase 3A Scope

The first implementation phase for migrating `output_recovery` should be narrow and focused on structural checks.

-   **Read-Only Adoption**: `OutputRecoveryRoutingMixin` may read from `RuntimeProtocolSemantics` only for structural-safe facts (e.g., `has_action`, `action_count`, `error_code`).
-   **No Behavior Change**: Initially, the new data should only be used for parity assertions or logging to validate its correctness against the legacy path.
-   **Fallback Path**: The existing logic reading from `ParsedModelOutput` and `ResponseSemantics` must be kept as a fallback.
-   **No Authority Change**: This phase must not change any authority boundaries. `ACTION_ONLY` and `PLAINTEXT_ONLY` shapes must not be used as proof of dispatch-readiness or final-answer correctness.

##### Phase 3A Acceptance Criteria

-   Full test suite remains green.
-   Output recovery decisions are unchanged for all existing fixtures.
-   Parity logs or assertions confirm that `RuntimeProtocolSemantics` provides the same structural facts (e.g., `action_count`, `error_code`) as the legacy fields.
-   No new compiler authority is added to `ProtocolDecisionBridge`.
-   No behavior is changed in `ActionPolicy`, `IntentTransitionHandler`, or `DispatchPipeline`.
-   Any structural check that is fully migrated to `RuntimeProtocolSemantics` must have dedicated unit tests covering its branches.

3.  **Phase 3: Migrate Output Recovery**
    -   Refactor `OutputRecoveryRoutingMixin` to consume the `RuntimeProtocolSemantics` adapter for structural checks (e.g., `has_action`, `action_count`) instead of legacy fields or `ResponseSemantics` helpers.
    -   Policy-based checks (e.g., evidence sufficiency) will still reside in the runtime.

4.  **Phase 4: Migrate Core Logic**
    -   Refactor `IntentTransitionHandler`, `PlanBoard`, and `MemoryBoard` to use the adapter.
    -   This will eliminate redundant response parsing within `IntentTransitionHandler`.

5.  **Phase 5: Deprecate Legacy Fields**
    -   Once all consumers are migrated, the legacy fields on `ParsedModelOutput` and the `ResponseSemantics` class can be deprecated and eventually removed. The legacy parser will become a fallback for unhandled cases only.

## 8. Compiler Error Code Authority Matrix

This table inventories compiler error codes and their authority status in `ProtocolDecisionBridge`.

Note: Some structural errors may have compiler diagnostics and recovery mappings in `output_recovery_routing.py`, but they are not considered compiler-authoritative unless explicitly listed in a `ProtocolDecisionBridge` set.

| Error Code | `invalid_kind` Mapping | Category | Bridge Authority | Notes |
|---|---|---|---|---|
| `E_UNCLOSED_THINK` | `malformed_incomplete_think` | Structural | Compiler | Purely structural error. |
| `E_ACTION_INSIDE_THINK` | `action_inside_think` | Structural | Compiler | Purely structural error. |
| `E_INTENT_INSIDE_THINK` | `intent_inside_think` | Structural | Compiler | Purely structural error. |
| `E_FILE_CONTENT_INSIDE_THINK` | `file_content_inside_think` | Structural | Compiler | Purely structural error. |
| `E_FILE_CONTENT_UNCLOSED` | `malformed_incomplete_file_content` | Structural | Compiler | File content pairing is structural. |
| `E_FILE_CONTENT_REQUIRES_ACTION` | `file_content_must_follow_action` | Structural | Compiler | File content pairing is structural (e.g., missing action, wrong order). |
| `E_FILE_CONTENT_ACTION_MISMATCH` | `file_content_must_follow_action` | Structural | Compiler | File content can only be paired with a single action that requires it. |
| `E_ACTION_PAYLOAD_ARRAY` | `action_payload_array` | Structural | Compiler | Action payload shape is structural. |
| `E_ACTION_PAYLOAD_NOT_OBJECT` | `action_payload_not_object` | Structural | Compiler | Action payload shape is structural. |
| `E_ACTION_PAYLOAD_XML_FIELDS` | `action_payload_xml_fields` | Structural | Compiler | Action payload shape is structural. |
| `E_ACTION_PAYLOAD_TOOL_CODE` | `action_payload_tool_code` | Structural | Compiler | Action payload shape is structural. |
| `E_PROTOCOL_TAG_IN_JSON_STRING` | `protocol_tag_in_json_string` | Structural | Compiler | Action payload content is structural. |
| `E_VISIBLE_TEXT_AFTER_ACTION` | `mixed_visible_text_and_control_protocol` | Structural | Compiler | Visible text after an action is a logical paradox. This includes text after an `intent`+`action` bundle. |
| `E_VISIBLE_TEXT_AFTER_INTENT` | `mixed_intent_transition_and_visible_answer` | Structural | Compiler | Visible text after a non-complete intent is invalid. |
| `E_MIXED_VISIBLE_TEXT_AND_CONTROL` | `mixed_visible_text_and_control_protocol` | Structural | Legacy | Authority is narrow; only simple `PRE_ACTION_TEXT_AND_ACTION` is compiler-authoritative. |
| `E_ATOMIC_BUNDLE_REQUIRES_EXACTLY_ONE_ACTION` | `action_payload_array` or `multiple_actions` | Structural | **Compiler** | Precise structural error related to bundle shape. |
| `E_INTENT_COMPLETE_WITH_ACTION` | `intent_complete_with_action_not_allowed` | Structural | **Compiler** | A complete intent cannot be combined with an action. |
| `E_MULTIPLE_INTENTS` | `conflicting_intent_transitions` | Structural | **Compiler** | Precise structural error. |

## 9. Inventory Consistency Rules

To keep documentation and behavior aligned, the following rules apply:

- **Bridge is source of truth**: Any error code considered compiler-authoritative *must* be in one of the `COMPILER_*_ERROR_CODES` sets in `ProtocolDecisionBridge`.
- **Docs must match bridge**: The authority matrix in this document must accurately reflect the sets in `ProtocolDecisionBridge`.
- **Test coverage is required**: Every code in a `ProtocolDecisionBridge` set must have at least one test in `tests/test_protocol_decision_bridge.py` confirming its authority.
- **Gap matrix for gaps**: If a compiler error code exists but is not yet authoritative, it should have a `tests/golden/responses/compiler_gaps/` case to document the gap. It must not be listed as compiler-authoritative in the docs.
- **Recovery mappings are separate**: `invalid_kind` mappings in `output_recovery_routing.py` or `response_pipeline_prevalidation.py` may exist before a code is compiler-authoritative. The docs must continue to mark these as `Legacy` authority until they are added to the bridge.

## 10. Execution Telemetry Invariants

This section clarifies the meaning of key telemetry fields related to action execution.

### Telemetry Lifecycle

1.  **Planning (`ExecutionPlan`)**: The `ResponsePipeline` creates an `ExecutionPlan` for dispatch-ready outcomes.
    -   `plan.action_effects` lists the actions *intended* for execution.
    -   `plan.output_effects` lists any user-visible text to be emitted before actions.

2.  **Dispatch (`DispatchPipeline`)**: The `DispatchPipeline` receives the `ExecutionPlan` and attempts to execute the actions in `action_effects`.

3.  **Commit (`execution_commit`)**: After execution, the `DispatchPipeline` creates an `execution_commit` containing the results.

4.  **Journaling (`ExecutionCommitObserver`)**: The `ExecutionCommitObserver` processes the commit and logs a journal entry.
    -   `committed_system_result_count` in the journal entry is the ground truth for how many tool/system results were successfully produced and committed.

### `ExecutionPlan.action_dispatched`

-   **Meaning**: This boolean field on the `ExecutionPlan` is currently **unused** and always `False` when the plan is created.
-   **Note**: A separate `AtomicBundlePlan.action_dispatched` flag exists for pre-validation logging of atomic bundles, but this is not the same as the field on the final `ExecutionPlan`.
-   **Correct Usage**: To determine if a plan includes actions intended for dispatch, check for the presence of `action_effects`. Do not rely on `action_dispatched`.

### `committed_system_result_count`

-   **Meaning**: This field, found in the execution commit artifacts, represents the actual number of tool results produced and committed after the `DispatchPipeline` runs.
-   **Scope**: It is the ground truth for how many actions were successfully executed in a turn.
-   **Example**: If `action_effects` has one item, and the tool call succeeds, `committed_system_result_count` will be `1`.

## 11. Regression Testing Checklist

To ensure these invariants are maintained, the following test suites must remain green after any related changes:

- Compiler golden tests (`tests/golden/responses/compiler/test_compiler_golden.py`)
- Semantic shadow tests (`tests/golden/responses/test_semantic_shadow.py`)
- Compiler gap matrix (if applicable)
- Protocol runtime integration tests (`tests/test_protocol_compiler_runtime_integration.py`)
- Pre-action text flow tests (`tests/agent/orchestration/test_pre_action_text_flow.py`)
- Mixed visible text and control protocol tests (`tests/test_mixed_visible_text_and_control_protocol.py`)
- Action array and atomic bundle tests
