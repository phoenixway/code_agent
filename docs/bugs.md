• Подивився саме те, що runtime показав моделі після першого перевищення лімітів у dumps/
  agent_dump_20260419_105932.txt:767, і проблема справді не в одному повідомленні, а в каскаді з кількох recovery-
  режимів.

  Що саме бачила модель

  Після першого intent_step_limit_soft_exceeded runtime відправив такий recovery prompt, видно в dumps/
  agent_dump_20260419_105932.txt:767:

  SYSTEM: Continue under the current intent contract.
  Reason: intent_step_limit_soft_exceeded.
  Allowed actions under the CURRENT intent contract: read_file, read_file_skeleton, read_chunk, search_content,
  search_files, run_shell, list_directory.
  Current contract goal remains the same: Determine current sorting logic and UI editing capabilities for activity
  records, and plan changes to sort by startTime and make startTime editable in the EditRecordDialog..
  The current intent contract remains valid and its goal remains the same.
  Intent here means the formal runtime contract for the current user-facing goal and allowed actions, not a new local
  intention, substep label, or next micro-step.
  Continue toward that goal using the updated allowed tools and constraints.
  Do not repeat the action pattern that was just blocked or low-value.
  Do not relabel, refresh, replace, or reactivate the intent contract unless there is a valid reason from the system
  prompt or runtime.
  Do not restart the task from the beginning. Continue from already gathered evidence, files, and conclusions under
  the same contract.
  Change the next action when needed. Do not change the contract without a valid reason.
  Return the next step that most increases progress toward the goal, or provide a plain-text answer if the goal can
  already be answered.
  Prefer a final allowed action, or return a final plain-text answer if the evidence is already enough.

  Після цього модель справді спробувала продовжити, але згенерувала malformed <action>. Тоді runtime показав друге
  повідомлення, видно в dumps/agent_dump_20260419_105932.txt:812:

  SYSTEM: Your last response contained malformed <action> content.
  Return only valid <action> content for the next step.
  For read-only investigation, multiple separate <action>...</action> blocks are allowed.
  Compatible format: one <action>...</action> block may contain a JSON array of read-only action objects.
  For any state-changing step, return only one valid <action>.
  Do not use JSON arrays for state-changing actions.
  No prose outside <action>.
  If unsure, prefer separate <action> blocks.
  If the edit payload is large, prefer write_file.
  If using edit_file, keep search_text/replace_text short and exact.

  Після hard-limit і вашого approve runtime дав третє повідомлення, видно в dumps/agent_dump_20260419_105932.txt:863:

  SYSTEM: Continue under the current intent contract.
  Reason: user_approved_more_steps_after_hard_limit.
  Allowed actions under the CURRENT intent contract: read_file, read_file_skeleton, read_chunk, search_content,
  search_files, run_shell, list_directory.
  Current contract goal remains the same: Determine current sorting logic and UI editing capabilities for activity
  records, and plan changes to sort by startTime and make startTime editable in the EditRecordDialog..
  The current intent contract remains valid and its goal remains the same.
  Intent here means the formal runtime contract for the current user-facing goal and allowed actions, not a new local
  intention, substep label, or next micro-step.
  Continue toward that goal using the updated allowed tools and constraints.
  Do not repeat the action pattern that was just blocked or low-value.
  Do not relabel, refresh, replace, or reactivate the intent contract unless there is a valid reason from the system
  prompt or runtime.
  Do not restart the task from the beginning. Continue from already gathered evidence, files, and conclusions under
  the same contract.
  Change the next action when needed. Do not change the contract without a valid reason.
  Return the next step that most increases progress toward the goal, or provide a plain-text answer if the goal can
  already be answered.
  User approved a small additional step budget for the CURRENT intent contract. Return the next valid <action> now.

  Потім знову malformed-action recovery, видно в dumps/agent_dump_20260419_105932.txt:906, з майже тим самим текстом.

  І нарешті після цього runtime вже дав policy-style stop/recovery, видно в dumps/agent_dump_20260419_105932.txt:932:

  SYSTEM: Previous action violated orchestration policy.
  Recommended next actions: search_content, search_files, edit_file, write_file.
  Choose a different strategy and return the next valid <action>.

  Що саме з цього нашкодило якості

  1. soft limit prompt був занадто довгим і семантично перевантаженим
     Він одночасно каже:

  - контракт лишається активним
  - не міняй intent
  - не повторюй blocked/low-value pattern
  - не починай спочатку
  - вибери наступний крок
  - або дай plain-text answer
  - але краще final allowed action

  Для моделі це не один чіткий режим, а мішанина з policy, anti-loop, intent semantics і task guidance. Після такого
  prompt їй важче вирішити, що зараз головне: формат, контракт, чи власне дослідження.

  2. Ключова суперечність: answer now і do next action одночасно
     У soft-limit recovery є дві конкуруючі інструкції:

  - provide a plain-text answer if the goal can already be answered
  - Prefer a final allowed action

  Це не катастрофа саме по собі, але в момент перевищення бюджету модель вже має бути в крихкому стані. Така
  двозначність штовхає її не в чистий mode shift, а в коливання між “закінчити” і “ще трохи копнути”.

  3. Malformed-action recovery додав ще більше неоднозначності замість звуження
     Повідомлення з dumps/agent_dump_20260419_105932.txt:812 формально каже “return only valid <action>”, але далі
     пише:

  - можна multiple separate <action> blocks
  - можна JSON array inside one block
  - separate blocks preferred if unsure

  Тобто після помилки формат не звужується, а навпаки дає кілька альтернативних синтаксисів. Це майже ідеальний рецепт
  для повторної format drift.

  4. Recovery prompt підсовує нерелевантні editing hints
     У malformed-action recovery є:

  - If the edit payload is large, prefer write_file.
  - If using edit_file, keep search_text/replace_text short and exact.

  Але конкретний контекст був read-only investigation. Тобто runtime після format error починає шуміти про write_file/
  edit_file, яких модель у той момент не просила. Це забруднює short-term objective.

  5. Після hard-limit approve runtime знову штовхає саме в tool mode
     Повідомлення з dumps/agent_dump_20260419_105932.txt:863 завершується дуже жорстко:

  - User approved a small additional step budget...
  - Return the next valid <action> now.

  Тобто після budget boundary модель уже не бачить справжнього вибору між “answer from current evidence” і “one more
  tool step”. Runtime фактично примусово переводить її в action mode. Це може бути продуктово допустимо після approve,
  але якість reasoning від цього падає: модель менше оцінює sufficiency of evidence і більше поспішає видати будь-який
  action.

  6. Другий malformed-action recovery добив контекст
     Після approve-more-steps модель дала ще один кривий action, і runtime знову показав той самий широкий format-
     recovery. У цей момент модель уже працює не над задачею, а над боротьбою з форматом, причому без чіткого
     дозволеного шаблону “зроби ось так і тільки так”.
  7. Фінальний policy prompt занадто різко змінює allowed strategy
     Повідомлення з dumps/agent_dump_20260419_105932.txt:932:

  - Previous action violated orchestration policy.
  - Recommended next actions: search_content, search_files, edit_file, write_file.

  Це вже інший режим мислення:

  - раніше дозволені були read_file/read_chunk/...
  - тут раптом рекомендовані edit_file/write_file
  - хоча intent усе ще INVESTIGATE

  Для моделі це виглядає як нестабільність правил гри. Вона бачить активний investigate-contract, але recovery
  пропонує modify-ish directions. Це підриває довіру до runtime signals.

  Найшкідливіші конкретні елементи

  Найбільш токсичними я вважаю саме ці фрагменти:

  - Prefer a final allowed action, or return a final plain-text answer...
    Причина: двозначність у critical moment.
  - Compatible format: one <action>...</action> block may contain a JSON array...
    Причина: після format error треба звужувати формат, а не розширювати.
  - If unsure, prefer separate <action> blocks.
    Причина: це ще одна альтернатива замість одного жорсткого recovery shape.
  - If the edit payload is large, prefer write_file.
    Причина: нерелевантний шум у read-only investigation.
  - Return the next valid <action> now.
    Причина: після hard-limit approval це знімає з моделі обов’язок оцінити, чи evidence уже достатній.
  - Recommended next actions: search_content, search_files, edit_file, write_file.
    Причина: мікс різних work modes, який конфліктує з active investigate contract.

  Кореневий висновок

  Погіршення якості сталося не тому, що runtime почав нагадувати про ліміт сам по собі. Воно сталося тому, що після
  першого soft-limit модель потрапила в стек із трьох різних meta-modes:

  1. stay in current intent
  2. fix your action format
  3. continue after hard limit approval
  4. policy violation, change strategy

  І кожен наступний prompt не спрощував режим, а додавав новий шар правил. У результаті модель втратила стабільну
  локальну ціль і почала оптимізуватись під orchestration compliance, а не під якісне продовження дослідження.

  Якщо хочеш, наступним кроком я можу зробити дуже точкову пропозицію: переписати саме post-soft-limit і post-
  malformed-action recovery prompts у короткі, односпрямовані повідомлення без зміни вашої продуктної логіки з approve
  more steps / stop and answer.

