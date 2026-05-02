# Orchestration Package Map

This document maps the current orchestration package layout after the semantic split.

## Public Runtime Surface

Use `modules.agent.orchestration` for the main runtime entry points:

- `Orchestrator`
- `LoopContext`
- `OrchestratorPromptBuilder`
- `IntentResponseParser`
- `ModelResponsePipeline`
- `ModelOutputRecoveryHandler`
- `IntentTransitionHandler`

These are re-exported from [modules/agent/orchestration/__init__.py](/home/romankozak/studio/public/it/angelica-ai/modules/agent/orchestration/__init__.py).

## Semantic Subpackages

### `prompts`

Prompt construction and recovery prompt rendering:

- `OrchestratorPromptBuilder`
- prompt builder mixins for intent, recovery, action-format, contract, and interactive prompts

### `parsers`

Response normalization and parsing helpers:

- `IntentResponseParser`
- think-boundary repair
- visible-text extraction
- intent/action parsing helpers

### `responses`

Model response handling and recovery:

- `ModelResponsePipeline`
- `ModelOutputRecoveryHandler`
- response-pipeline stages and prevalidation
- recovery routing and terminal recovery
- orchestration stage logging

### `transitions`

Formal intent transition handling:

- `IntentTransitionHandler`
- transition routing and apply helpers
- intent universe helpers

### `shared`

Shared orchestration contracts and policy normalization:

- typed decision/result dataclasses
- recovery context model
- recovery policy normalization
- reusable contract-level helpers needed by multiple semantic packages

### `runtime`

Runtime coordinators for the orchestration loop:

- `core`
- `pipeline`
- `recovery`
- `action_policy`
- `dispatch_pipeline`
- `dispatch_outcome`
- `loop_gate`
- `memory_board_stage`
- `plan_board_stage`
- `lifecycle`
- `policy`

## Root-Level Cross-Cutting Modules

Top-level orchestration files are now mostly compatibility wrappers plus a few true cross-cutting modules:

- `trace_export.py`
- compatibility wrappers for `runtime`, `shared`, `prompts`, `parsers`, `responses`, and `transitions`

## Compatibility Wrappers

Several legacy top-level modules remain as thin wrappers so existing imports do not break immediately.

Important wrappers now include:

- `decision_models.py` -> `shared.decision_models`
- `recovery_policy.py` -> `shared.recovery_policy`

Root runtime-named wrappers were removed after repo usage dropped to zero. Use `runtime.*` directly.

Most old helper wrappers were removed after internal imports moved to semantic package paths.

Policy:

- internal orchestration code should prefer semantic subpackage imports;
- external callers may continue using legacy wrapper imports during migration;
- wrappers can be removed after downstream imports are updated.
