# Orchestration Phase Architecture

This document defines the canonical phase order for orchestrator model-step handling.

The goal is to keep refactors aligned with the current runtime invariants and to prevent policy logic from drifting back into a single procedural blob.

## Core Rule

Model-step handling is phase-ordered.

The orchestrator must not reorder these phases casually, because several correctness rules depend on running earlier guards before later recovery or dispatch logic.

## Canonical Phase Order

1. `response_normalization`
2. `intent_prevalidation`
3. `intent_transition_handling`
4. `checkpoint_stages`
5. `response_classification`
6. `output_recovery`
7. `action_policy`
8. `dispatch_ready`

## Phase Responsibilities

### 1. Response Normalization

Primary implementation:

- `modules/agent/orchestration/parsing.py`
- `modules/agent/orchestration/parsing_normalization.py`
- `modules/agent/orchestration/think_repair.py`
- `modules/agent/orchestration/response_pipeline_prevalidation.py`

Responsibilities:

- preserve `raw_response`
- produce `normalized_response`
- apply only narrow, high-confidence safe repairs
- record repair diagnostics

Current allowed safe repair:

- conservative auto-close for unclosed `<think>` boundary

Not allowed here:

- semantic reinterpretation of malformed intent transitions
- broad protocol repair
- silently changing mixed visible-answer/control semantics

### 2. Intent Prevalidation

Primary implementation:

- `modules/agent/orchestration/response_pipeline_prevalidation.py`

Responsibilities:

- validate strict transition atomicity before applying an intent
- block malformed follow-up bundles before state mutation
- enforce terminal plaintext completion guards before transition application

Invariant:

- a rejected transition must remain an atomic no-op

### 3. Intent Transition Handling

Primary implementation:

- `modules/agent/orchestration/intent_transitions.py`
- `modules/agent/orchestration/intent_transition_apply.py`
- `modules/agent/orchestration/intent_transition_routing.py`

Responsibilities:

- apply accepted formal intent transitions
- reject invalid transitions without mutating active intent
- handle transition-only / reuse-only gates
- manage repeated transition defects and terminal loop breakers

Invariant:

- transition application is atomic
- rejected transitions do not partially mutate `active_intent`

### 4. Checkpoint Stages

Primary implementation:

- `modules/agent/orchestration/plan_board_stage.py`
- `modules/agent/orchestration/memory_board_stage.py`
- `modules/agent/orchestration/response_pipeline_stages.py`

Responsibilities:

- process plan-board and memory-board checkpoint output
- accept checkpoint-only turns where policy allows them
- enforce reflection-repair and checkpoint hard-stop rules

Invariant:

- checkpoint handling happens before generic output recovery and action policy

### 5. Response Classification

Primary implementation:

- `modules/agent/orchestration/parsing.py`
- `modules/agent/orchestration/parsing_intent.py`
- `modules/agent/orchestration/parsing_actions.py`

Responsibilities:

- classify top-level response shape
- detect structural invalid kinds
- detect mixed visible-text/control responses
- detect malformed action and malformed intent payload shapes

Invariant:

- classification decides protocol shape
- it does not apply runtime policy by itself

### 6. Output Recovery

Primary implementation:

- `modules/agent/orchestration/output_recovery.py`
- `modules/agent/orchestration/output_recovery_terminal.py`
- `modules/agent/orchestration/output_recovery_routing.py`

Responsibilities:

- map invalid kinds to recovery prompts
- escalate repeated structural defects
- issue terminal plaintext handoff when loop-breaking is required

Invariant:

- output recovery runs before action dispatch policy

### 7. Action Policy

Primary implementation:

- `modules/agent/orchestration/action_policy.py`

Responsibilities:

- allow or block the parsed action under current runtime contract
- enforce build-fix mode, disallowed actions, and bundle constraints
- request formal intent when action is outside the active contract

Invariant:

- action policy must not run before structural classification and output recovery

### 8. Dispatch Ready

Primary implementation:

- `modules/agent/orchestration/response_pipeline.py`
- `modules/agent/orchestration/dispatch_pipeline.py`
- `modules/agent/orchestration/dispatch_outcome.py`

Responsibilities:

- produce final dispatch-ready outcome
- preserve parsed segments and parsed output
- hand off to dispatch machinery only after all earlier phases pass

## Facade Modules

The current split intentionally uses thin facades as stable public entry points:

- `OrchestratorPromptBuilder`
- `IntentResponseParser`
- `ModelResponsePipeline`
- `ModelOutputRecoveryHandler`
- `IntentTransitionHandler`

Refactors should preserve these facades unless there is a deliberate public API change.

## Refactor Guidance

Safe refactors:

- moving helpers between phase-local mixins/modules
- improving diagnostics or trace fields
- tightening tests around phase ordering

Unsafe refactors unless justified explicitly:

- merging phases back into one procedural handler
- moving output recovery ahead of classification
- applying intent transitions before atomicity checks
- broadening normalization repair into semantic protocol repair
- letting action policy run before structural invalid handling

## Why This Matters

Recent fixes rely on this order for correctness:

- intent-only acceptance when formal intent is required
- atomic no-op rejection for conflicting transitions
- optional `<think>` with strict open/close boundaries
- build-fix mode after real compiler/build failure
- mixed visible-answer plus control-protocol rejection
- conservative unclosed-`<think>` auto-repair only outside atomic transition checks
