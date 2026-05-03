# Agent State Ownership

This document records the current ownership and lifecycle of the most important
orchestration-related fields on `modules.agent.state_manager.AgentState`.

It is not a full field-by-field dump of `AgentState`. The goal is narrower:

- make orchestration-owned state explicit
- distinguish turn-local latches from cross-turn resumable metadata
- prevent future refactors from silently resetting or reusing the wrong fields

## Canonical Source

The code-level ownership map lives in:

- [modules/agent/state_manager.py](/home/romankozak/studio/public/it/angelica-ai/modules/agent/state_manager.py)

Specifically:

- `AgentState.ORCHESTRATION_TURN_LOCAL_FIELDS`
- `AgentState.ORCHESTRATION_CROSS_TURN_FIELDS`
- `AgentState.RESUMABLE_INTENT_FIELDS`
- `AgentState.TECHNICAL_INTERRUPTION_FIELDS`
- `AgentState.orchestration_state_field_groups()`

## Field Groups

### Turn-Local Orchestration Fields

These are owned by the current orchestration turn and are expected to be reset
by `start_turn_runtime()`.

Examples:

- `orchestration_trace`
- `orchestration_trace_sequence`
- `memory_tag_expected_next_step`
- `reuse_only_intent_required`
- `transition_only_intent_required`
- `intent_transition_defect_*`
- `think_reflection_repair_kind`
- `build_fix_last_build_*`

Rule:

- these fields must not leak from one real user turn into the next

### Cross-Turn Orchestration Fields

These may legitimately survive beyond one turn because they represent resumable
work, pending closure, technical interruption context, or active build-fix mode.

Examples:

- `pending_loop_stop_info`
- `terminal_plaintext_completion_*`
- `pending_finalize_*`
- `last_resumable_*`
- `last_technical_interruption`
- `pending_resume_query`
- `build_fix_mode_*`

Rule:

- these fields are not automatically cleared by `start_turn_runtime()` unless a
  dedicated lifecycle step consumes/finalizes them

### Resumable Intent Fields

These are the minimal persisted contract snapshot used for resume/reuse flows.

Examples:

- `last_resumable_intent_id`
- `last_resumable_intent_type`
- `last_resumable_intent_goal`
- `last_resumable_intent_lineage_id`
- `last_resumable_intent_completion_reason`

Rule:

- these survive across turns until replaced by a newer resumable completion or
  explicit state reset

### Technical Interruption Fields

These carry interruption metadata for resume UX and retry/reuse logic.

Examples:

- `last_technical_interruption`
- `pending_resume_query`

Rule:

- they are cleared by interruption-specific flows such as
  `clear_technical_interruption()`, not by generic turn reset

## Lifecycle Notes

### `start_turn_runtime()`

This method resets turn-local orchestration state and also finalizes any
pending forced-plaintext completion before the new turn proceeds.

Important invariant:

- a fresh user turn must not inherit stale per-turn orchestration latches
- but it may still use recent resumable/technical metadata

### Forced Plaintext Completion

Relevant fields:

- `terminal_plaintext_completion_pending`
- `terminal_plaintext_completion_text`
- `pending_finalize_after_terminal_plaintext_completion`
- `pending_finalize_completion_reason`
- `pending_finalize_completion_source`

Rule:

- terminal plaintext handoff may span the boundary between response pipeline,
  dispatch outcome, and outer orchestrator loop
- finalization is explicit and must not be lost by an eager generic reset

### Trace Ownership

Trace fields are turn-local state, but schema ownership is not in
`AgentState`. The canonical trace schema owner is:

- [modules/agent/orchestration/shared/trace.py](/home/romankozak/studio/public/it/angelica-ai/modules/agent/orchestration/shared/trace.py)

`AgentState` only stores:

- `orchestration_trace`
- `orchestration_trace_sequence`

## Guidance

When adding new orchestration state:

1. Decide whether the field is turn-local or cross-turn.
2. Add it to the appropriate `AgentState` ownership group.
3. Add or update a lifecycle test if the reset/finalize behavior matters.
4. Avoid introducing new anonymous `setattr(state, "...")` write paths without
   also documenting which lifecycle owns the field.
