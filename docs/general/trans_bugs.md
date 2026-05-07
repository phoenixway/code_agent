
› що треба зробити щоб адресувати проблеми в дампі?


• Щоб адресувати проблеми в цьому дампі, я б ішов у такому порядку.

  1. Зробити transition boundary жорстким і однозначним
  Зараз найбільше шуму виникає саме на межі INVESTIGATE -> MODIFY.

  Що треба:

  - Дозволити runtime обробляти intent-transition як окремий крок стану, а не як “ще один шматок тексту в загальному
    response”.
  - Після complete + activate не намагатися в тому ж самому response ще й виконати action, якщо цей шлях нестабільний.
  - Визначити одне правило:
      - або дозволений complete + activate + action і це гарантовано підтримується пайплайном,
      - або після успішного transition runtime завжди просить наступний valid output окремим кроком.

  Моя думка: другий варіант чистіший і надійніший.

  2. Прибрати structural ambiguity для intent-only responses
  У дампі двічі видно проблему типу:

  - intent був валідний,
  - але не було next action / answer,
  - і пайплайн пішов у missing_action_or_answer.

  Що треба:

  - Явно класифікувати intent_only_without_next_step як окремий defect.
  - Для нього давати дуже конкретний recovery:
      - якщо intent щойно accepted/applied, не просити модель “подумати ще раз загалом”;
      - просити тільки next valid output under current contract.
  - Не змішувати цей кейс із загальним missing_action_or_answer, бо тут стан уже змінився.

  3. Зробити lifecycle контракту видимим у trace як typed events
  Зараз по дампу важко відрізнити:

  - completion accepted,
  - completion emitted but ignored,
  - completion accepted and then new contract opened,
  - completion accepted but user started follow-up turn.

  Що треба:

  - Логувати окремі події:
      - intent_completed
      - intent_closed
      - intent_replaced
      - intent_activated
      - intent_activation_deferred_until_next_turn
  - І логувати active_intent_id before/after.

  Тоді з дампа буде видно не “Status: ACTIVE десь далі”, а точний state transition.

  4. Розвести tool failure і contract failure
  У цьому дампі невдалий read_file через size-guard зробив картину стану візуально ніби контракт “пішов не туди”.

  Що треба:

  - Явно в runtime зафіксувати правило:
      - blocked tool step не закриває контракт,
      - blocked tool step не означає need for re-activation,
      - blocked tool step породжує тільки narrowed continuation.
  - Це треба відбивати і в recovery, і в логах.

  5. Зменшити свободу моделі саме в transition-момент
  Найгірша поведінка в дампі трапляється, коли модель намагається бути “розумною”:

  - завершити старе,
  - відкрити нове,
  - одразу почати реалізацію,
  - ще й вибрати не найкращий перший action.

  Що треба:

  - Після valid transition дати моделі короткий runtime message без зайвого тексту:
      - previous contract closed
      - new contract active
      - return the next valid output only
  - Не заливати в цей момент великий policy-text. У transition-моменті він тільки розмиває сигнал.

  6. Ввести окремий defect для overpacked transition response
  Зараз це, схоже, просто “формально allowed, practically fragile”.

  Що треба:

  - окремий defect на кшталт transition_bundle_too_dense
  - тригер, коли в одному response є:
      - completion intent
      - new activate/replace intent
      - action
  - recovery:
      - “Transition accepted/applied or not; now return only the next valid output.”
  - Це не карати як malformed, а нормалізувати як risky shape.

  7. Для MODIFY не дозволяти поганий перший крок після transition
  У дампі новий MODIFY одразу пішов у full read_file, який було заблоковано.

  Що треба:

  - Для fresh MODIFY contract задати кращий стартовий heuristic:
      - якщо файл великий або контекст уже частково відомий, first step має бути read_chunk / search_content /
        read_file_skeleton, а не read_file.
  - Це не prompt-only проблема; це краще підказувати runtime recovery/hints.

  8. Скоротити системні повідомлення після limit/transition
  У дампі модель після runtime-повідомлень часто починає робити більш “літературні”, але менш операційні responses.

  Що треба:

  - transition recovery і post-limit recovery робити коротшими;
  - у них залишати тільки:
      - current state
      - what is still active
      - exact allowed next output forms
      - one direct instruction
  - Прибрати довгі роз’яснення в ці моменти.

  9. Перевірити, що no-active-intent і active-contract universes справді різні
  У цьому дампі видно, що частина двозначності з’являється через змішування двох режимів.

  Що треба:

  - У кожному recovery явно фіксувати, в якому universe ми є:
      - no_active_contract
      - active_contract
      - transition_in_progress
  - Найкраще навіть окремим полем у logger/pipeline outcome.

  10. Найпрактичніший мінімум
  Якщо робити не все одразу, а тільки те, що дасть найбільший ефект:

  1. Окремий typed outcome для intent_only_without_next_step.
  2. Окремий typed outcome для complete+activate+action transition bundle.
  3. Typed lifecycle logs before_intent_id -> after_intent_id.
  4. Короткий recovery для transition-моментів.
  5. Heuristic: після переходу в MODIFY не штовхати модель у full read_file як перший крок.

  Якщо хочеш, я можу далі розкласти це вже як конкретний план змін у коді:

  - які саме модулі чіпати,
  - де parser,
  - де response pipeline,
  - де transition handler,
  - де defect detector,
  - де logging contract.



• З того, що ще реально варто зробити після цього пакета, я бачу такі кроки.

  1. Typed transition outcome замість текстоцентричного glue
  Зараз уже стало краще, але intent_transitions.py все ще багато вирішує через аналіз response_text і prompt
  branching.

  Що ще треба:

  - ввести явні outcome-и на кшталт:
      - intent_applied_no_followup
      - intent_completed_waiting_for_answer
      - transition_bundle_split_required
      - intent_rejected_policy
  - щоб response_pipeline працював із typed semantics, а не з неявним набором handled/reason/next_query.

  Це зменшить кількість “магії” на boundary.

  2. Єдиний lifecycle reducer для intent state
  Зараз частина lifecycle сидить в intent_runtime, частина в intent_transitions, частина в recovery semantics.

  Що ще треба:

  - одна точка, яка відповідає за:
      - activate
      - complete
      - replace
      - retry
      - close/finalize
  - і повертає один structured event:
      - before
      - requested
      - applied
      - after
      - requires_next_turn

  Тоді не доведеться окремо в різних місцях “домірковувати”, що сталося з контрактом.

  3. Явний transition_in_progress state
  Зараз я тільки додав universe label у логах. Але концептуально це вже проситься в state model.

  Що ще треба:

  - короткоживучий orchestration state:
      - no_active_contract
      - active_contract
      - transition_in_progress
  - особливо корисно для випадків:
      - complete -> answer
      - complete -> activate -> next step
      - activate accepted but next step missing

  Це прибере частину двозначності в recovery.

  4. Рознести parser classification і orchestration classification
  Зараз parsing.py уже визначає деякі orchestration-relevant дефекти.
  Це практично, але не ідеально чисто.

  Що ще треба:

  - parser має відповідати лише за structural facts:
      - intent count
      - action count
      - malformed action
      - visible text
  - orchestration classifier окремо має вирішувати:
      - intent_only_without_next_step
      - transition_bundle_too_dense
      - tool_history_echo_without_action
      - інші pipeline дефекти

  Це зробить архітектуру чистішою і тестованішою.

  5. Кращий dump/trace export
  Зараз trace вже корисніший, але для дамп-аналізу ще бракує короткого human-readable lifecycle блоку.

  Що ще треба:

  - у dump додати компактну секцію типу:
      - Intent lifecycle timeline
      - step 1: activated id=...
      - step 7: completion emitted
      - step 7: completion applied
      - step 8: no active contract
      - step 9: activated id=...
  - щоб не доводилося вичитувати це з raw prompt snapshots.

  Оце дало б найбільший виграш для діагностики.

  6. Окремі тести саме на dump-driven transition cases
  Зараз є хороші компонентні тести, але ще варто зацементувати сценарії з реальних дампів.

  Що ще треба:

  - тест на complete + activate + action
  - тест на activate only, потім valid next step окремим turn
  - тест на complete only, потім final answer
  - тест на blocked tool після fresh transition, але без втрати current contract
  - тест на повторний user follow-up зроби це після already completed intent

  Це найпростіший шлях не пустити ці баги назад.

  7. Менше “розуму” в core, більше явного pipeline контракту
  Ти вже правильно дивишся в бік чистоти ядра. Наступний реальний крок тут:

  - core.process() має тільки координувати
  - рішення мають повертати typed outcomes
  - recovery wording не повинно розмазуватись по різних місцях

  Це вже не блокер після мого патча, але це правильний наступний архітектурний етап.

  Якщо пріоритезувати, я б робив так:

  1. lifecycle reducer / typed transition outcomes
  2. transition_in_progress as real state
  3. dump lifecycle timeline
  4. dump-driven integration tests
  5. тільки потім чистити parser vs orchestration classification boundary

  Найбільшу практичну різницю зараз дадуть пункти 1, 3 і 4.

