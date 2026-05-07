# Phase 5 Design: TransitionSemanticValidator

- **Status**: Approved
- **Scope**: Design approved. Implementation is authorized for Step 1 only.

**Approved Implementation Scope: Step 1 Only**

This approval authorizes **only Phase 5 Step 1 (Scaffolding and Type Definition)**.
- Implementation of Step 2A, 2B, and 3 requires separate approval.
- Step 2C (plaintext followup) remains deferred until `get_visible_text` is designed.

## 1. Purpose and Guiding Principles

This document defines the design for the `TransitionSemanticValidator`, a new component responsible for classifying the followup surface of a model response after an intent transition has been applied.

The current logic for handling post-transition followup is spread across `IntentTransitionHandler`, `IntentTransitionRoutingMixin`, and `TransitionFollowupSemantics`. It relies on a complex web of private helper methods, regex, and direct calls to the protocol compiler. This makes the logic difficult to test, maintain, and reason about.

The `TransitionSemanticValidator` will centralize this logic, providing a single, testable entry point that returns a strongly-typed classification of the followup surface. This will decouple structural analysis from runtime policy, making the `IntentTransitionRoutingMixin` a simpler, more robust policy layer.

- **Single Access Point**: The validator will be the single testable entry point for transition/followup structural classification.
- **Strongly-Typed Output**: The validator will return a `dataclass` with an `Enum` kind, replacing ambiguous boolean flags and string-based reasons.
- **Behavior Preservation**: The validator will be designed to be a behavior-preserving refactor. Its initial implementation will replicate existing logic, and migration will be verified with parity tests.
- **Strict Authority Boundaries**: The validator provides **structural classification evidence**, not **policy decisions**. It can state that a response contains a single action, but it cannot state that the action is *allowed* to be dispatched.

## 2. Current Behavior Inventory

The current followup-handling logic is primarily located in `modules/agent/orchestration/transitions/intent_transitions.py`.

| Logic | Owner | Inputs | Semantics |
|---|---|---|---|
| `_followup_surface_summary` | `IntentTransitionHandler` | `response_text` | Main analysis entry point. Uses `ProtocolCompiler` and `TransitionFollowupSemantics` to generate a summary of nodes (intent, action, visible). |
| `_has_no_followup_after_intent` | `IntentTransitionHandler` | `response_text` | Checks if there is no substantive content after stripping the intent block. |
| `_reuse_has_inline_single_action` | `IntentTransitionHandler` | `intent_payload`, `response_text` | Checks for a single, isolated action after a `reuse` intent. |
| `_reuse_has_inline_plaintext_answer` | `IntentTransitionHandler` | `intent_payload`, `response_text` | Checks for a plaintext answer after a `reuse` intent. |
| `_followup_conflict_reason_after_current_transition` | `IntentTransitionHandler` | `intent_payload`, `response_text` | Detects conflicting content like multiple actions or mixed action/text. |
| `evaluate_transition` | `TransitionFollowupSemantics` | `summary`, `payload_mode`, runtime flags | Consumes the summary and applies policy to produce a `TransitionSemanticDecision`. |
| `handle_model_step` | `IntentTransitionRoutingMixin` | `intent_payload`, `response_text` | Top-level router that consumes decisions from the above helpers and generates prompts or passes control. |

This logic is a mix of structural analysis (e.g., counting nodes) and runtime policy (e.g., deciding `transition_only_recovery_cannot_bundle_action`). The goal of Phase 5 is to separate these concerns.

## 3. Proposed Validator Boundary

A new `TransitionSemanticValidator` class will be created.

- **Location**: `modules/agent/orchestration/transitions/transition_semantic_validator.py`
- **Interface**:
  ```python
  @dataclass(frozen=True)
  class TransitionValidationResult:
      kind: TransitionResultKind
      conflict_reason: str = ""
      # ... other relevant details

  class TransitionSemanticValidator:
      def validate(
          self,
          response_text: str,
          intent_payload: dict | None,
          # Context flags for behavior preservation.
          # Design TBD for Step 1: these flags are for preserving
          # existing classification behavior only, not for policy
          # enforcement. The validator must not become responsible
          # for runtime policy.
          transition_only_required: bool = False,
          reuse_only_required: bool = False,
      ) -> TransitionValidationResult:
          # ... implementation ...
  ```
- **Responsibilities**:
  - Isolate the followup surface by stripping the current intent block.
  - Analyze the surface using `ProtocolCompiler` and existing `TransitionFollowupSemantics` helpers.
  - Classify the surface and return a single, strongly-typed `TransitionValidationResult`.
- **Non-Responsibilities**:
  - Making policy decisions (this remains with `IntentTransitionRoutingMixin`).
  - Granting dispatch permission.
  - Changing any runtime state (`AgentState`).
  - Generating prompts.

## 4. Typed Result Model

The `TransitionResultKind` enum will provide an unambiguous classification of the followup surface.

```python
class TransitionResultKind(str, Enum):
    # Intent applied, no meaningful followup
    NO_FOLLOWUP = "no_followup"
    # Intent applied, followed by a valid single action
    FOLLOWUP_ACTION = "followup_action"
    # Intent applied, followed by a valid plaintext answer
    FOLLOWUP_PLAINTEXT = "followup_plaintext"
    # Intent applied, but followup is invalid (e.g., multiple actions)
    FOLLOWUP_CONFLICT = "followup_conflict"
    # A `transition_only` intent was bundled with an action
    TRANSITION_ONLY_VIOLATION = "transition_only_violation"
    # A `reuse_only` intent was bundled with an action
    REUSE_ONLY_VIOLATION = "reuse_only_violation"
    # A `complete` intent was bundled with an action
    COMPLETE_WITH_ACTION_VIOLATION = "complete_with_action_violation"
    # Fallback for unclassifiable cases
    UNKNOWN = "unknown"
```

## 5. Authority Boundaries

The validator's role is strictly limited to providing **structural classification evidence**. It does not enforce policy or make decisions.

- The validator's output is **evidence only**, not a policy decision.
- It does **not** grant dispatch permission. A result of `FOLLOWUP_ACTION` does not bypass `ActionPolicy`.
- It does **not** prove final-answer correctness or sufficiency. A result of `FOLLOWUP_PLAINTEXT` is a structural fact, not a quality judgment.
- It does **not** mutate active intent state. State changes remain the responsibility of `IntentPolicyEngine` and `IntentTransitionApplyMixin`.
- It does **not** enforce runtime policy. That responsibility remains with `IntentTransitionRoutingMixin` and other policy handlers.

## 6. Behavior Preservation Mapping

The validator will be implemented by migrating existing logic into the new structure. The `IntentTransitionRoutingMixin` will then be refactored to use the validator's typed result.

| Current Logic (`IntentTransitionHandler` / `TransitionFollowupSemantics`) | Proposed `TransitionValidationResult` | Risk | Phase 5 Step |
|---|---|---|---|
| `_has_no_followup_after_intent` | `kind=NO_FOLLOWUP` | Low | 2A |
| `_current_transition_has_inline_action_only` | `kind=FOLLOWUP_ACTION` | Low | 2A |
| `_followup_conflict_reason_after_current_transition` != "" | `kind=FOLLOWUP_CONFLICT` | Low | 2A |
| `evaluate_transition` -> `transition_only_recovery_cannot_bundle_action` | `kind=TRANSITION_ONLY_VIOLATION` | Low | 2B |
| `evaluate_transition` -> `reuse_only_transition_cannot_bundle_action` | `kind=REUSE_ONLY_VIOLATION` | Low | 2B |
| `evaluate_transition` -> `intent_complete_with_action_not_allowed` | `kind=COMPLETE_WITH_ACTION_VIOLATION` | Low | 2B |
| `_reuse_has_inline_plaintext_answer` | `kind=FOLLOWUP_PLAINTEXT` | Medium | Deferred (needs `get_visible_text`) |

## 7. Implementation Slicing (Future Work)

Implementation of this design will be a separate, future task, broken into safe, incremental steps.

- **Phase 5 Step 1: Scaffolding and Type Definition (Done)**
  - Created `transition_semantic_validator.py` with the `TransitionSemanticValidator` class, `TransitionValidationResult` dataclass, and `TransitionResultKind` enum.
  - The `validate` method returns `kind=UNKNOWN`.
  - Basic unit tests for the types and scaffold passed.
  - No logic was migrated.
  - **Next**: Design Step 2A.

- **Phase 5 Step 2A: Core Structural Logic Migration (Done)**
  - Implemented the core structural classification logic for `NO_FOLLOWUP`, `FOLLOWUP_ACTION`, and `FOLLOWUP_CONFLICT` inside `TransitionSemanticValidator`.
  - Added unit and parity tests, which passed.
  - No consumers were migrated, and no old helpers were modified.
  - Runtime behavior is unchanged.
  - **Next**: Design Step 2B.

---

### Phase 5 Step 2A Design: Core Structural Logic Migration

- **Status**: Approved for Implementation
- **Scope**: Design approved. Implementation is authorized for Step 2A only.
- **Implementation Scope**:
    - Implementation may add logic **only** inside `modules/agent/orchestration/transitions/transition_semantic_validator.py`.
    - Tests may be added/updated for Step 2A behavior and parity.
    - `IntentTransitionHandler` and `IntentTransitionRoutingMixin` are read-only for inspection. The existing helpers must not be changed.
    - No consumer migration is authorized.

#### 1. Goal

To migrate the fundamental, context-free structural analysis of the post-intent followup surface from the private methods of `IntentTransitionHandler` into the `TransitionSemanticValidator`. This step populates the validator with its core logic but does not yet migrate any consumers.

#### 2. Proposed Validator Implementation Structure

The `TransitionSemanticValidator.validate` method will be implemented to perform the following sequence:

1.  **Isolate Followup Surface**: Replicate the logic from `IntentTransitionHandler._strip_matching_current_intent_block` to remove the current `<intent>` block from the `response_text`.
2.  **Summarize Surface**: Replicate the logic from `IntentTransitionHandler._followup_surface_summary` to analyze the remaining text using `ProtocolCompiler` and `TransitionFollowupSemantics`. This produces a structured summary (node counts, shape, conflict reason).
3.  **Classify**: Based on the summary, classify the result into one of the core structural kinds.

The implementation of Step 2A may only add logic inside `transition_semantic_validator.py` and its tests. It may replicate or delegate to the existing helper behavior inside `TransitionSemanticValidator`, but must not remove, rename, or change `IntentTransitionHandler` private helpers. `IntentTransitionHandler` and `IntentTransitionRoutingMixin` are read-only for inspection during this step. Physical helper cleanup requires separate approval after consumer migration and parity tests.

#### 3. Behavior Preservation Mapping

| Result Kind | Current Source (`IntentTransitionHandler`) | Proposed Validator Logic |
|---|---|---|
| `NO_FOLLOWUP` | `_has_no_followup_after_intent` | After stripping the intent, check if the surface summary has `has_substantive_nodes: False`. |
| `FOLLOWUP_ACTION` | `_current_transition_has_inline_action_only` | After stripping the intent, check if the summary shows `shape=ACTION_ONLY`, `action_count=1`, `intent_count=0`, and `visible_count=0`. |
| `FOLLOWUP_CONFLICT` | `_followup_conflict_reason_after_current_transition` | After stripping the intent, check if the summary contains a non-empty `conflict_reason`. The reason will be propagated to the result. |

#### 4. Test Plan (for future implementation)

-   **Unit Tests**:
    -   Add dedicated tests for `validate` that produce `NO_FOLLOWUP` for responses with only an intent block.
    -   Add tests that produce `FOLLOWUP_ACTION` for valid intent-action bundles.
    -   Add tests that produce `FOLLOWUP_CONFLICT` for responses with multiple actions, mixed action/text, etc., and verify the `conflict_reason` is preserved.
-   **Parity Tests**:
    -   Create a new test file (`tests/test_transition_validator_parity.py`).
    -   This test will use a small, targeted fixture set of response strings for Step 2A. No new replay framework or broad corpus infrastructure will be built in this step.
    -   For each response, it will call the old `IntentTransitionHandler` helpers and the new `validator.validate` method.
    -   It will assert that the replicated logic exactly preserves the behavior of the current source helpers, ensuring that results are equivalent (e.g., `_has_no_followup_after_intent() == True` maps to `result.kind == NO_FOLLOWUP`).
    -   Any disagreements will be logged for analysis.

#### 5. Explicit Non-Goals for Step 2A

-   **No `FOLLOWUP_PLAINTEXT`**: The logic for detecting plaintext answers (`_reuse_has_inline_plaintext_answer`) is deferred until `get_visible_text` is designed. The validator will not return this kind in Step 2A.
-   **No Context-Sensitive Logic**: The logic for `TRANSITION_ONLY_VIOLATION`, `REUSE_ONLY_VIOLATION`, etc., which depends on runtime state flags, is deferred to Step 2B.
-   **No Consumer Migration**: `IntentTransitionRoutingMixin` will not be changed to call the validator in this step.
-   **No Helper Modification or Deletion**: The original private methods on `IntentTransitionHandler` must not be removed, renamed, or changed. Physical helper cleanup requires separate approval after consumer migration and parity tests are complete.

- **Phase 5 Step 2B: Context-Sensitive Logic Migration (Done)**
  - Implemented the context-sensitive classification logic for `TRANSITION_ONLY_VIOLATION`, `REUSE_ONLY_VIOLATION`, and `COMPLETE_WITH_ACTION_VIOLATION` inside `TransitionSemanticValidator`.
  - Added unit and parity tests, which passed.
  - No consumers were migrated, and no old helpers were modified.
  - Runtime behavior is unchanged.
  - **Next**: Design Step 3 (Consumer Migration).

---

### Phase 5 Step 2B Design: Context-Sensitive Logic Migration

- **Status**: Approved for Implementation
- **Scope**: Design approved. Implementation is authorized for Step 2B only.
- **Implementation Scope**:
    - Implementation may add logic **only** inside `modules/agent/orchestration/transitions/transition_semantic_validator.py`.
    - Tests may be added/updated for Step 2B behavior and parity.
    - `IntentTransitionHandler`, `IntentTransitionRoutingMixin`, and `TransitionFollowupSemantics` are read-only for inspection. The existing helpers must not be changed.
    - No consumer migration is authorized.
    - The priority order of context flag checks must match `TransitionFollowupSemantics.evaluate_transition`.

#### 1. Goal

To migrate the context-sensitive classification logic for followup actions that match existing context-sensitive violation classifications (e.g., `transition_only`, `reuse_only`, `complete`). This logic currently resides in `TransitionFollowupSemantics.evaluate_transition`.

#### 2. Proposed Validator Implementation Structure

The `TransitionSemanticValidator.validate` method will be extended. After performing the core structural analysis from Step 2A, it will apply context-sensitive rules if the structural classification is `FOLLOWUP_ACTION`.

**Validator Inputs**:
The `validate` method signature will be updated to include `completion_requested`. These flags are caller-supplied context facts used only to preserve the existing classification mapping. They must not make the validator responsible for deciding whether the policy itself applies.
```python
def validate(
    self,
    response_text: str,
    intent_payload: dict | None = None,
    *,
    transition_only_required: bool = False,
    reuse_only_required: bool = False,
    completion_requested: bool = False, # New flag
) -> TransitionValidationResult:
```

**Validator Logic**:
1.  Perform core structural analysis (Step 2A).
2.  If the result is `FOLLOWUP_ACTION`:
    - Apply context-sensitive rules. The priority order of these checks must exactly match the existing legacy behavior in `TransitionFollowupSemantics.evaluate_transition`. If the legacy implementation has a different priority, the validator must follow the legacy priority.
    - If `transition_only_required` is `True`, return `TRANSITION_ONLY_VIOLATION`.
    - If `reuse_only_required` is `True`, return `REUSE_ONLY_VIOLATION`.
    - If `completion_requested` is `True`, return `COMPLETE_WITH_ACTION_VIOLATION`.
3.  Otherwise, return the original structural classification.

This logic ensures that the validator provides a more specific classification when context is available, but it does not enforce policy. The consumer (`IntentTransitionRoutingMixin`) remains responsible for acting on the violation.

#### 3. Behavior Preservation Mapping

| Result Kind | Current Source (`TransitionFollowupSemantics.evaluate_transition`) | Proposed Validator Logic |
|---|---|---|
| `TRANSITION_ONLY_VIOLATION` | `kind="transition_only_recovery_cannot_bundle_action"` | `result.kind == FOLLOWUP_ACTION` and `transition_only_required=True` |
| `REUSE_ONLY_VIOLATION` | `kind="reuse_only_transition_cannot_bundle_action"` | `result.kind == FOLLOWUP_ACTION` and `reuse_only_required=True` |
| `COMPLETE_WITH_ACTION_VIOLATION` | `kind="intent_complete_with_action_not_allowed"` | `result.kind == FOLLOWUP_ACTION` and `completion_requested=True` |

#### 4. Test Plan (for future implementation)

-   **Unit Tests**:
    -   Add tests to `test_transition_semantic_validator.py` that verify a `FOLLOWUP_ACTION` is re-classified as `TRANSITION_ONLY_VIOLATION` when the `transition_only_required` flag is set.
    -   Add similar tests for `REUSE_ONLY_VIOLATION` and `COMPLETE_WITH_ACTION_VIOLATION`.
-   **Parity Tests**:
    -   Extend `test_transition_validator_parity.py` with fixtures that trigger these context-sensitive violations.
    -   The parity test will compare the validator's output against the decision from `TransitionFollowupSemantics.evaluate_transition`, which is the direct source of the legacy logic. This avoids building a broad `IntentTransitionRoutingMixin` harness.
    -   The test will verify that a `FOLLOWUP_ACTION` result from the validator, when combined with the context flags, maps correctly to the legacy decision kinds (`transition_only_recovery_cannot_bundle_action`, etc.).

#### 5. Explicit Non-Goals for Step 2B

-   **No Consumer Migration**: `IntentTransitionRoutingMixin` will not be changed.
-   **No Policy Enforcement**: The validator only classifies. It does not:
    - Decide whether policy flags (`transition_only_required`, etc.) are true.
    - Generate recovery prompts.
    - Mutate intent state.
    - Grant or deny dispatch permission.
-   **No `FOLLOWUP_PLAINTEXT`**: This remains deferred.
-   **No Helper Deletion**: `TransitionFollowupSemantics` will not be modified.

- **Phase 5 Step 2C: Defer Plaintext Followup**
  - The `FOLLOWUP_PLAINTEXT` result kind will be defined, but its implementation inside the validator is deferred.
  - The logic path for plaintext followup will remain on a legacy fallback in the consumer (`IntentTransitionRoutingMixin`) until `get_visible_text` is designed and approved in a later phase.

- **Phase 5 Step 3: Consumer Migration (Done)**
  - Migrated the first narrow slice of `IntentTransitionRoutingMixin` to use the validator for recovery/violation classifications (`TRANSITION_ONLY_VIOLATION`, `REUSE_ONLY_VIOLATION`, `COMPLETE_WITH_ACTION_VIOLATION`, `FOLLOWUP_CONFLICT`).
  - A fallback to legacy logic is preserved for all other cases.
  - Runtime behavior is unchanged.
- **Phase 5 Review: Next Migration Slice (Done)**
  - The review of remaining fallback paths is complete.
  - `NO_FOLLOWUP` and `FOLLOWUP_ACTION` are approved as safe candidates for a second migration slice.
  - `FOLLOWUP_PLAINTEXT` is deferred. `UNKNOWN` will remain a fallback.
- **Phase 5 Step 4: Second Consumer Migration (Done)**
  - Migrated `NO_FOLLOWUP` and `FOLLOWUP_ACTION` paths to use the validator.
  - Fallback for `FOLLOWUP_PLAINTEXT` and `UNKNOWN` preserved.
  - **Next**: Phase 5 boundary review.

---

### Phase 5 Step 3: Consumer Migration (Implementation)

- **Status**: Done.
- **Scope**: The first narrow slice of consumer migration in `IntentTransitionRoutingMixin` is complete.
- **Implementation Details**:
    - The `handle_model_step` method in `IntentTransitionRoutingMixin` was refactored to call `validator.validate`.
    - A `match/case` on the `result.kind` was used to route to the appropriate logic block for the approved first slice: `TRANSITION_ONLY_VIOLATION`, `REUSE_ONLY_VIOLATION`, `COMPLETE_WITH_ACTION_VIOLATION`, `FOLLOWUP_CONFLICT`.
    - A fallback to the legacy `evaluate_transition` path was preserved for all other kinds: `NO_FOLLOWUP`, `FOLLOWUP_ACTION`, `FOLLOWUP_PLAINTEXT`, `UNKNOWN`.
    - All tests passed, and runtime behavior is unchanged.

---

### Phase 5 Step 4: Second Consumer Migration (Implementation)

- **Status**: Done.
- **Scope**: The second narrow slice of consumer migration in `IntentTransitionRoutingMixin` is complete.
- **Implementation Details**:
    - The `handle_model_step` method in `IntentTransitionRoutingMixin` was updated to route `NO_FOLLOWUP` and `FOLLOWUP_ACTION` via the validator.
    - A fallback to the legacy `evaluate_transition` path was preserved for `FOLLOWUP_PLAINTEXT` and `UNKNOWN`.
    - All tests passed, and runtime behavior is unchanged.

#### 1. Goal

To perform the second narrow consumer migration slice for the `TransitionSemanticValidator`. This slice will migrate the `NO_FOLLOWUP` and `FOLLOWUP_ACTION` classifications, which represent the primary "happy paths" for post-transition followup.

#### 2. Proposed Implementation Structure

The `handle_model_step` method in `IntentTransitionRoutingMixin` will be refactored to expand the `match/case` on the `validator_result.kind`:

1.  **Add `case TransitionResultKind.NO_FOLLOWUP`**: This block will replicate the logic currently found in the legacy path for `transition_semantic.kind == "no_followup"`. Behavior preservation must be exact:
    -   The `intent_accepted_without_followup` prompt must be generated using the existing `prompt_builder` method.
    -   The returned `IntentHandlingDecision` must have `handled=True` and `reason="intent_accepted_without_followup"`.
    -   All existing side effects (`state.note_intent_only_response()`, `stage_logger.log(...)`) must be preserved.

2.  **Add `case TransitionResultKind.FOLLOWUP_ACTION`**: This block will replicate the pass-through logic for `transition_semantic.kind` in (`intent_applied_with_followup_action`, `intent_reuse_applied_with_inline_followup_action`). Behavior preservation must be exact:
    -   The returned `IntentHandlingDecision` must be `handled=False` to allow the response to proceed to dispatch.
    -   The existing stage logging for this path must be preserved.
    -   This migration does not grant dispatch authority; it only routes the response to the next stage (`ActionPolicyHandler`).

3.  **Fallback for remaining kinds**: The fallback path for `FOLLOWUP_PLAINTEXT` and `UNKNOWN` will be preserved, ensuring they continue to use the legacy `evaluate_transition` logic. This is critical for preserving complex final-answer and plaintext-reuse behaviors.

#### 3. Behavior Preservation Mapping

The `match/case` block will be extended to map the new validator result kinds to the existing logic blocks. All existing prompts, reason strings, source markers, and pass-through behavior must be preserved exactly.

**Proposed Second Slice:**

| `validator.kind` | Legacy `transition_semantic.kind` | Action |
|---|---|---|
| `NO_FOLLOWUP` | `no_followup` | Build and return `intent_accepted_without_followup` prompt. Preserve all side effects (logging, state updates). |
| `FOLLOWUP_ACTION` | `intent_applied_with_followup_action`, `intent_reuse_applied_with_inline_followup_action` | Return `IntentHandlingDecision(handled=False)` to pass through to dispatch. Preserve all logging. |

**Deferred / Fallback to Legacy Path:**

| `validator.kind` | Legacy Path | Action |
|---|---|---|
| `FOLLOWUP_PLAINTEXT` | `evaluate_transition` | Fall back to legacy path to preserve `intent_reuse_applied_with_inline_plaintext_answer` and `intent_completed_with_plaintext_answer` logic. |
| `UNKNOWN` | `evaluate_transition` | Fall back to legacy path to preserve behavior for unhandled edge cases. |

#### 4. Test Plan (for future implementation)

-   **Allowed Files**:
    -   `modules/agent/orchestration/transitions/intent_transition_routing.py`
    -   `tests/test_orchestration_components.py` (for `IntentTransitionHandlerTests`)
-   **Unit Tests**:
    -   Update `IntentTransitionHandlerTests` to use mocks for `validator.validate`.
    -   Add a mock-based routing test for `NO_FOLLOWUP` to verify it triggers the correct prompt-generating `IntentHandlingDecision`.
    -   Add a mock-based routing test for `FOLLOWUP_ACTION` to verify it returns a pass-through decision (`handled=False`).
    -   Ensure existing fallback tests for `FOLLOWUP_PLAINTEXT` and `UNKNOWN` are still valid and passing.
-   **Parity**: The existing parity tests for the validator (`tests/test_transition_validator_parity.py`) already ensure its output for `NO_FOLLOWUP` and `FOLLOWUP_ACTION` matches the legacy logic. No new parity tests are needed for this step.

#### 5. Explicit Non-Goals for Step 4

-   **No `get_visible_text`**: The fallback mechanism ensures the plaintext path is untouched.
-   **No Helper Deletion**: The old helpers in `IntentTransitionHandler` and `TransitionFollowupSemantics` will remain. They will be used by the fallback path.
-   **No Change to Prompts/Reasons**: The migration will reuse the existing prompt-building logic and reason strings.
-   **No `ActionPolicy` or Dispatch Changes**: The `FOLLOWUP_ACTION` path is a simple pass-through and does not grant dispatch authority.
-   **No Final-Answer/Sufficiency Changes**.
-   **No `history.py` modifications**.


## 8. Explicitly Deferred

This design and its subsequent implementation **do not** include:
- **Implementation of `get_visible_text`**: The validator's `FOLLOWUP_PLAINTEXT` logic will depend on a future `get_visible_text` accessor, but the implementation of that accessor is deferred. The initial validator will have a placeholder for this logic, and consumers must rely on a legacy fallback for this path.
- **Changes to `ActionPolicy` or dispatch behavior**: The validator does not grant dispatch permission.
- **Changes to final-answer/sufficiency logic**: The validator classifies structure, it does not determine if a plaintext answer is "correct" or "final".
- **Changes to memory/plan board logic**.
- **Any modifications to `history.py`**.
