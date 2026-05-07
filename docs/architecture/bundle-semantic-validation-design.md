# Phase 6 Design: Bundle Semantic Validation Pass

- **Phase 6 Status**: Approved
- **Step 1 (Scaffolding) Status**: Done
- **Step 2 (Compiler-Only Logic) Status**: Design for Step 2A approved.
- **Step 2A Implementation**: Authorized.
- **Step 2B/2C Implementation**: Not authorized.

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
    # A response shape that is a candidate for a batch of multiple read-only actions.
    # This is a structural classification only. ActionPolicy remains the authority
    # on whether the actions are truly safe to dispatch as a batch.
    READONLY_ACTION_BATCH_CANDIDATE = "readonly_action_batch_candidate"
    # Multiple actions that are not a valid read-only batch
    INVALID_MULTIPLE_ACTIONS = "invalid_multiple_actions"
    # Action payload is a JSON array, not an object
    INVALID_ACTION_ARRAY = "invalid_action_array"
    # <file_content> is missing or paired with the wrong action
    INVALID_FILE_CONTENT_PAIRING = "invalid_file_content_pairing"
    # A `complete` intent is bundled with an action.
    # DEFERRED: This classification touches intent completion policy and is
    # deferred from Step 2.
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

## 7. Implementation Slicing (High-Level)

- **Step 1: Design & Scaffolding (Done)**: Create the `BundleSemanticValidator` class, `BundleValidationResult` dataclass, and `BundleResultKind` enum. The `validate` method will return `UNKNOWN`. Add basic unit tests for the scaffold.
- **Step 2: Validator Implementation (Compiler-Only)**: Implement classification logic that relies **only** on compiler metadata (`compiler_ir`, `compiler_error_code`, etc.). Add comprehensive unit and parity tests against existing compiler-driven prevalidation logic. No consumers will be migrated.
- **Step 3: First Consumer Migration**: After parity is proven for Step 2, migrate the lowest-risk consumer: `_reject_compiler_invalid_atomic_bundle_before_transition`.
- **Step 4+**: Defer migration of `ActionPolicyHandler`-adjacent logic. Any further migration requires a new, separate design document and approval.

**Behavior Preservation**: Any future consumer migration must be a behavior-preserving refactor. It must preserve the exact legacy reason strings, recovery prompts, source markers, recovery IDs, and routing behavior.

## 8. Step 2 Design: Compiler-Only Classification Logic

This section details the design for Step 2. Implementation is not authorized until this design is approved.

### 8.1. Scope and Boundaries

Step 2 is strictly limited to implementing classification logic that can be derived from compiler metadata available in `parsed_output`.

- **Allowed Inputs**: The `validate` method may only inspect its `parsed_output` argument, specifically the `compiler_shape`, `compiler_error_code`, `compiler_ir`, and `invalid_kind` fields. It may use `semantic_accessors` to read these fields safely.
- **Forbidden Inputs**: The validator **must not** access runtime state, call `ActionPolicyHandler`, inspect `segments` (for this step), or perform any I/O.
- **Fallback**: If necessary compiler metadata is missing, the validator must return `BundleValidationResult(kind=BundleResultKind.UNKNOWN)`.

### 8.2. Classification Mapping

The following classifications are in scope for Step 2. They map directly to existing compiler-driven logic in `ResponsePipelinePrevalidationMixin` and `ProtocolCompiler`.

| Current Logic/Source | Compiler Metadata | Proposed `BundleResultKind` | Notes (to preserve for consumer migration) |
|---|---|---|---|
| `_reject_compiler_invalid_atomic_bundle_before_transition` | `compiler_error_code` = `E_ATOMIC_BUNDLE_REQUIRES_EXACTLY_ONE_ACTION`, `invalid_kind` = `action_payload_array` | `INVALID_ACTION_ARRAY` | reason: "Atomic intent/action bundle requires exactly one <action> block with one JSON object. Do not return an action array." |
| `_reject_compiler_invalid_atomic_bundle_before_transition` | `compiler_error_code` = `E_ATOMIC_BUNDLE_REQUIRES_EXACTLY_ONE_ACTION`, `invalid_kind` = `multiple_actions` | `INVALID_MULTIPLE_ACTIONS` | reason: "Atomic intent/action bundle requires exactly one <action> block. Do not return multiple <action> blocks." |
| `_reject_compiler_invalid_atomic_bundle_before_transition` | `compiler_error_code` = `E_FILE_CONTENT_REQUIRES_ACTION` or `E_FILE_CONTENT_ACTION_MISMATCH` | `INVALID_FILE_CONTENT_PAIRING` | reason: "write_file_block requires a complete <file_content>...</file_content> block immediately after </action>." |
| `ProtocolCompiler._classify` | `compiler_ir.shape` = `INTENT_ACTION_BUNDLE` (no errors) | `INTENT_ACTION_BUNDLE_CANDIDATE` | This is a structural candidate, not a policy approval. |
| `ProtocolCompiler._classify` | `compiler_ir.shape` = `READ_ONLY_BATCH_CANDIDATE` (no errors) | `READONLY_ACTION_BATCH_CANDIDATE` | This is a structural shape candidate. `ActionPolicy` still owns the final decision on whether the batch is safe to dispatch. |
| `ProtocolCompiler._classify` | `compiler_ir.shape` is `INTENT_ONLY` or `ACTION_ONLY` | `NO_BUNDLE_SHAPE` | These shapes are not bundles. Shapes with visible text (`PLAINTEXT_ONLY`, etc.) are deferred and must return `UNKNOWN`. |

### 8.3. Deferred Classifications

The following classifications are **out of scope** for Step 2:

- `INVALID_INTENT_COMPLETE_WITH_ACTION`: This classification is deferred because it touches intent completion policy, which is a separate domain from bundle structure.
- Any logic requiring `ActionPolicyHandler.validate_atomic_bundle_action`.
- `INVALID_MIXED_VISIBLE_TEXT` (requires `get_visible_text` design).
- Any classification requiring runtime state (e.g., active intent contract checks).
- Any classification of shapes that contain visible text (e.g., `PLAINTEXT_ONLY`, `INTENT_COMPLETE_WITH_TEXT`), which must return `UNKNOWN` until `get_visible_text` is designed.

### 8.4. Test Strategy for Step 2

- **Unit Tests**: Add tests to `test_bundle_semantic_validator.py` for each classification mapping defined above. Each test will construct a `ParsedModelOutput` with the necessary compiler fields to trigger the specific `BundleResultKind`.
- **Parity Tests**: Create a new test file for parity checks. These tests will not simulate or re-implement legacy logic. Instead, they will use mapping tables to assert that a given `compiler_error_code` and `invalid_kind` from a `ParsedModelOutput` fixture results in the expected `BundleResultKind`, based on the classification mapping in this design. This proves the validator correctly implements the documented mapping.
- **Boundary Tests**: Add tests to prove that `ActionPolicyHandler` is not called. This can be done using `unittest.mock.patch`.
- **Fallback Tests**: Add tests to ensure that `validate` returns `UNKNOWN` when compiler metadata is missing or ambiguous.

### 8.5. Proposed Implementation Slicing for Step 2

To ensure a safe and incremental implementation, Step 2 should be broken down further:

- **Step 2A: Error-Code-Driven Classification (Approved for Implementation)**: Implement only the classifications based on `compiler_error_code` that map to logic currently in `_reject_compiler_invalid_atomic_bundle_before_transition`. This includes: `INVALID_ACTION_ARRAY`, `INVALID_MULTIPLE_ACTIONS`, and `INVALID_FILE_CONTENT_PAIRING`.
- **Step 2B: Shape-Driven Classification (Design in Review)**: Implement the classifications based on `compiler_ir.shape` for clear bundle or non-bundle shapes: `INTENT_ACTION_BUNDLE_CANDIDATE`, `READONLY_ACTION_BATCH_CANDIDATE`, and `NO_BUNDLE_SHAPE` (for safe shapes like `INTENT_ONLY`).
- **Step 2C: Parity Testing (Design in Review)**: Implement the parity tests described in the test strategy to prove behavioral equivalence before any consumer is migrated.

## 9. Explicitly Deferred

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
