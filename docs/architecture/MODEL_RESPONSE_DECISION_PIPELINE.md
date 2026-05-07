# Model Response Decision Pipeline

## Goal

Define a clean, unified decision pipeline for processing model responses.

The purpose of this document is to:

- identify the real decision centers in the current architecture
- separate parsing, contract management, action-policy resolution, recovery, rendering, and execution
- reduce policy conflicts
- remove duplicated arbitration logic
- provide a migration path toward a simpler and more understandable orchestration flow

The desired outcome is a pipeline where each important decision is made exactly once.

## Core Principle

Every major question in response handling should have exactly one owner.

Examples:

- "What did the model return?" -> parser
- "Is the intent contract accepted / active / rejected?" -> intent runtime
- "Which action is allowed right now?" -> action-policy resolver
- "How should the loop recover from this invalid or blocked step?" -> recovery planner
- "How should this be phrased back to the model?" -> prompt renderer
- "How do we actually execute the allowed action?" -> dispatcher

If the same question is answered in multiple layers, policy conflicts will eventually appear.

## Target Pipeline

The desired processing flow is:

```text
raw model response
-> parser
-> parsed model output

parsed model output + runtime state
-> intent runtime
-> intent decision

parsed model output + intent decision + phase state + transient guards
-> action policy resolver
-> resolved action policy

if invalid / denied / blocked:
    -> recovery planner
    -> recovery decision
    -> prompt renderer
    -> next model query

if allowed:
    -> dispatcher
    -> tool result
    -> state update
```

This pipeline is simple because every layer has exactly one job.

## Decision Centers

The architecture should converge to four real decision centers.

### 1. Parser

Responsibility:

- parse the raw model output
- classify the response shape
- extract structured payloads

The parser should answer only:

- did the model return valid actions?
- did it return plain text?
- did it return an intent payload?
- did it emit invalid output such as audit/history echoes?

The parser should **not** decide:

- whether an action is allowed
- whether the intent should remain active
- how to recover
- which prompt to render next

### 2. Intent Runtime

Responsibility:

- own the formal intent contract lifecycle

The intent runtime should answer only:

- is the intent payload valid?
- should the current contract remain active?
- is a switch legitimate?
- is completion legitimate?
- what hard contract constraints are active now?

The intent runtime should **not** decide:

- phase-policy compatibility
- recovery wording
- malformed-output recovery strategy
- tool rendering

### 3. Action Policy Resolver

Responsibility:

- decide what actions are currently allowed, blocked, preferred, or incompatible

Inputs:

- active intent contract constraints
- current phase constraints
- stop-specific / recovery constraints
- task kind
- transient guards
- parsed actions

Outputs:

- a canonical action-policy result

Example:

```python
ResolvedActionPolicy(
    verdict="allow" | "deny" | "plaintext_only",
    authoritative_source="intent" | "phase" | "recovery" | "runtime",
    allowed_actions=[...],
    preferred_actions=[...],
    blocked_actions=[...],
    keep_current_intent=True | False,
    reason="...",
)
```

This is the main decision center for tool-use policy.

### 4. Recovery Planner

Responsibility:

- choose the recovery strategy after invalid, blocked, or low-value output

The recovery planner should answer only:

- should the loop retry?
- should it force plain-text completion?
- should it ask for exactly one narrower action?
- should it forbid audit/history markers?
- should it stop?

It should **not** re-arbitrate the full action policy.

Example:

```python
RecoveryDecision(
    mode="retry_with_prompt" | "force_plaintext" | "stop" | "ask_user",
    prompt_template="tool_history_echo" | "keep_current_intent" | "single_readonly_retry",
    single_action_only=False,
    state_changing_only=False,
    forbid_audit_markers=True,
)
```

## Downstream Consumers, Not Decision Centers

These layers should not own orchestration decisions:

- prompt builder / prompt renderer
- dispatcher
- UI rendering
- history writer

They should consume already-resolved decisions.

### Prompt Builder / Prompt Renderer

Should:

- render structured decisions into prompts

Should not:

- choose between intent and phase authority
- filter conflicting action sets
- decide whether to keep the current intent
- infer recovery strategy from raw stop-info fields

### Dispatcher

Should:

- validate execution feasibility
- execute actions
- return results

Should not:

- arbitrate between competing policy layers
- reinterpret deny-path semantics
- decide which actions are globally appropriate now

## Canonical Typed Objects

To make the pipeline understandable, the system should converge on a small set of typed models.

### 1. `ParsedModelOutput`

```python
ParsedModelOutput(
    thoughts=[...],
    intent_payload=None | {...},
    actions=[...],
    plain_text="...",
    invalid_kind=None | "tool_history_echo" | "history_tool" | "intent_only_deadend",
)
```

### 2. `IntentDecision`

```python
IntentDecision(
    applied=True | False,
    active_intent=...,
    keep_current_intent=True | False,
    rejection_reason="...",
)
```

### 3. `ResolvedActionPolicy`

```python
ResolvedActionPolicy(
    verdict="allow" | "deny" | "plaintext_only",
    authoritative_source="intent" | "phase" | "recovery" | "runtime",
    allowed_actions=[...],
    preferred_actions=[...],
    blocked_actions=[...],
    keep_current_intent=True | False,
    reason="...",
)
```

### 4. `RecoveryDecision`

```python
RecoveryDecision(
    mode="retry" | "plaintext_completion" | "stop" | "ask_user",
    prompt_template="keep_current_intent" | "tool_history_echo" | "single_readonly_retry",
    single_action_only=False,
    state_changing_only=False,
    forbid_audit_markers=True,
)
```

## Typical Sources of Architectural Entropy

These are the patterns that usually create policy conflict.

### 1. The same question answered in multiple layers

Examples:

- intent runtime says one thing, prompt builder reinterprets it
- state machine denies an action, dispatcher re-normalizes it differently
- recovery layer partially makes policy decisions instead of just choosing recovery mode

### 2. Rendering layers making policy decisions

This happens when prompt-building code:

- chooses the winning authority
- decides whether to keep current intent
- filters allowed actions
- downgrades one hint source in favor of another

Rendering should not do arbitration.

### 3. Untyped `dict` growth

Examples:

- `stop_info`
- `next_actions`
- `phase_allowed_actions`
- `recommended_next_actions`
- `intent_allowed_actions`

These fields tend to drift and accumulate hidden semantics.

### 4. Recommendation and permission getting mixed together

These are different concepts and should be represented separately.

Prefer explicit fields such as:

- `allowed_actions`
- `blocked_actions`
- `preferred_actions`
- `discouraged_actions`

## Authority Order

The system should have one explicit priority order for action constraints.

Recommended precedence:

1. runtime hard constraints
2. active intent contract
3. stop-specific recovery constraints
4. phase constraints
5. soft recommendations

This order should live in one resolver/policy module only.

It should not be reimplemented ad hoc in prompt rendering or dispatch code.

## Invalid Output Handling

Invalid output classification should also be centralized.

Examples of the same architectural class of problem:

- `TOOL_HISTORY`
- `history_tool`
- audit-marker echoes
- malformed pseudo-actions
- think-only replies with no valid action or final answer
- intent-only dead ends

These should be classified once in a dedicated layer.

Example output categories:

- `VALID_ACTION`
- `VALID_TEXT`
- `INVALID_AUDIT_ECHO`
- `INVALID_HISTORY_TOOL`
- `INVALID_EMPTY_REASONING`
- `INTENT_ONLY_DEADEND`

Then the recovery planner can map those categories to explicit recovery behavior.

## Current Cleanup Direction

The introduction of the MVP `AllowedActionsResolver` is a good first step.

That resolver should continue evolving into the canonical source for:

- merging intent / phase / recovery hints
- deciding authoritative action source
- resolving allowed vs. recommended vs. blocked actions

However, full architectural cleanliness will require more than just that resolver.

The other necessary cleanup is to remove duplicated decision logic from:

- prompt builder
- dispatcher
- recovery coordinator
- free-form `stop_info` handling

## Recommended Target Responsibilities

### Parser

- owns response structure
- owns invalid-output classification

### Intent Runtime

- owns contract lifecycle
- owns contract validity and transition legitimacy

### Action Policy Resolver

- owns action compatibility and authority arbitration

### Recovery Planner

- owns retry / completion / stop strategy

### Prompt Renderer

- owns textual rendering only

### Dispatcher

- owns execution only

## Migration Plan

This should be done incrementally, without a broad refactor in one step.

### Step 1. Finalize typed parsed-output classification

Introduce a stable `ParsedModelOutput` model and centralize invalid-output classification there.

### Step 2. Make `ResolvedActionPolicy` the primary carrier

Reduce dependence on scattered fields like:

- `next_actions`
- `intent_allowed_actions`
- `phase_allowed_actions`
- `recommended_next_actions`

Keep them only as compatibility fields during migration.

### Step 3. Introduce `RecoveryDecision`

Move recovery strategy semantics out of prompt-building code and into a typed object.

### Step 4. Turn `PromptBuilder` into a pure renderer

Prompt code should consume structured decisions and format them, not arbitrate them.

### Step 5. Remove orchestration-policy logic from dispatcher

The dispatcher should become execution-only.

### Step 6. Replace free-form `stop_info` dicts with typed models

That will reduce schema drift and improve traceability.

## What "Clean" Looks Like

The pipeline is clean when:

- a bug can be localized to one layer:
  - parsing bug
  - intent-runtime bug
  - action-policy bug
  - recovery-planning bug
- prompt rendering contains no policy arbitration
- dispatcher contains no orchestration-policy arbitration
- recommendations never silently conflict with allowed actions
- invalid output classification is centralized
- phase policy cannot silently override active intent authority unless explicitly allowed

## Short Conclusion

The main architectural objective is not more rules.

It is:

- a single understandable pipeline
- one owner per class of decision
- typed decision objects instead of schema-drifting dicts
- a clear boundary between decision-making and rendering

If this direction is followed, policy conflicts should shrink dramatically and dumps should become much easier to reason about.
