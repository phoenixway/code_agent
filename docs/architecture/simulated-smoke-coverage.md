# Simulated Smoke Coverage

This document tracks the simulated smoke-test layer for Angelica AI runtime contracts.

The goal of this layer is not to test model quality. It tests runtime behavior using scripted/synthetic inputs, fake commits, direct runtime helpers, and stable assertions around model-facing state.

## Scope

Simulated smoke tests protect behavior that previously appeared in live dumps as fragile or hard to diagnose:

- recovery visibility and recovery lifecycle;
- execution telemetry and export surfaces;
- edit/read recovery route selection;
- plan-review gate behavior after state-changing actions;
- subgoal board behavior and planner lineage safety.

This layer should stay compact. It is a smoke/net layer, not a replacement for focused unit tests.

## Current coverage

### P3.1 — recovery visibility

File:

- `tests/test_simulated_recovery_visibility_smoke.py`

Covers:

- recovery instructions become visible in the effective model-facing overlay;
- `next_turn` recovery instructions expire;
- `until_same_action_success` recovery instructions are hidden after matching success;
- recovery visibility is scoped to `current_intent`;
- raw history is preserved even when effective overlay hides recovery text;
- legacy recovery instructions without `recovery_visibility` metadata remain visible for backward compatibility.

Protected contract:

- raw history/debug data remains untouched;
- model-facing recovery overlay is filtered by lifecycle metadata;
- current-intent recovery does not leak into unrelated future intents.

### P3.2 — telemetry

File:

- `tests/test_simulated_telemetry_smoke.py`

Covers:

- fallback single-action dispatch telemetry;
- atomic bundle dispatch telemetry;
- preflight/blocked execution telemetry;
- state-changing action effect/applied fields;
- read-only success does not claim state change;
- runtime diagnostics and artifacts expose clarified execution commit fields.

Protected contract:

- telemetry distinguishes action presence, validation, dispatch, tool execution attempt, tool success, system result recording, state-change effect, and applied state change;
- dump/export surfaces should not mislead readers with ambiguous `action_dispatched=false` next to a committed system result.

### P3.3 — edit/read recovery routes

File:

- `tests/test_simulated_edit_tool_recovery_routes_smoke.py`

Covers:

- exact `edit_file` miss with unique fuzzy candidate routes toward `fuzzy_edit_file`;
- malformed line-range-like `edit_file` routes toward `replace_line_range`;
- repeated read of already available file content routes toward using existing content;
- repeated malformed `read_chunk` recovery remains covered by canonical recovery-coordinator tests rather than duplicated as a fragile smoke clone.

Protected contract:

- recovery route hints should move the model toward the correct tool, not repeat blind failing actions;
- read-file dedupe policy should preserve already available evidence instead of wasting context and steps.

### P3.5 — recovery lifecycle gaps

File:

- `tests/test_simulated_recovery_visibility_smoke.py`

Covers:

- current-intent recovery hides after intent change;
- legacy recovery without visibility metadata remains visible;
- mixed recovery overlays include only visible current-scope instructions plus legacy instructions;
- `run_shell` transient/timeout recovery metadata uses `next_turn` and `current_intent`;
- denied-action recovery lifecycle is next-turn and current-intent scoped.

Protected contract:

- recovery metadata is lifecycle-bound;
- recovery text should not become a sticky global law;
- legacy default remains fail-open visible unless explicitly scoped.

### P3.6 — plan-review gate

File:

- `tests/test_simulated_plan_review_smoke.py`

Covers:

- successful state-changing file actions set `plan_review_required_after_state_change`;
- `replace_line_range` participates in the post-state-change plan-review gate;
- `action -> plan_review_done` in the same response does not retroactively satisfy the gate;
- `plan_review_done -> action` clears/allows the next action;
- plain response without `plan_review_done` does not clear required plan review.

Protected contract:

- after a successful state-changing action, the next action must be preceded by valid plan review;
- checkpoint order matters;
- plan-review gate cannot be accidentally cleared by prose or by a checkpoint emitted after an action.

### P3.7 — subgoal board behavior and duplicate guard

File:

- `tests/test_simulated_subgoal_board_smoke.py`

Covers:

- duplicate active subgoals with the same normalized title are deduplicated;
- creating with the same id updates the existing step;
- `mark_done` without evidence is rejected at parse stage;
- weak non-empty `mark_done` evidence is currently accepted as characterization;
- `plan_review_done` alone does not create subgoal ops or mutate the board;
- plan board summary reflects canonical runtime board state after dedupe.

Protected contract:

- the planner should not create `sg_4` and `sg_5` hydras for the same active work item;
- subgoal parser requires evidence for `mark_done`, but does not semantically grade evidence quality;
- plan checkpoint tags are not subgoal mutations.

### P3.8 — planner board lineage

File:

- `tests/test_simulated_subgoal_board_smoke.py`

Covers:

- stale other-lineage board is rejected by planner normalization;
- `apply_update` under a new active intent creates a fresh board;
- board binding stamps `intent_id` and `lineage_id`;
- same lineage can carry a board across changed intent id;
- `HistoryManager` plan-board summary is projection-only and does not enforce lineage filtering itself.

Protected contract:

- planner lineage logic owns stale-board filtering;
- history projection must not silently repair or reinterpret board ownership;
- stale board protection happens before model-facing prompt projection.

## Known intentional gaps

### `mark_done` evidence quality

Current runtime contract:

- `mark_done` requires non-empty evidence;
- runtime does not semantically grade evidence quality;
- prompt/protocol guidance asks for concrete proof-of-change evidence.

Reason this remains a gap:

- evidence quality is context-dependent;
- string-based filters such as rejecting phrases like `Identified insertion point` would be brittle;
- a robust future guard should use structured runtime facts, not hardcoded phrase policing.

Possible future direction:

- allow `mark_done` only after a successful state-changing commit since the subgoal became active;
- or add structured evidence references such as `evidence_source="tool_result"` / `evidence_ref="last_execution_commit"`.

### History projection is not policy enforcement

`HistoryManager` can project `state.task_board` into prompt context, but it should not own stale-board or lineage policy.

Planner/prompt-builder layers should decide whether a board is valid for the active intent. History should remain a projection layer.

### Simulated smoke is not live model quality testing

These tests do not prove that a live LLM will choose the best next action. They prove that runtime surfaces, gates, recovery metadata, and board mutations behave consistently when given specific synthetic inputs.

## Non-scope for this layer

Do not use this layer for:

- broad prompt diet rewrites;
- Smart Patcher Android behavior;
- Gradle wrapper policy;
- new tools;
- provider/API behavior;
- model-quality evaluation;
- large history refactors.

## Maintenance rules

When adding a new simulated smoke test:

1. Prefer existing unit tests for fine-grained behavior.
2. Add smoke tests only for cross-layer or dump-visible runtime contracts.
3. Keep tests deterministic and model-free.
4. Avoid duplicating canonical unit tests unless the smoke test proves a different integration surface.
5. If a smoke test exposes a production gap, either:
   - characterize current behavior explicitly; or
   - make a small focused production fix with targeted tests.
6. Record intentional gaps here when they are deliberately left unfixed.

## Current next candidates

Reasonable future slices:

- structured `mark_done` evidence based on runtime facts, not phrase matching;
- additional planner report/telemetry smoke if board mutations become operational-journal visible;
- semantic runtime accessor migration tests around compiler metadata helpers.
