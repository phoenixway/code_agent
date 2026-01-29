# Пропозиції щодо логування взаємодії з моделлю

Цей документ містить пропозиції щодо логування того, що агент надсилає моделі та що отримує від неї, з особливим акцентом на реальні системні промпти.

## 1. **Логування системних промптів**

```python
# Записувати повний системний промпт перед кожним запитом
logger.debug(f"System prompt:\n{system_prompt}")

# Логувати окремо контекстні частини:
logger.debug(f"Tools description:\n{tools_prompt}")
logger.debug(f"Context prompt:\n{ctx_prompt}")
logger.debug(f"Agent configuration:\n{config_summary}")
```

## 2. **Логування повної історії повідомлень**

```python
# Записувати всю історію повідомлень у форматі JSON
history_dump = {
    "system": system_messages,
    "user": user_messages, 
    "assistant": assistant_messages,
    "metadata": {
        "timestamp": datetime.now().isoformat(),
        "token_count": token_estimator.count(history)
    }
}
logger.debug(f"Full message history:\n{json.dumps(history_dump, indent=2)}")
```

## 3. **Логування запитів до моделі**

```python
# Логувати параметри запиту
logger.debug(f"Model request to {model_name}:")
logger.debug(f"  Max tokens: {max_tokens}")
logger.debug(f"  Temperature: {temperature}")
logger.debug(f"  Stream: {stream}")

# Логувати повний запит (промпт + історія)
logger.debug(f"Full request payload:\n{json.dumps(request_payload, indent=2)}")
```

## 4. **Логування відповідей моделі**

```python
# Сира відповідь моделі
logger.debug(f"Raw model response:\n{response}")

# Метадані відповіді (якщо є)
if hasattr(response, 'usage'):
    logger.debug(f"Token usage: {response.usage}")
    logger.debug(f"Finish reason: {response.finish_reason}")

# Для streaming відповідей - логувати по частинах
async def log_streaming_response(stream):
    chunks = []
    async for chunk in stream:
        chunks.append(chunk)
        logger.debug(f"Stream chunk: {chunk}")
    full_response = ''.join(chunks)
    logger.debug(f"Full streaming response: {full_response}")
```

## 5. **Логування контекстних даних**

```python
# Логувати поточний контекст (файли, директорії)
logger.debug(f"Active context files: {context_manager.get_active_files()}")
logger.debug(f"Working directory: {os.getcwd()}")
logger.debug(f"Environment: {os.environ.get('ANGELICA_ENV', 'development')}")
```

## 6. **Різні рівні деталізації**

```python
# Рівні логування для різних випадків
LOG_LEVELS = {
    'minimal': ['system_prompt', 'final_response'],
    'normal': ['system_prompt', 'user_input', 'model_response', 'actions'],
    'debug': ['everything'],  # Все включаючи сирі промпти
    'audit': ['security_events', 'permission_checks']  # Для аудиту
}
```

## 7. **Формати збереження логів**

```python
# JSON-логи для машинного аналізу
json_log = {
    "timestamp": timestamp,
    "session_id": session_id,
    "user_input": user_input,
    "system_prompt": system_prompt,
    "model_request": request_data,
    "model_response": response_data,
    "parsed_actions": parsed_actions,
    "performance": {
        "response_time": response_time,
        "token_count": token_count
    }
}

# Текстові логи для людини
text_log = f"""
[{timestamp}] Session: {session_id}
User: {user_input}
System prompt (abridged): {system_prompt[:200]}...
Model: {model_name}
Response time: {response_time:.2f}s
Tokens: {token_count}
Actions: {len(parsed_actions)}
"""
```

## 8. **Спеціальне логування для налагодження**

```python
# Логування помилок парсингу
try:
    segments = parser.parse(response)
except Exception as e:
    logger.error(f"Parsing failed for response:\n{response}")
    logger.error(f"Error: {e}", exc_info=True)
    raise

# Логування несподіваних форматів відповідей
if not segments:
    logger.warning(f"Empty segments from response:\n{response}")
    logger.warning(f"Response starts with: {response[:100]}")
```

## 9. **Конфиденційність та безпека**

```python
# Маскування конфиденційних даних
def mask_sensitive_data(text):
    patterns = {
        r'api-?key[\s=:]+[\w\-]+': 'api-key=***',
        r'password[\s=:]+[\w!@#$%^&*]+': 'password=***',
        r'token[\s=:]+[\w\.]+': 'token=***'
    }
    for pattern, replacement in patterns.items():
        text = re.sub(pattern, replacement, text, flags=re.IGNORECASE)
    return text

# Логувати масковані дані
safe_prompt = mask_sensitive_data(system_prompt)
logger.debug(f"Masked system prompt:\n{safe_prompt}")
```

## 10. **Інтеграція з наявною системою**

```python
# Додати хуки логування в існуючий оркестратор
class LoggingOrchestrator(Orchestrator):
    async def process(self, user_input):
        # Лог перед запитом
        await self._log_pre_request(user_input)
        
        # Виклик батьківського методу
        result = await super().process(user_input)
        
        # Лог після запиту
        await self._log_post_request(result)
        
        return result
    
    async def _log_pre_request(self, user_input):
        self.logger.info(f"Starting request: {user_input[:50]}...")
        if self.logger.isEnabledFor(logging.DEBUG):
            # Детальне логування тільки на рівні DEBUG
            await self._log_full_context()
```

## Ключові моменти для реалізації:

1. **Конфігуровані рівні деталізації** - від мінімального до повного логування
2. **Маскування конфиденційних даних** - API ключі, паролі тощо
3. **JSON-логи для аналізу** + текстовий формат для читання
4. **Логування streaming відповідей** - по частинах і повністю
5. **Метадані продуктивності** - час відповіді, використання токенів
6. **Логування помилок** з повним контекстом для налагодження
7. **Сесійні лог-файли** - групування за сесіями користувача

Найкорисніше для налагодження: логувати **повний системний промпт**, **сирі відповіді моделі** та **результати парсингу** у форматі, зрозумілому для аналізу.

---

*Документ створено: 2026-01-28 17:11:57*  
*Останнє оновлення: 2026-01-28 17:11:57*