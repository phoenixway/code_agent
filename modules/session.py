# modules/session.py
import json
import os
import asyncio

class SessionManager:
    def __init__(self, history, context, ui):
        self.session_file = os.path.join(os.getcwd(), ".angelica_session.json")
        self.history = history
        self.context = context
        self.ui = ui

    def save_session(self):
        data = {"history": self.history.messages, "context": list(self.context.basket.keys())}
        with open(self.session_file, 'w') as f:
            json.dump(data, f)

    def load_session(self):
        if os.path.exists(self.session_file):
            with open(self.session_file, 'r') as f:
                data = json.load(f)
            self.history.messages = data.get("history", [])
            
            # Restore context
            for file_path in data.get("context", []):
                self.context.add_path(file_path)
            
            # Optionally, notify UI
            if self.ui:
                asyncio.create_task(self.ui.print_system("💾 Session loaded."))

    def clear_session(self):
        if os.path.exists(self.session_file):
            os.remove(self.session_file)
            return True
        return False
