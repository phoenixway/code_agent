# Architecture Recommendations: Sub-goal Tracking and Memory Invalidation

This document outlines the required changes to support formal XML-based sub-goal tracking and memory invalidation.

## 1. Prompt Engineering Changes (`modules/defaults.py`)

### Sub-goal Protocol
Add a new section to define when and how to break down tasks:

```markdown
## SUB-GOAL PROTOCOL
If the active intent goal is complex, you MUST break it down into explicit sub-goals using XML tags.
Sub-goals must be concrete, actionable, and verifiable.

Supported actions (emit these after and alongside memory tags):
- <subgoal action="create" id="sg_1">Setup database schema</subgoal>
- <subgoal action="mark_done" id="sg_1">Setup database schema and migrations</subgoal>
- <subgoal action="modify" id="sg_1">...</subgoal>
- <subgoal action="remove" id="sg_1">...</subgoal>

Rules:
- Never mark a sub-goal done without citing concrete evidence.
- You must clear or complete all sub-goals before emitting `<intent mode="complete">`.
```

### Memory Invalidation Protocol
Formalize the invalidation of stale memory:

```markdown
Supported tags (now require IDs for future invalidation):
- 

MEMORY INVALIDATION RULE:
When reading new evidence that contradicts existing memory, you MUST explicitly invalidate the stale memory using:
- <invalidate_memory target_id="f1" reason="Found newer implementation in core.py" />
```

## 2. Backend Architecture Changes (Python)

### Parsing
- **Target:** `modules/parser.py`, `modules/agent/orchestration/intent_response_parser.py`, or a new parser.
- **Action:** Extend logic to capture `<subgoal>` and `<invalidate_memory>` tags.

### State Management
- **Target:** `modules/agent/orchestration/state_manager.py` or `intent_runtime.py`.
- **Action:** Create a `SubGoalManager` to hold the list of active/completed sub-goals for the current intent. Handle `create`, `mark_done`, `modify`, and `remove` actions.

### Memory Board Engine
- **Target:** `modules/memory_board_engine.py`.
- **Action:** Convert memory entries to use unique IDs. Add an `invalidate_entry(id, reason)` method to remove or mark entries as `[INVALIDATED]`, allowing the model to see the evolution without treating it as current fact.

### Prompt Injection
- **Target:** `modules/history_materials.py` or `orchestrator_prompt_builder.py`.
- **Action:** Inject the current active sub-goals next to the active intent contract and memory board.

```text
## ACTIVE INTENT CONTRACT
Status: ACTIVE
Goal: ...

## ACTIVE SUB-GOALS
[sg_1] Setup database schema (Pending)
[sg_3] Implement UI bindings (Pending)
(Completed: sg_2)

## MEMORY BOARD
[f1] ...
```
