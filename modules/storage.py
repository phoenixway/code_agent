import json
import os
from datetime import datetime

class Storage:
    def __init__(self, session_dir="sessions"):
        self.session_dir = session_dir
        if not os.path.exists(session_dir):
            os.makedirs(session_dir)
        self.current_session = f"session_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
        self.history = []

    def save_message(self, role, content):
        self.history.append({"role": role, "content": content, "timestamp": str(datetime.now())})
        with open(os.path.join(self.session_dir, self.current_session), "w", encoding="utf-8") as f:
            json.dump(self.history, f, indent=4, ensure_ascii=False)

# Тестовий виклик
if __name__ == "__main__":
    s = Storage()
    s.save_message("user", "Hello")
    print(f"Збережено в {s.current_session}")