from textual.widgets import Static
from rich.text import Text

class TokenStatusBar(Static):
    def __init__(self, **kwargs):
        super().__init__("History: 0/0 | Session: 0", **kwargs)
        self.history_tokens = 0
        self.max_tokens = 0
        self.session_tokens = 0

    def update_tokens(self, history_tokens: int, max_tokens: int, session_tokens: int):
        self.history_tokens = history_tokens
        self.max_tokens = max_tokens
        self.session_tokens = session_tokens
        
        history_text = f"History: {self.history_tokens}/{self.max_tokens}"
        session_text = f"Session: {self.session_tokens}"
        
        self.update(f"{history_text} | {session_text}")
