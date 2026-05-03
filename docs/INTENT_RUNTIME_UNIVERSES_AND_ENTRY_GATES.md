# Intent Runtime Universes And Entry Gates

This note documents the current orchestration contract around formal intent usage.

## Core Rule

The agent must not drift into unrestricted multi-step tool execution without an explicit runtime state.

Runtime now supports exactly two orchestration universes:

1. `ACTIVE INTENT CONTRACT`
2. `NO ACTIVE INTENT CONTRACT` with a short, explicit `INTENTLESS_SHORT_MODE`

There is no third implicit mode.

## Universe A: Active Intent Contract

When a formal contract is active, the system prompt injects `## ACTIVE INTENT CONTRACT`.

Recovery in this universe may say:

- continue under the current contract
- do not emit another activate intent
- use current allowed actions
- do not restart from zero

Phase conflicts may be overridden by the active intent if runtime policy allows it.

This is the governed multi-step mode.

## Universe B: No Active Intent Contract

When no formal contract is active, the system prompt injects `## INTENT MODE STATUS` with:

- `Status: NO ACTIVE INTENT CONTRACT`
- `Runtime mode: INTENTLESS_SHORT_MODE`
- `intentless_steps_used`
- `intentless_steps_limit`
- `formal_intent_required_now`

Recovery in this universe must not talk as if a current contract exists.

Recovery in this universe should say:

- continue from already gathered evidence
- do not restart from zero
- if the next step needs governed multi-step execution, activate a formal intent now
- until activation succeeds, do not assume contract-scoped permissions or allowed actions

## Entry Gate Into Governed Multi-Step Work

Governed multi-step work must enter through a formal accepted intent contract.

The main entry gate is:

- `ActionPolicyHandler`

If runtime detects multi-step tool use without an active contract, it now:

1. returns `multi_step_without_intent_contract`
2. sets sticky runtime state via `state.require_intent(...)`
3. forces the next model step to return a valid `<intent>` before further tool use

This closes the former gap where the agent could continue for many steps without a contract even though downstream orchestration assumed one existed.

## Intentless Short Mode

Intentless short mode is intentionally narrow.

It exists only to allow very short unguided work before a contract is required.

The limit is controlled by:

- `INTENTLESS_SHORT_MODE_MAX_STEPS`

Once that limit is exceeded, runtime raises:

- `multi_step_without_intent_contract`

This is the canonical defect for "the system is already effectively in multi-step work, but no active contract exists".

## Invalid Intent Syntax

If the model emits an `<intent>` block with invalid JSON and there is no active contract, runtime treats that as a contract-entry failure.

The system now:

- keeps `intent_required_until_activated`
- returns a strong recovery prompt asking for exactly one corrected `<intent>`
- explicitly states that there is still no active accepted contract

This prevents malformed intent activation from silently falling back into bare action execution.

## Response Normalization And Unclosed `<think>` Repair

Before normal response classification, orchestration now runs a narrow response-normalization step.

The normalization contract is:

- `raw_response`
- `normalized_response`
- `repairs_applied`
- `repair_blocked_reason`
- think-repair diagnostics

The only structural auto-repair currently allowed in this step is conservative boundary repair for an unclosed `<think>` block.

### What May Be Auto-Repaired

Runtime may insert `</think>` automatically only when confidence is high that the model already switched from private reasoning into real protocol output.

Examples:

- open `<think>` followed by a valid top-level `<action>{...}</action>`
- open `<think>` followed by a canonical sequence such as:
  - `<finding ...>...</finding>`
  - `<memory_update_done />`
  - `<action>{...}</action>`

### What Must Not Be Auto-Repaired

Ambiguous cases must stay invalid and go through normal recovery, not auto-repair.

Examples:

- tags mentioned inside prose such as `I may use <action> later`
- tags inside backticks or fenced code
- escaped tags such as `&lt;action>`
- quoted protocol examples
- malformed or incomplete `<action>` payloads
- open `<think>` followed by `<intent ...>` in the intent-transition atomicity path

### Atomicity Rule

Intent-transition prevalidation is stricter than ordinary no-intent action classification.

If a response is being checked for intent-transition atomicity:

- think auto-repair is blocked
- the original malformed bundle is validated as-is
- runtime must not auto-close `<think>` in a way that could partially legitimize a malformed intent+follow-up bundle

### Trace Fields

The normalization stage now emits stable trace fields for dump analysis:

- `think_repair_applied`
- `think_repair_reason`
- `think_repair_confidence`
- `think_repair_tag`
- `think_repair_insert_at`
- `think_repair_blocked_by_atomicity`
- `repair_blocked_reason`

## Practical Consequence For Modification Tasks

The state machine may classify the task as `MODIFICATION` while the current phase is still `OBSERVE`.

That classification alone is not enough to grant governed modification execution.

Clean modification flow depends on a real active `MODIFY` intent contract.

Without that contract, runtime remains in the no-contract universe and should not pretend that modify permissions are already active.

## Files

Primary implementation points:

- `modules/agent/orchestration/runtime/policy.py`
- `modules/agent/orchestration/runtime/action_policy.py`
- `modules/agent/orchestration/prompts/prompting.py`
- `modules/agent/orchestration/transitions/intent_transitions.py`
- `modules/agent/intent_runtime.py`
