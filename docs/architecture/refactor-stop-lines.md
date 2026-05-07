# Refactor Stop Lines

The following changes are **forbidden** without a new, explicit design document and approval. These stop lines are in place to prevent regressions and maintain stability during the Semantic Runtime Migration.

- **Do not make `RuntimeProtocolSemantics.has_action` or `action_count` dispatch-authoritative.**
  - These are structural facts from the compiler. The runtime (`ActionPolicy`, etc.) owns dispatch authority.

- **Do not replace `ResponseSemantics.has_any_action_proposal` with `RuntimeProtocolSemantics.has_action`.**
  - `has_any_action_proposal` is a broad, backward-compatible check for recovery evidence. `RPS.has_action` is a stricter structural fact. They serve different purposes.

- **Do not remove the `compiler_ir.action_ops` fallback from `has_any_action_proposal`.**
  - This is a critical compatibility shim that allows the runtime to see compiler-detected actions even when the legacy parser does not create an action segment.

- **Do not treat `compiler_shape == 'ACTION_ONLY'` alone as dispatch permission.**
  - This shape only describes the protocol structure. It does not bypass runtime policy checks (e.g., `ActionPolicy`, checkpoint validation).

- **Do not migrate `ActionPolicy` authority to the compiler.**
  - `ActionPolicy` depends on runtime state (e.g., active intent contract) that the compiler does not have.

- **Do not treat compiler `INVALID` responses as dispatchable.**
  - A response that the compiler deems structurally `INVALID` must never be dispatched, even if legacy parsers detect action-like content. That content is recovery evidence only.

- **Do not change `search_quality` from diagnostic-only.**
  - The search quality classifier must not be used to block or recover actions without a new, approved design.

- **Do not change core runtime behaviors.**
  - Formal intent recovery, final-answer/sufficiency logic, and action array/multi-action behaviors are frozen.

- **Do not begin the `history.py` refactor.**
  - The large `history.py` refactor is blocked until the semantic runtime boundary is stable and proven.
