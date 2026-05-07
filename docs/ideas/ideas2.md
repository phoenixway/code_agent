
 Тепер, після підпапок, я б уже не робив великі механічні переноси. Наступні покращення мають бути про чистоту меж і
  навігацію.

  1. Прибрати compatibility wrappers поступово.
     Зараз вони корисні як migration layer, але з часом варто перевести внутрішні імпорти на нові шляхи і залишити
     wrappers лише тимчасово. Потім можна буде видалити зайві top-level shim-файли.
  2. Зробити один public surface для кожної підпапки.
     Тобто в prompts/__init__.py, parsers/__init__.py, responses/__init__.py, transitions/__init__.py явно
     експортувати тільки потрібні entry points і helper-и, а не все підряд.
  3. Вирівняти naming conventions між підпапками.
     Зараз є змішання:

  - *_builder
  - *_handler
  - *_pipeline
  - *_routing
  - *_apply
    Я б зафіксував просте правило:
  - facade/entry point
  - routing
  - apply
  - terminal
  - shared
  - models

  4. Виділити shared orchestration infrastructure в окрему semantic group.
     Наприклад:

  - decision_models.py
  - recovery_policy.py
  - можливо trace_export.py
    Зараз вони ще лежать у корені orchestration/, хоча вже не належать конкретно до prompts/parsers/responses/
    transitions.

  5. Оновити docs під нову структуру.
     Зараз architecture docs вже непогані, але варто додати коротку “map of package”:

  - де шукати parsing
  - де шукати response pipeline
  - де шукати prompt factories
  - де шукати transition logic

  6. Додати import hygiene tests.
     Прості тести/перевірки, що:

  - фасади імпортуються без циклів
  - compatibility wrappers резолвляться коректно
  - нові підпакети мають стабільний public API

  7. Потім уже чистити action_policy.py.
     Не через нову велику реорганізацію, а через локальні semantic slices:

  - build-fix gates
  - disallowed action handling
  - multi-action/read-only batching

  Якщо пріоритезувати:

  1. перевести внутрішні імпорти на нові підпапки
  2. зафіксувати public API в __init__.py
  3. package map doc
  4. import hygiene tests
  5. cleanup action_policy.py

  Найкращий наступний крок, на мій погляд:
  internal imports cleanup + explicit public API exports. Це дасть найбільшу користь після вже зробленої
  реорганізації.
***

› що ти порекомендував би далі для покращення організації коду?


• Тепер уже не варто робити ще один великий mechanical split. Наступні покращення мають бути про межі модулів і
  зменшення зв’язності.

  Я б рекомендував такий порядок.

  1. Почистити root modules/agent/orchestration/ до справді cross-cutting речей.
     Зараз там ще живуть координатори на кшталт modules/agent/orchestration/core.py, modules/agent/orchestration/
     pipeline.py, modules/agent/orchestration/recovery.py, modules/agent/orchestration/action_policy.py. Я б або лишив
     це як явний runtime layer, або з часом виніс у підпапку типу runtime/, щоб root не був змішаним.
  2. Ввести чітке правило залежностей між підпакетами.
     Наприклад:

  - parsers не знає про responses і transitions
  - prompts не знає про responses
  - responses може знати про parsers
  - transitions не повинні тягнути prompt/render logic, окрім фасаду
    Це краще зафіксувати в докі й простому import-hygiene test.

  3. Виділити shared infrastructure окремо.
     decision_models.py, recovery_policy.py, можливо частину trace/schema helpers логічно винести в щось на кшталт
     orchestration/shared/ або orchestration/contracts/. Це зменшить “все важливе лежить у root”.
  4. Локально дочистити action_policy.py.
     Не великим split-ом, а semantic slices:

  - build-fix gating
  - blocked/disallowed action handling
  - read-only batch rules
  - terminal plaintext handoff helpers
    Це зараз один із останніх файлів, де policy ще зібрана занадто щільно.

  5. Почати поступове видалення compatibility wrappers.
     Не одразу, а через migration plan:

  - позначити wrappers як deprecated у docstring
  - перевести зовнішні імпорти в репо
  - потім прибрати непотрібні shim-файли
    Зараз вони корисні, але довго тримати їх не варто.

  6. Додати архітектурні тести не лише на exports, а й на boundaries.
     Наприклад:

  - які модулі не мають імпортувати одне одного
  - які entry points є єдино дозволеними для зовнішнього використання
  - відсутність циклів між semantic subpackages

  Якщо пріоритетно, я б робив так:

  1. dependency rules + tests
  2. cleanup action_policy.py
  3. shared/contracts subpackage
  4. migration plan for wrapper removal

  Найкращий наступний практичний крок, на мій погляд: зафіксувати dependency boundaries між prompts/parsers/responses/
  transitions і додати тести на ці правила. Це дасть найбільший захист від повзучої деградації структури.

***

• Тепер я б уже не чіпав package structure великими рухами. Вона стала достатньо чистою. Далі найбільшу користь дадуть
  не нові переноси, а зменшення зв’язності й ясність контрактів усередині вже створених шарів.

  Мій пріоритет був би такий.

  1. Почистити modules/agent/orchestration/runtime/ по відповідальностях.
     Зараз це правильний шар, але всередині нього ще є великі вузли:

  - runtime/recovery.py
  - runtime/core.py
  - runtime/action_policy.py
    Я б не дробив їх механічно, а добивав через локальні seams:
  - окремі policy families
  - окремі state-transition helpers
  - менше knowledge leakage між runtime і prompt/recovery logic

  2. Зробити явні typed contracts для runtime collaborators.
     Зараз багато чого передається як agent, state, prompt_builder, intent_transitions. Я б поступово вводив більш
     явні protocol-like контракти або dataclass dependencies для:

  - what runtime expects from state
  - what response pipeline expects from parser/output recovery
  - what recovery expects from prompt builder
    Це сильно спростить подальший refactor.

  3. Уніфікувати state access.
     У коді багато getattr/setattr на state. Частина цього виправдана, але місцями це вже masking real dependencies. Я
     б ввів:

  - кілька small state helper APIs
  - grouped state views for intent/runtime/recovery
    Тоді orchestration логіка стане менш “stringly-typed”.

  4. Винести orchestration trace/diagnostics в окремий маленький subsystem.
     Зараз trace_export.py і stage_logging уже ок, але я б добив:

  - один canonical trace schema doc
  - one place for trace field defaults
  - one place for serialization/export
    Щоб нові діагностичні поля не розповзалися.

  5. Почистити старі назви в modules/agent/ верхнього рівня.
     Там ще видно історичні нашарування:

  - policy_engine
  - intent_policy_engine
  - defect_detector
  - intent_response_parser уже прибраний як shim, але семантично схожі overlap-и ще є
    Я б зробив короткий naming audit: які модулі є справді актуальними owners, а які лише історичний багаж.

  6. Зробити один architecture index doc для всього modules/agent.
     Не тільки orchestration, а:

  - core
  - state
  - intent runtime
  - orchestration
  - dispatch
  - technical interruptions
  - history/context
    Коротка мапа сильно знизить вартість будь-яких наступних змін.

  Якщо вибрати один найкращий наступний крок, я б взяв:

  - runtime/action_policy.py cleanup
    або
  - state access cleanup around orchestration/runtime.

  Саме там зараз найбільше залишкової складності, не в package layout.

***

Тепер я б уже не робив нові structural splits. Організація коду стала достатньо чистою. Найкращий наступний крок, на
  мій погляд, уже не про layout, а про контракти і state discipline.

  Пріоритет такий.

  1. Почистити доступ до AgentState по всьому orchestration/runtime шару.
     Ми вже зробили це локально для action_policy, recovery, core, pipeline, dispatch_outcome, але pattern ще не
     закритий системно. Я б:

  - переглянув решту runtime/response/transitions модулів;
  - добив явні state adapters там, де ще є багато getattr/setattr;
  - зафіксував правило, що новий orchestration code не лізе в state напряму без причини.

  2. Ввести явні collaborator protocols або dependency bundles.
     Зараз багато фасадів усе ще приймають “широкі” agent objects. Це вже краще, ніж було, але наступний крок —
     зробити менше implicit dependencies:

  - що саме потрібно prompt_builder;
  - що саме потрібно response_pipeline;
  - що саме потрібно recovery/transitions;
  - окремі typed bundles замість “весь agent”.

  3. Зробити короткий audit state_manager.py.
     Не переписувати його весь, а:

  - позначити orchestration-owned fields;
  - позначити dispatch-owned fields;
  - позначити resumable-intent/terminal-completion fields;
  - зафіксувати lifecycle кожного критичного поля.
    Зараз це найбільше місце, де архітектурна ясність ще відстає від cleanup модулів.

  4. Додати architecture tests на “no new direct state mutation”.
     Не абсолютно жорсткі, але хоча б guardrails:

  - runtime adapters allowed;
  - direct setattr(self.state, ...) у певних зонах або заборонити, або трекати;
  - нові trace/schema owners не дублюються.

  5. Після цього вже можна думати про deeper semantic cleanup:

  - intent_runtime.py
  - state_manager.py
  - можливо action_dispatcher.py
    Але це вже суттєво ризикованіша робота.

  Якщо вибрати один найкращий наступний крок, я б взяв:

  state_manager.py ownership audit + docs/tests around orchestration-owned state fields.`

  Бо зараз package/module structure уже хороша, а найбільша залишкова складність сидить саме в shared mutable state,
  не в розкладанні файлів.

 
› Explain this codebase
