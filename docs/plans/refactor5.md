Далі я б ішов **не в код**, а в дуже контрольований перехід: спочатку закрити governance docs, потім зробити точний inventory, і тільки потім маленький accessor-module step. Інакше можна знову розбудити рефакторингового кракена 🦑.

## 0. Спочатку закрити Governance Phase 1

Тобто той prompt для aider, який я дав вище: **вирівняти docs між собою**.

Ціль: щоб `current-refactor-state.md`, `semantic-runtime-roadmap.md`, `constitution`, `stop-lines`, `test-contracts` казали одну й ту саму правду.

Після цього в тебе має бути стабільний “командний пункт”:

```text
Governance docs aligned
→ current state true
→ stop lines complete
→ next phase explicitly named
→ no code touched
```

Це важливо, бо зараз `current-refactor-state.md` ще каже, що активна фаза це Phase 1 design, тоді як фактичний стан уже далі: Phase 3A закрита, Phase 3B-pre design boundary є, і активна робота зараз governance/docs-only. 

---

## 1. Потім Phase 3B-Inventory: Consumer Inventory, але вже дуже практичний

Наступний реальний крок після governance:

```text
Phase 3B-Inventory:
Find every consumer of response semantics and classify it.
No behavior change.
Mostly docs + maybe comments only.
```

Треба не “рефакторити”, а скласти таблицю:

```text
Consumer
File/function
Current source
Semantic meaning
Authority class
Future accessor
Risk
Migration allowed now?
```

Шукати в коді такі речі:

```text
has_any_action_proposal
has_action_segment
parsed_action_count
compiler_ir
action_ops
RuntimeProtocolSemantics.has_action
RuntimeProtocolSemantics.action_count
invalid_kind
visible_text
is_plaintext_answer_path
memory_update_done
subgoal
file_content
```

Класифікація має бути така:

```text
A. compiler metadata
B. compatibility action proposal
C. recovery evidence
D. dispatch authority
E. runtime policy
F. final-answer/plaintext guard
G. memory/subgoal/checkpoint policy
```

Особливо треба відмітити небезпечні місця, де хтось може випадково подумати:

```text
RPS.has_action == можна dispatch
```

А це заборонено. `RPS.has_action/action_count` є structural facts, не dispatch authority. 

---

## 2. Після inventory: Phase 3B-API Design

Тільки коли видно всіх consumers, тоді оформити мінімальний API.

Я б не робив великий semantic framework. Перший набір має бути скромний, як кишеньовий мультиметр:

```python
get_compiler_metadata(parsed_output)

has_any_action_proposal_compat(parsed_output, parsed_action_count=0)

has_compiler_ir_action_ops(parsed_output)

is_compiler_invalid(parsed_output)

is_compiler_invalid_with_legacy_action(parsed_output, parsed_action_count=0)

is_dispatch_candidate_shape(parsed_output)
```

Але назви треба підбирати обережно.

Особливо:

```python
is_dispatch_candidate_shape(...)
```

має означати лише:

```text
shape can enter runtime dispatch checks
```

а не:

```text
dispatch allowed
```

Бо `compiler_shape == ACTION_ONLY` сам по собі не permission. Це прямо зафіксовано в stop-lines. 

---

## 3. Потім Phase 3B-Implementation: Accessor module, no consumer migration

Оце перший маленький code step.

Створити, наприклад:

```text
modules/agent/orchestration/responses/semantic_accessors.py
```

Або, якщо хочеш обережніше:

```text
modules/agent/orchestration/responses/runtime_semantic_access.py
```

Я б вибрав **`semantic_accessors.py`**, бо воно коротке й ясно.

Дозволено:

```text
- add module
- add unit tests
- no existing consumer migration
- no behavior change
```

Тести мають бити саме по небезпечних розгалуженнях:

```text
1. compiler-valid action
2. compiler INVALID + legacy action-like segment
3. compiler_ir.action_ops without legacy segment
4. parsed_action_count > 0
5. legacy has_action_segment only
6. no action
```

Тут критичний тест-контракт: `compiler_ir.action_ops` мусить лишатися compatibility action proposal, бо вже є тести, які це захищають. 

---

## 4. Потім Phase 3B-Wrap: замінити дубльовані checks на accessors

Тільки після тестів accessor-ів.

Мінімальний перший consumer:

```text
ResponseSemantics.has_any_action_proposal
```

Його можна зробити thin wrapper над новим accessor-ом, але behavior must stay identical:

```text
parsed_action_count > 0
OR compiler_ir.action_ops
OR legacy has_action_segment
```

Це не дає dispatch permission. Це тільки compatibility detection.

Це буде гарний “закритий шов”: старий helper лишається API-сумісним, але логіка стає канонічною і тестованою.

---

## 5. Тільки потім TransitionSemanticValidator

Ось після цього вже варто брати:

```text
TransitionSemanticValidator
```

До цього моменту він не буде читати хаотичну суміш `segments`, `compiler_ir`, `visible_text`, regex-helper-ів і локальних умов. Він буде опиратися на semantic access layer.

Це важливий порядок:

```text
не validator → accessor
а accessor → validator
```

Інакше validator народиться з тими самими старими нутрощами, просто в новій коробці.

---

# Мій рекомендований маршрут на кілька днів

```text
1. Governance docs alignment
2. Consumer inventory
3. Semantic accessor API design
4. Accessor module + tests, no consumer migration
5. Wrap ResponseSemantics.has_any_action_proposal
6. Then TransitionSemanticValidator design
```

Найближчий наступний prompt для aider має бути **не про код**, а про inventory:

```text
Task:
Create a precise semantic consumer inventory for the response protocol/runtime pipeline.

Phase:
Phase 3B-Inventory.

Task type:
docs-only / audit-only.

Allowed files:
- docs/architecture/semantic-runtime-roadmap.md
- docs/architecture/current-refactor-state.md
- docs/architecture/protocol-authority-boundaries.md
- docs/architecture/test-contracts.md
- docs/architecture/refactor-stop-lines.md

Read-only context files to inspect:
- modules/agent/orchestration/responses/response_semantics.py
- modules/agent/orchestration/responses/runtime_protocol_semantics.py
- modules/agent/orchestration/responses/response_pipeline_stages.py
- modules/agent/orchestration/responses/response_pipeline_prevalidation.py
- modules/agent/orchestration/responses/output_recovery.py
- modules/agent/orchestration/responses/output_recovery_routing.py
- modules/agent/orchestration/intent_transition_routing.py
- modules/agent/orchestration/runtime/action_policy.py
- modules/agent/orchestration/dispatch_pipeline.py

Forbidden:
- Do not change production code.
- Do not change tests.
- Do not migrate any consumer.
- Do not implement semantic accessors.
- Do not change runtime behavior.
- Do not treat RuntimeProtocolSemantics.has_action/action_count as dispatch-authoritative.
- Do not remove compiler_ir.action_ops fallback from has_any_action_proposal.
- Do not start history.py refactor.

Goal:
Add a consumer inventory table documenting every place that consumes response semantics.

For each consumer, record:
- file/function;
- current source:
  - ParsedModelOutput field
  - ResponseSemantics helper
  - compiler_ir
  - RuntimeProtocolSemantics
  - raw response text / regex
  - runtime state
- semantic meaning:
  - compiler metadata
  - compatibility action proposal
  - recovery evidence
  - dispatch authority
  - runtime policy
  - final-answer/plaintext guard
  - memory/subgoal/checkpoint policy
- future accessor candidate;
- migration risk;
- whether migration is allowed in the next implementation phase.

Important authority rules:
- compiler INVALID responses never dispatch actions;
- legacy action-like content in compiler INVALID responses is recovery evidence only;
- RuntimeProtocolSemantics.has_action/action_count are not dispatch-authoritative;
- ResponseSemantics.has_any_action_proposal is compatibility detection, not dispatch permission;
- compiler_ir.action_ops fallback in has_any_action_proposal is protected;
- ActionPolicy and dispatch remain runtime-owned.

Expected output:
- Documentation-only diff.
- Updated roadmap/current-state if needed.
- No production behavior change.
```

Моя головна думка: **далі треба не ще один великий “розумний рефакторинг”, а каталогізація consumers.** Це як перед операцією: не різати, поки на карті не підписані судини.
