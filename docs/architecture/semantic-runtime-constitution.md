# Semantic Runtime Migration: Constitution

## 1. Purpose

This document is the supreme governing law for the Semantic Runtime Migration refactor. It ensures all work, whether by human or AI, proceeds in a safe, incremental, and behavior-preserving manner.

## 2. Core Objective

To systematically replace legacy response-parsing logic with a robust, compiler-driven semantic access layer, making the runtime more reliable, efficient, and maintainable without altering existing behavior unless explicitly designed.

## 3. Supreme Invariants

These invariants are the highest law and must not be violated.

1.  **Compiler `INVALID` Is Final**: A response that the protocol compiler deems structurally `INVALID` must **never** be dispatched.
2.  **Legacy Content Is Recovery Evidence**: Action-like content detected by legacy parsers in a compiler-`INVALID` response is considered **recovery evidence only**, not dispatch evidence.
3.  **Compiler Facts Are Not Authority**: `RuntimeProtocolSemantics.has_action` and `action_count` are structural facts, not dispatch authority.
4.  **Compatibility Is Not Authority**: `ResponseSemantics.has_any_action_proposal` is a backward-compatible check for recovery evidence. It is **not** dispatch permission.
5.  **`compiler_ir.action_ops` Fallback Is Protected**: The fallback in `has_any_action_proposal` that checks `compiler_ir.action_ops` is a critical compatibility shim and must not be removed without a new design.
6.  **Runtime Owns Policy**: `ActionPolicy`, dispatch decisions, and all other runtime policies remain owned by the runtime, not the compiler.
7.  **`history.py` Refactor Is Blocked**: The large `history.py` refactor must not begin until the semantic runtime boundary is stable and proven.
8.  **`search_quality` Is Diagnostic-Only**: `search_quality` remains diagnostic-only unless explicitly approved otherwise.
9.  **Docs-Only Tasks Are Isolated**: `docs-only` tasks must not change production code or tests.
10. **Formal Intent Recovery Is Frozen**: Formal intent recovery is frozen during the current migration phase.
11. **Final-Answer Behavior Is Frozen**: Final-answer/sufficiency behavior is frozen during the current migration phase.
12. **Multi-Action Behavior Is Frozen**: Action array / multi-action behavior is frozen during the current migration phase.
13. **Test Contracts Are Guarded**: Tests protecting critical invariants must not be removed or softened without naming the invariant and recording explicit approval.

## 4. Authority Model

-   **Compiler Authority**: Limited to precise, structural diagnostics (e.g., malformed tags, invalid nesting).
-   **Runtime Authority**: Owns all semantic and policy decisions (e.g., `ActionPolicy`, evidence sufficiency, final answer correctness).

For details, see `docs/architecture/protocol-authority-boundaries.md`.

## 5. Forbidden Changes Without Explicit New Approval

The following changes are forbidden without a new, approved design document.

-   Making `RuntimeProtocolSemantics.has_action` or `action_count` dispatch-authoritative.
-   Replacing `ResponseSemantics.has_any_action_proposal` with `RuntimeProtocolSemantics.has_action`.
-   Treating `compiler_shape == 'ACTION_ONLY'` alone as dispatch permission.
-   Migrating `ActionPolicy` authority to the compiler.

For a complete list, see `docs/architecture/refactor-stop-lines.md`.

## 6. Work Mode Rules

-   **Narrow Scope**: Each task must be confined to its stated goal and phase.
-   **Behavior Preservation**: No production code change may alter runtime behavior unless explicitly part of a documented design.
-   **Incrementalism**: Prefer small, verifiable steps over large, complex changes.

## 7. Phase Governance

All work must adhere to the current phase defined in `docs/architecture/semantic-runtime-roadmap.md`. Each phase has strict `Allowed`, `Forbidden`, and `Done When` criteria that must be respected.

## 8. Test Contract Authority

The tests listed in `docs/architecture/test-contracts.md` are the official guardians of the Supreme Invariants. These tests must remain green at all times. Any change that breaks a test contract is a violation of this constitution unless accompanied by an approved design update.

## 9. Aider Behavior Rules

Any AI agent (e.g., aider) working on this project must:
1.  Read and acknowledge this constitution and the canonical documents.
2.  State the current refactor phase for every task.
3.  Adhere strictly to the `Forbidden` rules of the current phase.
4.  Never expand a task's scope into a future phase.
5.  Default to documentation-only or test-only changes unless explicitly instructed to change production code.

## 10. Canonical Documents

-   `semantic-runtime-constitution.md` (this document)
-   `current-refactor-state.md`
-   `semantic-runtime-roadmap.md`
-   `protocol-authority-boundaries.md`
-   `refactor-stop-lines.md`
-   `test-contracts.md`

## 11. Updating This Constitution

This document can only be amended by a formal process that includes:
1.  A design proposal outlining the change.
2.  An update to relevant test contracts.
3.  Approval from the project lead.
