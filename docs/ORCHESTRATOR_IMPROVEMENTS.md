# Покращення оркестратора (Orchestrator Enhancements)

Цей документ містить пропозиції щодо покращення класу `Orchestrator` у модулі `modules/agent/orchestrator.py`.

## Поточний стан

Поточний оркестратор працює за принципом "Think -> Act -> Loop", але має кілька областей для покращення:

1. **Обробка помилок**: Лише базовий try-except
2. **Логування**: Мінімальне, лише для summarization
3. **Продуктивність**: Немає кешування чи оптимізації
4. **Читабельність**: Великий метод `process()`
5. **Безпека**: Немає валідації вхідних даних
6. **Моніторинг**: Відсутні метрики продуктивності

## Пропозиції покращень

### 1. Покращена обробка помилок

```python
# Додати клас для обробки помилок
class OrchestratorError(Exception):
    pass

class ModelError(OrchestratorError):
    pass

class ParsingError(OrchestratorError):
    pass

# Додати retry-логіку
async def process_with_retry(self, user_input, max_retries=3):
    for attempt in range(max_retries):
        try:
            return await self.process(user_input)
        except (ModelError, asyncio.TimeoutError) as e:
            if attempt == max_retries - 1:
                raise
            await asyncio.sleep(2 ** attempt)  # Exponential backoff
```

### 2. Детальне логування

```python
import logging
import time

class Orchestrator:
    def __init__(self, agent):
        self.logger = logging.getLogger(__name__)
        # ...
    
    async def process(self, user_input):
        self.logger.info(f"Starting processing for input: {user_input[:50]}...")
        start_time = time.time()
        
        try:
            # ... існуючий код ...
            
            # Логування статистики
            duration = time.time() - start_time
            self.logger.info(f"Processing completed in {duration:.2f}s, {consecutive_calls} steps")
            
        except Exception as e:
            self.logger.error(f"Processing failed: {e}", exc_info=True)
            raise
```

### 3. Оптимізація продуктивності

```python
from functools import lru_cache

class Orchestrator:
    def __init__(self, agent):
        self._cached_prompt = None
        self._prompt_hash = None
    
    def _get_system_prompt(self):
        current_hash = hash(self.agent.tool_manager.get_tools_prompt() + 
                          self.agent.context_manager.get_context_prompt())
        
        if self._cached_prompt is None or self._prompt_hash != current_hash:
            tools_prompt = self.agent.tool_manager.get_tools_prompt()
            ctx_prompt = self.agent.context_manager.get_context_prompt()
            system_msg = f"{DEFAULT_SYSTEM_PROMPT.format(tools_description=tools_prompt)}\n\n{ctx_prompt}"
            
            self._cached_prompt = system_msg
            self._prompt_hash = current_hash
        
        return self._cached_prompt
```

### 4. Рефакторинг для читабельності

```python
# Розбити великий метод на менші
async def process(self, user_input):
    await self._prepare_context(user_input)
    
    try:
        while self._should_continue():
            await self._execute_step()
    finally:
        await self._cleanup()
    
    await self._summarize()

async def _execute_step(self):
    """Виконання одного кроку в циклі Think-Act."""
    await self.ui.start_thinking()
    
    # Отримання відповіді від моделі
    response = await self._get_model_response()
    if not response:
        return False
    
    # Парсинг та виконання
    segments = self.parser.parse(response)
    result = await self._execute_actions(segments)
    
    # Оновлення історії
    await self._update_history(segments, result)
    
    return result.should_continue
```

### 5. Нові функції (переривання, пауза)

```python
class Orchestrator:
    def __init__(self, agent):
        self._is_interrupted = False
        self._pause_event = asyncio.Event()
        self._pause_event.set()  # Початково не на паузі
    
    async def interrupt(self):
        """Перервати виконання."""
        self._is_interrupted = True
        if self.state.current_task:
            self.state.current_task.cancel()
    
    async def pause(self):
        """Поставити на паузу."""
        self._pause_event.clear()
    
    async def resume(self):
        """Продовжити виконання."""
        self._pause_event.set()
    
    async def _check_interruption(self):
        """Перевірити, чи потрібно перервати або поставити на паузу."""
        await self._pause_event.wait()
        if self._is_interrupted:
            raise asyncio.CancelledError("Execution interrupted by user")
```

### 6. Метрики продуктивності

```python
from dataclasses import dataclass
from typing import Optional
import time

@dataclass
class PerformanceMetrics:
    total_steps: int = 0
    total_time: float = 0.0
    avg_step_time: float = 0.0
    model_calls: int = 0
    tool_calls: int = 0
    tokens_used: int = 0

class Orchestrator:
    def __init__(self, agent):
        self.metrics = PerformanceMetrics()
        self._step_start_time: Optional[float] = None
    
    async def _execute_step(self):
        self._step_start_time = time.time()
        
        # ... виконання кроку ...
        
        step_duration = time.time() - self._step_start_time
        self.metrics.total_steps += 1
        self.metrics.total_time += step_duration
        self.metrics.avg_step_time = self.metrics.total_time / self.metrics.total_steps
```

### 7. Валідація вхідних даних

```python
import re

def validate_input(self, user_input: str) -> bool:
    """Валідація вхідних даних."""
    if not user_input or not isinstance(user_input, str):
        return False
    
    if len(user_input.strip()) == 0:
        return False
    
    # Перевірка на потенційно небезпечні команди
    dangerous_patterns = [
        r"rm\\s+-rf", r"mkfs", r"dd\\s+if=", 
        r":(){:|:&};:",  # Fork bomb
    ]
    
    for pattern in dangerous_patterns:
        if re.search(pattern, user_input, re.IGNORECASE):
            self.logger.warning(f"Potentially dangerous input detected: {pattern}")
            return False
    
    return True
```

### 8. Підтримка плагінів

```python
# Додати систему плагінів
class PluginSystem:
    def __init__(self):
        self.plugins = []
    
    def register_plugin(self, plugin):
        self.plugins.append(plugin)
    
    async def before_step(self, context):
        for plugin in self.plugins:
            await plugin.before_step(context)
    
    async def after_step(self, context, result):
        for plugin in self.plugins:
            await plugin.after_step(context, result)

class Orchestrator:
    def __init__(self, agent):
        self.plugin_system = PluginSystem()
    
    async def _execute_step(self):
        context = self._create_context()
        await self.plugin_system.before_step(context)
        
        # ... виконання кроку ...
        
        await self.plugin_system.after_step(context, result)
```

## Пріоритети впровадження

1. **Високий пріоритет**:
   - Додати логування (найважливіше для налагодження)
   - Покращити обробку помилок (покращить стабільність)
   - Додати переривання (покращить UX)

2. **Середній пріоритет**:
   - Розбити великий метод (покращить підтримку коду)
   - Додати метрики продуктивності
   - Додати валідацію вхідних даних

3. **Низький пріоритет**:
   - Оптимізація продуктивності (кешування)
   - Підтримка плагінів

## План впровадження

1. Почати з додавання логування та покращення обробки помилок
2. Додати функцію переривання
3. Провести рефакторинг великого методу
4. Додати метрики та валідацію
5. Оптимізувати продуктивність
6. Додати систему плагінів

---

*Документ створено: 2026-01-28 17:11:57*  
*Останнє оновлення: 2026-01-28 17:11:57*