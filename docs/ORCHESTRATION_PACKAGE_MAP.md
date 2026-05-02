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

## Root-Level Cross-Cutting Modules

Some orchestration modules stay at the root because they coordinate multiple semantic areas:

- `core.py`
- `pipeline.py`
- `recovery.py`
- `action_policy.py`
- `dispatch_pipeline.py`
- `dispatch_outcome.py`
- `loop_gate.py`
- `memory_board_stage.py`
- `plan_board_stage.py`
- `decision_models.py`

## Compatibility Wrappers

Several legacy top-level modules remain as thin wrappers around semantic subpackages so existing imports do not break immediately.

Policy:

- internal orchestration code should prefer semantic subpackage imports;
- external callers may continue using legacy wrapper imports during migration;
- wrappers can be removed after downstream imports are updated.
