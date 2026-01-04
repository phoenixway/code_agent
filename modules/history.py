# modules/history.py
class HistoryManager:
    def __init__(self, chat_provider, max_tokens=4000):
        self.messages = []
        self.chat = chat_provider
        self.max_tokens = max_tokens

    def add_message(self, role, content):
        self.messages.append({"role": role, "content": content})

    def get_history_for_api(self):
        return self.messages

    def check_and_summarize(self, ui):
        tokens = sum(len(m["content"]) for m in self.messages) // 4
        if tokens > self.max_tokens:
            ui.print_system("Summarizing history...")
            # Логіка сумаризації через self.chat
            pass
