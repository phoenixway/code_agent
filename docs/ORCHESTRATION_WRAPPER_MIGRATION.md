# Orchestration Wrapper Migration

This document tracks the legacy top-level wrapper modules under `modules.agent.orchestration`.

## Purpose

These files exist only to preserve older import paths while the orchestration package migrates to semantic subpackages.

They are not the preferred internal import surface.

Preferred internal imports:

- `modules.agent.orchestration.prompts.*`
- `modules.agent.orchestration.parsers.*`
- `modules.agent.orchestration.responses.*`
- `modules.agent.orchestration.transitions.*`
- `modules.agent.orchestration.shared.*`

## Current Wrapper Inventory

### Removed runtime wrappers

The following root wrappers were removed after repo usage dropped to zero:

- `core.py`
- `pipeline.py`
- `recovery.py`
- `action_policy.py`
- `dispatch_pipeline.py`
- `dispatch_outcome.py`
- `loop_gate.py`
- `memory_board_stage.py`
- `plan_board_stage.py`
- `lifecycle.py`
- `policy.py`

Use `runtime.*` directly.

### Public facade wrappers

- `prompting.py` -> `prompts.prompting`
- `parsing.py` -> `parsers.parsing`
- `response_pipeline.py` -> `responses.response_pipeline`
- `output_recovery.py` -> `responses.output_recovery`
- `intent_transitions.py` -> `transitions.intent_transitions`

### Shared-contract wrappers

- `decision_models.py` -> `shared.decision_models`
- `recovery_policy.py` -> `shared.recovery_policy`

### Removed helper wrappers

The following helper wrappers were removed after the repo stopped importing them:

- `stage_logging.py`
- `visible_text.py`
- `think_repair.py`
- `parsing_actions.py`
- `parsing_intent.py`
- `parsing_normalization.py`
- `response_pipeline_prevalidation.py`
- `response_pipeline_stages.py`
- `response_guards.py`
- `response_semantics.py`
- `output_recovery_routing.py`
- `output_recovery_terminal.py`
- `intent_transition_apply.py`
- `intent_transition_routing.py`
- `intent_universe.py`
- `action_format_prompt_builder.py`
- `contract_prompt_builder.py`
- `intent_prompt_builder.py`
- `interactive_prompt_builder.py`
- `prompt_builder_shared.py`
- `recovery_prompt_builder.py`

## Migration Policy

1. Internal orchestration code should not add new imports from wrapper modules.
2. New tests should prefer semantic package imports unless they explicitly verify wrapper compatibility.
3. External callers may continue using wrapper imports until a dedicated removal pass is scheduled.
4. Public/runtime/shared wrappers may remain during migration; helper wrappers should not be reintroduced without a concrete compatibility need.

## Removal Plan

Phase 1:

- keep wrappers
- prevent new internal dependencies on them
- keep compatibility tests green

Phase 2:

- migrate remaining external imports in this repo to semantic package paths
- reduce wrapper-only tests to a single compatibility suite
- remove runtime wrappers once repo usage reaches zero

Phase 3:

- helper wrappers already removed once internal repo usage dropped to zero
- keep public facade wrappers only if external consumers still need them

Phase 4:

- remove remaining wrappers after explicit release-note/deprecation decision
