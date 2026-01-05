# modules/history.py
class HistoryManager:
    def __init__(self, chat_provider, logger=None, max_tokens=4000):
        self.messages = []
        self.chat = chat_provider
        self.max_tokens = max_tokens
        self.logger = logger

    def add_message(self, role, content):
        if self.logger:
            self.logger.info(f"LOG_HISTORY_ADD_MESSAGE_RAW: Role={role}, Content='{repr(content)}'")
        
        if content and isinstance(content, str):
            cleaned = content.strip()
            
            if self.logger:
                self.logger.info(f"LOG_HISTORY_ADD_MESSAGE_CLEANED: Role={role}, Content='{repr(cleaned)}'")

            if cleaned:
                self.messages.append({"role": role, "content": cleaned})

    def get_history_for_api(self):
        return self.messages

    # modules/history.py

    async def check_and_summarize(self, ui):
        # Приблизний підрахунок токенів
        tokens = sum(len(m["content"]) for m in self.messages) // 4
        
        if tokens > self.max_tokens:
            # ДОДАНО await, бо ui.print_system тепер асинхронний
            await ui.print_system(f"History too long ({tokens} tokens). Summarizing...")
            
            # Створюємо запит для сумаризації
            history_text = "\n".join([f"{m['role']}: {m['content']}" for m in self.messages])
            prompt = f"Summarize the following conversation history briefly, keeping key facts:\n\n{history_text}"
            
            try:
                # Викликаємо ШІ. Оскільки це запит до моделі, він МАЄ бути асинхронним
                summary = ""
                async for chunk in self.chat.get_streaming_response(prompt, []):
                    summary += chunk
                
                # Очищуємо історію та залишаємо тільки сумаризацію
                self.messages = [
                    {"role": "system", "content": f"Previous conversation summary: {summary}"}
                ]
                
                await ui.print_system("History summarized successfully.")
                
            except Exception as e:
                await ui.print_error(f"Failed to summarize history: {str(e)}")
