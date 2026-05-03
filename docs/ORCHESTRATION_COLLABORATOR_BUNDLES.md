# Orchestration Collaborator Bundles

This document defines the current collaborator-bundle pattern used in
`modules.agent.orchestration`.

The goal is simple:

- reduce wide `agent` coupling in orchestration handlers
- make required collaborators explicit
- keep constructor contracts narrow without changing runtime semantics

## Canonical Rule

Orchestration handlers should prefer a narrow collaborator bundle over direct
dependence on a wide `agent` object whenever the handler only needs a small,
stable subset of collaborators.

Wide `agent` access is still tolerated at outer wiring boundaries, but it
should not remain the dominant dependency pattern inside handlers.

## Current Bundles

### Runtime Layer

Implementation:

- [modules/agent/orchestration/runtime/dependencies.py](/home/romankozak/studio/public/it/angelica-ai/modules/agent/orchestration/runtime/dependencies.py)

Bundle:

- `RuntimeCollaborators`

Current usage examples:

- `dispatch_pipeline.py`
- `loop_gate.py`
- `lifecycle.py`

Typical collaborators:

- `state`
- `history`
- `config`
- `ui`
- `logger`
- `dispatcher`

### Response Layer

Implementation:

- [modules/agent/orchestration/responses/dependencies.py](/home/romankozak/studio/public/it/angelica-ai/modules/agent/orchestration/responses/dependencies.py)

Bundle:

- `ResponseLayerCollaborators`

Current usage example:

- `output_recovery.py`

Typical collaborators:

- `state`
- `config`
- `ui`
- `logger`

### Transition Layer

Implementation:

- [modules/agent/orchestration/transitions/dependencies.py](/home/romankozak/studio/public/it/angelica-ai/modules/agent/orchestration/transitions/dependencies.py)

Bundle:

- `TransitionLayerCollaborators`

Current usage example:

- `intent_transitions.py`

Typical collaborators:

- `state`
- `config`
- `ui`
- `logger`

## Design Rules

### 1. Bundles should be layer-local

Do not create one mega-bundle for the whole orchestration package.

Reason:

- `runtime`, `responses`, and `transitions` have different stability and
  dependency needs
- a mega-bundle would recreate wide implicit coupling under a different name

### 2. Bundles should expose collaborators, not behavior

Good:

- `state`
- `history`
- `config`
- `ui`
- `logger`

Bad:

- policy decisions
- orchestration branching logic
- mixed convenience methods that hide ownership boundaries

### 3. Handlers may still keep local adapters

Bundles and adapters solve different problems:

- bundles narrow constructor-time dependency shape
- adapters narrow state/history mutation access inside handler logic

Using both is expected.

### 4. Outer wiring may still start from `agent`

This pattern does not require eliminating `agent` from outer constructors
entirely.

It only requires that handlers quickly translate a broad `agent` into a
narrower local dependency contract.

## Migration Guidance

When touching an older orchestration handler:

1. Identify the real collaborator set it uses.
2. Add or reuse a layer-local bundle if the dependency shape is stable.
3. Replace direct `self.agent.log` / `self.agent.ui` / `agent.config` access
   with bundle-backed access where practical.
4. Avoid mixing bundle introduction with behavioral refactors unless needed.

## Non-Goals

This pattern does not try to:

- remove every `agent` reference from orchestration immediately
- replace all state access with bundles
- enforce dependency injection purity across the entire codebase

It is a pragmatic narrowing step, not a full inversion-of-control rewrite.
