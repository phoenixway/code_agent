# Phase 9 Design: Plan-First Bundle Execution

- **Phase 9 Status**: Step 2 Producer/Consumer Contract Design Complete
- **Scope**: Action / bundle execution path only
- **Non-Goals**:
  - No parser rewrite
  - No final-answer or stop-gate migration
  - No board/checkpoint migration
  - No runtime behavior change in this step

## Goal

Re-open the deferred plan-first execution thread with a concrete authority split:

- Compiler / IR owns structure.
- Policy owns permission and semantic safety.
- Execution layer owns side effects.
- Response pipeline orchestrates, but should not remain the long-term owner of semantic re-parsing for dispatch.

This step is design-only. It does not authorize execution-path migration yet.

## Current Execution Path

The current action / bundle flow is already partially plan-shaped, but it is not yet plan-first end to end.

1. `ResponsePipelinePrevalidationMixin._apply_compiler_diagnosis(...)`
   - Runs the protocol compiler.
   - Stores `compiler_shape`, `compiler_error_code`, `compiler_ir`, and `runtime_protocol_semantics` on `ParsedModelOutput`.
2. `ResponsePipelineStagesMixin._run_classification_stage(...)`
   - Parses/classifies the response.
   - Preserves legacy parser segments.
   - Keeps compiler-derived facts alongside legacy fields.
3. `ResponsePipelineStagesMixin._run_post_classification_stage(...)`
   - Runs output recovery, authority arbitration, and `ActionPolicy`.
   - Builds `ExecutionPlan` only at the `dispatch_ready` outcome boundary via `_build_execution_plan(...)`.
4. `DispatchPipeline.run_iteration(...)`
   - Receives both `segments` and optional `execution_plan`.
   - Emits `pre_action_text` from `ExecutionPlan.output_effects`.
   - Still dispatches via raw `segments` using `dispatcher.dispatch_segments(...)`.
5. `DispatchOutcomeHandler`
   - Builds `ExecutionCommit` from processed dispatch segments and system results.

## Current Authority Split

| Layer | Current owner | Current evidence | Notes |
|---|---|---|---|
| Structural protocol shape | Compiler / IR | `compiler_shape`, `compiler_ir`, `runtime_protocol_semantics` | Good progress from Phases 6-8. |
| Atomic bundle structural validation | `BundleSemanticValidator` + compiler metadata | `parsed_output`, compiler error code / IR | Phase 6 complete. |
| Atomic bundle policy validation | `ActionPolicyHandler` | `parsed_output.compiler_ir` plus legacy `segments` fallback | Phase 7 complete, but still not plan-first. |
| Response orchestration | `ResponsePipeline*` mixins | raw response, parsed output, segments, runtime state | Still mixes structure, policy routing, and dispatch preparation. |
| Side effects / tool execution | `DispatchPipeline` + dispatcher | raw `segments` | Main remaining non-plan-first boundary. |

## Current Compiler IR Usage

Compiler IR is already consumed in several places:

- `ResponsePipelinePrevalidationMixin` stores IR on `ParsedModelOutput`.
- `ResponsePipelineStagesMixin._build_execution_plan(...)` derives:
  - `transaction_kind`
  - `state_effects`
  - `action_effects`
  - `output_effects` for pre-action text
- `ActionPolicyHandler` reads IR for:
  - effective action payload
  - `file_content`
  - action count
  - multi-write / write-like checks
  - atomic bundle candidate extraction

This means the producer-side IR groundwork already exists. The missing piece is consumer-side execution authority.

## Current ActionPolicy / Validation Boundary

`ActionPolicyHandler` currently owns permission and runtime-policy checks, including:

- formal intent requirements
- multi-write escalation
- build-fix intent restrictions
- disallowed actions under active intent
- action-shape guards
- atomic bundle action validation

This boundary should remain intact in Phase 9. The plan-first slice must not move permission logic into the compiler or dispatch layer.

## Current ResponsePipeline Responsibility

The response pipeline currently does all of the following:

- normalization
- parsing/classification
- compiler diagnosis
- recovery routing
- authority arbitration
- policy gating
- execution-plan construction
- dispatch handoff

That is the main design pressure for Phase 9. The pipeline should remain the orchestrator, but it should not remain the long-term source of dispatch semantics by reinterpreting raw segments at the dispatch boundary.

## Existing Phase 6 / 7 Decisions To Preserve

Phase 9 must preserve the decisions already locked in by the earlier bundle work:

- Only validated bundle/execution plans may authorize runtime mutation or dispatch.
- Compiler owns structure; runtime policy does not replace compiler shape facts.
- `ActionPolicyHandler` remains the permission gate for runtime-owned checks.
- Legacy compatibility fields and fallbacks remain acceptable when parity is not yet proven.
- No behavior-changing cleanup of legacy `reason` / `details` contracts is in scope here.

## Remaining Legacy Semantics Dependencies

The current execution path is still not fully plan-first because these dependencies remain:

- `DispatchPipeline` still executes `segments`, not plan-derived action commands.
- `ActionPolicyHandler._atomic_bundle_candidate_commands(...)` still falls back to legacy parsed `segments` when IR actions are absent.
- `ResponsePipelineOutcome.dispatch_ready(...)` still carries both `segments` and `execution_plan`.
- `DispatchOutcomeHandler` still infers committed actions from processed dispatch segments instead of a plan/commit contract alone.

These are the concrete seams for future migration.

## Step 1 Design Gate Conclusion

The design gate is open for the Plan-First Bundle Execution slice.

- **Go**: continue with a narrow design/implementation sequence focused on bundle/action dispatch only.
- **Do Not Do Yet**:
  - do not move final-answer logic
  - do not move stop-gate authority
  - do not migrate board/checkpoint semantics
  - do not remove legacy fallbacks before parity is proven

## Step 2: Producer / Consumer Contract Design

This step defines the smallest contract that can move bundle/action execution closer
to plan-first behavior without changing side effects.

### 1. Current producer / consumer flow

- **Producer today**
  - `ResponsePipelineStagesMixin._build_execution_plan(...)` creates `ExecutionPlan`.
  - It runs late, only on the `dispatch_ready` branch.
  - It reads:
    - `parsed_output.compiler_shape`
    - `parsed_output.compiler_ir`
    - `step.intent_payload`
    - runtime state / intent transition info
- **Fields populated today**
  - `shape`
  - `transaction_kind`
  - `state_effects`
  - `action_effects`
  - `output_effects`
  - `bundle_validated`
  - `transition_applied`
  - `action_dispatched`
  - `active_intent_unchanged`
  - `before_active_intent_id`
  - `after_active_intent_id`
- **Where `compiler_ir` is available**
  - `ResponsePipelinePrevalidationMixin._apply_compiler_diagnosis(...)`
    stores it on `ParsedModelOutput` before post-classification orchestration.
- **Where `segments` are still used**
  - `ResponsePipelineStagesMixin` still passes `segments` in `dispatch_ready`.
  - `DispatchPipeline` still calls `dispatcher.dispatch_segments(segments, state)`.
  - `DispatchOutcomeHandler` still reconstructs from processed segments.
  - `ActionPolicyHandler._atomic_bundle_candidate_commands(...)` still falls back to
    legacy action segments when IR action ops are absent.
- **Where `ActionPolicy` validates**
  - `ResponsePipelineStagesMixin._run_post_classification_stage(...)` calls
    `ActionPolicyHandler.decide(...)` before `dispatch_ready`.
  - Atomic bundle prevalidation paths also call
    `ActionPolicyHandler.validate_atomic_bundle_action(...)`.
- **Where side effects execute**
  - `DispatchPipeline.run_iteration(...)`
  - `_dispatch_segments(...)`
  - downstream dispatcher / tool execution

### 2. Proposed minimal `ExecutionPlan` contract

The first migrated slice should keep `ExecutionPlan` small and descriptive.

- **Required authoritative fields**
  - `shape`
  - `transaction_kind`
  - `action_effects`
  - `output_effects`
  - `bundle_validated`
  - `transition_applied`
  - `before_active_intent_id`
  - `after_active_intent_id`
- **Required invariants**
  - Plan exists only for dispatch-authoritative outcomes.
  - Plan is built only after compiler structure is accepted and `ActionPolicy`
    permission checks pass.
  - Compiler-invalid responses never produce a dispatch-authoritative plan.
  - Plan must describe the same action count/order as the dispatch path used for
    the migrated slice.
- **Optional compatibility fields**
  - `state_effects`
  - `active_intent_unchanged`
  - `action_dispatched`
    - remains observational / compatibility-only at plan-build time
    - must not become predictive authority for dispatch success
- **Source fields from compiler IR**
  - `shape` from `compiler_shape`
  - action payload / path / command summaries from `compiler_ir.action_ops`
  - pre-action visible text from `compiler_ir.pre_action_text`
  - write/read shape hints from `ActionOpIR.read_only` / `write_like`
- **Fields still derived from runtime or legacy compatibility**
  - before/after intent ids from runtime transition state
  - `bundle_validated` from the already-completed bundle / policy path
  - temporary `segments` handoff until dispatch parity is proven

### 3. First migration candidate

- **Chosen slice**
  - single dispatch-ready action flow where compiler IR already provides exactly one
    authoritative `ActionOpIR`
  - includes the existing atomic intent+action bundle path and the equivalent
    single-action dispatch-ready path that already builds one `ExecutionPlan`
- **Why this is the lowest-risk slice**
  - compiler IR already carries the action payload and pre-action text
  - `ActionPolicyHandler` already reads compiler IR first
  - current `ExecutionPlan` already summarizes this path
  - readonly multi-action batches and broader batch execution stay out of scope
  - final-answer and stop-gate authority remain untouched

### 4. Fallback strategy

- Use `ExecutionPlan` as the primary producer-side contract only when:
  - `parsed_output.compiler_ir` is present
  - compiler shape is dispatch-authoritative for the migrated slice
  - `ActionPolicy` has already passed
- Keep `segments` fallback when:
  - IR action ops are absent
  - path is outside the first migrated slice
  - parity is not yet proven between plan-derived and segment-derived dispatch inputs
- Behavior-preservation rule:
  - no path may dispatch more, fewer, or different actions just because a plan is
    present
  - on mismatch or uncertainty, fall back to the current segment-based dispatch path

### 5. Tests required before implementation

- characterization tests for current `ExecutionPlan` shape and field population
- parity tests comparing plan-derived action summary/input against
  segment-derived action summary/input for the first migrated slice
- fallback tests proving segment dispatch remains active outside the migrated slice
- no-dispatch-on-invalid tests proving compiler-invalid and policy-rejected cases do
  not gain a dispatch path through the plan contract
- pre-action-text parity tests proving UI emission remains identical

### 6. Authority boundaries

- **Compiler / IR**
  - owns structure only
  - provides `ActionOpIR`, visible-text source, and shape facts
- **`ActionPolicy`**
  - owns permission only
  - decides whether the structurally valid action is allowed to proceed
- **`DispatchPipeline`**
  - owns side effects only
  - must not reinterpret policy or parse raw semantics
- **`ResponsePipeline`**
  - orchestrates only
  - may assemble and pass the plan, but should not remain the long-term semantic
    source for execution behavior

## Proposed Phase 9 Sequence

### Step 3: ExecutionPlan Contract Characterization Tests

Design complete; implementation pending explicit approval.

- lock down current `ExecutionPlan` production for the first migrated slice
- add parity coverage between plan-derived and segment-derived action inputs
- prove fallback behavior on non-migrated paths

### Step 4: Producer-Side Narrowing

Future implementation, pending approval.

- make `ResponsePipelineStagesMixin._build_execution_plan(...)` the canonical
  producer for the migrated slice
- keep `ActionPolicy` on the permission boundary
- preserve `segments` fallback for non-migrated paths

### Step 5: Dispatch Consumer Migration

Future implementation, pending approval.

- let `DispatchPipeline` consume plan-derived dispatch inputs for the migrated slice
- preserve side effects and outcome behavior
- keep compatibility fallback until plan/segment parity is proven

## Safety Gate

Phase 9 implementation must remain behavior-preserving:

- no dispatch side-effect changes
- no permission-boundary changes
- no final-answer authority changes
- no parser rewrite
- no board/checkpoint migration in this slice
