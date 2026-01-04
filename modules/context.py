# modules/context.py
class ContextManager:
    def __init__(self, files_module):
        self.files = files_module
        self.basket = {}

    def add_file(self, path):
        content = self.files.read_file(path)
        if content:
            self.basket[path] = content
            return True
        return False

    def remove_file(self, path):
        return self.basket.pop(path, None) is not None

    def clear(self):
        self.basket.clear()

    def get_stats(self):
        chars = sum(len(c) for c in self.basket.values())
        return len(self.basket), chars // 4

    def get_context_prompt(self):
        if not self.basket: return ""
        out = "\n--- CONTEXT ---\n"
        for p, c in self.basket.items():
            out += f"FILE: {p}\n{c}\n---\n"
        return out

    def list_files(self):
        return list(self.basket.keys())
