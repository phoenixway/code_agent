# Dephased Execution Policy Notes

This note captures the current MVP de-phasing step.

## Decision

Phases are no longer an authoritative execution policy source for the coding agent.

The runtime execution policy is now driven primarily by:

1. intent universe
2. active intent contract
3. allowed actions
4. stop / defect reason
5. action history and no-progress heuristics

## What Changed

The old `action_not_allowed_in_phase` gate was removed from `PolicyEngine.evaluate_pre_action()`.

That means:

- phase does not block the next action anymore
- stale phase state does not need MODIFY / INVESTIGATE override escape hatches
- pre-action denial now comes from actual safety / scope / repetition / reread rules

## Remaining Role Of Phase

`AgentPhase` still exists in code for compatibility and lightweight debug labeling, but it is no longer the main source of execution truth.

Phase is now effectively secondary metadata.

## Why

The previous architecture had multiple conflicting policy layers:

- task kind
- phase
- active intent
- recovery hints

In practice, active intent and recovery policy were already stronger and more correct than phase.

The result was confusing runtime states such as:

- `Task kind: MODIFICATION`
- `Current phase: OBSERVE`

That combination was misleading for the model and required many special-case overrides.

## New Direction

The intended clean architecture is:

- universe decides whether a formal contract exists
- active intent decides governed action family
- recovery decides next-step shape from stop reason
- phase is optional debug metadata only

## Follow-up

Further cleanup should remove or simplify remaining legacy references that still assume phase-based authority in:

- older tests
- recovery text branches that still mention phase semantics
- any debug copy that still frames phase as a hard execution boundary

