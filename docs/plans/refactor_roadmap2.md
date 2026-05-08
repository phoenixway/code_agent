Ось поточна дорожня карта по нашому refactor-ланцюгу, у стислому, але робочому форматі.

# Semantic Runtime Migration Roadmap

## Phase 1. Protocol / compiler foundation

**Ціль:** зробити response protocol не regex-магією, а структурною моделлю.

Сенс фази:

```text
raw model output
→ protocol parser / compiler
→ compiler_ir / semantic facts
→ runtime decisions
```

Типові артефакти:

```text
ProtocolCompiler
RuntimeProtocolSemantics
compiler_ir
protocol authority boundaries
test contracts
```

Статус у нашому ланцюгу: **вже пройдена/фундамент закладено**.

---

## Phase 2. Semantic accessors foundation

**Ціль:** прибрати пряме читання legacy `ParsedModelOutput`, regex-fields, `segments`, `compiler_ir` з різних consumers через єдиний accessor-шар.

Сенс:

```text
не: consumer сам копирсається в parsed_output
а: consumer питає semantic_accessors
```

Приклади accessor-напрямків:

```text
has_any_action_proposal_compat
get_action_ops
get_pre_action_text
get_compiler_metadata
has_substantial_think
is_leaked_system_result
```

Статус: **частково зроблено / accessor-wrapper шар працює**.

---

## Phase 3. Response semantics consumer migration

**Ціль:** переводити старі helpers у `ResponseSemantics` на semantic accessors без зміни behavior.

Приклад уже зробленого:

```text
ResponseSemantics.has_any_action_proposal
→ semantic_accessors.has_any_action_proposal_compat
```

Важливі правила:

```text
- behavior-preserving only
- no authority change
- no dispatch permission change
- no prompt/reason/source marker changes
```

Статус: **частково зроблено**.

---

## Phase 4. Semantic accessor expansion / API governance

**Ціль:** перед кожним новим accessor зробити design, approval, implementation, tests.

Приклади accessor-кандидатів:

```text
is_leaked_system_result(raw_response)
has_substantial_think(raw_response)
get_visible_text(raw_response)       # небезпечний, окрема фаза/дизайн
get_followup_surface(...)
```

Статус: **триває як governance-шар**.

---

# Phase 5. TransitionSemanticValidator

**Ціль:** винести transition/followup classification з `IntentTransitionHandler` / routing helpers у typed validator.

## Phase 5 Step 1. Scaffold

**Зроблено.**

Створено основу:

```text
TransitionSemanticValidator
TransitionValidationResult
TransitionResultKind
```

Без consumer migration.

---

## Phase 5 Step 2A. Structural followup classification

**Зроблено.**

Класифікації:

```text
NO_FOLLOWUP
FOLLOWUP_ACTION
FOLLOWUP_CONFLICT
```

Але на цьому етапі ще без runtime consumer migration.

---

## Phase 5 Step 2B. Context-sensitive transition violations

**Зроблено.**

Класифікації:

```text
TRANSITION_ONLY_VIOLATION
REUSE_ONLY_VIOLATION
COMPLETE_WITH_ACTION_VIOLATION
```

Без зміни старих helpers.

---

## Phase 5 Step 3. First consumer migration slice

**Зроблено.**

Мігрували через validator тільки recovery/violation cases:

```text
TRANSITION_ONLY_VIOLATION
REUSE_ONLY_VIOLATION
COMPLETE_WITH_ACTION_VIOLATION
FOLLOWUP_CONFLICT
```

Залишили fallback:

```text
NO_FOLLOWUP
FOLLOWUP_ACTION
FOLLOWUP_PLAINTEXT
UNKNOWN
```

---

## Phase 5 Step 4. Second consumer migration slice

**Зроблено.**

Мігрували:

```text
NO_FOLLOWUP
FOLLOWUP_ACTION
```

Зберегли legacy behavior:

```text
NO_FOLLOWUP:
- handled=True
- reason="intent_accepted_without_followup"
- state.note_intent_only_response()
- state_machine.intent_runtime sync

FOLLOWUP_ACTION:
- handled=False
- pass-through behavior
- no dispatch permission
```

---

## Phase 5 Boundary Review

**Зроблено. Phase 5 закрито.**

Залишено legacy fallback:

```text
FOLLOWUP_PLAINTEXT
UNKNOWN
```

Причина:

```text
FOLLOWUP_PLAINTEXT залежить від get_visible_text / final-answer / sufficiency semantics.
Це окрема печера, не частина TransitionSemanticValidator refactor.
```

Статус Phase 5:

```text
Complete with fallbacks
```

---

# Phase 6. BundleSemanticValidator

**Ціль:** створити typed validator для bundle / atomic bundle / compiler bundle evidence.

Головна межа:

```text
BundleSemanticValidator = structural classification evidence
не ActionPolicy
не DispatchPipeline
не recovery prompt generator
не state mutator
не dispatch permission
```

## Phase 6 Step 1. Scaffolding

**Зроблено.**

Створено:

```text
modules/agent/orchestration/responses/bundle_semantic_validator.py
tests/test_bundle_semantic_validator.py
```

Додано:

```text
BundleResultKind
BundleValidationResult
BundleSemanticValidator
validate(...) -> UNKNOWN
```

---

## Phase 6 Step 2A. Error-code-driven classification

**Зроблено.**

Мапінги:

```text
E_ATOMIC_BUNDLE_REQUIRES_EXACTLY_ONE_ACTION
+ invalid_kind=action_payload_array
→ INVALID_ACTION_ARRAY

E_ATOMIC_BUNDLE_REQUIRES_EXACTLY_ONE_ACTION
+ invalid_kind=multiple_actions
→ INVALID_MULTIPLE_ACTIONS

E_FILE_CONTENT_REQUIRES_ACTION
→ INVALID_FILE_CONTENT_PAIRING

E_FILE_CONTENT_ACTION_MISMATCH
→ INVALID_FILE_CONTENT_PAIRING
```

Залишено deferred:

```text
E_INTENT_COMPLETE_WITH_ACTION -> UNKNOWN
```

---

## Phase 6 Step 2B. Shape-driven classification

### Step 2B.1. `INTENT_ACTION_BUNDLE`

**Зроблено.**

```text
INTENT_ACTION_BUNDLE
→ INTENT_ACTION_BUNDLE_CANDIDATE
```

Не policy approval.

---

### Step 2B.2. `READ_ONLY_BATCH_CANDIDATE`

**Зроблено.**

```text
READ_ONLY_BATCH_CANDIDATE
→ READONLY_ACTION_BATCH_CANDIDATE
```

Критичне значення:

```text
це structural candidate only
не “batch безпечний”
не dispatch permission
ActionPolicy все ще вирішує safety
DispatchPipeline все ще виконує
```

---

### Step 2B.3. `INTENT_ONLY`

**Зроблено кодом, green tests. Docs-closure наступний.**

```text
INTENT_ONLY
→ NO_BUNDLE_SHAPE
```

Значення:

```text
compiler recognized non-bundle shape from approved subset
не final-answer signal
не sufficiency signal
не safety decision
не означає “нема control content взагалі”
не dispatch permission
```

Залишено `UNKNOWN`:

```text
ACTION_ONLY
PLAINTEXT_ONLY
INTENT_COMPLETE_WITH_TEXT
MEMORY_TEXT
PRE_ACTION_TEXT_AND_ACTION
unknown / ambiguous shapes
```

---

## Phase 6 Step 2C. Parity testing

**Наступний логічний етап. Ще не approved / не implemented.**

Ціль:

```text
довести, що BundleSemanticValidator classification відповідає existing compiler-driven prevalidation behavior
до будь-якої consumer migration
```

Можливі підкроки:

```text
Step 2C Design
Step 2C Approval
Step 2C Implementation:
- parity fixtures
- mapping tests
- compiler-output based tests
- no consumer migration
```

Критично:

```text
не імітувати legacy logic занадто широко
не створювати другу копію старої логіки
краще mapping tables + direct legacy helper/path where practical
```

---

## Phase 6 Step 3. First consumer migration

**Майбутній етап. Не approve-ити зараз.**

Найімовірніший перший consumer:

```text
ResponsePipelinePrevalidationMixin._reject_compiler_invalid_atomic_bundle_before_transition
```

Чому саме він:

```text
- already compiler-driven
- найнижчий ризик
- ближче до Step 2A mappings
```

Перший consumer slice має йти тільки після:

```text
Step 2C parity tests green
design approval
implementation approval
```

Заборони:

```text
- не мігрувати _reject_invalid_atomic_bundle_before_transition одразу
- не чіпати ActionPolicyHandler.validate_atomic_bundle_action
- не міняти prompts/reasons/source markers
- не міняти dispatch behavior
```

---

## Phase 6 Step 4+. ActionPolicy-adjacent bundle logic

**Далеке майбутнє / окремий design.**

Сюди належать:

```text
ActionPolicyHandler.validate_atomic_bundle_action
ActionPolicyHandler.decide read-only batch logic
runtime intent contract checks
segments-based checks
```

Це вже небезпечніша зона, бо там:

```text
policy
dispatch eligibility
read-only safety
runtime state
intent contract
```

Поки статус:

```text
deferred
separate design required
```

---

# Deferred / blocked dragons 🐉

## get_visible_text

Окрема майбутня фаза.

Не чіпати в Phase 6.

Пов’язано з:

```text
FOLLOWUP_PLAINTEXT
final-answer/sufficiency
visible-control boundary
plaintext completion
terminal answer guards
```

---

## FOLLOWUP_PLAINTEXT

Залишається legacy fallback.

Не мігрувати без `get_visible_text` design.

---

## INVALID_MIXED_VISIBLE_TEXT

Є тільки enum placeholder.

Не реалізовувати без окремого visible-text design.

---

## INVALID_INTENT_COMPLETE_WITH_ACTION

Deferred / cross-phase overlap.

Причина:

```text
торкається intent completion semantics
уже було близько до Phase 5 transition logic
не чистий bundle-shape case
```

---

## ACTION_ONLY

Залишається `UNKNOWN`.

Причина:

```text
не bundle, але action-bearing/control-bearing
не можна зливати в NO_BUNDLE_SHAPE без окремого approval
```

---

# Поточний найкоротший стан

```text
Phase 5: complete with fallbacks

Phase 6:
- Step 1 scaffold: done
- Step 2A error-code classification: done
- Step 2B.1 INTENT_ACTION_BUNDLE: done
- Step 2B.2 READ_ONLY_BATCH_CANDIDATE: done
- Step 2B.3 INTENT_ONLY -> NO_BUNDLE_SHAPE: code done, tests green, docs closure next
- Step 2C parity testing: next design phase
- Step 3 consumer migration: not yet
```

# Найближчі 3 дії

```text
1. Docs-closure для Phase 6 Step 2B.3.
2. Design Phase 6 Step 2C parity testing.
3. Лише після parity: design першої consumer migration для _reject_compiler_invalid_atomic_bundle_before_transition.
```

Метафора стану: ми вже зібрали семантичний компас і відкалібрували стрілки. Але ще не варто віддавати йому кермо корабля. Спершу порівняти з мапою старого штурмана.
