# Phase 5 Design: TransitionSemanticValidator

- **Status**: In Review
- **Scope**: Design only. Implementation is forbidden until this design is approved.

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

- **Phase 5 Step 1: Scaffolding and Type Definition**
  - Create `transition_semantic_validator.py` with the `TransitionSemanticValidator` class, `TransitionValidationResult` dataclass, and `TransitionResultKind` enum.
  - The `validate` method will initially do nothing but return `kind=UNKNOWN`.
  - Add basic unit tests for the new types.
  - **No consumer migration.**

- **Phase 5 Step 2A: Core Structural Logic Migration**
  - Migrate the core structural classification logic for `NO_FOLLOWUP`, `FOLLOWUP_ACTION`, and `FOLLOWUP_CONFLICT` from `IntentTransitionHandler`'s private methods into the `validate` method.
  - The validator will use the existing `TransitionFollowupSemantics` as a helper.
  - Add extensive unit tests and parity tests for these specific result kinds.
  - **No consumer migration.**

- **Phase 5 Step 2B: Context-Sensitive Logic Migration**
  - Migrate the logic for context-sensitive violations: `TRANSITION_ONLY_VIOLATION`, `REUSE_ONLY_VIOLATION`, and `COMPLETE_WITH_ACTION_VIOLATION`.
  - This step depends on finalizing the design for how context flags are passed to the validator.
  - Add unit tests and parity tests for these specific result kinds.
  - **No consumer migration.**

- **Phase 5 Step 2C: Defer Plaintext Followup**
  - The `FOLLOWUP_PLAINTEXT` result kind will be defined, but its implementation inside the validator is deferred.
  - The logic path for plaintext followup will remain on a legacy fallback in the consumer (`IntentTransitionRoutingMixin`) until `get_visible_text` is designed and approved in a later phase.

- **Phase 5 Step 3: Consumer Migration**
  - Refactor `IntentTransitionRoutingMixin.handle_model_step` to:
    1. Call `validator.validate(...)`.
    2. Use a `match/case` or `if/elif` block on the `result.kind` to route to the correct logic (e.g., generate prompt, pass through).
  - This will replace the multiple calls to the old private helpers.
  - The old private helpers in `IntentTransitionHandler` will remain until all migrated paths have established parity and a separate cleanup is approved.

## 8. Explicitly Deferred

This design and its subsequent implementation **do not** include:
- **Implementation of `get_visible_text`**: The validator's `FOLLOWUP_PLAINTEXT` logic will depend on a future `get_visible_text` accessor, but the implementation of that accessor is deferred. The initial validator will have a placeholder for this logic, and consumers must rely on a legacy fallback for this path.
- **Changes to `ActionPolicy` or dispatch behavior**: The validator does not grant dispatch permission.
- **Changes to final-answer/sufficiency logic**: The validator classifies structure, it does not determine if a plaintext answer is "correct" or "final".
- **Changes to memory/plan board logic**.
- **Any modifications to `history.py`**.
