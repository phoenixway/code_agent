# Angelica AI Architecture Overview

Angelica AI is a modular, CLI-based AI agent designed to perform software engineering tasks. It follows a loop-based architecture where the agent perceives the environment (files, user input), processes it via an LLM, and acts through a set of defined tools.

## High-Level Structure

The application is structured around a central **Agent** class that coordinates several specialized modules.

### Core Components

1.  **Agent (`modules/agent/core.py` / `AngelicaAgent`)**
    -   The main entry point and orchestrator.
    -   Manages the main execution loop: `User Input -> Context Assembly -> LLM Request -> Response Parsing -> Action Execution -> Output Feedback`.
    -   Handles high-level error catching and session management.

2.  **Orchestration Runtime (`modules/agent/orchestration/`)**
    -   **`runtime/core.py` / `Orchestrator`**: Thin runtime coordinator for the main Think -> Act -> Loop cycle.
    -   **`runtime/lifecycle.py` / `TurnLifecycle`**: Bootstraps a user turn by updating history, state runtime, and state machine references.
    -   **`runtime/policy.py` / `IntentGuard`**: Decides when a formal intent is required before additional tool use.
    -   **`parsers/parsing.py` / `IntentResponseParser`**: Extracts `<intent>` blocks and detects malformed or dead-end model replies.
    -   **`prompts/prompting.py` / `OrchestratorPromptBuilder`**: Owns wording for system prompts, recovery prompts, and completion prompts.
    -   **`runtime/recovery.py` / `RecoveryCoordinator`**: Chooses recovery actions and stop/continue transitions from runtime stop reasons.

3.  **Response Processing (`modules/parser.py` & `modules/processor.py`)**
    -   **Parser (`ResponseParser`)**:
        -   Splits the response into a sequence of `Segment` objects: `THOUGHT`, `TEXT`, `ACTION`.
        -   **Fallback Logic**: If `<think>` tags are malformed (e.g., more closing than opening), it treats everything up to the last `</think>` as thought content.
        -   **Security**: Actions found inside `<think>` blocks are strictly ignored.
        -   **Scanning**: Uses an iterative scanner to extract multiple sequential actions interspersed with text.
    -   **Processor (`ResponseProcessor`)**:
        -   Executes the extracted `ACTION` segments.
        -   Handles the `return_control` logic: if a tool requests to return control, the execution loop pauses and returns results to the LLM.

4.  **Tool System (`modules/tools/`)**
    -   **`manager.py`**: Dynamically loads tool classes and exposes them to the processor.
    -   **`base.py`**: Base class for all tools.
    -   Tools are defined in `modules/tools/definitions/` (e.g., `files.py`, `shell.py`).

5.  **Context Manager (`modules/context.py`)**
    -   Prepares the "Context Window" for the LLM.
    -   **Project Structure**: Generates a tree view of the current directory, respecting `.gitignore`.
    -   **File Basket**: Manages a cache of read files to include their content in the system prompt.

6.  **History Manager (`modules/history.py`)**
    -   Stores the conversation history (User, Assistant, System).
    -   **Summarization**: Automatically calls the LLM to summarize the conversation when the token limit is exceeded, preventing context overflow.

7.  **Permission Policy (`modules/policy.py`)**
    -   Security layer that intercepts actions before execution.
    -   Modes:
        -   `ask`: Prompts the user for confirmation (default).
        -   `always`: Executes everything automatically.
        -   `never`: Denies all side-effect actions.
    -   Global safety switch:
        -   `allow_side_effect_tools: false` blocks side-effect tools (shell/file writes/git changes) regardless of mode.

8.  **File System (`modules/files.py`)**
    -   A wrapper around `pathlib` to perform safe file operations (read, write, edit).

### Data Flow

1.  **Input**: User types a request in the TUI.
2.  **Context**: `ContextManager` gathers the project tree and open files. `ToolManager` provides the list of available tools.
3.  **Prompt**: `HistoryManager` combines history + context + tools definitions into a prompt.
4.  **Inference**: The `ChatProvider` sends the prompt to the configured Model (Ollama, OpenAI, etc.).
5.  **Intent/Recovery Preprocessing**: The orchestration layer extracts intent contracts, memory-board updates, and malformed/dead-end responses.
6.  **Parsing**: `ResponseParser` converts model output into typed segments.
7.  **Verification**: `PermissionPolicy`, `IntentGuard`, and orchestration policy checks constrain what can execute next.
8.  **Execution**: `ActionDispatcher` and `ToolManager` execute the permitted tool actions.
9.  **Feedback**: The result (stdout/stderr/file content) is fed back into the history as a "System" message, allowing the agent to react to the result.

## Safety Model

Execution is bounded by three runtime limits (from `config.yaml`):

- `max_consecutive_calls`: maximum autonomous loop steps before forced confirmation.
- `max_step_seconds`: timeout for one model step.
- `max_session_seconds`: timeout for the whole orchestration session.

Shell execution is additionally constrained by:

- `max_shell_command_length`
- `shell_blocklist`
- optional `shell_allowlist_prefixes`

## Directory Structure

```text
/
├── tui.py              # TUI entry point
├── agent.py            # Legacy orchestrator
├── modules/            # Core logic modules
│   ├── processor.py    # Parsing and execution logic
│   ├── context.py      # Context management
│   ├── history.py      # Chat history & summarization
│   ├── logger.py       # Logging setup and utilities
│   ├── agent/orchestration/ # Orchestrator runtime, recovery, prompting, turn lifecycle
│   ├── tools/          # Tool definitions & manager
│   ├── files.py        # File I/O
│   └── ...
├── tests/              # Unit tests
│   ├── test_modules.py # Basic component tests
│   └── test_core_logic.py # Core logic & edge case tests
└── docs/               # Documentation
```

## Logging

The application uses a two-file logging system, managed by the `modules/logger.py` module.

### Log Files

1.  **`communication.log`**:
    -   **Purpose**: Records the core interaction between the user, the agent, and the AI model. It is designed to be human-readable and provides a clean, visual representation of the conversation flow.
    -   **Content**: Contains only the formatted `OUTGOING` (to AI) and `INCOMING` (from AI) messages.
    -   **Behavior**: This log is automatically cleared at the start of each new application session.

2.  **`debug.log`**:
    -   **Purpose**: Captures all other internal logging information, including debug messages, warnings, and errors from all modules. This file is intended for developers for debugging and tracing application behavior.
    -   **Content**: Detailed, timestamped logs with log levels (DEBUG, INFO, WARNING, ERROR).
    -   **Behavior**: This log is overwritten at the start of each new application session.

### How to Log

The `modules/logger.py` module provides a simple API for logging.

-   **Debug Logging**: To log general debug information, import the logger and use its methods. The `AngelicaAgent` class instance has a `log` attribute that holds the debug logger.
    ```python
    # In a module that has access to the agent instance
    self.agent.log.debug("This is a debug message.")
    self.agent.log.error("This is an error.")
    ```

-   **Communication Logging**: To log the primary AI interactions, use the communication logger. This is typically only done within the `get_response` method in `agent.py`.
    ```python
    # In agent.py
    self.comm_log.info(f"--- OUTGOING ---\n{query}\n")
    ```

---

## Future Improvements & Architectural Recommendations

*Дата аналізу: 28 січня 2025*  
*Автор: Angelica AI (автономний аналіз)*

### 📊 Аналіз поточної архітектури

#### Сильні сторони:
- ✅ **Модульна структура** (modules/, providers/, tools/)
- ✅ **Розділення відповідальностей** (UI, агент, тули)
- ✅ **Підтримка кількох AI провайдерів** (OpenAI, Gemini, Ollama)
- ✅ **TUI інтерфейс** з Textual (сучасний, крос-платформений)
- ✅ **Система тулів** з динамічним завантаженням
- ✅ **Конфігурація через змінні середовища**

#### Слабкі місця (виявлені під час роботи):
1. **Проблеми з обробкою помилок CSS** - Textual має обмежену підтримку CSS
2. **Складність тестування UI компонентів** - важко тестувати TUI без реального інтерфейсу
3. **Відсутність чіткої документації архітектури**
4. **Можливі проблеми з потокобезпечністю** (async/sync змішування)
5. **Обмежена підтримка Markdown у Textual**
6. **Жорсткі залежності** між компонентами
7. **Розкидана конфігурація** по різних файлах
8. **Мінімальна обробка помилок** у критичних місцях

### 🚀 Пропозиції щодо покращення архітектури

#### 1. Рефакторинг та покращення модульності

**Пропонована структура:**
```
src/
  core/           # Ядро системи
    agent/        # Логіка агента
    orchestration/# Оркестрація тулів
    memory/       # Історія та контекст
  
  ui/             # UI компоненти
    tui/          # Textual UI
    widgets/      # Перевикористовувані віджети
  
  tools/          # Система тулів
    base/         # Базові класи
    builtin/      # Вбудовані тули
    extensions/   # Розширення
    
  providers/      # AI провайдери
  utils/          # Утиліти
```

#### 2. Впровадження Dependency Injection

**Пропоноване рішення:**
```python
# container.py
from dependency_injector import containers, providers

class Container(containers.DeclarativeContainer):
    config = providers.Configuration()
    
    # Провайдери
    ai_provider = providers.Singleton(
        lambda c: create_provider(c.provider.name, c.provider.api_key),
        config=config
    )
    
    # Менеджери
    tool_manager = providers.Singleton(
        ToolManager,
        provider=ai_provider
    )
```

#### 3. Покращення системи тулів

**Пропозиції:**
```python
# 1. Тули з типами даних та валідацією
@tool
def search_files(
    pattern: Annotated[str, "Шаблон пошуку"],
    path: Annotated[Optional[str], "Шлях для пошуку"] = "."
) -> List[str]:
    """Пошук файлів за шаблоном"""
    pass

# 2. Тули з безпекою (sandboxing)
@tool(sandbox=True, timeout=30)
def run_shell(command: str):
    """Виконання shell команди з обмеженнями"""
    pass
```

#### 4. Покращення UI/UX

**Пропозиції:**
```python
# 1. Абстрактний UI слой
class UIAdapter(ABC):
    @abstractmethod
    def display_message(self, message: Message):
        pass
    
    @abstractmethod
    def display_tool_call(self, tool_call: ToolCall):
        pass

# 2. Підтримка кількох UI бекендів
class TextualUI(UIAdapter):
    # Поточний Textual UI
    pass

class RichCLI(UIAdapter):
    # Простий CLI з Rich
    pass
```

#### 5. Покращення системи конфігурації

**Пропозиції:**
```yaml
# config.yaml
provider:
  name: "openai"
  api_key: "${OPENAI_API_KEY}"
  model: "gpt-4"

tools:
  enabled:
    - search_files
    - read_file
    - edit_file
    - run_shell
  disabled:
    - git_commit  # Небезпечні тули вимкнено за замовчуванням

ui:
  theme: "dark"
  compact_mode: true
  show_timestamps: false
```

#### 6. Покращення обробки помилок та логування

```python
class ErrorHandler:
    def __init__(self):
        self.logger = structlog.get_logger()
    
    async def handle_tool_error(self, tool_name: str, error: Exception):
        self.logger.error(
            "tool_execution_failed",
            tool=tool_name,
            error_type=type(error).__name__,
            error_message=str(error)
        )
        
        # Користувацькі повідомлення про помилки
        error_messages = {
            "FileNotFoundError": "Файл не знайдено",
            "PermissionError": "Немає доступу до файлу",
        }
        
        return error_messages.get(type(error).__name__, "Сталася помилка")
```

#### 7. Додавання плагінов та розширень

```python
# Структура плагінів:
# plugins/
#   code_analysis/
#     __init__.py
#     plugin.py
#   git_integration/
#     __init__.py
#     plugin.py

# Реєстрація плагінів:
class PluginManager:
    def __init__(self):
        self.plugins = []
    
    def load_plugin(self, plugin_path: str):
        # Динамічне завантаження плагінів
        pass
```

### 🎯 Нові функціональні можливості

#### 1. Система контексту та пам'яті
```python
class ContextManager:
    def __init__(self):
        self.conversation_history = []
        self.file_context = {}  # Контекст файлів
        self.project_context = {}  # Контекст проекту
    
    def add_to_context(self, file_path: str, content: str):
        """Додавання файлу до контексту"""
        self.file_context[file_path] = {
            "content": content,
            "last_modified": datetime.now(),
            "tokens": count_tokens(content)
        }
```

#### 2. Багатоагентна система
```python
class MultiAgentSystem:
    def __init__(self):
        self.agents = {
            "coder": CodeAgent(),
            "tester": TestingAgent(),
            "reviewer": CodeReviewAgent(),
        }
    
    async def collaborate(self, task: str):
        """Колаборація між агентами"""
        # Кодер пише код
        code = await self.agents["coder"].solve(task)
        
        # Тестер тестує
        test_results = await self.agents["tester"].test(code)
        
        # Ревьюер перевіряє
        review = await self.agents["reviewer"].review(code)
        
        return {
            "code": code,
            "tests": test_results,
            "review": review
        }
```

#### 3. Інтеграція з IDE та редакторами
```python
# Плагін для VS Code/Neovim
# - Автодоповнення на основі контексту
# - Швидкі команди через хоткеї
# - Інтеграція з LSP
```

#### 4. Офлайн режим та локальні моделі
```python
class LocalProvider(AIProvider):
    def __init__(self, model_path: str):
        self.model = load_local_model(model_path)
    
    async def generate(self, prompt: str) -> str:
        # Генерація з локальної моделі
        return await self.model.generate(prompt)
```

#### 5. Система навчання та адаптації
```python
class LearningSystem:
    def __init__(self):
        self.feedback_history = []
        self.success_patterns = []
    
    def learn_from_feedback(self, task: str, solution: str, feedback: str):
        """Навчання на основі зворотного зв'язку"""
        self.feedback_history.append({
            "task": task,
            "solution": solution,
            "feedback": feedback
        })
```

### 🔧 Технічні покращення

#### 1. Тестування
```python
# Пропоновано:
# 1. Модульні тести для кожного компонента
# 2. Інтеграційні тести для тулів
# 3. E2E тести для UI
# 4. Property-based тести для критичних компонентів
# 5. Тести продуктивності
```

#### 2. Документація
```python
# 1. Автоматична генерація документації з docstrings
# 2. Документація архітектури
# 3. Приклади використання
# 4. Туторіали для розробників
```

#### 3. CI/CD Pipeline
```yaml
# GitHub Actions workflow:
# 1. Лінтери (black, isort, flake8)
# 2. Тести (pytest з покриттям)
# 3. Білд для різних платформ
# 4. Автоматичне релізування
```

### 📈 Roadmap покращень

**Фаза 1: Стабілізація (1-2 тижні)**
1. Рефакторинг agent.py на менші модулі
2. Покращення обробки помилок
3. Додавання структурованого логування
4. Покращення тестів

**Фаза 2: Розширення (2-4 тижні)**
1. Система плагінів
2. Покращена система конфігурації
3. Багатоагентна архітектура
4. Система контексту

**Фаза 3: Інтеграції (1-2 місяці)**
1. IDE плагіни
2. Веб-інтерфейс
3. API для інтеграції з іншими інструментами
4. Офлайн режим

### 🎨 UI/UX покращення

1. **Теми оформлення** - темна/світла теми, кастомні кольори
2. **Швидкі команди** - хоткеї для частовикористовуваних дій
3. **Історія команд** - пошук та повторне використання
4. **Автодоповнення** - контекстне автодоповнення команд
5. **Візуалізація** - графіки для аналізу коду, діаграми залежностей

### 🔒 Безпека

1. **Sandboxing** - ізоляція виконання тулів
2. **Аудит дій** - логування всіх операцій
3. **Контроль доступу** - обмеження доступу до файлів
4. **Валідація вводу** - перевірка параметрів тулів

### 💡 Висновок

**Ключові напрямки покращення:**

1. **Архітектура:** Рефакторинг на більш модульну структуру з DI
2. **Розширюваність:** Система плагінів та кастомних тулів
3. **UI/UX:** Абстрактний UI слой для підтримки різних інтерфейсів
4. **Безпека:** Sandboxing та контроль доступу
5. **Продуктивність:** Кешування, оптимізація, локальні моделі

**Найважливіші перші кроки:**
1. Рефакторинг agent.py на менші компоненти
2. Впровадження Dependency Injection
3. Покращення системи конфігурації
4. Додавання структурованого логування

Ці зміни зроблять додаток більш стійким, розширюваним та зручним для розробки нових функцій.
