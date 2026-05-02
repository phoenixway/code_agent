# Agent Public API

This document defines the supported import surface for `modules.agent`.

## Root Package

The root package `modules.agent` is intentionally narrow and lazy-loaded.

Supported root-level exports:

- `AngelicaAgent`
- `TechnicalInterruption`

Use:

- `from modules.agent import AngelicaAgent`
- `from modules.agent import TechnicalInterruption`

## Preferred Implementation Imports

Implementation code should prefer explicit submodule imports such as:

- `modules.agent.core`
- `modules.agent.technical_interruptions`
- `modules.agent.orchestration.runtime.*`
- `modules.agent.orchestration.prompts.*`
- `modules.agent.orchestration.parsers.*`
- `modules.agent.orchestration.responses.*`
- `modules.agent.orchestration.transitions.*`
- `modules.agent.orchestration.shared.*`

## Removed Compatibility Shims

The following legacy wrappers were removed after repo usage dropped to zero:

- `modules.agent.orchestrator`
- `modules.agent.recovery_coordinator`
- `modules.agent.orchestrator_prompt_builder`
- `modules.agent.turn_lifecycle`
- `modules.agent.intent_response_parser`
- `modules.agent.intent_guard`
