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
- response-layer collaborator bundles

### `transitions`

Formal intent transition handling:

- `IntentTransitionHandler`
- transition routing and apply helpers
- intent universe helpers
- transition-layer collaborator bundles

### `shared`

Shared orchestration contracts and policy normalization:

- typed decision/result dataclasses
- recovery context model
- recovery policy normalization
- canonical trace schema/helpers in `shared/trace.py`
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
- runtime collaborator bundles

## Root-Level Cross-Cutting Modules

The orchestration root no longer contains compatibility wrappers.

The only true cross-cutting root module is:

- `trace_export.py`

## Root Surface

The orchestration root now contains only:

- [__init__.py](/home/romankozak/studio/public/it/angelica-ai/modules/agent/orchestration/__init__.py): narrow public facade
- [trace_export.py](/home/romankozak/studio/public/it/angelica-ai/modules/agent/orchestration/trace_export.py): export adapter over `shared/trace.py`

All old top-level wrapper modules were removed after repo usage dropped to zero.

Policy:

- import the supported root facade from `modules.agent.orchestration` only when you need the explicit public API;
- otherwise import implementation code from semantic subpackages directly.

Trace ownership note:

- `modules.agent.orchestration.shared.trace` is the canonical owner of trace schema defaults, entry append helpers, snapshot shape, and text rendering.
- `trace_export.py` and `responses/stage_logging.py` are adapters over that shared trace layer, not independent schema owners.
