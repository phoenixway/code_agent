Так. Ось стратегія, як **прибрати або сильно зменшити другий контур керування** без того, щоб розвалити агент на шматки.

## Суть проблеми

Зараз у тебе є два керуючі шари:

### Контур 1. Intent-driven

Він уже досить сильний:

* `active_intent`
* `intent_type`
* `allowed_actions`
* `safe_steps_limit`
* `retry_limit`
* intent-aware recovery / prompting / transitions.

### Контур 2. State-machine heuristic-driven

Він теж реально керує поведінкою:

* `task_kind`
* `mode`
* `_observe_budget()`
* `_read_only_limit()`
* `pre_action_policy()` / `decide()`
* fallback logic у recovery/completion.

Проблема не в тому, що другий контур зовсім безкорисний. Проблема в тому, що він:

* частково дублює перший,
* не є настільки надійним,
* але при цьому все ще може впливати на критичні рішення.

Це як мати двох штурманів у машині, де один бачить реальну карту, а другий часом ворожить по хмарах ☁️

---

# Ціль

Не “видалити все зі state machine”.

А зробити так:

**Intent contract керує роботою.
State machine лише страхує, діагностує і ловить цикли.**

Тобто другий контур має перейти з ролі:

* “співкерівник поведінки”

у роль:

* “guardrail / diagnostics / fallback”

---

# Стратегія

## Етап 1. Забрати у другого контуру право визначати тип поточної роботи під час active intent

### Ціль

Під час активного контракту рішення про:

* modify vs investigate
* completion style
* recovery style
* action expectations

мають братися **з `active_intent_type`**, а не з `task_kind`.

### Практично це означає

У всіх critical decision points має бути правило:

`ACTIVE INTENT > LAST COMPLETED INTENT > TASK KIND`

Зараз це вже частково порушено, зокрема в `output_recovery.py`, де `_is_modify_context()` дивиться і на `task_kind`, і через це modify-validator стріляє хибно. 

### Результат етапу

Другий контур перестає конкурувати з активним контрактом у найнебезпечніших місцях.

---

## Етап 2. Перетворити `task_kind` на bootstrap/fallback, а не на глобальну істину

### Ціль

`task_kind` лишається лише для випадків:

* на старті turn, коли intent ще не активований
* коли треба мати грубий initial mode
* коли active intent узагалі відсутній

### Що це дає

Навіть якщо `_classify_task_kind()` помилиться, помилка не полетить у completion validators, recovery branches і contract-aware flows.

### Практична політика

* `task_kind` дозволено використовувати:

  * у `start_turn()`
  * у heuristic diagnostics
  * у fallback flows when no active intent exists
* `task_kind` заборонено використовувати:

  * як authoritative source для modify context при active intent
  * для contract-aware completion choice
  * для validators, що можуть розвернути behavior loop

---

## Етап 3. Від’єднати budgets від “типу задачі” настільки, наскільки це можливо

Ось тут найтонше місце.

Зараз `task_kind` впливає на:

* `_observe_budget()`
* `mode`
* `_read_only_limit()`
* далі на `pre_action_policy()` через state machine.

### Проблема

Це означає, що heuristic detector уже не просто “підказує”, а реально задає ритм і терпимість до read-only exploration.

### Мета

Поступово перейти від:

* **task-type-based budgets**

до:

* **intent-type-based budgets**
  або навіть
* **contract metadata-based budgets**

### Краща майбутня модель

Наприклад:

* `INVESTIGATE` → один budget profile
* `MODIFY` → інший
* `VERIFY` → інший
* `SUMMARIZE` → інший

Тобто не state machine вгадує режим по user_input, а active contract прямо приносить режим із собою.

---

## Етап 4. Спрощення ролі `WorkMode`

### Що з ним зараз

`mode = RESEARCH` або `IMPLEMENT` виводиться з `task_kind`. 

### Питання

Чи справді тобі потрібен окремий `WorkMode`, якщо вже є:

* `intent_type`
* `allowed_actions`
* `safe_steps_limit`
* retry state
* recovery state

### Моя оцінка

`WorkMode` може лишитися, але:

* або як derived convenience label,
* або як purely diagnostic field.

А не як ще один майже-нормативний шар, який штовхає policy engine.

### Ціль на потім

Або:

* прибрати `WorkMode` зовсім,
* або робити його **derived from active intent type**, а не from heuristic `task_kind`.

---

## Етап 5. Звести `pre_action_policy()` до анти-лупа і safety, а не до другого мозку

### Що має лишитися в state machine / policy engine

Корисні речі:

* anti-loop
* stagnation detection
* repeated action cycle detection
* reread pathologies
* broad recon overuse
* batch sanity
* maybe session-level fatigue signals

Це справді потрібні речі. Вони не дублюють intent contract, а страхують його.

### Що треба прибирати з другого контуру

Менш корисні речі:

* самостійне “вгадування”, investigate це чи modify, коли active intent уже існує
* повторне визначення completion style
* modify-vs-inspect gating поверх accepted contract
* heuristic preemption of contract truth

---

# План робіт

## Фаза A. Stabilize without demolition

Це вже майже твій поточний напрям.

### Задачі

1. Усі critical decisions зробити contract-first:

   * output recovery
   * plain-text completion
   * completion validators
   * modify context detection

2. `task_kind` лишити fallback only

3. Зібрати debug traces:

   * source of truth for current work type
   * active intent type
   * task kind
   * which source was used for decision

### Критерій успіху

У trace більше не буває ситуації:

* active intent = INVESTIGATE
* а validator/recovery працює як MODIFY

---

## Фаза B. Intent-aware budgets

### Задачі

1. Виділити всі місця, де `task_kind` впливає на budgets

2. Ввести intent-based equivalents:

   * `INTENT_OBSERVE_BUDGETS`
   * `INTENT_READ_ONLY_LIMITS`
   * maybe `INTENT_STAGNATION_LIMITS`

3. Якщо active intent є:

   * budget брати з intent type

4. Якщо intent нема:

   * fallback на heuristic task kind

### Критерій успіху

State machine більше не визначає exploration tolerance через грубу класифікацію запиту, коли вже є formal contract.

---

## Фаза C. Shrink `WorkMode`

### Задачі

1. Знайти всі місця використання `mode`

2. Розділити їх на:

   * purely diagnostic
   * behavior-changing

3. Behavior-changing usage:

   * перевести на intent-based rule
   * або прибрати

4. Diagnostic usage:

   * можна залишити

### Критерій успіху

`WorkMode` або стає derived cosmetic label, або зникає без функціонального болю.

---

## Фаза D. Thin state machine

### Задачі

Залишити state machine як:

* anti-loop controller
* stagnation detector
* safety and repetition monitor

Прибрати роль:

* secondary task arbiter
* secondary behavior policy authority

### Критерій успіху

State machine уже не може самостійно переодягнути task у неправильний костюм, але все ще вміє зупинити модель, якщо вона починає гризти той самий кабель тричі.

---

# Практичний порядок виконання

Я б робив ось так:

### Крок 1

Завершити contract-first changes у critical branches
Це найменш ризиковано і вже дає великий виграш.

### Крок 2

Додати observability
Логувати:

* `active_intent_type`
* `task_kind`
* `decision_type_source` = `active_intent | last_completed_intent | task_kind`
* `completion_mode_source`

Без цього далі буде важко ловити привидів.

### Крок 3

Inventory usages
Зробити список:

* де використовується `task_kind`
* де використовується `mode`
* де використовуються `_observe_budget()` і `_read_only_limit()`
* які з цих usage реально behavior-changing

### Крок 4

Перевести budgets на intent-aware model
Спершу паралельно:

* старий heuristic path
* новий intent-aware path
* feature flag або switch

### Крок 5

Після стабілізації видалити heuristic authority
Коли intent-aware path підтвердиться на практиці, можна:

* спростити `_classify_task_kind()`
* зменшити роль `mode`
* прибрати зайві branches

---

# Принципи, щоб не зламати систему

## 1. Не робити великого знесення без traceability

Кожен зріз другого контуру має супроводжуватись:

* логами
* зрозумілим fallback
* чітким критерієм успіху

## 2. Не вбивати anti-loop захист

Другий контур шкідливий не весь.
Його найцінніша частина це саме:

* anti-loop
* anti-reread
* broad recon control
* stagnation alarms

Оце треба зберегти.

## 3. При active intent heuristic cannot outrank contract

Це головне правило.

## 4. Better one governor than two arguing governors

Краще один чіткий керуючий шар і один тонкий страховий, ніж два майже-рівноправні шари, які іноді тягнуть у різні боки.

---

# В одному абзаці

План такий: спершу зробити всі critical recovery/completion/output-рішення contract-first, щоб `active_intent_type` став головною правдою, а `task_kind` лишився лише fallback без права переважувати контракт. Потім поступово винести budgets і `WorkMode` з heuristic task classification у intent-aware модель, залишивши state machine тільки як anti-loop / stagnation / safety layer. Кінцева ціль не в тому, щоб “вбити state machine”, а в тому, щоб перетворити її з другого уряду на акуратну огорожу вздовж дороги.

Якщо хочеш, наступним кроком я можу зробити для цього окремий **технічний roadmap-документ** у твоєму стилі: з фазами, файлами, ризиками, критеріями готовності і порядком rollout.
