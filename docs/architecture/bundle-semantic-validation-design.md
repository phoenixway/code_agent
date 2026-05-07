# Phase 6 Design: Bundle Semantic Validation Pass

- **Status**: Approved
- **Scope**: Design approved. Implementation is authorized for Step 1 (scaffolding) only.
- **Implementation Scope**: The approved implementation scope for this design is **Step 1 (Scaffolding and Type Definition) only**. Steps 2, 3, 4, and beyond require separate design review and approval. The `INVALID_MIXED_VISIBLE_TEXT` classification remains deferred.

## 1. Purpose and Guiding Principles

This document defines the design for a `BundleSemanticValidator`, a new component responsible for classifying the structural validity and safety of action bundles.

Currently, the logic for validating "atomic" intent-action bundles and other multi-action responses is spread across `ResponsePipelinePrevalidationMixin`, `ActionPolicyHandler`, and the `ProtocolCompiler`. This distribution makes the rules difficult to track, test, and maintain.

The `BundleSemanticValidator` will centralize the classification interface for atomic bundle validation evidence incrementally. It will provide a single, testable component that returns a strongly-typed classification, which will simplify the pre-dispatch pipeline and clarify the boundary between structural validation and runtime policy. The validator classifies evidence; it does not own all validation logic and does not replace `ResponsePipelinePrevalidationMixin`, `ActionPolicyHandler`, or `DispatchPipeline`.

- **Single Access Point**: The validator will be the single testable entry point for bundle classification.
- **Strongly-Typed Output**: The validator will return a `dataclass` with an `Enum` kind, replacing ambiguous string-based reasons and scattered boolean checks.
- **Behavior Preservation**: The validator will be designed as a behavior-preserving refactor. Its initial implementation will replicate existing logic, verified with parity tests.
- **Strict Authority Boundaries**: The validator provides **structural classification evidence only**, not **policy decisions**. It can state that a response contains an invalid bundle, but it cannot generate a recovery prompt, decide to stop the loop, or grant dispatch permission. It does not replace `ActionPolicy` or `DispatchPipeline`.

## 2. Current Behavior Inventory

| Logic | Owner | Inputs | Semantics |
|---|---|---|---|
| `_reject_compiler_invalid_atomic_bundle_before_transition` | `ResponsePipelinePrevalidationMixin` | `parsed_output` (compiler fields) | Rejects bundles based on specific compiler error codes (`E_ATOMIC_BUNDLE...`, `E_FILE_CONTENT...`). |
| `_reject_invalid_atomic_bundle_before_transition` | `ResponsePipelinePrevalidationMixin` | `parsed_output`, `segments`, `ActionPolicyHandler.validate_atomic_bundle_action` | Orchestrates bundle validation, calling `ActionPolicyHandler` for deeper checks. |
| `validate_atomic_bundle_action` | `ActionPolicyHandler` | `segments`, `parsed_output`, runtime context | Performs detailed validation of a single-action bundle, including file body pairing and intent contract checks. |
| `decide` (multi-action logic) | `ActionPolicyHandler` | `segments`, `parsed_output` | Handles non-bundle multi-action cases, such as allowing read-only batches. |
| `_classify` | `ProtocolCompiler` | `ResponseAst` | The ultimate source of structural shapes (`INTENT_ACTION_BUNDLE`, `READ_ONLY_BATCH_CANDIDATE`) and errors. |
| `resolve_protocol_authority` | `protocol_decision_bridge` | `parsed_output` | Arbitrates between compiler and legacy `invalid_kind` for bundle-related errors like `multiple_actions`. |

## 3. Proposed Validator Boundary

A new `BundleSemanticValidator` class will be created.

- **Location**: `modules/agent/orchestration/responses/bundle_semantic_validator.py`
- **Interface**:
  ```python
  @dataclass(frozen=True)
  class BundleValidationResult:
      kind: BundleResultKind
      reason: str = ""
      # ... other relevant details

  class BundleSemanticValidator:
      def validate(
          self,
          parsed_output: ParsedModelOutput,
          segments: list,
          # ... other context if needed
      ) -> BundleValidationResult:
          # ... implementation ...
  ```
- **Responsibilities**:
  - Analyze `parsed_output` (including `compiler_ir`) and `segments`.
  - Classify the response's bundle structure and safety.
  - Return a single, strongly-typed `BundleValidationResult`.
- **Non-Responsibilities**:
  - Making policy decisions (this remains with `ActionPolicyHandler` and the response pipeline).
  - Granting dispatch permission.
  - Mutating runtime state.
  - Generating recovery prompts.
  - Executing actions.

## 4. Typed Result Model

The `BundleResultKind` enum will provide an unambiguous classification.

```python
class BundleResultKind(str, Enum):
    # Not a bundle shape
    NO_BUNDLE_SHAPE = "no_bundle_shape"
    # A structurally valid atomic intent-action bundle candidate
    INTENT_ACTION_BUNDLE_CANDIDATE = "intent_action_bundle_candidate"
    # A structurally valid batch of multiple read-only actions candidate
    READONLY_ACTION_BATCH_CANDIDATE = "readonly_action_batch_candidate"
    # Multiple actions that are not a valid read-only batch
    INVALID_MULTIPLE_ACTIONS = "invalid_multiple_actions"
    # Action payload is a JSON array, not an object
    INVALID_ACTION_ARRAY = "invalid_action_array"
    # <file_content> is missing or paired with the wrong action
    INVALID_FILE_CONTENT_PAIRING = "invalid_file_content_pairing"
    # A `complete` intent is bundled with an action
    INVALID_INTENT_COMPLETE_WITH_ACTION = "invalid_intent_complete_with_action"
    # Visible text is mixed with control protocol tags (DEFERRED - placeholder only)
    # This classification must not be implemented in Phase 6 without a separate
    # get_visible_text / visible-control boundary design.
    INVALID_MIXED_VISIBLE_TEXT = "invalid_mixed_visible_text"
    # Fallback for unclassifiable or non-bundle cases
    UNKNOWN = "unknown"
```

## 5. Authority Boundaries

The validator's role is strictly limited to providing **structural and safety classification evidence**.

- The validator's output is **evidence only**, not a policy decision.
- It does **not** grant dispatch permission. A result of `INTENT_ACTION_BUNDLE_CANDIDATE` does not bypass `ActionPolicy`.
- It does **not** replace `ActionPolicy` or `DispatchPipeline`.
- It does **not** mutate runtime state.
- It does **not** execute actions.
- It does **not** generate recovery prompts.

## 6. Behavior Preservation Mapping (High-Level)

| Current Logic | Proposed `BundleValidationResult` | Risk |
|---|---|---|
| `_reject_compiler_invalid_atomic_bundle_before_transition` (for `E_ATOMIC_BUNDLE...`) | `kind=INVALID_MULTIPLE_ACTIONS` or `INVALID_ACTION_ARRAY` | Low |
| `_reject_compiler_invalid_atomic_bundle_before_transition` (for `E_FILE_CONTENT...`) | `kind=INVALID_FILE_CONTENT_PAIRING` | Low |
| `ActionPolicyHandler.validate_atomic_bundle_action` (file body check) | `kind=INVALID_FILE_CONTENT_PAIRING` | Medium (Deferred) |
| `ActionPolicyHandler.decide` (read-only batch check) | `kind=READONLY_ACTION_BATCH_CANDIDATE` or `INVALID_MULTIPLE_ACTIONS` | Medium (Deferred) |
| `ProtocolCompiler` shape `INTENT_ACTION_BUNDLE` | `kind=INTENT_ACTION_BUNDLE_CANDIDATE` | Low |

Logic from `ActionPolicyHandler` is considered higher risk and is deferred. Any migration of `ActionPolicyHandler`-adjacent logic requires a separate design approval after the initial compiler-driven validation is complete.

## 7. Implementation Slicing (Future Work)

- **Step 1: Design & Scaffolding**: Create the `BundleSemanticValidator` class, `BundleValidationResult` dataclass, and `BundleResultKind` enum. The `validate` method will return `UNKNOWN`. Add basic unit tests for the scaffold. (This design document fulfills the "Design" part).
- **Step 2: Validator Implementation (Compiler-Only)**: Implement classification logic that relies **only** on compiler metadata (`compiler_ir`, `compiler_error_code`, etc.). Add comprehensive unit and parity tests against existing compiler-driven prevalidation logic. No consumers will be migrated.
- **Step 3: First Consumer Migration**: After parity is proven for Step 2, migrate the lowest-risk consumer: `_reject_compiler_invalid_atomic_bundle_before_transition`.
- **Step 4+**: Defer migration of `ActionPolicyHandler`-adjacent logic. Any further migration requires a new, separate design document and approval.

**Behavior Preservation**: Any future consumer migration must be a behavior-preserving refactor. It must preserve the exact legacy reason strings, recovery prompts, source markers, recovery IDs, and routing behavior.

## 8. Explicitly Deferred

- `DispatchPipeline` or `ActionPolicy` rewrites.
- `get_visible_text` implementation and `INVALID_MIXED_VISIBLE_TEXT` classification.
- `FOLLOWUP_PLAINTEXT` migration.
- Final-answer/sufficiency logic.
- Memory/plan board validation.
- `history.py` refactor.
- Deletion of any legacy helpers until all consumers are migrated.

## 9. Test Plan (for future implementation)

- **Unit Tests**: For each `BundleResultKind`, create tests that provide specific `ParsedModelOutput` and `segments` to trigger that classification.
- **Parity Tests**: Create tests that run a response through both the old logic (`_reject_invalid_atomic_bundle_before_transition`, etc.) and the new validator, asserting that the outcomes are equivalent.
- **Regression Tests**: Ensure existing tests for key invariants (e.g., from `test-contracts.md`) continue to pass, especially those related to action arrays and compiler `INVALID` states.
