# План рефакторингу для `run_step` (Historical Draft)

> Status: historical draft.  
> This document reflects an earlier refactoring direction and is no longer the canonical implementation plan for orchestration.  
> The current authoritative architecture is described in `docs/ORCHESTRATION_PHASE_ARCHITECTURE.md`.

Цей документ описує запропонований план рефакторингу для методу `run_step` в `modules/agent/orchestration/response_pipeline.py`.

### Аналіз поточної реалізації

Метод `run_step` наразі є центральним координатором, який послідовно викликає низку внутрішніх методів, що представляють етапи обробки:
1. `_run_initial_stages`
2. `_run_checkpoint_stage`
3. `_run_classification_stage`
4. `_run_post_classification_stage`

Кожен етап може повернути проміжний результат (`outcome`) і негайно зупинити подальшу обробку. Це створює лінійний, але жорстко зв'язаний потік керування всередині одного методу. Така структура є ідеальним кандидатом для застосування патерну **"Ланцюжок обов'язків" (Chain of Responsibility)**.

### План рефакторингу

Пропонується перетворити кожен етап обробки на окремий об'єкт-обробник (Handler), що дозволить зробити систему більш гнучкою, розширюваною та дотримуватися принципів SOLID.

#### Крок 1: Створення базового класу `Handler`

Визначимо абстрактний клас, який описує інтерфейс обробника та можливість зв'язування в ланцюжок.

```python
from __future__ import annotations
from abc import ABC, abstractmethod
from typing import Any, Optional

class Handler(ABC):
    """Абстрактний клас для обробника в ланцюжку."""
    _next_handler: Optional[Handler] = None

    def set_next(self, handler: Handler) -> Handler:
        """Встановлює наступний обробник і повертає його для зручного зв'язування."""
        self._next_handler = handler
        return handler

    @abstractmethod
    async def handle(self, context: Any) -> Any:
        """Обробляє запит і/або передає його далі по ланцюжку."""
        if self._next_handler:
            return await self._next_handler.handle(context)
        return context
```

#### Крок 2: Створення об'єкта `PipelineContext`

Щоб уникнути передачі великої кількості параметрів між обробниками, всі дані, необхідні для обробки, будуть інкапсульовані в одному об'єкті-контексті.

```python
from dataclasses import dataclass
from typing import Optional, Any
from .decision_models import ResponsePipelineOutcome

@dataclass
class PipelineContext:
    """Контекст, що містить стан і дані для обробки в ланцюжку."""
    agent_ctx: Any
    step: Any
    raw_response: Optional[str] = None
    reflection_state: Optional[tuple] = None
    checkpoint_state: Optional[Any] = None
    classified: Optional[Any] = None
    outcome: Optional[ResponsePipelineOutcome] = None

    def should_stop(self) -> bool:
        """Перевіряє, чи було встановлено кінцевий результат, що має зупинити ланцюжок."""
        return self.outcome is not None
```

#### Крок 3: Реалізація конкретних обробників

Кожен етап з `run_step` стає окремим класом, що успадковує `Handler`.

*   **`InitialStageHandler`**: Інкапсулює логіку `_run_initial_stages`.
*   **`CheckpointStageHandler`**: Інкапсулює логіку `_run_checkpoint_stage`.
*   **`ClassificationStageHandler`**: Інкапсулює `_run_classification_stage`.
*   **`PostClassificationStageHandler`**: Інкапсулює `_run_post_classification_stage`.

Приклад реалізації одного з обробників:

```python
class InitialStageHandler(Handler):
    def __init__(self, pipeline: "ModelResponsePipeline"):
        self.pipeline = pipeline

    async def handle(self, context: PipelineContext) -> PipelineContext:
        # Логіка, що раніше була в _run_initial_stages
        raw_response, reflection_state, early_outcome = await self.pipeline._run_initial_stages(context.agent_ctx, context.step)

        if early_outcome is not None:
            context.outcome = early_outcome
            return context # Зупиняємо ланцюжок, повертаючи контекст

        # Готуємо дані для наступного обробника
        context.raw_response = raw_response
        context.reflection_state = reflection_state

        # Передаємо управління далі по ланцюжку
        return await super().handle(context)
```
Інші обробники реалізуються за аналогічною схемою, перевіряючи `context.should_stop()` перед виконанням своєї логіки.

#### Крок 4: Оновлення методу `run_step`

Нова версія `run_step` буде відповідати лише за побудову та запуск ланцюжка обробників.

```python
# Всередині класу ModelResponsePipeline

async def run_step(self, ctx, step) -> ResponsePipelineOutcome:
    """Запускає конвеєр обробки за допомогою ланцюжка обов'язків."""

    # Побудова ланцюжка обробників
    pipeline_head = InitialStageHandler(self)
    pipeline_head.set_next(CheckpointStageHandler(self)) \
                 .set_next(ClassificationStageHandler(self)) \
                 .set_next(PostClassificationStageHandler(self))

    # Створення початкового контексту
    initial_context = PipelineContext(agent_ctx=ctx, step=step)

    # Запуск ланцюжка
    final_context = await pipeline_head.handle(initial_context)

    # Повернення фінального результату з контексту
    return final_context.outcome
```

### Переваги запропонованого рефакторингу

1.  **Гнучкість та розширюваність**: Легко додавати нові етапи, видаляти або змінювати їх порядок, не модифікуючи існуючий код.
2.  **Ізоляція логіки (Single Responsibility Principle)**: Кожен обробник має одну чітку відповідальність, що спрощує його розуміння, тестування та підтримку.
3.  **Зменшення зв'язності (Loose Coupling)**: Основний клас `ModelResponsePipeline` більше не керує кожним кроком, а лише ініціює процес. Обробники знають лише про існування наступного в ланцюжку.
4.  **Покращена читабельність**: Конфігурація ланцюжка в `run_step` наочно та декларативно описує весь процес обробки.

## Критика цього драфту з точки зору поточної архітектури

Цей документ був корисним як ранній поштовх до декомпозиції `run_step`, але в поточному стані коду його не слід використовувати як актуальний план реалізації.

### 1. Базова проблема вже частково вирішена

`run_step` більше не є старим монолітним методом, для якого писався цей план.

У поточній реалізації:

- `modules/agent/orchestration/response_pipeline.py` вже є thin coordinator
- prevalidation винесено в `modules/agent/orchestration/response_pipeline_prevalidation.py`
- execution stages винесено в `modules/agent/orchestration/response_pipeline_stages.py`

Тобто вихідна ціль документа вже значною мірою досягнута іншим способом.

### 2. `Chain of Responsibility` тут не є найкращим патерном

Головна слабкість цього плану в тому, що він припускає відносно вільний ланцюжок handler-ів, який можна легко переставляти або розширювати.

Для цього runtime це радше недолік, ніж перевага.

Поточна orchestration-модель залежить від жорсткого phase ordering:

1. response normalization
2. intent prevalidation
3. intent transition handling
4. checkpoint stages
5. response classification
6. output recovery
7. action policy
8. dispatch-ready outcome

Ці фази не повинні вільно переставлятися, бо correctness залежить від їхнього порядку.

### 3. `PipelineContext` занадто абстрактний

Ідея одного універсального mutable context виглядає зручною, але в цій системі вона легко перетворюється на ще одну неявну state bag.

У поточному runtime вже є кілька різних видів stage state:

- normalization state
- reflection state
- checkpoint state
- classification state
- transition defect state
- terminal plaintext state

Тому без чітких ownership boundaries такий `PipelineContext` лише сховає складність, а не зменшить її.

### 4. Декларативний pipeline тут має бути fixed-phase, а не “вільним ланцюжком”

Правильніший напрямок для цього репо зараз:

- thin facade modules
- explicit stage contracts
- fixed phase pipeline
- stable phase ordering

А не generic chain-of-responsibility framework.

### 5. Актуальне джерело істини

Для поточного коду орієнтуватися слід на:

- `docs/ORCHESTRATION_PHASE_ARCHITECTURE.md`

Саме він відображає реальний поділ і інваріанти після вже виконаних refactor-ів.
