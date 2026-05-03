# Orchestration Wrapper Migration

This document records the removal of legacy top-level wrapper modules under `modules.agent.orchestration`.

## Purpose

The migration is complete. Root wrapper modules are no longer part of the supported surface.

Preferred internal imports:

- `modules.agent.orchestration.prompts.*`
- `modules.agent.orchestration.parsers.*`
- `modules.agent.orchestration.responses.*`
- `modules.agent.orchestration.transitions.*`
- `modules.agent.orchestration.shared.*`

## Removed Wrapper Inventory

### Runtime wrappers removed

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

### Facade/shared wrappers removed

- `prompting.py`
- `parsing.py`
- `response_pipeline.py`
- `output_recovery.py`
- `intent_transitions.py`
- `decision_models.py`
- `recovery_policy.py`

### Helper wrappers removed

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

## Post-Migration Policy

1. Do not reintroduce root wrapper modules without a concrete compatibility requirement.
2. Use semantic subpackages directly for implementation imports.
3. Keep compatibility checks focused on the supported root facade in `modules.agent.orchestration.__init__`, not on deleted wrapper paths.
