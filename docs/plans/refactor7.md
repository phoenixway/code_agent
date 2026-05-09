Ось моя рекомендована **подальша дорожня карта рефакторингу** після поточного стану:

```text
Current completed state:
- Terminal Answers slice: closed for now.
- Plan-First dispatch-boundary preparation slice: closed for now.
- Dispatch remains segment-driven.
- PlanDispatchCandidate and ExecutionPlan metadata are diagnostic-only.
- Final-answer / stop-gate migration deferred.
- Candidate-driven dispatch / synthetic segment adapter deferred.
```

## 1. Board / Checkpoint Consumer Slice

### Phase 10 Step 1: Board/Checkpoint Consumer Slice Preflight

**Мета:** інвентаризувати всі board/checkpoint consumers і зрозуміти, які з них можна мігрувати вузько й без зміни поведінки.

Scope:

* `PlanBoardStageHandler`
* `MemoryBoardStageHandler`
* `CHECKPOINT_WITH_VISIBLE_TEXT`
* `CHECKPOINT_ONLY`
* memory/subgoal/finding/fact/decision/progress/preference/path tags
* current checkpoint routing / recovery / continuation behavior

Forbidden:

* no dispatch changes
* no final-answer changes
* no stop-gate changes
* no ActionPolicy changes
* no parser rewrite

**Очікуваний результат:** список consumers + risk matrix + перший вузький кандидат.

---

### Phase 10 Step 2: Board/Checkpoint Characterization Tests

**Мета:** зафіксувати поточну поведінку перед міграцією.

Tests:

* checkpoint-only response
* checkpoint + visible text
* checkpoint + action
* board tags before/after action
* malformed checkpoint cases
* memory/subgoal mixed tags
* no behavior drift in recovery/continue/dispatch decisions

**Без production code**, тільки tests + docs.

---

### Phase 10 Step 3: First Board/Checkpoint Consumer Migration Design + Implementation

Тут можна вже об’єднати design + implementation, якщо preflight показує низький ризик.

Ймовірний перший кандидат:

```text
CHECKPOINT_ONLY або CHECKPOINT_WITH_VISIBLE_TEXT
```

Правило:

* typed/classified semantic result can be primary signal
* legacy path remains fallback
* no new behavior
* no board policy authority expansion

---

## 2. Board / Checkpoint Slice Closure

### Phase 10 Step 4: Board/Checkpoint Migration Review

**Мета:** вирішити, чи можна мігрувати ще один consumer або краще закрити slice.

Можливі висновки:

* close board/checkpoint slice after 1–2 safe migrations
* defer complex board policy paths
* document remaining risks

Я б не намагався одразу “вичистити все”, якщо починаються policy/authority edges.

---

## 3. Final Answer / Plaintext Path Preflight

### Phase 11 Step 1: Final Answer Authority Preflight

Це найризикованіший блок. Його не треба чіпати до завершення Board/Checkpoint.

Scope:

* `PLAINTEXT_TERMINAL_ANSWER`
* `ResponseSemantics.is_plaintext_answer_path`
* intent completion finalization
* `terminal_plaintext_completion_pending`
* missing action / missing answer recovery
* stop/continue behavior

Expected likely conclusion:

```text
No direct migration yet.
Need separate FinalAnswerPolicy / StopGate design.
```

Тут не можна просто замінити legacy checks на `TerminalAnswerClassifier`, бо classifier структурний, а final-answer path — policy/authority.

---

## 4. Final Answer Policy Extraction

### Phase 11 Step 2: FinalAnswerPolicy Design

**Мета:** відділити:

```text
structural terminal answer classification
```

від:

```text
is this response sufficient to complete/stop/finalize intent?
```

Можливий новий компонент:

```python
FinalAnswerPolicy
```

Inputs:

* `TerminalAnswerSemanticResult`
* intent state
* active intent
* visible text
* action count
* recovery state
* stop reason
* terminal completion pending state

Output:

```python
FinalAnswerDecision
```

але це краще робити тільки після preflight.

---

## 5. Plan-First Dispatch Continuation

Повернутися до Plan-First варто пізніше.

### Phase 12 Step 1: Side-Effect Boundary Preflight

Не implementation. Тільки review:

* чи можна synthetic segment adapter?
* чи можна direct candidate dispatch?
* що робити з `processed_segs`?
* як не зламати `DispatchOutcomeHandler`?
* як `ExecutionCommit` буде рахувати committed actions?

Expected likely result:

```text
Need DispatchInput / DispatchCommit contract before candidate-driven dispatch.
```

---

### Phase 12 Step 2: DispatchInput Contract Design

Можливий новий контракт:

```python
DispatchInput
```

який може бути побудований з:

* legacy segments
* plan candidate
* synthetic compatibility segment

Але dispatcher side effects мають лишатися однаковими.

---

## 6. Cleanup / Legacy Fallback Retirement

Це тільки після кількох стабільних міграцій.

### Phase 13: Fallback Retirement Review

Candidates:

* leaked-system-result fallback
* truncated terminal fallback
* internal-summary fallback
* board/checkpoint fallback
* plan-first metadata fallback

Правило:

```text
No fallback removal unless exact parity is proven by tests and logs.
```

---

# Рекомендований найближчий план

Я б робив так:

```text
Phase 10 Step 1: Board/Checkpoint Consumer Slice Preflight
Phase 10 Step 2: Board/Checkpoint Characterization Tests
Phase 10 Step 3: First Board/Checkpoint Consumer Migration
Phase 10 Step 4: Board/Checkpoint Slice Review / Closure

Phase 11 Step 1: Final Answer Authority Preflight
Phase 11 Step 2: FinalAnswerPolicy Design, if needed

Phase 12 Step 1: Plan-First Side-Effect Boundary Preflight
Phase 12 Step 2: DispatchInput Contract Design

Phase 13: Legacy Fallback Retirement Review
```

Мій головний принцип далі: **не відкривати одночасно final-answer і dispatch side-effect boundary**. Це дві найнебезпечніші зони. Спочатку краще закрити Board/Checkpoint, бо це логічний deferred slice і він менш токсичний.
