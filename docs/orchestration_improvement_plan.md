# План Покращення Архітектури Оркестрації (Historical Draft)

> Status: Historical Draft.
> This document describes a pre-split orchestration architecture and should not
> be used as the current implementation plan.
> Canonical current references:
> `docs/ORCHESTRATION_PHASE_ARCHITECTURE.md`,
> `docs/ORCHESTRATION_PACKAGE_MAP.md`,
> `docs/ORCHESTRATION_DEPENDENCY_RULES.md`,
> `docs/ORCHESTRATION_COLLABORATOR_BUNDLES.md`.

## Фінальний глибокий аналіз архітектури

Основна проблема сучасної архітектури криється не в її компонентах, а в способі їхньої взаємодії, особливо в файлі `modules/agent/orchestration/response_pipeline.py`.

### 1. Центральна проблема: Процедурний моноліт `run_step`

- **Розташування:** Метод `run_step` у класі `ModelResponsePipeline`.
- **Спостереження:** Цей метод є величезним (сотні рядків) процедурним скриптом, який послідовно виконує всі мислимі завдання, пов'язані з обробкою відповіді від ШІ:
    - Перевірка атомарності переходу між `intent`-ами.
    - Застосування оновлень до дошки планування (`plan_board_stage`).
    - Застосування оновлень до дошки пам'яті (`memory_board_stage`).
    - Застосування десятків правил валідації та відновлення (`guards`, `output_recovery`).
    - Перевірка політик безпеки та дій (`action_policy`).
- **Конфлікт:** Такий підхід робить систему надзвичайно **жорсткою**. Будь-яка зміна в логіці (наприклад, додавання нового правила валідації або нового етапу обробки) вимагає модифікації цього гігантського методу, що підвищує ризик помилок і ускладнює тестування. Архітектура є **модульною лише на рівні файлів, але не на рівні логіки виконання**.

### 2. Проблема: Монолітний контекст `ctx`

- **Спостереження:** Об'єкт `ctx` передається з методу в метод, і кожен компонент може читати або змінювати будь-яку його частину. Це створює неявні залежності між компонентами, які важко відстежити.
- **Конфлікт:** Компоненти не є по-справжньому незалежними. Наприклад, етап `action_policy` залежить від стану, встановленого `intent_transitions` кількома кроками раніше, і ця залежність не є очевидною з сигнатур методів.

### Ключова рекомендація: Перехід до патерну "Ланцюжок обов'язків" (Chain of Responsibility)

Замість одного гігантського методу `run_step`, я пропоную впровадити справжній конвеєр обробки, де кожен етап є незалежним об'єктом.

**Пропонована архітектура:**

```python
# Концептуальний код
class ResponsePipeline:
    def __init__(self, stages: list[Stage]):
        self.stages = stages

    async def run(self, context: ResponseContext) -> FinalOutcome:
        for stage in self.stages:
            context = await stage.process(context)
            if context.is_finalized():
                break
        return context.to_outcome()

# Приклад етапу
class IntentTransitionStage(Stage):
    async def process(self, context: ResponseContext) -> ResponseContext:
        # Логіка, що відповідає тільки за переходи між intent-ами
        # ...
        return context
```

**Переваги:**

1.  **Гнучкість:** Послідовність етапів (`stages`) можна буде **динамічно** змінювати залежно від типу завдання (`intent`).
2.  **Ізоляція та тестованість:** Кожен `Stage` буде маленьким, сфокусованим класом з єдиною відповідальністю.
3.  **Явність:** Потік керування стане явним і зрозумілим із самої послідовності етапів.
4.  **Розширюваність:** Додавання нової функціональності зводитиметься до створення нового класу `Stage` та його включення до конвеєра.

### Дорожня карта

1.  **Рефакторинг `ModelResponsePipeline`:** Винести логіку з методу `run_step` в окремі класи-`Stage`.
2.  **Створення `PipelineManager`:** Розробити клас, який буде відповідати за створення та конфігурацію конвеєрів (`ResponsePipeline`).
3.  **Ізоляція контексту:** Створити спеціалізований об'єкт `ResponseContext` для конвеєра, який буде містити лише необхідну для обробки відповіді інформацію.


---

## Глибока пропозиція: Архітектура на основі "Етапів" (Stages)

Попередній аналіз виявив, що ключова проблема архітектури — це монолітний метод `run_step` у `modules/agent/orchestration/response_pipeline.py`. Я пропоную перейти до патерну "Ланцюжок обов'язків" (Chain of Responsibility). Тепер я представлю конкретний план реалізації цього патерну, який зробить систему значно гнучкішою та надійнішою.

### 1. Базовий контракт: `Stage` та `ResponseContext`

Вводимо два базові компоненти: `Stage` (етап обробки) та `ResponseContext` (контейнер даних, що передається між етапами).

**Інтерфейс етапу (`Stage`):**
Кожен етап буде незалежним класом з одним методом `process`.

```python
# У новому файлі, наприклад, modules/agent/orchestration/stages/base.py
from abc import ABC, abstractmethod
from dataclasses import dataclass

@dataclass
class ResponseContext:
    """Контейнер даних для конвеєра обробки відповіді."""
    raw_response: str
    model_step_result: ModelStepResult # Результат від моделі

    # Стан, що змінюється етапами
    is_finalized: bool = False # Чи потрібно зупинити конвеєр?
    stop_reason: str | None = None # Причина зупинки
    next_prompt: str | None = None # Запит для наступної ітерації (якщо потрібно)

    # Результати парсингу
    segments: list | None = None
    parsed_output: ParsedOutput | None = None

    def finalize(self, reason: str, next_prompt: str | None = None):
        """Допоміжний метод для зупинки конвеєра."""
        self.is_finalized = True
        self.stop_reason = reason
        self.next_prompt = next_prompt

class Stage(ABC):
    """Абстрактний базовий клас для всіх етапів конвеєра."""
    @abstractmethod
    async def process(self, context: ResponseContext) -> ResponseContext:
        """Обробляє контекст і повертає його оновлену версію."""
        pass
```

### 2. Рефакторинг `run_step` на окремі `Stage`-класи

Тепер ми можемо розбити логіку з гігантського методу `run_step` на логічні, ізольовані етапи.

**Приклади класів-етапів (в `modules/agent/orchestration/stages/`):**

- **`IntentValidationStage(Stage)`**:
  - **Відповідальність:** Перевірка відповіді *перед* застосуванням зміни `intent`.
  - **Логіка:** Містить логіку з методів `_reject_truncated_terminal_completion_before_transition` та `_reject_invalid_intent_followup_before_transition`.
  - **Результат:** Якщо валідація не пройдена, викликає `context.finalize()` з відповідним промптом для виправлення.

- **`IntentTransitionStage(Stage)`**:
  - **Відповідальність:** Застосування переходу `intent` (activate, complete, etc.).
  - **Логіка:** Викликає `self.intent_transitions.handle_model_step`.
  - **Результат:** Якщо перехід відбувся і вимагає негайної зупинки (наприклад, `complete`), фіналізує контекст.

- **`StateCheckpointStage(Stage)`**:
  - **Відповідальність:** Оновлення дошок планування та пам'яті.
  - **Логіка:** Послідовно викликає `self.plan_board_stage.apply()` та `self.memory_board_stage.apply()`.
  - **Результат:** Модифікує `context.raw_response`, видаляючи з нього оброблені теги пам'яті та плану.

- **`ReflectionAndLoopGuardStage(Stage)`**:
  - **Відповідальність:** Мета-логіка: виявлення циклів, бездіяльності, потреби в рефлексії.
  - **Логіка:** Містить логіку перевірки `reflection_repair_pending` та лічильників `memory_checkpoint_only_streak`, `nonproductive_thinking_streak`.
  - **Результат:** Може фіналізувати контекст і згенерувати промпт, що змушує модель "подумати ще раз" або змінити стратегію.

- **`ParseAndRecoverStage(Stage)`**:
  - **Відповідальність:** Парсинг фінальної відповіді та виправлення структурних помилок (неправильний XML/JSON).
  - **Логіка:** Використовує `self.parser` та `self.output_recovery`.
  - **Результат:** Заповнює `context.segments` та `context.parsed_output` або фіналізує з промптом для виправлення синтаксису.

- **`ActionPolicyStage(Stage)`**:
  - **Відповідальність:** Перевірка, чи дозволені дії, які хоче виконати модель.
  - **Логіка:** Використовує `self.action_policy.decide`.
  - **Результат:** Якщо дія заборонена, фіналізує контекст з повідомленням про помилку.

### 3. Новий `ResponsePipeline` та динамічна конфігурація

Сам клас `ModelResponsePipeline` стане дуже простим. Його головне завдання — запустити етапи в правильній послідовності.

```python
# В оновленому modules/agent/orchestration/response_pipeline.py

class ModelResponsePipeline:
    def __init__(self, agent, ...):
        # Ініціалізація всіх необхідних етапів
        self.stages = [
            IntentValidationStage(...),
            IntentTransitionStage(...),
            StateCheckpointStage(...),
            ReflectionAndLoopGuardStage(...),
            ParseAndRecoverStage(...),
            ActionPolicyStage(...),
        ]

    async def run_step(self, ctx, step) -> ResponsePipelineOutcome:
        # 1. Створюємо початковий контекст
        response_context = ResponseContext(
            raw_response=step.response,
            model_step_result=step
        )

        # 2. Запускаємо конвеєр
        for stage in self.stages:
            response_context = await stage.process(response_context)
            if response_context.is_finalized:
                break

        # 3. Перетворюємо фінальний контекст на результат, зрозумілий для Orchestrator
        return self.to_outcome(response_context)
```

**Наступний крок (Динамічний конвеєр):** Надалі, замість жорстко заданого списку `self.stages`, можна впровадити `PipelineManager`, який буде повертати різний набір етапів залежно від поточного `intent`-у агента. Наприклад, для `intent: "MODIFY"` він може додавати `RunTestsStage` в кінець конвеєра.

### Висновок

Цей підхід не просто виправляє проблему монолітного методу. Він трансформує архітектуру, роблячи її:
- **Композитною:** Система будується з маленьких, незалежних "цеглинок".
- **Керованою:** Потік виконання стає явним і легко відстежується.
- **Розширюваною:** Додавання нової логіки валідації або нового кроку обробки — це просто створення нового класу `Stage` і його додавання до списку, а не зміна існуючого коду.

Це створює міцний фундамент для реалізації більш складних інтелектуальних функцій, таких як адаптивне планування та довгострокова стратегія.
