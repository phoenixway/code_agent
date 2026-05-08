Я б **не дозволяв action-before-intent зараз**. Навіть якщо логічно іноді “нешкідливо”, архітектурно це відкриє занадто багато дверей саме в найчутливішому місці.

### Action before intent

На вигляд:

```xml
<action>...</action><intent mode="activate">...</intent>
```

можна трактувати як “спершу дія, потім пояснив контракт”. Але для runtime це поганий порядок, бо intent contract має бути відомий **до** action-policy check.

Інакше виникає питання: під яким intent перевіряти дію?

* під старим active intent?
* під новим intent, який стоїть після action?
* як atomic bundle?
* чи intent застосовується до наступного turn, а action до поточного?

Це вже не compiler facts. Це runtime policy semantics.

Тому моя рекомендація:

```text
intent before action is the only valid atomic bundle order.
action before intent remains INVALID.
```

Впровадити “нешкідливий порядок” технічно не дуже складно в parser/classifier, але **дорого в policy**. Треба буде змінювати:

* `IntentTransitionHandler`;
* atomic bundle prevalidation;
* `ActionPolicyHandler.validate_atomic_bundle_action`;
* recovery wording;
* tests for intent/action atomicity;
* possibly trace semantics;
* docs around transition application order.

Тобто це вже не Step 4E. Це окрема фаза.

### Checkpoint-only / board-only

Тут інша ситуація. Я б **логічно дозволив checkpoint-only як structural output**, але не вводив би нову terminal/dispatch semantics зараз.

Тобто:

```xml
<fact>...</fact>
<memory_update_done />
<subgoal ...>...</subgoal>
```

може бути compiler-recognized. Але питання “що runtime робить із таким turn?” має залишатися в existing board stages / runtime policy.

Тут безпечна модель така:

```text
board-only is structurally recognized, but not a final answer and not dispatch.
```

І це якраз те, що ми зараз робимо через facts-first:

* compiler бачить tags;
* RPS показує facts;
* consumers ще не мігруються;
* board-only shape taxonomy відкладається.

### Чому не варто зараз “покращувати старий протокол”

Бо Step 4E — це не новий protocol design. Це refactor substrate: дати runtime чисті structural facts, щоб потім уже можна було спокійно вирішувати semantics.

Якщо зараз одночасно:

* додати facts;
* дозволити action-before-intent;
* зробити checkpoint-only valid shape;
* змінити terminal behavior;

то ми не зрозуміємо, що зламалось: parser, classifier, runtime policy, board stage чи terminal answer classifier.

### Як я бачу правильну чергу

1. **Закрити Step 4E facts-first**

   * без нових policy meanings;
   * без action-before-intent;
   * без board-only shapes;
   * full suite green.

2. **Step 4F shadow sufficiency**

   * довести, що facts достатні для майбутнього classifier.

3. **TerminalAnswerClassifier shadow mode**

   * ще без consumer migration.

4. **Окрема mini-phase: protocol grammar cleanup**
   Тут можна розглянути:

   * чи потрібен `CHECKPOINT_ONLY`;
   * чи board-only should be valid shape;
   * чи inline subgoal в prose structural or literal;
   * чи action-before-intent має бути allowed/deprecated/invalid.

### Моя позиція

* **Action-before-intent:** лишити invalid. Не чіпати зараз.
* **Checkpoint-only:** compiler-visible facts так, новий valid shape ні.
* **Old protocol cleanup:** так, але після Step 4E, окремо.
* **Inline protocol tags inside prose:** краще вважати literal/plaintext, якщо вони не стоять як standalone protocol blocks. Це безпечніше.

Коротко: **старий протокол проблемний, але Step 4E має бути “очі, не воля”.** Спочатку дати системі бачити структуру, потім окремо вирішувати, які нові порядки чи shapes легалізувати.
