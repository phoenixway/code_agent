# Phase 7 Design: ActionPolicy-Dependent Bundle Validation

- **Phase 7 Status**: Design Approved
- **Implementation**: Authorized for Step 2 (Characterization Tests) only

## 1. Purpose and Guiding Principles

This document defines the design for refactoring the runtime-policy-dependent validation of "atomic" intent-action bundles. This is a direct continuation of Phase 6, which handled compiler-only bundle validation.

The primary goal is to clarify the complex validation logic currently split between `ResponsePipelinePrevalidationMixin` and `ActionPolicyHandler`, specifically focusing on the `_reject_invalid_atomic_bundle_before_transition` method and its main dependency, `ActionPolicyHandler.validate_atomic_bundle_action`.

- **Clarify Authority**: Reinforce the boundary between structural validation (`BundleSemanticValidator`) and runtime policy (`ActionPolicyHandler`).
- **Improve Testability**: First, lock down existing behavior with characterization tests. Then, evaluate whether introducing strongly-typed policy results is warranted to improve testability and clarity.
- **Strict Behavior Preservation**: This is a pure refactoring. All changes must preserve the exact legacy behavior. This includes:
    - The exact `ResponsePipelineOutcome` fields, `AtomicBundlePlan` fields, and `stage_logger` metadata.
    - The exact legacy `reason` strings, `details` dictionary fields, and inputs to the `prompt_builder`.
    - Distinct legacy `reason` strings must not be collapsed into a single enum kind unless characterization tests prove they are behavior-equivalent.
- **No New Behavior**: This phase will not introduce new validation rules or change existing ones.

## 2. Current Behavior Inventory

The validation of a potential atomic bundle involves a collaboration between the prevalidation mixin and the action policy handler.

| Component | Method | Inputs | Authority | Output |
|---|---|---|---|---|
| `ResponsePipelinePrevalidationMixin` | `_reject_invalid_atomic_bundle_before_transition` | `ctx`, `payload`, `parsed_output`, `segments` | Orchestration, Routing | `ResponsePipelineOutcome` (rejection) or `None` (pass-through) |
| `ActionPolicyHandler` | `validate_atomic_bundle_action` | `ctx`, `segments`, `proposed_active_intent` | Runtime Policy, Safety | `AtomicBundleActionValidationResult` (boolean `ok` + details) |

### `_reject_invalid_atomic_bundle_before_transition` Flow:

1.  **Gating**: Checks if `payload_mode` is a bundle mode (`activate`, `reuse`, `replace`) and if `has_any_action_proposal` is true.
2.  **Intent Preview**: Calls `intent_transitions.preview_payload_decision` to get the proposed active intent. Rejects if the transition itself is invalid.
3.  **Policy Delegation**: Calls `ActionPolicyHandler.validate_atomic_bundle_action` with the proposed intent.
4.  **Routing**:
    - If `validate_atomic_bundle_action` returns `ok=True`, the method passes through, allowing the pipeline to continue.
    - If `validate_atomic_bundle_action` returns `ok=False`, the method constructs a `ResponsePipelineOutcome` to reject the action and trigger a recovery prompt, using the `reason` and `details` from the validation result.

### `validate_atomic_bundle_action` Flow:

This method performs a series of checks. The first one to fail returns a result.

1.  **Command Count**: Ensures exactly one action command is present (using `_atomic_bundle_candidate_commands`).
2.  **Action Shape Guard**: Checks for invalid action shapes (e.g., `noop_edit`, `intent` payload inside `<action>`).
3.  **File Body Validation**: Ensures actions that require a file body (e.g., `write_file_block`) have one.
4.  **Intent Guard**: Checks if the action requires an intent and if the proposed intent satisfies the contract (e.g., action is in `allowed_actions`).
5.  **Pre-Action Check**: Performs final runtime checks via `intent_runtime.pre_action_check`.

## 3. Authority Boundary and Component Design

The existing component boundaries are largely correct but can be clarified.

- **`BundleSemanticValidator`**: Remains unchanged. Its authority is limited to compiler-only structural facts. It will **not** be extended to depend on `segments` or `ActionPolicy`.
- **`ActionPolicyHandler`**: This is the correct owner for runtime policy and safety checks. The `validate_atomic_bundle_action` method will be refactored internally to be clearer but will remain here.
- **`ResponsePipelinePrevalidationMixin`**: This is the correct owner for pre-dispatch routing. It will continue to orchestrate the validation call and route the outcome.

**Conclusion**: The current design preference is to avoid introducing a new component unless characterization tests (Step 2) reveal a clear need. The refactoring will focus on clarifying the existing interface between `ActionPolicyHandler` and `ResponsePipelinePrevalidationMixin`. `BundleSemanticValidator` must not be extended with `segments` or `ActionPolicy` dependencies.

## 4. Candidate Typed Result Model

This is a candidate model for a future refactoring step. It may be introduced only after characterization tests (Step 2) are complete and a separate implementation step is approved.

The existing `AtomicBundleActionValidationResult` could be enhanced by replacing the string-based `reason` with a strongly-typed `Enum`.

```python
# To be created in a suitable policy models file
class AtomicBundlePolicyResultKind(str, Enum):
    OK = "ok"
    REJECTED_MULTIPLE_ACTIONS = "rejected_multiple_actions"
    REJECTED_INVALID_SHAPE = "rejected_invalid_shape"
    REJECTED_MISSING_FILE_CONTENT = "rejected_missing_file_content"
    REJECTED_INTENT_REQUIRED = "rejected_intent_required"
    REJECTED_INTENT_ACTION_NOT_ALLOWED = "rejected_intent_action_not_allowed"
    UNKNOWN = "unknown"

# To be updated
@dataclass
class AtomicBundleActionValidationResult:
    kind: AtomicBundlePolicyResultKind
    details: dict | None = None
```

## 5. Behavior Preservation Mapping

This table provides an illustrative mapping of the current logic in `validate_atomic_bundle_action` to the candidate typed result. It **must not** be used as an implementation map until Step 2 characterization tests have inventoried the exact legacy `reason` strings, `details` dictionaries, prompt inputs, and logging metadata.

Do not collapse distinct legacy `reason` strings into a shared enum kind unless characterization tests prove they are behavior-equivalent.

| Current Check | Current `reason` | Proposed `kind` | Risk |
|---|---|---|---|
| Not exactly one command | `atomic_bundle_requires_exactly_one_action` | `REJECTED_MULTIPLE_ACTIONS` | Low |
| `_handle_action_shape_guard` | `noop_edit`, etc. | `REJECTED_INVALID_SHAPE` | Low |
| `_bundle_file_body_validation` | `missing_file_content_block` | `REJECTED_MISSING_FILE_CONTENT` | Low |
| `intent_guard.action_requires_intent` | `intent_action_not_allowed`, etc. | `REJECTED_INTENT_REQUIRED` | Low |
| `preview_runtime.pre_action_check` | `intent_action_not_allowed`, etc. | `REJECTED_INTENT_ACTION_NOT_ALLOWED` | Low |
| All checks pass | N/A | `OK` | Low |

The `details` dictionary in the result will continue to hold the message and other data needed to construct the exact legacy recovery prompt.

## 6. Implementation Slicing

Phase 7 will be implemented in small, verifiable steps.

- **Step 1: Design (This Document)**: The design is approved.
- **Step 2: Characterization Tests (Done)**: Characterization tests were added to `tests/test_action_policy.py` (new file) and `tests/test_response_pipeline_prevalidation.py`. The tests cover all rejection and pass-through branches, locking down the exact legacy behavior of `ActionPolicyHandler.validate_atomic_bundle_action` and `ResponsePipelinePrevalidationMixin._reject_invalid_atomic_bundle_before_transition`. All tests passed. No production code was changed.

The following steps are future candidates. Each requires a separate approval.

- **Step 3A: Typed Result Scaffolding (Done)**:
    - **Goal**: Create the scaffolding for the typed result model.
    - **Implementation**: Created `modules/agent/orchestration/runtime/action_policy_models.py` with the `AtomicBundlePolicyResultKind` enum and `AtomicBundleActionValidationResult` dataclass. Added `tests/test_action_policy_models.py`. All tests passed. No runtime behavior was changed.
- **Candidate Step 3B: `ActionPolicyHandler` Refactor (Ready for Review)**:
    - Refactor `ActionPolicyHandler.validate_atomic_bundle_action` to return the new `AtomicBundleActionValidationResult` with the typed `kind`.
    - This would be an internal refactor of `ActionPolicyHandler`. All characterization tests from Step 2 must continue to pass without any changes to the tests themselves.
- **Candidate Step 4: Consumer Migration (Not Authorized)**:
    - Refactor `ResponsePipelinePrevalidationMixin._reject_invalid_atomic_bundle_before_transition` to use the new typed result from `validate_atomic_bundle_action`.
    - The `if/elif` logic would switch on `result.kind` instead of string comparisons.
    - All characterization tests must continue to pass.

## 7. Explicitly Deferred

- **DispatchPipeline** or broad **ActionPolicy** rewrites.
- Plan-first execution (Phase 8).
- `get_visible_text` implementation.
- Classification of `ACTION_ONLY` or any visible-text shapes.
- Deletion of any legacy helpers.
- Migration of any other consumers.

## 8. Test Strategy

- **Characterization Tests**: Before any production code is changed (Step 2), create tests that capture the full input/output behavior of the target methods. These tests will serve as a contract that the refactoring must not break.
- **Behavior Preservation**: The test suite must prove that for a given input, the `ResponsePipelineOutcome` (or `None` for pass-through) is identical before and after the refactoring. This includes the `reason`, `source`, `next_query`, and `atomic_bundle_plan` fields.
- **Regression Tests**: Existing tests in `test_response_pipeline_stages.py` and other related files must remain green.

## 9. Recommendation

This design is approved. The scaffolding for the typed result is complete. The next step is to review and approve the implementation of **Phase 7, Step 3B: `ActionPolicyHandler` Refactor**.
