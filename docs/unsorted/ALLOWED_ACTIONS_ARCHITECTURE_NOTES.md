# Allowed Actions Architecture Notes

## Goal

Document the next architectural improvements after introducing the MVP `AllowedActionsResolver`.

The main objective is not to add more policy rules, but to reduce duplicated responsibility across:

- intent runtime
- phase/state machine policy
- recovery logic
- dispatcher
- prompt builder

## Current Direction

The MVP `AllowedActionsResolver` is the right direction because it creates a canonical merge point for:

- active intent contract constraints
- phase constraints
- recovery/stop-specific hints
- recommendation-level hints

The next improvements should push more of the system toward typed, centralized decision objects instead of ad-hoc dict fields and local branching.

## Recommended Next Steps

### 1. Make `ResolvedActionPolicy` the single format across the full path

The system should converge on one canonical shape for action-policy decisions.

Instead of passing loose fields like:

- `next_actions`
- `intent_allowed_actions`
- `phase_allowed_actions`
- `recommended_next_actions`
- `next_actions_source`

prefer one structured object such as:

```python
ResolvedActionPolicy(
    allowed_actions=[...],
    recommended_actions=[...],
    blocked_actions=[...],
    authoritative_source="intent" | "phase" | "recommended",
    keep_current_intent=True | False,
)
```

This object should become the primary payload passed from policy/recovery layers into rendering and orchestration.

### 2. Separate hard constraints from soft recommendations

Architecturally, these concepts should be explicit rather than inferred from wording.

Prefer distinct fields for:

- `allowed_actions`
- `blocked_actions`
- `preferred_actions`
- `discouraged_actions`

This removes ambiguity in prompts and reduces logic leakage into the prompt builder.

### 3. Introduce a canonical `StopReason -> RecoveryPolicy` mapping

Recovery behavior is still spread across multiple layers.

Add a small typed mapper/registry that decides, for each stop reason:

- whether the current intent should stay active
- whether plain-text completion is allowed/preferred
- whether exactly one read-only action is required
- whether only state-changing actions are valid
- whether audit/history markers must be explicitly forbidden
- which action source is authoritative

This keeps policy in one place and leaves prompt rendering simpler.

### 4. Remove policy decisions from `PromptBuilder`

`PromptBuilder` should ideally render already-resolved policy decisions instead of making orchestration choices itself.

It should consume objects like:

- `ResolvedActionPolicy`
- `RecoveryDecision`

and focus only on presentation.

That means logic such as:

- preferring current intent over phase recovery
- deciding whether conflicting phase actions should be ignored
- determining which action source wins

should move out of rendering and into resolver/policy layers.

### 5. Make authority order explicit in one place

The system should have one clearly defined priority order for action constraints:

1. runtime hard constraints
2. active intent contract
3. stop-specific recovery constraints
4. phase constraints
5. soft recommendations

This precedence should live in one resolver/policy module only.

### 6. Let `IntentRuntime` expose normalized capability semantics

Today `IntentRuntime` mostly exposes:

- intent type
- allowed actions
- limits
- blocked signatures

It would be cleaner if it also exposed a normalized capability profile, for example:

- `can_read`
- `can_modify`
- `can_batch_readonly`
- `can_complete_now`
- `can_switch_intent`

That would remove scattered checks and reduce dependence on raw action-name lists.

### 7. Demote legacy `next_actions` to compatibility-only status

`next_actions` has become an overloaded carrier for different meanings.

Architecturally, it should become a compatibility alias only.

The primary carrier should instead be a typed resolved policy object.

### 8. Replace free-form `stop_info` dicts with typed models

`stop_info` currently behaves like an evolving schema.

This should be replaced over time with typed models such as:

- `RecoveryContext`
- `RecoveryDecision`
- `ResolvedActionPolicy`

Benefits:

- less schema drift
- fewer magic keys
- better testability
- clearer dumps and debug traces

### 9. Add a dedicated invalid-output classifier

The following cases should be treated as one architectural class of problems:

- `TOOL_HISTORY`
- `history_tool`
- audit marker echoes
- malformed pseudo-actions
- think-only replies with no valid action or answer
- intent-only dead ends

Instead of scattered heuristics, add a classifier that returns typed categories like:

- `VALID_ACTION`
- `VALID_TEXT`
- `INVALID_AUDIT_ECHO`
- `INVALID_HISTORY_TOOL`
- `INVALID_EMPTY_REASONING`
- `INTENT_ONLY_DEADEND`

Then orchestration can map those categories to explicit recovery behavior.

### 10. Keep policy before dispatch, keep dispatcher execution-focused

The dispatcher should ideally:

- validate execution feasibility
- execute tools
- return results

It should not keep accumulating orchestration-policy knowledge.

The system is already moving in that direction; continue pushing policy resolution upward into state machine / recovery / resolver layers.

### 11. Add a single debug snapshot for resolved action policy

For dump analysis, log one canonical snapshot per important decision:

- active intent type
- phase
- stop reason
- source candidates
- authoritative source
- allowed actions
- recommended actions
- keep-current-intent flag

This will make future debugging much easier and reduce guesswork.

### 12. Reduce branching in text-generation paths

Recovery text is still assembled from multiple conditional layers.

Prefer:

- one structured recovery decision
- one renderer

instead of multiple places conditionally mutating the final wording.

## Priority Order

If implemented incrementally, the best order is:

1. make `ResolvedActionPolicy` and `RecoveryDecision` the primary typed objects across the whole orchestration path
2. move policy choices out of `PromptBuilder`
3. replace loose `stop_info` dict growth with typed models
4. add a dedicated invalid-output classifier
5. retire `next_actions` as the main cross-layer payload

## Short Conclusion

The next big architectural gain is not another engine.

It is:

- typed decision objects
- one canonical policy merge point
- cleaner separation between decision-making and rendering

That will reduce system entropy more than adding more local fixes or more special-case branching.
