# Phase 9 Design: Plan-First Bundle Execution

- **Phase 9 Status**: Step 5A Parity Probe Complete
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

Complete.

- lock down current `ExecutionPlan` production for the first migrated slice
- add parity coverage between plan-derived and segment-derived action inputs
- prove fallback behavior on non-migrated paths

### Step 4: Producer-Side Narrowing

Future implementation, pending approval.

- make `ResponsePipelineStagesMixin._build_execution_plan(...)` the canonical
  producer for the migrated slice
- keep `ActionPolicy` on the permission boundary
- preserve `segments` fallback for non-migrated paths

### Step 5A: Dispatch Bridge Parity Probe

Complete.

- validate eligibility and exact parity for the eligible single-action slice
- keep actual dispatch segment-driven
- preserve side effects and outcome behavior
- keep compatibility fallback until an IR-derived candidate contract is proven

## Step 4: First Producer Migration / Dispatch Consumer Preflight

### 1. What Step 5 should migrate

Step 5 should **not** do a broad producer rewrite and should **not** directly replace
segment dispatch across the whole pipeline.

The safest first move is:

- keep the current producer shape in `ResponsePipelineStagesMixin._build_execution_plan(...)`
- keep `ResponsePipelineOutcome.dispatch_ready(...)` carrying both `segments` and `execution_plan`
- add a **narrow dispatch bridge/helper** on the consumer side

Reason:

- the producer is already stable enough for the first slice
- `ActionPolicy` already consumes compiler IR first and remains the permission gate
- the highest behavior-risk sits at the dispatch side-effect boundary, not at plan creation
- a bridge/helper allows narrow opt-in for a single proven slice while keeping full
  segment fallback

### 2. Safest first migrated slice

The first migrated slice should be exactly:

- single-action dispatch-ready path
- compiler IR contains exactly one authoritative `ActionOpIR`
- `ActionPolicy` has already allowed the action
- no compiler-invalid state
- no multi-action batch

This includes:

- valid atomic intent+action bundle with one action
- equivalent single-action dispatch-ready path where the same `ExecutionPlan`
  contract is already produced

This excludes:

- readonly multi-action batches
- any path without exactly one authoritative IR action op
- final-answer / stop-gate / board-checkpoint paths

### 3. Where legacy `segments` fallback must remain

`segments` fallback must remain in all of these cases:

- `execution_plan` is missing
- `parsed_output.compiler_ir` is missing
- IR contains zero or multiple action ops
- plan/IR payload cannot be translated losslessly to the dispatch input surface
- path is outside the first migrated slice
- any runtime uncertainty about parity between plan-derived and segment-derived inputs

Step 5 must therefore keep the legacy `dispatcher.dispatch_segments(...)` path and
use the bridge/helper only when the slice is explicitly eligible.

### 4. What counts as behavior drift

Any of the following counts as drift and is forbidden in Step 5:

- dispatching when the current segment path would not dispatch
- dispatching a different action type, path, command, or file content
- changing action count or order
- bypassing existing `ActionPolicy` checks
- changing pre-action text emission order or content
- changing post-dispatch reconstruction or outcome routing
- removing segment fallback on uncertain parity

### 5. Exact Step 5A implementation shape

Step 5A should implement a **parity probe/helper first**, not a full dispatch consumer replacement.

Recommended shape:

- add a narrow helper at the dispatch boundary that:
  - inspects `iteration.execution_plan`
  - inspects `iteration.parsed_output.compiler_ir`
  - when exactly one authoritative `ActionOpIR` is present, validates that the
    current segment-derived input is losslessly equivalent for that one action
  - otherwise returns "fallback to segments"
- keep `DispatchPipeline.run_iteration(...)` as the orchestrator of this decision
- keep actual side effects routed through the existing segment-based dispatcher contract
- preserve `processed_segs` / `DispatchOutcomeHandler` expectations

This makes Step 5A an instrumentation/parity implementation, not yet a full
plan-authoritative dispatch migration.

### 6. Tests required for Step 5A

- eligible single-action path uses the parity probe without changing observable
  dispatch outcome
- same path still matches legacy segment-derived dispatch payload
- fallback remains active when:
  - no plan exists
  - IR action count is not exactly one
  - IR payload is not losslessly usable
- no-dispatch-on-invalid remains true
- pre-action-text emission remains unchanged
- `ActionPolicy` still runs before any bridge-derived dispatch input is used

### 7. Preflight conclusion

- **Chosen first implementation target**:
  first dispatch-boundary parity probe/helper for the single-action dispatch-ready slice
- **Why**:
  narrowest side-effect-adjacent migration with existing parity coverage and explicit
  fallback points
- **Not authorized in Step 5A**:
  broad producer rewrite, multi-action migration, fallback removal, or direct
  replacement of the segment dispatch path across all consumers

## Step 5A: Parity Probe Outcome

- A narrow dispatch-boundary parity probe/helper is implemented.
- The helper only recognizes the eligible slice when:
  - `execution_plan` exists
  - `parsed_output.compiler_ir` exists
  - IR has exactly one `ActionOpIR`
  - the IR payload matches the segment-derived action payload exactly
  - the plan action summary matches the same action exactly
  - no unsupported action shape is present
- Even on the eligible slice, dispatch still routes through the existing
  segment-driven dispatcher contract and preserves processed-segment/outcome expectations.
- The helper returns the existing `segments`; it does not yet build a new
  plan-authoritative dispatch input.
- On any mismatch or uncertainty, dispatch falls back explicitly to the legacy
  segment path.

## Step 5B: IR-Derived Dispatch Candidate Contract

Complete.

### 1. Current segment dispatch input contract

The current dispatcher contract is still segment-based:

- `DispatchPipeline._dispatch_segments(...)` calls
  `dispatcher.dispatch_segments(segments, state)`.
- `ActionDispatcher.dispatch_segments(...)` expects an ordered segment list where:
  - `segment.type == "thought"` carries `segment.content` text for thought rendering
  - `segment.type == "text"` carries visible assistant text
  - `segment.type == "action"` carries `segment.content` as a dict command payload
- action dispatch is derived from:
  - `action_segments = [seg for seg in segments if seg.type == "action"]`
  - `action_commands = [seg.content for seg in action_segments]`
- current action payload shape is therefore:
  - a dict with action fields such as `type`, `path`, `command`, `overwrite`, etc.
- `file_content` / file block handling is still segment-coupled:
  - write-like/file-content-backed actions are represented via the segment stream
  - the current parity probe correctly excludes these shapes for now
- processed segment expectations remain unchanged:
  - `DispatchOutcomeHandler` reconstructs and interprets `processed_segs`
  - `ExecutionCommit` counts committed action segments from `processed_segs`

### 2. Proposed IR-derived candidate contract

The first candidate surface should be an internal helper type, for example:

- `PlanDispatchCandidate`

Minimum required fields:

- `action_type: str`
- `payload: dict[str, Any]`
- `action_summary: str`
- `source: Literal["compiler_ir"]`
- `matched_segment_index: int`

Optional compatibility fields:

- `compiler_shape: str`
- `transaction_kind: str`
- `pre_action_text: str | None`

Explicit exclusions for the first slice:

- no `file_content` / file block candidate surface yet
- no multi-action candidate list
- no board/checkpoint payloads
- no final-answer or text-only dispatch candidate

### 3. Losslessness rules

Step 5C may only build a candidate when all of these are true:

- exactly one IR action op
- exactly one segment action
- IR action payload is a dict
- IR action has no file-content-backed shape
- candidate payload equals segment action payload exactly
- candidate summary equals `ExecutionPlan.action_effects[0]`
- candidate `action_type` matches IR and payload consistently

Fallback is mandatory for:

- missing `execution_plan`
- missing `compiler_ir`
- zero or multiple IR action ops
- zero or multiple segment actions
- payload mismatch
- summary mismatch
- unsupported shape
- any uncertainty

### 4. How Step 5C should work

Step 5C should not change dispatch behavior. It should:

1. build `PlanDispatchCandidate` from IR/plan for the eligible single-action slice
2. compare the candidate against the current segment-derived action
3. if the match is exact, keep routing through the existing dispatcher contract
4. keep `segments` fallback fully intact

This means Step 5C still does not make dispatch plan-authoritative. It only makes
the IR-derived candidate surface concrete and testable.

### 5. Tests required for Step 5C

- candidate builds for eligible `read_file` single action
- candidate payload equals segment payload exactly
- candidate summary equals `ExecutionPlan.action_effects[0]`
- no candidate for file-content-backed action
- no candidate for multi-action path
- no candidate for payload mismatch
- `run_iteration(...)` still dispatches with the same observable segment behavior

### 6. Step 5B conclusion

- The first IR-derived dispatch candidate surface is precise enough for implementation.
- It is intentionally narrower than a dispatch bridge:
  - candidate contract only
  - no dispatch behavior change
  - no fallback removal
  - no side-effect change

## Safety Gate

Phase 9 implementation must remain behavior-preserving:

- no dispatch side-effect changes
- no permission-boundary changes
- no final-answer authority changes
- no parser rewrite
- no board/checkpoint migration in this slice
