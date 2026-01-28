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
        
    async def get_streaming_response(self, query: str, history_manager: HistoryManager, ui=None, state=None):
        """Отримує відповідь від моделі частинами з підтримкою Smart Stop."""
        full_text = ""
        history_data = history_manager.get_history_for_api()
        
        # 1. Логування вихідного запиту
        if self.comm_log:
            self.comm_log.info(f"--- OUTGOING ---\n{query}\n")
        
        try:
            async for chunk in self.chat.get_streaming_response(query, history_data):
                full_text += chunk
                
                # --- SMART STOP LOGIC ---
                # Перевіряємо останні 50 символів на наявність закриваючого тегу дії.
                # Це запобігає "галюцинаціям" (коли агент продовжує говорити після дії).
                if "</action>" in chunk or "</action>" in full_text[-50:]:
                    if self.comm_log:
                        self.comm_log.info("--- SMART STOP TRIGGERED (</action> detected) ---")
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
    
    async def _update_token_stats(self, query, response, history_manager, ui, state):
        """Підраховує токени та оновлює UI."""
        try:
            tokenizer = self.chat.get_tokenizer()
            if tokenizer:
                p_tokens = len(tokenizer.encode(query))
                c_tokens = len(tokenizer.encode(response))
            else:
                p_tokens = len(query) // 4
                c_tokens = len(response) // 4
            
            state.add_tokens(p_tokens, c_tokens)
            
            if hasattr(ui, 'update_token_status'):
                await ui.update_token_status(
                    history_tokens=history_manager.current_token_count,
                    max_tokens=history_manager.max_tokens,
                    session_tokens=state.session_tokens
                )
        except Exception as e:
            if self.log: self.log.warning(f"Token update failed: {e}")

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
