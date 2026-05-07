# Orchestration Public API

This document defines the supported import surface for `modules.agent.orchestration`.

## Root Package Policy

The root package `modules.agent.orchestration` is intentionally narrow.

Supported root-level exports:

- `Orchestrator`
- `LoopContext`
- `OrchestratorPromptBuilder`
- `IntentResponseParser`
- `ModelResponsePipeline`
- `ModelOutputRecoveryHandler`
- `IntentTransitionHandler`

These names are re-exported from [modules/agent/orchestration/__init__.py](/home/romankozak/studio/public/it/angelica-ai/modules/agent/orchestration/__init__.py).

## Preferred Import Paths

For implementation code, prefer semantic subpackages:

- `modules.agent.orchestration.runtime.*`
- `modules.agent.orchestration.prompts.*`
- `modules.agent.orchestration.parsers.*`
- `modules.agent.orchestration.responses.*`
- `modules.agent.orchestration.transitions.*`
- `modules.agent.orchestration.shared.*`

## Compatibility Policy

The former top-level orchestration wrapper modules were removed after repo
usage dropped to zero.

Do not reintroduce new root helper/runtime/shared wrappers.

Compatibility-focused tests may verify the absence of those old wrapper paths,
but implementation code must use the semantic subpackages directly.

## External Import Boundary

Outside the orchestration package, imports should use only:

- `modules.agent.orchestration`
- `modules.agent.orchestration.runtime.*`
- `modules.agent.orchestration.prompts.*`
- `modules.agent.orchestration.parsers.*`
- `modules.agent.orchestration.responses.*`
- `modules.agent.orchestration.transitions.*`
- `modules.agent.orchestration.shared.*`
- `modules.agent.orchestration.trace_export`
