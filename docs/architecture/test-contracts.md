# Test Contracts

This document lists key tests that protect critical invariants of the response protocol and orchestration pipeline. These tests must remain green.

| Invariant | Key Test(s) | File |
|---|---|---|
| **Compiler `INVALID` blocks legacy action dispatch** | `test_compiler_invalid_unclosed_think_blocks_legacy_action_dispatch` | `tests/test_protocol_compiler_runtime_integration.py` |
| **`compiler_ir.action_ops` provides compatibility action proposal** | `test_is_plaintext_answer_path_rejects_compiler_ir_action_without_legacy_segment` | `tests/test_response_semantics.py` |
| | `test_nonproductive_thinking_turn_false_for_compiler_ir_action_without_legacy_segment` | `tests/test_response_guards.py` |
| **Malformed `<think>` escalates to terminal handoff** | `test_malformed_incomplete_think_escalates_to_handoff_on_third_repeat` | `tests/test_malformed_think_escalation.py` |
| **Action payload array is recovered, not dispatched** | `test_single_action_block_with_json_array_gets_specific_invalid_kind` | `tests/test_action_array_diagnosis.py` |
| | `test_output_recovery_uses_action_array_prompt_not_multiple_action_prompt` | `tests/test_action_array_diagnosis.py` |
| **Output recovery routes based on compiler metadata** | `test_output_recovery_compiler_strategy_routing_with_snapshot` | `tests/test_runtime_protocol_semantics.py` |
| **Search quality classification is diagnostic-only** | (No specific test) | `modules/agent/orchestration/runtime/action_policy.py` |
| | The `_log_search_quality` method in `ActionPolicyHandler` only logs; it does not return a decision or block dispatch. | |
| **Compiler provides structural facts for terminal answers** | `test_golden_structural_facts` | `tests/test_compiler_structural_facts.py` |

---

## Changing Test Contracts

The tests listed here are the guardians of the Supreme Invariants from the constitution. They must not be weakened without explicit approval.

-   **Before changing or removing a test**, identify the invariant it protects.
-   **State whether the invariant still stands.** If the invariant is being changed, this requires an update to the constitution and explicit design approval.
-   **Refactoring is allowed** only if equivalent or stronger protection for the invariant is maintained.
