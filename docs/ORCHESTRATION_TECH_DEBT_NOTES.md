# Orchestration Tech Debt Notes

## Purpose

This document captures targeted technical debt around orchestration cleanliness, model-facing hygiene, and diagnosability.

The goal is not to fix everything at once. The goal is to:

- keep the architecture understandable
- make orchestration behavior easy to test
- make failures easy to explain from logs
- remove legacy concepts that keep leaking into model behavior

Large refactors should be driven by architectural clarity. Smaller fixes should be done reactively when they block real agent work.

## Current Debt Areas

### 1. Legacy vocabulary still leaks through internal architecture

Even after removing runtime generation of assistant-visible `TOOL_HISTORY`, the codebase still contains legacy terminology such as:

- `tool_history_echo`
- `history_tool`
- prompt helpers and tests named around `TOOL_HISTORY`

This is a debt because:

- old terminology keeps old mental models alive in the code
- internal names tend to leak into prompts, logs, tests, and future fixes
- it becomes harder to distinguish backward-compat parsing from current architecture

Desired direction:

- rename legacy-facing invalid kinds to neutral names such as:
  - `historical_marker_echo`
  - `invalid_history_marker_echo`
- rename helper methods accordingly
- keep backward-compatible parsing behavior, but stop treating old token names as part of the current system vocabulary

Important constraint:

- backward compatibility may still require detection of legacy markers in parser/recovery code
- but current runtime architecture should not be expressed in legacy terms

### 2. Internal diagnostic vocabulary and model-facing language are not explicitly separated

Right now some orchestration concepts exist simultaneously as:

- internal invalid kinds
- recovery-prompt language
- test assertions
- documentation terms

This is a debt because:

- model-facing strings can accidentally repeat internal marker names
- internal enums/diagnostics can become coupled to prompt phrasing
- changing one layer becomes harder because the others implicitly depend on exact wording

Desired direction:

- define a clear split between:
  - internal diagnostics vocabulary
  - model-facing prompt language

Examples:

- internal: `historical_marker_echo`
- model-facing: "You echoed a historical tool marker from prior execution."

Principle:

- internal names should optimize for precision and stability
- model-facing text should optimize for compliance and clarity
- the two should be mapped explicitly, not collapsed into one vocabulary

### 3. Conversation/history sanitation is distributed across multiple places

Right now sanitation-like behavior is spread across:

- parser cleanup
- history filtering
- recovery prompting
- model-response validation

This is a debt because:

- no single place defines what is safe to send back to the model
- different layers may implement overlapping but slightly different filtering rules
- subtle artifacts can bypass one layer and still leak through another

Observed risk pattern:

- a legacy assistant artifact appears in history
- one filter only removes a narrow form of it
- the model later sees the artifact and imitates it

Desired direction:

- introduce one explicit sanitation boundary for model-facing conversation state
- likely as a component such as:
  - `ConversationSanitizer`
  - or `ModelContextSanitizer`

Responsibilities of that component should include:

- removing legacy historical markers
- removing audit placeholders
- removing assistant artifacts that should never re-enter model context
- normalizing content before it is added to model-facing API payload

Important constraint:

- parser should stay focused on response parsing/classification
- history manager should not become the de facto home of all sanitation logic
- sanitation should be a named architectural boundary, not an emergent side effect

### 4. Documentation and tests still preserve obsolete runtime concepts as if they were first-class

Current documentation and tests still refer to legacy marker names because they were historically real.

This is acceptable for backward-compat references, but it becomes debt when:

- docs present legacy markers as normal orchestration concepts
- tests assert exact legacy phrasing that should no longer be part of current runtime language
- future contributors cannot tell whether a term is current or compatibility-only

Desired direction:

- separate docs into:
  - current architecture
  - compatibility / legacy handling
- keep tests for legacy detection
- avoid using legacy tokens as normative language in current architecture docs

## Recommended Cleanup Order

The following order is intentionally conservative and architecture-first.

### Step 1. Remove legacy terminology from current runtime vocabulary

Scope:

- rename `tool_history_echo` to a neutral term
- rename prompt/recovery helpers to neutral names
- update tests and docs to reflect the new current vocabulary
- preserve backward-compatible parsing of old markers

Expected result:

- the code stops describing current behavior in legacy terms
- internal language becomes cleaner and less likely to leak into prompts

### Step 2. Introduce a dedicated model-context sanitation boundary

Scope:

- create `ConversationSanitizer` or `ModelContextSanitizer`
- move model-facing history cleanup into that component
- make `HistoryManager.get_history_for_api()` depend on that component instead of ad hoc filtering
- centralize policy for removing:
  - historical markers
  - audit placeholders
  - assistant-only orchestration artifacts

Expected result:

- one clear place answers the question: "what is safe to send back to the model?"
- debugging becomes easier because sanitation rules are not scattered

### Step 3. Update docs to reflect current architecture vs compatibility behavior

Scope:

- separate current orchestration language from compatibility notes
- document which artifacts are legacy-only
- document where sanitation happens

Expected result:

- contributors can quickly understand what is current, what is tolerated, and why

## What Not To Do Immediately

The following should not be bundled into the same cleanup unless a real blocking bug requires it:

- broad changes to unrelated intent/phase policy
- broad changes to dispatch behavior
- large history-manager refactors without a clear responsibility map
- bundling architecture cleanup with reactive bugfixes that change runtime semantics

Reason:

- conversation hygiene and orchestration policy are different concerns
- mixing them makes regressions harder to isolate

## Second Step: Plan For A Clean, Testable, Well-Instrumented Orchestration Architecture

This is the next architectural step after the vocabulary/sanitation cleanup above.

The goal is to build an orchestration architecture that is:

- easy to understand
- easy to unit test at each step
- heavily diagnosable through structured logs
- easy to repair when runtime behavior drifts

### A. Define the orchestration pipeline as explicit named stages

The pipeline should be documented and reflected in code as a sequence of named stages.

Candidate stages:

1. model response acquisition
2. intent extraction / transition handling
3. memory-board response processing
4. parse / classify
5. response recovery decision
6. dispatch
7. dispatch outcome / recovery

## Additional Tech Debt: Full Stage Result Normalization

### Current state

The orchestration cleanup already introduced two useful layers of typed control flow:

- `LoopControlDecision` for loop-level semantics such as:
  - continue
  - stop
  - pass-through
- `PreDispatchDecision` for pre-dispatch stage-local decisions

This materially improved consistency across:

- `RecoveryCoordinator`
- `DispatchOutcomeHandler`
- `OrchestrationPipeline`
- `DispatchPipeline`
- `ModelResponsePipeline`
- pre-dispatch helpers such as action policy, output recovery, and memory-board handling

However, the system still has one visible asymmetry:

- `LoopGateDecision` remains a custom shape
- some stage-local semantics are still represented by dedicated fields rather than one formalized stage-result protocol
- pre-dispatch and loop-gate decisions are close in spirit, but not yet modeled through one explicit abstraction

### Why this is still debt

This is architectural debt because the system now has *mostly* unified decision semantics, but not a single final answer to:

- what is the canonical return type for any orchestration stage?
- how should a stage express:
  - continue
  - stop
  - pass
  - dispatch-ready
  - metadata such as retries or parsed action count

Right now the answer is understandable for a reader who already knows the recent refactors, but it is not yet fully obvious from the type system alone.

That means:

- new orchestration stages may drift back toward ad hoc dataclasses
- contributors may not know whether to use:
  - `LoopControlDecision`
  - `PreDispatchDecision`
  - `PipelineIterationDecision`
  - or a fresh one-off result type
- logs and traces are better than before, but the conceptual contract is not completely closed

### Desired direction

Introduce one explicit documented protocol for orchestration stage results.

Possible shape:

- `StageResult`
  - `mode="continue" | "stop" | "pass" | "dispatch_ready"`
  - `next_query`
  - `reason`
  - `source`
  - optional metadata payload

This does **not** necessarily require flattening every current dataclass into one giant generic object immediately.

A safer direction is:

1. keep the current specialized result classes where they help readability
2. make them all implement one clearly documented semantic contract
3. make every stage map cleanly to one of the canonical modes
4. ensure trace logging reflects the same mode language everywhere

### Good target outcome

After that cleanup, a contributor should be able to answer these questions quickly:

- What can any orchestration stage return?
- Which stage owns the decision?
- How is that decision logged?
- How does it affect the main loop?

And they should be able to discover the answer by reading:

- one small typed model section
- one small pipeline section
- one dump/trace sample

without needing to reconstruct behavior from several different dataclasses.

### Suggested implementation order

1. Document the canonical stage-result modes explicitly.
2. Decide whether `LoopGateDecision` should stay special or conform to the shared contract.
3. Normalize trace output so top-level pipeline traces and stage-local traces use the same mode vocabulary.
4. Only then consider whether to collapse or further simplify the remaining result dataclasses.

### What not to do

- Do not merge all result types into one oversized dataclass without a strong semantic reason.
- Do not rewrite working orchestration stages just to reduce the number of classes.
- Do not trade away readability in individual handlers for abstract purity.

The real goal is not “fewer dataclasses”.

The real goal is:

- one understandable orchestration contract
- one predictable logging vocabulary
- one testable decision pipeline
8. history update / context update

Each stage should have:

- a clear input type
- a clear output type
- a clear logging contract
- isolated unit tests

### B. Use typed inputs and outputs at every orchestration boundary

Each orchestration stage should exchange typed decision objects, not loose dicts and implicit mutations wherever possible.

That makes it easier to:

- test stages independently
- replay failures
- inspect exact transition points in logs
- avoid hidden coupling between components

Good properties of typed outcomes:

- they are serializable enough for logs
- they can carry `reason`, `source`, and `next_action` style metadata
- they reduce ambiguity about what a stage decided and why

### C. Introduce structured stage-level logging

The most useful logging improvement is not "more logs", but stage logs with stable fields.

Each stage should log:

- stage name
- input summary
- output summary
- decision reason
- authoritative source
- whether control continues, recovers, dispatches, or stops

Examples of log fields:

- `stage=response_pipeline`
- `stage=intent_transition`
- `stage=output_recovery`
- `decision=continue|dispatch|recover|stop`
- `reason=...`
- `source=...`
- `invalid_kind=...`
- `allowed_actions_source=...`

This should make it possible to answer:

- why did the orchestrator continue instead of dispatch?
- why did it recover instead of answer?
- why was a tool blocked?
- which layer decided the next allowed actions?

### D. Make each stage directly unit-testable without full orchestrator execution

For each stage component, tests should cover:

- happy path
- invalid input path
- recovery path
- compatibility path
- log-worthy edge cases

Tests should avoid requiring a full end-to-end orchestrator run when the logic under test is local to one stage.

This improves:

- speed
- clarity
- confidence during refactors

### E. Keep end-to-end tests focused on pipeline composition

Full orchestration tests should still exist, but their job should be narrower:

- verify stage composition
- verify loop continuation / stop behavior
- verify no artifact leaks back into model context
- verify structured recovery prompts are selected correctly

They should not be the only place where behavior is understandable.

### F. Treat logging as a diagnostic contract

Logs should be stable enough that a dump can be inspected like a pipeline trace.

Desired property:

- when orchestration misbehaves, the dump should reveal the exact stage and exact reason without needing guesswork

That means:

- stable stage names
- stable reason codes
- stable typed decision summaries
- no over-reliance on free-form prose logs for critical control decisions

### G. Fix remaining bugs reactively, not by mixing them into the architecture pass

After the architecture is clean and observable:

- fix concrete blocking bugs one by one
- use dumps and stage logs to identify the exact failing boundary
- avoid speculative policy changes unless a concrete bug demonstrates the need

This should create the biggest practical improvement:

- easier debugging
- safer refactors
- faster iteration when orchestration quality drops

## Summary

The immediate architectural debt is:

- legacy terminology remains in the current vocabulary
- model-facing and internal language are not cleanly separated
- sanitation is not a first-class architectural boundary
- docs and tests still partly present obsolete concepts as normal

The next strategic step should focus on:

- explicit pipeline stages
- typed stage boundaries
- structured stage-level logging
- isolated unit tests per stage
- end-to-end tests only for stage composition

That combination is likely to produce the biggest real-world improvement in agent behavior and maintainability.
