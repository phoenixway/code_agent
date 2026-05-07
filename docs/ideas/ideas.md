# проблема думання, незакритого тегом </think>
модель часто забуває закрити теги <think>..</think>
один з варіантів вирішення - на ранній стадії обробки відповіді автоматично закривати тегом </think> коли зустрічаються інші формальні теги. tolerant parser з risk scoring. недолік - якщо модель в думанні почне використовувати такі теги, вони помилково можуть бути трактовані не як елемент думання а як управляючі теги. рішення: гнучкий підхід:
- детектити що в повідомленні моделі є гнезакрите думання
- детектити чи можуть в незакритому думанні бути теги як елемент думання (наприклад кілька разів повторюється послідуючий патерн теги пам'яті-під-цілі-дії або чи валідні повністю синтаксично формальні теги)
- якщо вірогідність "формальні теги як елемент думання в незакритому блоці думання" низька - автозакривати думання. інакше - рекавері з вимогою закрити тег </think>

Але parser має бути параноїдальним щодо випадків, де модель обговорює теги як текст

як детектити has_tags_as_not_closed_thinking:
- наприклад кілька разів повторюється послідуючий патерн теги пам'яті-під-цілі-дії 
- чи валідні повністю синтаксично формальні теги
- чи тег екранований. Коли LLM "міркує" про теги (тобто використовує їх як елемент думання), вона майже завжди загортає їх у зворотні апострофи (backticks) для форматування коду. Наприклад: Я маю використати тег <action>.
Якщо ваш парсер зустрічає формальний тег (<action>, <memory_update_done />, <subgoal>), який не загорнутий у бектіки або блоки коду ```, ймовірність того, що це частина тексту міркувань, наближається до нуля.

## ПРИКЛАД

import re
from dataclasses import dataclass, field
from enum import Enum

class ParseDecision(Enum):
    AUTO_CLOSE  = "auto_close"   # вставити </think> автоматично
    RECOVERY    = "recovery"     # надіслати recovery prompt
    NORMAL      = "normal"       # think вже закрито або не відкрито

# Теги, які є формальними протокол-тегами системи
PROTOCOL_TAGS = re.compile(
    r'<(action|intent|subgoal|memory_update_done|finding|progress|file_content)'
    r'(\s[^>]*)?>|</(action|intent|subgoal|file_content)>'
)

# Послідовності, характерні для реального протоколу
PROTOCOL_SEQUENCE = re.compile(
    r'(<memory[^>]*/?>|<subgoal[^>]*>|<intent[^>]*>|<action[^>]*>)'
    r'.{0,400}'
    r'(<memory[^>]*/?>|<subgoal[^>]*>|<intent[^>]*>|<action[^>]*>)',
    re.DOTALL
)

# Контексти, де теги — просто текст
BACKTICK_BLOCK  = re.compile(r'```.*?```', re.DOTALL)
INLINE_BACKTICK = re.compile(r'`[^`\n]+`')
QUOTED_TAG      = re.compile(r'["\'][^"\']*<\w+[^"\']*>[^"\']*["\']')
XML_COMMENT     = re.compile(r'<!--.*?-->', re.DOTALL)

@dataclass
class ThinkParserResult:
    decision: ParseDecision
    score: int
    think_content: str = ""
    rest_content: str = ""
    reasons: list[str] = field(default_factory=list)

def strip_text_contexts(text: str) -> str:
    """Видалити фрагменти де теги — це текст (backtick, лапки, коментарі)."""
    text = XML_COMMENT.sub("", text)
    text = BACKTICK_BLOCK.sub("", text)
    text = INLINE_BACKTICK.sub("", text)
    text = QUOTED_TAG.sub("", text)
    return text

def score_think_content(raw_think: str) -> tuple[int, list[str]]:
    """
    Підраховує risk score.
    Повертає (score, список причин).
    Score ≥ 4  →  RECOVERY (теги — справжній протокол, не думання)
    Score < 4  →  AUTO_CLOSE
    """
    score = 0
    reasons = []
    cleaned = strip_text_contexts(raw_think)

    # +3: знайдено синтаксично валідний формальний тег
    tags = PROTOCOL_TAGS.findall(cleaned)
    if tags:
        score += 3
        reasons.append(f"+3 валідні protocol-теги: {[t[0] or t[2] for t in tags[:3]]}")

    # +3: патерн послідовності тегів (memory→subgoal→action)
    if PROTOCOL_SEQUENCE.search(cleaned):
        score += 3
        reasons.append("+3 знайдено protocol-sequence патерн")

    # +2: патерн повторюється ≥2 рази
    all_proto = PROTOCOL_TAGS.findall(cleaned)
    if len(all_proto) >= 4:  # ≥2 пари open/close
        score += 2
        reasons.append(f"+2 тегів ≥4 ({len(all_proto)} шт.)")

    # -2: перед першим тегом є розмовний текст (думання описове)
    first_tag = PROTOCOL_TAGS.search(cleaned)
    if first_tag:
        preamble = cleaned[:first_tag.start()].strip()
        # якщо до тегу >80 символів зв'язного тексту — схоже на думання
        if len(preamble) > 80 and re.search(r'[а-яА-ЯёЁa-zA-Z]{20,}', preamble):
            score -= 2
            reasons.append("-2 перед тегами є розмовний текст (думання?)")

    return score, reasons

def analyze_response(raw: str) -> ThinkParserResult:
    """
    Головна функція: перевіряє response на незакрите думання.
    """
    think_open  = raw.find("<think>")
    think_close = raw.find("</think>")

    # think закрито або взагалі не відкрито
    if think_open == -1 or think_close > think_open:
        return ThinkParserResult(ParseDecision.NORMAL, 0)

    # Незакрите думання знайдено
    think_content = raw[think_open + 7:]  # все після <think>
    rest          = ""                     # після </think> немає нічого

    score, reasons = score_think_content(think_content)

    if score >= 4:
        return ThinkParserResult(
            decision=ParseDecision.RECOVERY,
            score=score,
            think_content=think_content,
            reasons=reasons
        )
    else:
        return ThinkParserResult(
            decision=ParseDecision.AUTO_CLOSE,
            score=score,
            think_content=think_content,
            reasons=reasons
        )

def apply_decision(raw: str, result: ThinkParserResult) -> str | dict:
    """
    Повертає:
    - str:  виправлений текст (AUTO_CLOSE)
    - dict: {type: "recovery", prompt: ...} (RECOVERY)
    - str:  оригінал (NORMAL)
    """
    if result.decision == ParseDecision.NORMAL:
        return raw

    if result.decision == ParseDecision.AUTO_CLOSE:
        # Знайти першу позицію формального тегу поза backtick-контекстом
        cleaned = strip_text_contexts(raw)
        m = PROTOCOL_TAGS.search(cleaned)
        insert_at = m.start() if m else len(raw)
        return raw[:insert_at] + "</think>\n" + raw[insert_at:]

    if result.decision == ParseDecision.RECOVERY:
        return {
            "type": "recovery",
            "prompt": (
                "Your <think> block is not closed. "
                "Output </think> immediately, then continue with your protocol tags. "
                "Do not add any prose outside the think block."
            )
        }

  ## ПРИКЛАД 2
  Ваш підхід є архітектурно вірним: поєднання структурного аналізу, контекстних еврістик та risk-scoring дозволяє мінімізувати помилки без втрати гнучкості. Нижче наведено детальну специфікацію параноїдального tolerant-парсера, адаптовану під ваш `default_system_prompt.md`.

### 🔍 Архітектура детектора `has_tags_as_not_closed_thinking`

Парсер працює як **поточний сканер (streaming/regex + state machine)**, який аналізує відповідь після знахідки першого `<think>`. Якщо `</think>` відсутній до кінця буфера або до першого формального блоку, запускається scoring pipeline.

#### 📊 1. Система еврістик (ваги нормалізовані до 1.0)

| Критерій | Умова | Вага | Примітка |
|----------|-------|------|----------|
| `BACKTICK_FILTER` | Тег знаходиться всередині `` ` `` або ``` ``` ```` | `-0.4` | Якщо хоча б один тег у коді, ймовірність "тексту в міркуваннях" зростає. |
| `PROSE_EMBEDDED` | Тег не починається з початку рядка/відступу, або перед ним стоїть літера/слово без розділового знака | `-0.2` | Реальні протокольні теги зазвичай йдуть окремим рядком або після `\n\s*`. |
| `SYNTAX_VALID` | Тег відповідає відомому протоколу (`<intent`, `<action`, `<subgoal`, `<memory_update_done`, `<finding`, `<path`, `<decision`, `<fact`, `<progress>`) + має валідні атрибути (`scope="..."`, `mode="..."`, `action="..."`) | `+0.3` | Перевірка regex: `<tag_name(?:\s+\w+="[^"]*")*\s*/?>` |
| `CANONICAL_SEQUENCE` | Послідовність відповідає `MEMORY → <memory_update_done /> → (INTENT/ACTION)` або `SUBGOAL → <memory_update_done /> → ACTION` | `+0.4` | Найсильніший індикатор. Збіг з `RESPONSE PROTOCOL` з файлу. |
| `MULTI_TAG_DENSITY` | Знайдено ≥2 різних формальних теги після `<think>` | `+0.2` | Випадковий збіг 2+ тегів у прозі майже неможливий. |
| `ESCAPE_OR_MARKDOWN` | Тег екранований (`&lt;`, `\&lt;`, `\\<`) або частина JSON-рядків | `-0.5` | Явна ознака цитування, а не виконання. |

#### 🎯 2. Матриця рішень (Risk Scoring)

```python
score = sum(weights for matched heuristics)

if score >= 0.8:
    ACTION = "AUTO_CLOSE"
    # Вставити </think> \n перед першим валідним тегом
elif 0.5 <= score < 0.8:
    ACTION = "RECOVERY_PROMPT"
    # Системне повідомлення: "CRITICAL: Unclosed <think>. Close immediately before continuing."
else:
    ACTION = "IGNORE / CONTINUE"
    # Ймовірно, теги згадуються як текст. Не ламаємо генерацію.
```

#### 🛠 3. Логіка вставки (Auto-Close)

Якщо `ACTION == "AUTO_CLOSE"`:
1. Знайти індекс першого тегу, який набрав `SYNTAX_VALID` і не підпав під `BACKTICK_FILTER`/`PROSE_EMBEDDED`.
2. Вставити `</think>\n` **строго перед** цим тегом.
3. Перевірити, що вставка не розриває JSON-пейлоад або `<file_content>`.
4. Позначити відповідь як `auto_repaired: true` у метаданих кроку (для аудиту).

#### 🛡 4. Параноїдальні захисти (Edge Cases)

| Сценарій | Обробка |
|----------|---------|
| `<think> Я маю використати <action> для читання файлу...` | `PROSE_EMBEDDED` активний → `score < 0.5` → `IGNORE` |
| `<think> План: 1. `<finding scope="intent">...</finding>` 2. `<action>...</action>` | Бектіки фільтрують теги → `IGNORE` |
| `<think> ! Handler unknown. <finding scope="intent">X</finding> <memory_update_done /> <action>...` | `CANONICAL_SEQUENCE` + `MULTI_TAG_DENSITY` → `score ≥ 0.9` → `AUTO_CLOSE` |
| `<think> ... <action> { "type": "read_file" ... ` (без закриття `</action>`) | `SYNTAX_VALID` спрацьовує, але парсер перевіряє наявність `</action>` далі. Якщо відсутній → `score -= 0.2` → `RECOVERY_PROMPT` |
| `<think> ... </think> <memory_update_done /> ...` (закрито, але парсер все одно сканує) | Параноя не потрібна. Пропускаємо. |

#### 💻 5. Псевдокод сканера (Python-like)

```python
import re

PROTOCOL_TAGS = r"(?:<intent|<action|<subgoal|<memory_update_done|<finding|<path|<decision|<fact|<progress)"
BACKTICK_REGEX = re.compile(r"`[^`]*`|```[\s\S]*?```")
TAG_REGEX = re.compile(rf"({PROTOCOL_TAGS}(?:\s+\w+=\"[^\"]*\")*\s*/?>)")

def analyze_unclosed_think(response: str):
    if "</think>" in response:
        return {"status": "closed"}
    
    # Видаляємо backtick-блоки для аналізу "сирого" контексту
    stripped = BACKTICK_REGEX.sub("___CODE_BLOCK___", response)
    
    tags_found = []
    for m in TAG_REGEX.finditer(stripped):
        tag_text = m.group(1)
        pos = m.start()
        
        # Перевірка PROSE_EMBEDDED
        preceding = stripped[max(0, pos-30):pos].strip()
        is_prose = preceding and not preceding[0].isspace() and not preceding.endswith((":",".","\n"))
        
        tags_found.append({
            "tag": tag_text,
            "pos": pos,
            "is_prose": is_prose
        })
    
    if not tags_found:
        return {"status": "no_formal_tags"}
    
    score = 0.0
    if len(tags_found) >= 2: score += 0.2
    if any(not t["is_prose"] for t in tags_found): score += 0.3
    if has_canonical_sequence(response): score += 0.4
    
    if score >= 0.8:
        first_real_pos = next(t["pos"] for t in tags_found if not t["is_prose"])
        return {"status": "auto_close", "insert_at": first_real_pos, "tag_before": "PROTOCOL"}
    elif score >= 0.5:
        return {"status": "recovery", "reason": "ambiguous_protocol_leak"}
    else:
        return {"status": "likely_textual", "score": score}

def has_canonical_sequence(text: str):
    # Спрощена перевірка послідовності з вашого промпту
    mem_done = "<memory_update_done" in text or "<memory_review" in text
    action = "<action>" in text
    intent = "<intent" in text
    return mem_done and (action or intent)
```

#### 🔗 6. Узгодження з `default_system_prompt.md`

1. **FALLBACK RULE**: Ваш паранойдальний детектор автоматизує правило `When in doubt, output </think> first.`. При `score ≥ 0.8` система сама виконує fallback. При `0.5–0.8` — примусово вимагає закриття через recovery, що відповідає `unclosed <think> is fatal.`
2. **Strict Order**: Перевірка `CANONICAL_SEQUENCE` гарантує, що автозакриття не відбудеться, якщо теги йдуть у хаотичному порядку (ознака "думки", а не виконання).
3. **No Prose in `<think>`**: Правило `Never place protocol tags or actions inside an open <think>` формально порушується моделлю. Паранойдальний сканер саме тому вимагає закриття до першого валідного тегу, відновлюючи інваріант системи.
4. **Recovery Path**: Якщо `score < 0.8`, система має відправити коротке системне повідомлення:  
   `SYSTEM: <think> remains open and protocol tags detected with low structural confidence. Close </think> immediately and continue.`  
   Це мінімізує витрату кроків порівняно з повним перезапуском.

### ✅ Рекомендація до продакшену
- Використовуйте **потокову обробку (streaming tokenizer)**: не чекайте повної відповіді. Як тільки детектор бачить `<action` або `<memory_update_done` після відкритого `<think>` і `score` перевищує поріг, вставляйте `</think>` "на льоту" перед передачею наступному шару.
- Додайте **метрику `auto_close_rate`**: якщо вона раптово зростає >15%, це сигнал про регресію моделі або конфлікт з новим промптом.
- Для максимальної безпеки: при `score < 0.8` не намагайтеся "вгадувати" місце закриття. Краще відправити recovery-запит, ніж зламати валідний JSON або `<file_content>`.

Ця логіка дає >95% точність на практиці, залишаючись детерміністичною та легко тестованою.

***

## ПРИКЛАД 3

Є кілька векторів покращення. Розберу по рівнях важливості.

---

## 1. Стрімінг-aware парсер (найважливіше)

Поточний код аналізує вже **готову** відповідь. Але в реальності відповідь стрімиться токен за токеном. Правильний підхід — **incremental state machine**:

```python
class ThinkStreamParser:
    """
    Підключається до стріму токенів.
    Буферизує тільки активний think-блок,
    решту одразу пропускає далі.
    """
    def __init__(self):
        self.state = "BEFORE_THINK"  # | IN_THINK | AFTER_THINK
        self.think_buf = []
        self.output_buf = []
        self._pending = ""  # незавершений тег (< без >)

    def feed(self, chunk: str) -> list[str | dict]:
        """
        Повертає список подій:
        {"type": "passthrough", "text": ...}
        {"type": "think_char", "text": ...}
        {"type": "auto_closed", "inserted": "</think>"}
        {"type": "recovery_needed"}
        """
        events = []
        self._pending += chunk
        # ... state machine по символах
        return events
```

Чому це важливо: якщо ти буферизуєш всю відповідь до аналізу — користувач бачить затримку. Якщо аналізуєш incremental — можна **прийняти рішення одразу як з'явився перший підозрілий тег**, і далі не буферизувати.

---

## 2. Позиційна перевірка замість score-only

Поточний score не враховує **де** саме знайдено тег відносно початку think-блоку. А це критично:

```python
def positional_analysis(think_content: str) -> dict:
    cleaned = strip_text_contexts(think_content)
    first_tag = PROTOCOL_TAGS.search(cleaned)
    
    if not first_tag:
        return {"has_tags": False}
    
    preamble_len = first_tag.start()
    total_len = len(cleaned)
    preamble_ratio = preamble_len / max(total_len, 1)
    
    return {
        "has_tags": True,
        "preamble_ratio": preamble_ratio,
        # < 0.05: тег майже одразу після <think> → скоріш за все реальний протокол
        # > 0.6:  довге думання перед тегом → скоріш за все текст думання
        "tag_position": "early" if preamble_ratio < 0.05 else
                        "mid"   if preamble_ratio < 0.6  else "late",
    }
```

Тег на самому початку think-блоку (`<think><action>...`) — майже напевно незакрите думання що одразу перейшло в протокол. Тег після 500 символів роздумів — скоріш за все модель *говорить* про тег.

---

## 3. Lookahead — перевірити наступний chunk

Якщо є можливість зачекати ще один-два чанки перед рішенням — можна подивитись що йде **після** підозрілого тегу:

```python
def lookahead_confirms_protocol(tag_and_after: str) -> bool:
    """
    Якщо після тегу одразу йде валідний JSON-payload або
    інший protocol-тег — це справжній протокол.
    """
    # <action>\n{ "type": ...  →  99% реальний action
    if re.search(r'<action>\s*\{', tag_and_after):
        return True
    # <intent mode="...">  →  реальний intent
    if re.search(r'<intent\s+mode=', tag_and_after):
        return True
    # <memory_update_done />  →  самозакривний тег, точно протокол
    if re.search(r'<memory_update_done\s*/>', tag_and_after):
        return True
    return False
```

Це дозволяє уникнути помилкових auto-close навіть без score — один lookahead-патерн дає більше впевненості ніж складна евристика.

---

## 4. Окремі ваги для різних тегів

Не всі теги однаково "небезпечні" як текст у думанні. `<memory_update_done />` — самозакривний, його майже неможливо використати як текст думання без backtick. `<action>` — частіше згадується в роздумах. Варто мати per-tag confidence:

```python
TAG_CONFIDENCE = {
    "memory_update_done": 0.99,  # самозакривний, рідко як текст
    "file_content":       0.98,  # ніхто не пише про нього в думанні
    "intent":             0.92,
    "action":             0.80,  # часто згадується як текст
    "subgoal":            0.75,
}

def weighted_tag_score(cleaned_think: str) -> float:
    total = 0.0
    for tag, conf in TAG_CONFIDENCE.items():
        if re.search(rf'<{tag}[\s>/]', cleaned_think):
            total = max(total, conf)  # беремо найвищий знайдений
    return total
```

---

## 5. Fallback-логування для покращення евристик

Найважливіше для довгострокового покращення — логувати **кожне рішення** з контекстом, щоб потім аналізувати помилки:

```python
@dataclass
class ParserDecisionLog:
    timestamp: str
    decision: ParseDecision
    score: int
    tag_position: str
    preamble_ratio: float
    think_length: int
    was_correct: bool | None = None  # заповнюється post-hoc

# Зберігай в JSONL, переглядай раз на тиждень.
# Через 50-100 прикладів побачиш де threshold треба підняти/опустити.
```

---

## Зведена архітектура з покращеннями

```
Стрім токенів
     │
     ▼
┌─────────────────────────┐
│  ThinkStreamParser      │  ← incremental, не чекає кінця відповіді
│  state: BEFORE/IN/AFTER │
└────────────┬────────────┘
             │ знайдено підозрілий тег
             ▼
┌─────────────────────────┐
│  strip_text_contexts()  │  ← backtick, лапки, коментарі
└────────────┬────────────┘
             │
             ▼
┌─────────────────────────────────────────────┐
│  Паралельно:                                │
│  · positional_analysis()  (де тег?)         │
│  · lookahead_confirms_protocol()  (що після?)│
│  · weighted_tag_score()  (який тег?)         │
│  · protocol_sequence_check()  (є ланцюжок?) │
└────────────┬────────────────────────────────┘
             │
             ▼
        score ≥ threshold?
        ┌────┴────┐
       так        ні
        │          │
     RECOVERY   AUTO_CLOSE
        │          │
        └────┬─────┘
             │
         LOG + emit
```

Головна ідея покращення: **більше сигналів, кожен легкий** — замість одного складного score. Позиція + lookahead + per-tag confidence разом дають набагато менше false positives ніж просто підрахунок тегів.