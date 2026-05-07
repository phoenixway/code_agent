Так, це логічніше. Перед великим рефакторингом `history.py >1500 lines` краще закрити старий шов: **semantic runtime on compiler-based IR**. Інакше history-refactor буде будуватися на старих двох напівджерелах істини: legacy parser/segments + compiler IR/RPS.

Я б зараз сформулював наступну фазу так:

```text
Phase 3B-pre: Semantic Runtime on Compiler IR, design + read-only parity
```

Не “перемкнути все на compiler IR”, а зробити **офіційний шар semantic runtime**, який читає compiler IR, але ще не забирає authority у runtime policy.

## Що саме треба закрити перед history.py

Тобі треба не просто `RuntimeProtocolSemantics`, а стабільний міст:

```text
ProtocolCompiler IR
    ↓
RuntimeProtocolSemantics snapshot
    ↓
Semantic runtime helpers
    ↓
output_recovery / response_pipeline / action_policy consumers
```

Зараз частково вже є:

```text
compiler metadata: error_code / recovery_id / invalid_kind
compiler_ir.action_ops fallback in ResponseSemantics.has_any_action_proposal
RPS parity diagnostics
output recovery metadata helper
```

Але немає чіткого “семантичного runtime API”, який каже:

```text
ось що можна питати у compiler IR
ось що не можна
ось де fallback
ось які invalid cases не dispatch-authoritative
```

## Наступний правильний крок

Я б робив **Phase 3B-pre audit + API boundary**, не implementation-switch.

Мета: створити або оформити один модуль/шар типу:

```text
modules/agent/orchestration/responses/runtime_semantic_access.py
```

або розширити існуючий:

```text
runtime_protocol_semantics.py
response_semantics.py
```

але дуже обережно.

Функції-кандидати:

```python
get_compiler_metadata(parsed_output)
has_compiler_valid_action(parsed_output)
has_any_action_proposal_compat(parsed_output, parsed_action_count)
is_compiler_invalid_with_legacy_action(parsed_output, parsed_action_count)
is_dispatch_authoritative_action_shape(parsed_output)
```

Ключ: **назви мають кодувати authority**. Не `has_action`, а наприклад:

```text
has_any_action_proposal_compat
```

бо це не “можна dispatch”, а “є action-like proposal для recovery/policy checks”.

## Prompt для aider

```text
Phase 3B-pre: design semantic runtime access layer on compiler-based IR.

Context:
Project: Angelica AI.

We want to close the old protocol/runtime semantic migration before starting a large history.py refactor.

Current state:
- ProtocolCompiler produces compiler IR.
- RuntimeProtocolSemantics exists as compiler-derived snapshot.
- Output recovery metadata reads are centralized through RuntimeProtocolSemantics-backed helper:
  error_code, recovery_id, invalid_kind.
- ResponseSemantics.has_any_action_proposal currently uses:
  parsed_action_count > 0
  OR compiler_ir.action_ops
  OR legacy has_action_segment
  This is existing tested compatibility behavior.
- RuntimeProtocolSemantics.has_action/action_count are NOT dispatch-authoritative.
- Compiler-invalid responses can intentionally disagree with legacy action detection:
  compiler/RPS: INVALID, action_count=0, has_action=False
  legacy: has_action_segment=True, parsed_action_count>0
  This mismatch is expected and safety-critical.

Goal:
Create a design/audit foundation for a semantic runtime access layer based on compiler IR, without changing runtime behavior yet.

Do not change:
- ProtocolCompiler
- RuntimeProtocolSemantics core behavior
- ActionPolicy decisions
- dispatch behavior
- output recovery behavior
- search_quality
- history.py
- broad search policy
- final answer sufficiency
- action array behavior

Relevant files to inspect:
- modules/agent/orchestration/responses/runtime_protocol_semantics.py
- modules/agent/orchestration/responses/response_semantics.py
- modules/agent/orchestration/responses/response_pipeline_prevalidation.py
- modules/agent/orchestration/responses/response_pipeline_stages.py
- modules/agent/orchestration/responses/output_recovery.py
- modules/agent/orchestration/responses/output_recovery_routing.py
- modules/agent/orchestration/runtime/action_policy.py
- modules/agent/orchestration/runtime/dispatch_pipeline.py
- modules/agent/orchestration/shared/decision_models.py
- docs/architecture/response_protocol.md
- tests/test_response_semantics.py
- tests/test_runtime_protocol_semantics.py
- tests/test_protocol_compiler_runtime_integration.py
- tests/test_response_pipeline_refactor.py
- tests/test_response_guards.py
- tests/test_action_array_diagnosis.py
- tests/test_malformed_think_escalation.py

Search for:
- has_any_action_proposal
- compiler_ir
- action_ops
- has_action_segment
- action_count
- parsed_action_count
- runtime_protocol_semantics
- compiler_shape
- ACTION_ONLY
- INTENT_ACTION_BUNDLE
- INVALID
- dispatch_ready
- actions_allowed_to_proceed
- is_plaintext_answer_path
- nonproductive_thinking
- force_plaintext_completion
- missing_action_or_answer
- missing_memory_update_done

Task:

1. Add a design section to docs/architecture/response_protocol.md.

Suggested heading:
##### Phase 3B-pre: Semantic Runtime Access Layer

Document the goal:
- define explicit semantic accessors over compiler IR / RuntimeProtocolSemantics;
- separate compatibility detection from dispatch authority;
- avoid scattered direct reads of compiler_ir / legacy segments;
- preserve current behavior until a later implementation phase.

2. Document authority vocabulary.

Use these terms:

A. Compiler metadata authority:
- error_code
- recovery_id
- invalid_kind
Already used by output recovery metadata helpers.

B. Compatibility action proposal:
- means “there is action-like content that policy/recovery must consider”
- may use parsed_action_count, compiler_ir.action_ops, or legacy has_action_segment
- used by ResponseSemantics.has_any_action_proposal
- NOT equivalent to dispatch permission

C. Dispatch-authoritative action:
- means action is structurally valid and allowed to proceed to dispatch
- remains owned by response pipeline + ActionPolicy + runtime checks
- RuntimeProtocolSemantics.has_action/action_count are not sufficient alone

D. Compiler-invalid safety state:
- compiler shape INVALID means action_ops should not become dispatch authority
- legacy action-like segments in invalid responses are recovery evidence, not dispatch evidence

3. Inventory current semantic consumers.

For each consumer, document:
- function/location
- current source:
  - compiler_ir.action_ops
  - RuntimeProtocolSemantics
  - legacy segments
  - parsed_action_count
  - has_action_segment
- semantic meaning:
  - metadata
  - compatibility action proposal
  - dispatch authority
  - recovery evidence
  - plaintext/final-answer guard
  - checkpoint/memory policy
- migration recommendation:
  - keep as-is
  - wrap in semantic accessor later
  - runtime-owned / do not migrate
  - diagnostic-only candidate

Important consumers to cover:
- ResponseSemantics.has_any_action_proposal
- ResponseSemantics.is_plaintext_answer_path
- response guard nonproductive thinking checks
- force_plaintext_completion block
- _reject_invalid_intent_followup_before_transition
- zero_action_invalid
- output recovery action-like checks
- ActionPolicy dispatch path

4. Propose future API names, but do not implement unless trivial docs-only examples.

Suggested future accessor names:
- get_compiler_metadata(parsed_output)
- has_any_action_proposal_compat(parsed_output, parsed_action_count)
- has_compiler_ir_action_ops(parsed_output)
- is_compiler_invalid(parsed_output)
- is_compiler_invalid_with_legacy_action(parsed_output, parsed_action_count)
- is_dispatch_authoritative_action_shape(parsed_output)

Document expected semantics and non-goals for each.

5. Add explicit stop lines.

- Do not replace has_any_action_proposal with RuntimeProtocolSemantics.has_action.
- Do not use RPS.action_count as dispatch proof.
- Do not treat ACTION_ONLY shape alone as dispatch permission.
- Do not treat INVALID legacy action segments as dispatchable.
- Do not migrate ActionPolicy authority in Phase 3B-pre.

6. Add acceptance criteria for a future implementation phase.

Future implementation may proceed only when:
- all semantic accessors have tests for compiler-valid and compiler-invalid cases;
- invalid compiler + legacy action mismatch remains recovery-owned;
- existing tests for response guards, plaintext path, force_plaintext_completion, action array, malformed think remain green;
- dispatch behavior is unchanged unless a separate explicit design approves it.

7. Production code:
Prefer docs-only for this task.
If you find a tiny duplicate direct read that can be documented but not safely changed, leave it unchanged.
Do not refactor code in this task.

8. Run:
pytest -q tests

9. Show:
git diff --stat
git diff -- docs/architecture/response_protocol.md
```

## Чому це правильний міст перед `history.py`

Бо `history.py` рефакторинг майже точно торкнеться:

```text
що лишати в контексті
що стискати
що вважати evidence
що вважати action/result
що переносити в memory
що показувати моделі як canonical state
```

Якщо semantic runtime ще мутний, history refactor почне консервувати стару плутанину. Спершу треба назвати речі:

```text
compat action proposal ≠ dispatch action
compiler-invalid legacy action ≠ action to execute
compiler metadata ≠ runtime policy
```

Після цього вже можна різати `history.py` без відчуття, що під скальпелем не тканина, а клубок проводів.
