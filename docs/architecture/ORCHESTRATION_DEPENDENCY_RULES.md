# Orchestration Dependency Rules

This document defines package-boundary rules for `modules.agent.orchestration`.

## Goal

Keep semantic subpackages loosely coupled so orchestration logic does not collapse back into a single mutable blob.

## Allowed Dependency Directions

### `prompts`

Purpose: render prompts and recovery text.

Allowed:

- local prompt mixins/modules
- `shared`
- intent-universe read helpers
- higher-level non-orchestration render helpers

Disallowed:

- `responses`
- `parsers`
- runtime coordinators such as `core`, `pipeline`, `dispatch_pipeline`

### `parsers`

Purpose: normalize and classify raw model responses.

Allowed:

- local parser helpers
- `shared`

Disallowed:

- `responses`
- `transitions`
- prompt builders
- runtime coordinators

### `responses`

Purpose: response pipeline, output recovery, response semantics, stage logging.

Allowed:

- local response helpers
- `shared`
- parser-visible-text helpers

Disallowed:

- `prompts`
- `transitions`
- runtime coordinators

Special rule:

- `responses/stage_logging.py` may format runtime log lines, but canonical trace schema ownership belongs to `shared/trace.py`.
- response modules must not introduce alternate trace-entry defaults or a competing trace snapshot format.
- response handlers should prefer `ResponseLayerCollaborators` for stable constructor-time dependencies instead of broad direct `agent` coupling where practical.

### `transitions`

Purpose: validate/apply/reject formal intent transitions.

Allowed:

- local transition helpers
- `shared`
- parser-visible-text helpers
- response stage logging only

Disallowed:

- prompt builders
- response pipeline/recovery internals other than stage logging
- runtime coordinators

Preferred dependency pattern:

- transition handlers should prefer `TransitionLayerCollaborators` for `state/config/ui/logger` instead of reaching through a wide `agent` object after initialization.

### `shared`

Purpose: cross-package contracts and policy normalization.

Allowed:

- local shared modules
- non-orchestration helper dependencies

Includes:

- typed decision/result dataclasses
- recovery policy normalization
- canonical trace schema, append helpers, snapshot helpers, and text rendering

Disallowed:

- `prompts`
- `parsers`
- `responses`
- `transitions`
- runtime coordinators

### `runtime`

Purpose: orchestrate loop execution by coordinating semantic packages.

Allowed:

- local runtime helpers
- `prompts`
- `parsers`
- `responses`
- `transitions`
- `shared`
- non-orchestration runtime dependencies

Disallowed:

- helper wrappers in the orchestration root

Preferred dependency pattern:

- runtime coordinators should prefer `RuntimeCollaborators` when a handler only needs a stable subset such as `state/history/config/ui/logger/dispatcher`.

## Runtime Layer

The canonical coordinator implementation now lives under `modules.agent.orchestration.runtime`.

Top-level wrapper modules in `modules.agent.orchestration` were removed after migration to semantic subpackages.
