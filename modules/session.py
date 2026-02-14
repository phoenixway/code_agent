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
        self.loaded_session = False
        self.loaded_messages_count = 0
        self.loaded_context_count = 0
        self._load_notice_emitted = False

    def save_session(self):
        data = {"history": self.history.messages, "context": list(self.context.basket.keys())}
        with open(self.session_file, 'w') as f:
            json.dump(data, f)

    def load_session(self):
        self.loaded_session = False
        self.loaded_messages_count = 0
        self.loaded_context_count = 0

        if os.path.exists(self.session_file):
            with open(self.session_file, 'r') as f:
                data = json.load(f)
            loaded_messages = data.get("history", [])
            self.history.messages = loaded_messages
            self.loaded_messages_count = len(loaded_messages)
            
            # Restore context
            loaded_context = data.get("context", [])
            for file_path in loaded_context:
                self.context.add_path(file_path)
            self.loaded_context_count = len(loaded_context)
            self.loaded_session = bool(self.loaded_messages_count or self.loaded_context_count)
            
            # Optionally, notify UI
            if self.ui:
                self._emit_load_notice()

    def _emit_load_notice(self):
        """Print one-time startup notice about loaded session state."""
        if self._load_notice_emitted or not self.loaded_session or not self.ui:
            return
        self._load_notice_emitted = True
        asyncio.create_task(
            self.ui.print_system(
                f"💾 Session loaded: {self.loaded_messages_count} messages, "
                f"{self.loaded_context_count} context paths."
            )
        )

    def clear_session(self):
        if os.path.exists(self.session_file):
            os.remove(self.session_file)
            self.loaded_session = False
            self.loaded_messages_count = 0
            self.loaded_context_count = 0
            self._load_notice_emitted = False
            return True
        self.loaded_session = False
        self.loaded_messages_count = 0
        self.loaded_context_count = 0
        self._load_notice_emitted = False
        return False
