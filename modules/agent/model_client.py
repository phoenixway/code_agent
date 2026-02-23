"""Клієнт для роботи з AI моделями."""

from modules.chat import get_chat_provider
from modules.history import HistoryManager

class ModelClient:
    """Відповідає за комунікацію з LLM та управління контекстом запиту."""
    
    def __init__(self, config, logger=None, comm_logger=None):
        self.config = config
        self.log = logger
        self.comm_log = comm_logger # Відновлено логер комунікації
        self.chat = get_chat_provider(config.default_model)
        self._tokenizer_warning_logged = False
        self._smart_stop_trailing_text_limit = 200
        
    async def get_streaming_response(
        self,
        query: str,
        history_manager: HistoryManager,
        ui=None,
        state=None,
        system_message: str | None = None,
    ):
        """Отримує відповідь від моделі частинами з підтримкою Smart Stop."""
        full_text = ""
        history_data = history_manager.get_history_for_api()
        if system_message and isinstance(system_message, str):
            history_data = [{"role": "system", "content": system_message}] + history_data
        
        # 1. Логування вихідного запиту
        if self.comm_log:
            self.comm_log.info(f"--- OUTGOING ---\n{query}\n")
        
        try:
            async for chunk in self.chat.get_streaming_response(query, history_data):
                full_text += chunk
                
                # --- SMART STOP LOGIC ---
                # Зупиняємо достроково лише коли вже є повні action-блоки
                # і модель продовжує "балакати" поза ними.
                # Це не ріже multi-action батчі (кілька <action>...</action> підряд).
                if self._should_smart_stop(full_text):
                    if self.comm_log:
                        self.comm_log.info("--- SMART STOP TRIGGERED (trailing non-action text detected) ---")
                    # Примусово обриваємо генерацію
                    break
                # ------------------------

        except Exception as e:
            if self.log: self.log.error(f"AI Error: {e}")
            return f"Error: {e}"
        
        # 2. Логування вхідної відповіді (вже обрізаної)
        if self.comm_log:
            self.comm_log.info(f"--- INCOMING ---\n{full_text}\n")
            
        # 3. Оновлення статистики токенів
        if state and ui:
            await self._update_token_stats(query, full_text, history_manager, ui, state)
            
        return full_text

    def _should_smart_stop(self, full_text: str) -> bool:
        if not full_text or "</action>" not in full_text:
            return False
        lower = full_text.lower()
        open_count = lower.count("<action")
        close_count = lower.count("</action>")
        # Якщо ще незакриті action-блоки, чекати далі.
        if close_count < open_count:
            return False
        last_close = lower.rfind("</action>")
        if last_close == -1:
            return False
        trailing = full_text[last_close + len("</action>"):]
        trailing_stripped = trailing.lstrip()
        if not trailing_stripped:
            return False
        # Якщо далі одразу стартує наступний action-блок — це валідний батч.
        if trailing_stripped.lower().startswith("<action"):
            return False
        # Дозволяємо короткі пробіли/службовий шум; блокуємо довгий "хвіст" поза action.
        return len(trailing_stripped) >= self._smart_stop_trailing_text_limit
    
    async def _update_token_stats(self, query, response, history_manager, ui, state):
        """Підраховує токени та оновлює UI."""
        try:
            p_tokens = self._estimate_tokens(query)
            c_tokens = self._estimate_tokens(response)
            
            state.add_tokens(p_tokens, c_tokens)
            
            if hasattr(ui, 'update_token_status'):
                await ui.update_token_status(
                    history_tokens=history_manager.current_token_count,
                    max_tokens=history_manager.max_tokens,
                    session_tokens=state.session_tokens
                )
        except Exception as e:
            if self.log: self.log.warning(f"Token update failed: {e}")

    def _estimate_tokens(self, text: str) -> int:
        """Estimate tokens safely even if provider has no tokenizer support."""
        tokenizer = None
        get_tokenizer = getattr(self.chat, "get_tokenizer", None)
        if callable(get_tokenizer):
            try:
                tokenizer = get_tokenizer()
            except Exception as e:
                if self.log and not self._tokenizer_warning_logged:
                    self.log.warning(f"Tokenizer unavailable, using fallback estimation: {e}")
                    self._tokenizer_warning_logged = True
        elif self.log and not self._tokenizer_warning_logged:
            self.log.info(
                "Provider has no get_tokenizer(); using character-based token estimation."
            )
            self._tokenizer_warning_logged = True

        if tokenizer and hasattr(tokenizer, "encode"):
            try:
                return len(tokenizer.encode(text))
            except Exception:
                # If tokenizer fails for some text, fallback to approximation.
                pass
        if not text:
            return 0
        return max(1, len(text) // 4)

    async def switch_model(self, model_name: str, ui=None):
        """Перемикає провайдера моделі."""
        if hasattr(self.chat, 'model_name') and self.chat.model_name == model_name:
            if ui: await ui.print_system(f"Модель {model_name} вже активна.")
            return True

        if ui: await ui.print_system(f"Перемикаюсь на {model_name}...")
        
        new_provider = get_chat_provider(model_name)
        if new_provider:
            self.chat = new_provider
            if ui:
                await ui.update_header(f"{self.chat.model_name}")
                await ui.print_system(f"✅ Модель змінено на {model_name}")
            return True
        return False
