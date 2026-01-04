# modules/processor.py
import json
import re
import subprocess
from modules.files import EditBlock

class ResponseProcessor:
    def __init__(self, ui, files, chat, policy):
        self.ui = ui
        self.files = files
        self.chat = chat
        self.policy = policy

    def process_response(self, response):
        blocks = re.findall(r"```json\n(.*?)\n```", response, re.DOTALL)
        results = []
        for b in blocks:
            try:
                data = json.loads(b)
                items = data if isinstance(data, list) else [data]
                for item in items:
                    res = self._handle_item(item)
                    if res: results.append(res)
            except: pass
        return "\n".join(results) if results else None

    def _handle_item(self, item):
        t = item.get("type")
        if t == "run_command":
            cmd = item.get("command")
            self.ui.print_system(f"Shell: {cmd}")
            if self.policy.should_ask() and input("Run? (y/n): ") != "y": return "User cancelled"
            r = subprocess.run(cmd, shell=True, capture_output=True, text=True)
            return f"STDOUT: {r.stdout}\nSTDERR: {r.stderr}"
        elif t == "edit_file":
            # Виклик files.apply_edit...
            pass
        return None
