modules/agent/orchestration/protocol/spec.py
modules/agent/orchestration/protocol/classifier.py
modules/agent/orchestration/responses/protocol_decision_bridge.py
modules/agent/orchestration/responses/response_pipeline_stages.py
modules/agent/orchestration/responses/output_recovery_routing.py
modules/agent/orchestration/responses/semantic_checks.py
modules/agent/orchestration/transitions/intent_transition_routing.py
modules/agent/orchestration/transitions/intent_transitions.py
docs/architecture/response_protocol.md
tests/test_protocol_decision_bridge.py
tests/test_protocol_compiler_runtime_integration.py
tests/test_protocol_compiler_pipeline.py
tests/test_mixed_visible_text_and_control_protocol.py
tests/golden/responses/compiler/test_compiler_golden.py
tests/golden/responses/test_semantic_shadow.py

We are continuing the legacy-to-compiler response protocol migration.

Current checkpoint:
Compiler-authoritative structural diagnostics include:
- action payload diagnostics
- file_content pairing diagnostics
- tags-inside-think diagnostics
- E_UNCLOSED_THINK
- E_VISIBLE_TEXT_AFTER_ACTION
- E_VISIBLE_TEXT_AFTER_INTENT
- E_ATOMIC_BUNDLE_REQUIRES_EXACTLY_ONE_ACTION
- E_MULTIPLE_INTENTS
- E_INTENT_COMPLETE_WITH_ACTION

Recently completed:
- ACTION_ONLY safe-subset audit.
- ACTION_ONLY shape alone remains legacy/runtime governed.
- Valid ACTION_ONLY still goes through output recovery, ActionPolicy, checkpoint policy, and dispatch pipeline.
- No broad ACTION_ONLY compiler authority was added.

Still NOT broadly compiler-authoritative:
- PLAINTEXT_ONLY by shape
- ACTION_ONLY by shape
- valid INTENT_ACTION_BUNDLE dispatch
- broad E_MIXED_VISIBLE_TEXT_AND_CONTROL
- complete intent + visible final answer policy
- runtime policies: evidence sufficiency, subgoal validation, search narrowing, ActionPolicy

Next migration area:
PLAINTEXT_ONLY / final answer boundary audit.

Goal:
Audit whether PLAINTEXT_ONLY shape can ever be compiler-authoritative.
Do NOT add PLAINTEXT_ONLY compiler authority in this step.
Document and test that compiler_shape == PLAINTEXT_ONLY alone is never enough to complete an intent or answer the user when runtime policy requires more evidence.

Key rule:
compiler_shape == PLAINTEXT_ONLY only says the response has no protocol action/control blocks.
It does NOT prove:
- evidence sufficiency
- intent completion
- subgoal completion
- final answer correctness
- user goal satisfaction
- safe early stop

Tasks:
1. Search for:
   - PLAINTEXT_ONLY
   - plain text
   - final answer
   - intent_complete
   - completion_requested
   - intent_accepted_without_followup
   - terminal_plaintext_completion
   - evidence sufficiency
   - sufficient evidence
   - premature conclusion
   - goal_completed
   - no_followup
   - has_visible_answer
   - dispatch_allowed

2. Inventory PLAINTEXT_ONLY cases:
   A. plain answer with no active intent
   B. plain answer with active INVESTIGATE intent and sufficient evidence
   C. plain answer with active intent but missing evidence
   D. plain answer after tool result that is too broad/noisy
   E. plain answer after recovery prompt asking for action-only correction
   F. plain text that is actually protocol-looking literal/code
   G. complete intent + visible text current behavior
   H. terminal_plaintext_completion fallback
   I. malformed prior step followed by plaintext
   J. user explicitly asks for final answer from current evidence

For each case document:
   - compiler shape/error_code/recovery_id
   - legacy/runtime decision
   - current ProtocolDecisionBridge authority
   - runtime stage that decides final outcome
   - whether compiler could ever own it safely
   - risk level

3. Add docs section:
   "PLAINTEXT_ONLY Final-Answer Boundary Audit"

The section must clearly state:
   - PLAINTEXT_ONLY is structural only.
   - It is never sufficient to prove answer correctness or intent completion.
   - Runtime remains authoritative for sufficiency, active intent completion, subgoal completion, and user-facing stop decisions.
   - Compiler may own precise invalid diagnostics involving plaintext position/mixing, but not broad plaintext acceptance.

4. Add tests only if boundary coverage is missing:
   - ProtocolDecisionBridge test:
     compiler_shape="PLAINTEXT_ONLY", no compiler_error_code
     => source="legacy", reason="legacy_default"

   - Pipeline/transition test if easy:
     active intent + PLAINTEXT_ONLY without completion/evidence should not be treated as compiler-authoritative completion.

   - Regression:
     broad E_MIXED_VISIBLE_TEXT_AND_CONTROL remains legacy/default.
     complete intent + visible text remains current legacy/runtime governed behavior.

5. Do not change behavior.
6. Do not add new authority rules.
7. Do not change parser behavior.
8. Do not change prompts.
9. Do not change evidence sufficiency, subgoal validation, search policy, ActionPolicy, or intent transition semantics.

Run:
grep -R "PLAINTEXT_ONLY\|plain text\|final answer\|intent_complete\|completion_requested\|intent_accepted_without_followup\|terminal_plaintext_completion\|evidence sufficiency\|sufficient evidence\|premature conclusion\|goal_completed\|no_followup\|has_visible_answer\|dispatch_allowed" -n modules/agent/orchestration tests docs

python -m py_compile modules/agent/orchestration/protocol/classifier.py \
                     modules/agent/orchestration/responses/protocol_decision_bridge.py \
                     modules/agent/orchestration/responses/response_pipeline_stages.py \
                     modules/agent/orchestration/responses/output_recovery_routing.py \
                     modules/agent/orchestration/transitions/intent_transition_routing.py \
                     modules/agent/orchestration/transitions/intent_transitions.py

pytest tests/test_protocol_decision_bridge.py \
       tests/test_protocol_compiler_runtime_integration.py \
       tests/test_protocol_compiler_pipeline.py \
       tests/test_mixed_visible_text_and_control_protocol.py \
       tests/golden/responses/compiler/test_compiler_golden.py \
       tests/golden/responses/compiler_gaps/test_compiler_gap_matrix.py \
       tests/golden/responses/test_semantic_shadow.py

pytest -q tests

Expected outcome:
- Prefer docs/tests audit only.
- No broad PLAINTEXT_ONLY compiler authority.
- If any test/docs inconsistencies are found, fix them.
- Runtime remains final authority for final-answer and intent completion decisions.