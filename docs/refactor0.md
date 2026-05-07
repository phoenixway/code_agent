• Залишилось
  Нижче план того, що ще має сенс доробити, щоб дійти до цільової архітектури source -> lexer -> parser -> AST ->
  shape -> IR -> semantic validator -> transaction plan -> executor, без broad rewrite.

  1. Transition semantic pass добити
  Зараз:

  - accepted followup already typed
  - rejected followup partially typed

  Ще зробити:

  - звести accepted + rejected routing під один TransitionSemanticValidator
  - повернути один typed result для:
      - accepted_without_followup
      - accepted_with_action
      - accepted_with_plaintext
      - followup_conflict
      - transition_only_violation
      - reuse_only_violation
      - rejected_reuse_without_active
      - rejected_redundant_reactivation
      - terminal_repeated_transition_defect
  - залишити IntentTransitionRoutingMixin лише mapper-ом у IntentHandlingDecision

  2. Semantic validators винести з runtime helper-ів у явний pass
  Зараз compiler/IR уже впливає на:

  - file_content pairing
  - formal intent required
  - action allowed by active/proposed intent
  - частину plaintext/recovery guards

  Ще зробити:

  - окремий semantic_validators.py або passes/semantic.py
  - pure validators:
      - validate_formal_intent_requirement(ir, state)
      - validate_action_allowed(ir, state)
      - validate_bundle_shape(ir, state)
      - validate_completion_followup(ir, state)
  - прибрати залишки raw/segment-first branching

  3. Bundle path довести до справжнього plan-first
  Зараз є:

  - AtomicBundlePlan
  - ExecutionPlan
  - ExecutionCommit
  - no-op artifact for invalid bundle

  Ще зробити:

  - будувати ExecutionPlan і для reject, і для success одним API
  - executor має приймати plan, а не сирі segments
  - commit має породжуватись лише з ExecutionPlan
  - інваріанти зробити assertions/metrics-first:
      - invalid bundle -> no transition, no dispatch
      - rejected intent -> no state mutation

  4. RecoveryStrategy registry розширити до повного покриття
  Зараз registry є лише для covered compiler defects.

  Ще зробити:

  - винести більше legacy invalid_kind branches у ErrorValue/recovery_id -> strategy
  - покрити хоча б:
      - formal intent required
      - reuse without active intent
      - transition-only
      - followup conflict
      - completion with action
  - додати must_include/must_not_include tests для них

  5. Repeat escalation уніфікувати
  Зараз escalation є для частини compiler-driven recovery.

  Ще зробити:

  - один fingerprint builder для:
      - parser/shape errors
      - transition semantic errors
      - bundle semantic errors
  - один escalation policy:
      - first normal
      - second strict
      - third terminal/handoff

  6. Replay/observability доробити до повного compiler artifact
  Зараз є compact trace/replay snapshots.

  Ще зробити:

  - повний replay object:
      - tokens
      - ast
      - shape
      - ir
      - semantic validation result
      - execution plan
      - execution commit
  - один canonical serializer для trace/export/replay dump
  - optional diff old-vs-new diagnosis while shadow behavior remains anywhere

  7. Memory / operational state остаточно розвести
  Зараз:

  - operational_journal already exists
  - memory prompt уже safer

  Ще зробити:

  - перестати використовувати model-authored memory tags для routine operational success
  - journal зробити primary source для:
      - last committed action
      - last committed result
      - recent runtime operations
  - memory board лишити для durable semantic knowledge only

  8. Legacy leftovers дочистити
  Зараз ще лишились місця, де рішення йдуть через:

  - invalid_kind
  - raw regex helpers
  - legacy segments as fallback

  Ще зробити:

  - inventory і cleanup:
      - has_action_segment
      - raw followup regexes
      - prompt/recovery branches on legacy names
      - recent_problem_actions residual uses
  - для кожного такого місця:
      - або перевести на compiler/IR
      - або явно позначити legacy fallback

  9. Test corpus розширити
  Зараз є fixtures + targeted regressions.

  Ще зробити:

  - property/metamorphic tests для:
      - literal tags in markdown/code
      - bundle exact-one-action invariant
      - completion/text/control mixing
      - repeated recovery escalation
      - stale plan board suppression
  - кожен новий dump bug -> fixture + expected shape/error/recovery/transaction flags

  10. Gradual rollout завершити
  Рекомендований порядок:

  1. Добити TransitionSemanticValidator
  2. Винести semantic validators в окремий pass
  3. Перевести bundle execution на plan-first
  4. Розширити recovery registry
  5. Дочистити legacy branches
  6. Після стабілізації вирішити, чи потрібен parser generator взагалі

  Що я б робив наступним
  Найкращий наступний крок зараз:

  1. зробити один TransitionSemanticValidator API для accepted + rejected cases;
  2. після цього винести bundle semantic validation в окремий pure pass;
  3. потім уже підв’язати executor до ExecutionPlan.

  Якщо хочеш, я можу одразу піти в пункт 1 і зробити цей validator.

*****************8


› дай план того що ще залишилось зробити за таким принципом. спочатку складова mvp. потім решта


• MVP
  Це мінімум, після якого pipeline вже буде виглядати як справжній compiler/runtime seam, а не набір partial bridges.

  1. TransitionSemanticValidator
     Що зробити:

  - об’єднати accepted + rejected transition/followup rules в один validator API
  - повернути typed decision/result замість розкиданих helper-ів
  - лишити routing mixin thin mapper-ом

  Результат:

  - transition logic перестане бути розмазана по handler/routing helper-ах
  - менше raw branching і менше шансів на stage disagreement

  2. Окремий semantic validator pass
     Що зробити:

  - винести з runtime helper-ів у pure validators:
      - formal intent required
      - action allowed by active/proposed intent
      - bundle exact-one-action
      - file_content pairing
      - completion followup constraints
  - зробити API рівня IR + state -> Ok/Err

  Результат:

  - semantics більше не житимуть у prevalidation/action_policy/transition helpers одночасно
  - з’явиться один канонічний semantic layer

  3. Bundle path -> plan-first
     Що зробити:

  - уніфікувати invalid/success bundle under one ExecutionPlan contract
  - executor/dispatch path має брати plan, а не покладатися на legacy parsed segments
  - reject path теж повинен повертати explicit no-op plan/result

  Результат:

  - all-or-nothing bundle стане не convention, а execution contract
  - transition_applied / action_dispatched стануть deterministic artifacts

  4. Recovery registry для всіх уже compiler-driven і transition-driven cases
     Що зробити:

  - перенести ще ключові recovery branches з invalid_kind у ErrorValue/recovery_id -> strategy
  - покрити:
      - transition-only
      - reuse without active
      - followup conflict
      - completion-with-action
      - formal-intent-required
  - додати contract tests

  Результат:

  - recovery більше не залежатиме від legacy names як primary interface
  - wrong-root-cause loops ще зменшаться

  5. Regression coverage для MVP seams
     Що зробити:

  - тести на:
      - accepted/rejected transition semantic decisions
      - bundle no-op vs success plan
      - semantic validator pass
      - recovery strategies for those errors

  Результат:

  - можна буде безпечніше прибирати legacy fallback-и

  Після MVP
  Це вже hardening, cleanup і доведення до повної архітектури.

  1. Unified escalation engine
     Що зробити:

  - один fingerprint builder для parser/shape/semantic/transition errors
  - один escalation policy для repeated failures

  2. Повний observability/replay artifact
     Що зробити:

  - canonical replay object:
      - tokens
      - ast
      - shape
      - ir
      - semantic result
      - execution plan
      - execution commit
  - один serializer для trace/export/dump/replay

  3. Memory vs operational state separation добити
     Що зробити:

  - прибрати залишкову залежність operational flows від model-authored memory
  - journal зробити primary runtime fact source для recent actions/results

  4. Legacy cleanup pass
     Що зробити:

  - інвентаризувати всі залишки:
      - raw regex routing
      - invalid_kind-first branches
      - has_action_segment fallbacks
      - recent_problem_actions residues
  - або перевести на compiler artifacts, або позначити intentional fallback

  5. Property/metamorphic corpus expansion
     Що зробити:

  - systematic tests for:
      - literal tags in markdown/code
      - action array vs single action
      - visible/control mixing
      - repeated escalation
      - stale lineage suppression

  6. Optional final architecture step
     Що зробити:

  - вирішити, чи потрібен generator-backed parser
  - робити це лише якщо handwritten parser реально почне заважати

  Як я б це робив по черзі

  1. TransitionSemanticValidator
  2. semantic validator pass
  3. bundle ExecutionPlan as primary runtime contract
  4. recovery registry expansion
  5. legacy cleanup
  6. observability/replay hardening
  7. broader test corpus
  8. optional parser/codegen decisions

  Якщо хочеш, я можу відразу розбити ще й це на MVP-1, MVP-2, MVP-3 з оцінкою в годинах на кожен шматок.

***

Protocol compiler migration paused at safe boundary.
Next authority rules require explicit runtime regression tests.
Do not broaden PLAINTEXT_ONLY or ACTION_ONLY by shape alone.