# modules/session.py
import json

class SessionManager:
    def __init__(self, config_dir, history, context, ui):
        self.dir = config_dir / "sessions"
        self.dir.mkdir(exist_ok=True)
        self.history = history
        self.context = context
        self.ui = ui

    def save_session(self, name):
        data = {"history": self.history.messages, "context": self.context.list_files()}
        with open(self.dir / f"{name}.json", 'w') as f:
            json.dump(data, f)
