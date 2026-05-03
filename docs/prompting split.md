# План split для prompting.py (Historical Draft)

> Status: Historical Draft.
> The semantic prompt split has already been completed under
> `modules/agent/orchestration/prompts/`.
> Keep this note only as historical rationale; do not treat it as an active
> refactoring plan.

Я б ділив цей файл не “по довжині”, а по **ролях побудови prompt-ів**. Зараз `prompting.py` одночасно робить 4 різні роботи:

1. читає runtime state
2. будує статусні блоки для system prompt
3. будує recovery prompts
4. має купу дрібних format-specific шаблонів

Через це він уже схожий на диспетчерську з 27 телефонами 📞

## Як я б розрізав

### 1. `prompt_builder_base.py`

Тут лишити:

* `OrchestratorPromptBuilder` як фасад
* доступ до `agent/state/config`
* дрібні helper-методи типу:

  * `_current_active_intent()`
  * `_intent_universe()`
  * `_current_intent_goal()`
  * `_current_intent_allowed_actions()`
  * `_action_hints_from_stop_info()`

Тобто це тонкий orchestration facade, а не місце для всіх текстів. Базою може залишитися поточний клас, але він має лише делегувати. 

### 2. `prompt_sections.py`

Сюди винести побудову **великих системних секцій**:

* `build_active_intent_contract_prompt()`
* `build_no_active_intent_contract_prompt()`
* `build_memory_board_protocol_prompt()`
* `build_system_message()` частково, або хоча б його section assembly helpers

Це окрема роль: **runtime status rendering**.
Вона логічно відрізняється від recovery. 

### 3. `intent_prompts.py`

Сюди винести все, що стосується **intent lifecycle**:

* `build_intent_required_prompt()`
* `build_invalid_intent_contract_prompt()`
* `build_intent_transition_rejected_prompt()`
* `build_intent_completed_prompt()`
* `build_approved_changed_goal_prompt()`
* `build_keep_original_goal_prompt()`
* `build_reuse_current_intent_prompt()`

Тобто все, що каже моделі:

* активуй intent
* не реактивуй
* заверши intent
* тримай поточний intent
* не міняй goal. 

### 4. `recovery_prompts.py`

Це найбільший і найважливіший кандидат на окремий модуль.

Сюди винести:

* `build_keep_current_intent_recovery_prompt()`
* `build_no_active_intent_recovery_prompt()`
* `build_typed_stop_recovery_prompt()`
* `build_orchestrated_recovery_prompt()`
* `typed_recovery_header()`
* `_format_next_actions_hint()`

Це окрема підсистема: **policy/recovery wording**.
Саме вона у вас зараз найактивніше еволюціонує, тому їй краще жити окремо. 

### 5. `action_format_prompts.py`

Сюди винести все про **формат наступної відповіді**:

* `build_action_format_recovery_prompt()`
* `build_malformed_action_strict_recovery_prompt()`
* `build_audit_marker_echo_strict_recovery_prompt()`
* `build_missing_action_or_answer_prompt()`
* `build_tool_history_echo_without_action_prompt()`
* `build_intent_only_deadend_prompt()`
* `build_malformed_read_file_payload_prompt()`
* `build_malformed_read_file_skeleton_payload_prompt()`
* `build_malformed_read_chunk_payload_prompt()`
* `build_repeated_malformed_read_chunk_payload_prompt()`

Це окремий світ: **shape / syntax / output contract repair**.
Він зараз змішаний із high-level recovery, і це створює кашу. 

### 6. `interactive_ui_prompts.py`

Сюди дрібні UI-facing тексти:

* `build_suspect_intent_change_message()`
* `build_intent_overrun_message()`
* `build_suspect_intent_change_confirmation_suffix()`
* `build_intent_overrun_confirmation_suffix()`

Це окремий клас відповідальності: **людські confirm/choice prompts**. 

### 7. `diagnostic_helpers.py` або `prompt_state_summary.py`

Сюди helper-логіку, яка не є prompt wording напряму:

* `_summarize_last_action()`
* `_derive_current_best_answer()`
* `_effective_intent_step_limit()`
* `_intent_steps_remaining()`

Це state summarization, не recovery і не intent lifecycle. 

---

## Як це виглядало б архітектурно

Я б лишив **один публічний фасад**:

* `OrchestratorPromptBuilder`

А всередині він мав би компоненти:

* `PromptStateSummary`
* `PromptSectionsRenderer`
* `IntentPromptFactory`
* `RecoveryPromptFactory`
* `ActionFormatPromptFactory`
* `InteractivePromptFactory`

Тобто зовні нічого не ламається, а всередині файл розпадається на маленькі ролі.

---

## Найкращий порядок розбиття

Я б не різав усе за один раз. Робив би так:

### Крок 1

Винести **`action_format_prompts.py`**
Бо це майже чисті шаблони й вони найменш ризикові для переносу.

### Крок 2

Винести **`intent_prompts.py`**

### Крок 3

Винести **`recovery_prompts.py`**
Оце вже найважливіший і найцінніший модуль.

### Крок 4

Винести **`prompt_sections.py`**

### Крок 5

Після цього залишити в `prompting.py` лише фасад і композицію.

---

## Чого я б не робив

Я б не ділив:

* “перші 300 рядків / другі 300 рядків”
* “basic / advanced prompts”
* “small methods / big methods”

Це дає гарну геометрію файлів, але погану семантику.

І я б не розносив кожен один метод в окремий файл.
Тобі потрібні **підмодулі за роллю**, а не музей дрібних уламків.

---

## Моя рекомендована схема імен

Приблизно так:

* `modules/agent/orchestrator/prompting/__init__.py`
* `modules/agent/orchestrator/prompting/builder.py`
* `modules/agent/orchestrator/prompting/sections.py`
* `modules/agent/orchestrator/prompting/intent_prompts.py`
* `modules/agent/orchestrator/prompting/recovery_prompts.py`
* `modules/agent/orchestrator/prompting/action_format_prompts.py`
* `modules/agent/orchestrator/prompting/interactive_prompts.py`
* `modules/agent/orchestrator/prompting/state_summary.py`

Це, на мій смак, найчистіше.

---

## Найкоротша відповідь

**Найкраще ділити цей файл на підмодулі за типом prompt-а:**

* system/status sections
* intent lifecycle prompts
* recovery prompts
* action-format repair prompts
* UI confirmation prompts
* state-summary helpers

А `OrchestratorPromptBuilder` лишити тонким фасадом, який усе це збирає докупи. 

Якщо хочеш, я можу дати вже **конкретний план класів і методів: що саме в який новий файл переносити 1-в-1**.
