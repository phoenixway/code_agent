> **NOTE**: This is a historical planning document and advisory note.
> It is not authoritative.
> Canonical governance for the Semantic Runtime Migration is defined in `docs/architecture/`.
> If this document conflicts with `docs/architecture/*`, the architecture documents are the source of truth.

ITS JUST DRAFT!

## Моя оцінка варіантів

### Варіант із повним `ProtocolSpec → lexer → parser → AST → IR → semantic validator → ExecutionPlan`

Архітектурно це найчистіша ціль. Він правильно формулює “runtime protocol as small language”, де model output лише пропонує, а validated `ExecutionPlan` мутує стан або запускає side effects. Там добре розведені `ProtocolSpec`, lexer/parser, AST, shape, IR, semantic validation, transaction plan, executor, recovery strategy і replay. 

Але як **наступний практичний refactor** це занадто великий ковток. Це план на кілька великих етапів, не на один “закрити старий шов”. Якщо його дати aider-у зараз, він може почати будувати нову імперію поверх старої, а не закривати міграційний борг.

### Варіант “MVP спочатку: TransitionSemanticValidator → semantic pass → plan-first bundle → recovery registry”

Це ближче до реального маршруту. Він добре виділяє MVP: спершу transition semantics, потім окремий semantic validator pass, потім bundle path як plan-first, потім recovery registry і regression coverage. 

Але я б не починав прямо з `TransitionSemanticValidator`, якщо твоя найближча мета саме “semantic runtime on compiler-based IR”. `TransitionSemanticValidator` важливий, але він уже ближче до policy/transition semantics. Перед ним треба оформити **semantic access layer**, щоб validators не продовжили читати суміш `segments`, `compiler_ir`, `has_action_segment`, `invalid_kind` і локальних helper-ів.

### Варіант “semantic extraction migration / adapter first”

Оце я вважаю найкращим наступним ходом. Він прямо потрапляє в твій поточний стан: structural diagnostics уже частково compiler-driven, але runtime semantic consumers ще змішані. План пропонує audit, adapter/snapshot, legacy fallback, shadow/parity, а вже потім consumer migration. 

Це і є правильний міст перед `history.py`.

---

# Рекомендований довгоживучий план

Я б назвав його:

```text
Semantic Runtime Migration Roadmap
Goal: move runtime semantic extraction from legacy parser fields toward compiler IR snapshots,
without giving compiler IR direct policy/dispatch authority.
```

## Phase 0. Freeze current boundary

**Status:** майже зроблено.

Зафіксовано:

```text
compiler metadata authority:
- error_code
- recovery_id
- invalid_kind

compatibility action proposal:
- parsed_action_count
- compiler_ir.action_ops
- legacy has_action_segment

not dispatch authority:
- RuntimeProtocolSemantics.has_action
- RuntimeProtocolSemantics.action_count
- ACTION_ONLY shape alone
```

Треба просто не розмивати цю межу.

---

## Phase 1. Semantic Access Layer, docs + tiny API design

**Мета:** створити офіційний словник і API-рамку, але ще не перемикати consumers.

Ключові поняття:

```text
compiler metadata authority
compatibility action proposal
dispatch-authoritative action
compiler-invalid safety state
runtime-owned policy
```

Майбутні accessor-и:

```python
get_compiler_metadata(parsed_output)
has_any_action_proposal_compat(parsed_output, parsed_action_count)
has_compiler_ir_action_ops(parsed_output)
is_compiler_invalid(parsed_output)
is_compiler_invalid_with_legacy_action(parsed_output, parsed_action_count)
is_dispatch_authoritative_action_shape(parsed_output)
```

Важливо: на цьому етапі **не міняти поведінку**.

---

## Phase 2. Inventory semantic consumers

**Мета:** знайти всіх читачів legacy/compiler semantic fields.

Шукати:

```text
has_action_segment
action_segments
parsed_action_count
compiler_ir
action_ops
visible_text
visible_answer
intent_payload
memory_update_done
subgoal
file_content
effects_preview
is_plaintext_answer_path
has_any_action_proposal
```

Класифікувати кожен consumer:

```text
A. metadata / diagnostics
B. compatibility action proposal
C. recovery evidence
D. dispatch authority
E. runtime policy
F. final-answer/plaintext guard
G. memory/subgoal/checkpoint policy
```

Вихідний artifact: таблиця в docs.

---

## Phase 3. Implement semantic accessor module, no consumer migration

Ось тут уже можна код, але дуже малий.

Наприклад:

```text
modules/agent/orchestration/responses/runtime_semantic_access.py
```

або якщо хочеш не множити файли:

```text
modules/agent/orchestration/responses/response_semantics.py
```

Я б радив окремий файл, бо це “міст”, не legacy semantics.

Мінімальні functions:

```python
def compiler_metadata(parsed_output) -> dict: ...
def has_compiler_ir_action_ops(parsed_output) -> bool: ...
def has_any_action_proposal_compat(parsed_output, parsed_action_count: int = 0) -> bool: ...
def is_compiler_invalid(parsed_output) -> bool: ...
def is_compiler_invalid_with_legacy_action(parsed_output, parsed_action_count: int = 0) -> bool: ...
```

Тести мають покрити:

```text
compiler valid action
compiler invalid with legacy action-like segment
legacy-only action segment
parsed_action_count > 0
no action
```

Це ще не runtime migration. Це просто “офіційний мультиметр”.

---

## Phase 4. Replace duplicate reads with accessors, behavior-preserving

Тільки там, де вже існує така сама логіка.

Наприклад:

```python
ResponseSemantics.has_any_action_proposal
```

може делегувати до:

```python
has_any_action_proposal_compat(...)
```

але expected behavior має лишитись:

```text
parsed_action_count > 0
OR compiler_ir.action_ops
OR has_action_segment
```

Не чіпати:

```text
ActionPolicy dispatch
ExecutionPlan
output recovery decisions
formal intent gate
memory/subgoal validation
```

Це хороший “MVP close”: legacy scattered reads стають wrapped, але authority не змінюється.

---

## Phase 5. TransitionSemanticValidator design/implementation

Ось тут уже варіант із `TransitionSemanticValidator` стає правильним наступним шматком. 

Мета:

```text
accepted/rejected transition/followup rules → один typed validator result
```

Покрити typed result-ами:

```text
accepted_without_followup
accepted_with_action
accepted_with_plaintext
followup_conflict
transition_only_violation
reuse_only_violation
rejected_reuse_without_active
rejected_redundant_reactivation
terminal_repeated_transition_defect
```

Це вже semantic validation, але scoped.

---

## Phase 6. Bundle semantic validation pass

Після transition validator:

```text
validate_bundle_shape(ir, state)
validate_action_allowed(ir, state)
validate_file_content_pairing(ir, state)
validate_completion_followup(ir, state)
```

Ще не executor rewrite. Просто pure-ish validators.

---

## Phase 7. Plan-first bundle execution

Оце перший великий runtime contract shift:

```text
IR / validated proposal
→ ExecutionPlan
→ ExecutionCommit
```

Тут уже важливі invariants:

```text
invalid bundle -> no transition, no dispatch
rejected intent -> active intent unchanged
valid bundle -> exactly one transition/action flow
```

Це не варто починати, поки semantic access layer і validators не стабілізовані.

---

## Phase 8. RecoveryStrategy registry expansion

Після typed semantic errors:

```text
ErrorValue / recovery_id -> RecoveryStrategy
```

Покрити:

```text
formal intent required
reuse without active
transition-only
followup conflict
completion with action
action array
mixed visible/control
unclosed think
```

Це прибирає “wrong root cause recovery”.

---

## Phase 9. Observability/replay artifact

Потім:

```text
tokens
AST
shape
IR
semantic result
ExecutionPlan
ExecutionCommit
```

Це вже для довгого debug-майбутнього.

---

## Phase 10. Legacy cleanup

Тільки після попередніх фаз:

```text
raw regex helpers
invalid_kind-first branches
has_action_segment direct reads
recent_problem_actions residues
legacy segments as primary source
```

Для кожного:

```text
migrated
intentional fallback
runtime-owned, do not migrate
```

---

# Що я б НЕ робив зараз

Не починав би одразу з повного `ProtocolSpec`/lexer/parser rewrite. Це стратегічно правильно, але тактично небезпечно. У тебе вже є compiler pipeline, RPS, tests, recovery registry шматками. Повний “Phase -1 → Phase 16” варто тримати як **North Star**, але не як найближчий execution plan. 

Не мігрував би `RuntimeProtocolSemantics.has_action/action_count` у dispatch або policy.

Не чіпав би `history.py`, поки semantic access layer не має чітких names/authority boundaries.

---

# Найближчий конкретний наступний крок

Я б зробив **Phase 1–2 одним docs-only/audit завданням**, а потім **Phase 3 маленьким code step**.

Ось prompt для aider на перший крок:

```text
Create a long-lived Semantic Runtime Migration roadmap and consumer inventory.

Context:
Project: Angelica AI.

We are closing the old protocol/runtime semantic migration before starting a large history.py refactor.

Current state:
- ProtocolCompiler and RuntimeProtocolSemantics exist.
- Output recovery compiler metadata reads are centralized for error_code/recovery_id/invalid_kind.
- ResponseSemantics.has_any_action_proposal may use parsed_action_count, compiler_ir.action_ops, or legacy has_action_segment.
- RuntimeProtocolSemantics.has_action/action_count are not dispatch-authoritative.
- Compiler-invalid responses may intentionally disagree with legacy action detection:
  compiler/RPS: INVALID, action_count=0, has_action=False
  legacy: has_action_segment=True or parsed_action_count>0
- This mismatch is recovery evidence, not dispatch permission.

Goal:
Add a durable roadmap and inventory for migrating runtime semantic extraction toward compiler IR / semantic accessors.

Docs/audit only.
Do not change production code.
Do not change tests.
Do not migrate consumers yet.

Relevant files:
- docs/architecture/response_protocol.md
- modules/agent/orchestration/responses/response_semantics.py
- modules/agent/orchestration/responses/runtime_protocol_semantics.py
- modules/agent/orchestration/responses/response_pipeline_prevalidation.py
- modules/agent/orchestration/responses/response_pipeline_stages.py
- modules/agent/orchestration/responses/output_recovery.py
- modules/agent/orchestration/responses/output_recovery_routing.py
- modules/agent/orchestration/runtime/action_policy.py
- modules/agent/orchestration/runtime/dispatch_pipeline.py
- tests/test_response_semantics.py
- tests/test_runtime_protocol_semantics.py
- tests/test_response_pipeline_refactor.py
- tests/test_response_guards.py
- tests/test_protocol_compiler_runtime_integration.py

Search for:
- has_action_segment
- parsed_action_count
- action_segments
- compiler_ir
- action_ops
- visible_text
- visible_answer
- intent_payload
- memory_update_done
- subgoal
- file_content
- effects_preview
- has_any_action_proposal
- is_plaintext_answer_path
