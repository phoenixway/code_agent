# Current Refactor State: Semantic Runtime Migration

This document is the single source of truth for the current state of the Semantic Runtime Migration refactor.

## Current Phase

- **Phase 4: Behavior-Preserving Wrapper Migration (Design for next consumer)**
- **Status**: Batch 1 migration is complete. Next step is to plan the next behavior-preserving migration.

## Completed Governance

- **Governance Phase 1: Governance Alignment**
  - All governance documents (`constitution`, `roadmap`, `stop-lines`, etc.) are aligned with the actual completed work and established boundaries.

## Completed Work

- **Phase 0: Boundary Freeze**
  - `RuntimeProtocolSemantics` adapter created for compiler-derived data.
  - Adapter populated in response pipeline for diagnostic use.
- **Phase 2: Consumer Inventory**
  - A detailed inventory of all locations that consume response semantics was created and approved.
  - The inventory lives in `docs/architecture/protocol-authority-boundaries.md`.
- **Phase 3A: Compiler Metadata Migration (in `output_recovery`)**
  - Centralized helper for reading `error_code`, `recovery_id`, and `invalid_kind` from `RuntimeProtocolSemantics` with legacy fallbacks.
  - All compiler strategy handlers and `_compiler_repeat_fingerprint` now use the centralized helper.
  - Parity diagnostics added to log differences between legacy and new semantic sources.
  - **Boundary**: This work is complete and closed.
- **Phase 3: Accessor Module (Implementation)**
  - `modules/agent/orchestration/responses/semantic_accessors.py` created with four approved accessors (`get_compiler_metadata`, `has_any_action_proposal_compat`, `is_compiler_invalid`, `is_compiler_invalid_with_legacy_action`).
  - Dedicated unit tests created in `tests/test_semantic_accessors.py`.
  - No consumers were migrated, and no runtime behavior was changed.
- **Phase 4 (Step 1): `has_any_action_proposal` Migration**
  - `ResponseSemantics.has_any_action_proposal` now delegates to `semantic_accessors.has_any_action_proposal_compat`.
  - Behavior was preserved, and all relevant tests passed.
  - No other consumers were migrated.
- **Phase 4 (Batch 1): Call-Site Migrations**
  - Migrated `OutputRecoveryRoutingMixin._compiler_strategy_decision` to use `get_compiler_metadata`.
  - Migrated `ModelOutputRecoveryHandler._has_any_action_proposal` to use `has_any_action_proposal_compat`.
  - The `output_recovery_compiler_metadata` helper was preserved.
  - No other consumers were migrated, and runtime behavior was unchanged.
- **Next Accessor Batch (Implementation)**
  - Implemented `is_leaked_system_result` and `has_substantial_think` in `semantic_accessors.py`.
  - Added dedicated unit tests, which passed.
  - `get_visible_text` was not implemented and remains deferred.
  - No consumers were migrated, and no runtime behavior was changed.

## Known Authority Boundaries

- **Compiler**: Authoritative for precise, structural diagnostics. A compiler-`INVALID` response must never be dispatched.
- **Runtime**: Authoritative for all semantic and policy decisions (e.g., `ActionPolicy`, evidence sufficiency, final answer correctness).
- **Compatibility Shim**: `ResponseSemantics.has_any_action_proposal` is a protected compatibility helper for detecting action-like content for recovery purposes. It is not dispatch authority.

## Current Known Risks

- **Mixed Authority**: The response pipeline still consumes a mix of legacy parser fields and new compiler-derived data.
- **Implicit Semantics**: Many runtime decisions still rely on fragile regex-based helpers.
- **Scope Creep**: The `history.py` refactor is explicitly blocked.

## Next Intended Step

- Review and approve the "Phase 4 Batch 2" migration design.
- The plan proposes migrating two low-risk consumers (`ResponsePipelineStagesMixin` and `ResponseGuardPolicy`) to their accessor equivalents.
- Implementation is blocked until the plan is approved.

## Test Status

- All tests are currently passing.
- Key test contracts are documented in `test-contracts.md`.
