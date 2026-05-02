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

### `shared`

Purpose: cross-package contracts and policy normalization.

Allowed:

- local shared modules
- non-orchestration helper dependencies

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

## Compatibility Wrappers

Legacy wrapper modules are still allowed for external compatibility, but internal orchestration code should import from semantic subpackages directly.

Important wrappers now include:

- `decision_models.py`
- `recovery_policy.py`
- `prompting.py`
- `parsing.py`
- `response_pipeline.py`
- `output_recovery.py`
- `intent_transitions.py`

## Runtime Layer

The canonical coordinator implementation now lives under `modules.agent.orchestration.runtime`.

Top-level runtime-named files in `modules.agent.orchestration` were removed after migration to `runtime/`.
