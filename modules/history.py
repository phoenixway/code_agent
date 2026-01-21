# modules/history.py
class HistoryManager:
    def __init__(self, chat_provider, logger=None, max_tokens=4000):
        self.messages = []
        self.chat = chat_provider
        self.max_tokens = max_tokens
        self.logger = logger

    def add_message(self, role, content):
        if self.logger:
            self.logger.debug(f"LOG_HISTORY_ADD_MESSAGE_RAW: Role={role}, Content='{repr(content)}'")
        
        if content and isinstance(content, str):
            cleaned = content.strip()
            
            if self.logger:
                self.logger.debug(f"LOG_HISTORY_ADD_MESSAGE_CLEANED: Role={role}, Content='{repr(cleaned)}'")

            if cleaned:
                self.messages.append({"role": role, "content": cleaned})

    def add_messages(self, messages):
        """Adds a list of messages to the history."""
        for message in messages:
            self.add_message(message["role"], message["content"])

    def get_history_for_api(self):
        return self.messages

    @property
    def current_token_count(self):
        """Calculates and returns the current token count of the history."""
        if not self.messages:
            return 0
        
        tokenizer = self.chat.get_tokenizer()
        if not tokenizer:
            # Fallback to a rough character-based estimation if no tokenizer is available
            return sum(len(m["content"]) for m in self.messages) // 4

        token_count = 0
        for message in self.messages:
            token_count += len(tokenizer.encode(message['content']))
        return token_count

    # modules/history.py

    async def check_and_summarize(self, ui):
        tokens = sum(len(m["content"]) for m in self.messages) // 4
        if tokens > self.max_tokens:
            if await ui.confirm_action({"type": "summarize_history"}):
                await self.summarize(ui)

    async def summarize(self, ui):
        await ui.print_system(f"History too long ({sum(len(m['content']) for m in self.messages) // 4} tokens). Summarizing...")
        history_text = "\n".join([f"{m['role']}: {m['content']}" for m in self.messages])
        prompt = f"Summarize the following conversation history briefly, keeping key facts:\n\n{history_text}"
        try:
            summary = ""
            async for chunk in self.chat.get_streaming_response(prompt, []):
                summary += chunk
            self.messages = [
                {"role": "system", "content": f"Previous conversation summary: {summary}"}
            ]
            await ui.print_system("History summarized successfully.")
        except Exception as e:
            await ui.print_error(f"Failed to summarize history: {str(e)}")
