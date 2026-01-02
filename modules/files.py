import difflib
import os
from rich.console import Console
from rich.panel import Panel

class FileModule:
    def __init__(self):
        self.console = Console()

    def show_diff(self, filename, old_content, new_content):
        # Генерує та показує різницю між старою та новою версією
        diff = difflib.unified_diff(
            old_content.splitlines(),
            new_content.splitlines(),
            fromfile=f"a/{filename}",
            tofile=f"b/{filename}",
            lineterm=""
        )
        diff_text = "\n".join(list(diff))
        if diff_text:
            self.console.print(Panel(diff_text, title="Proposed Changes (Diff)", border_style="yellow"))
            return True
        return False

    def write_file(self, path, content):
        try:
            with open(path, "w", encoding="utf-8") as f:
                f.write(content)
            return True
        except Exception as e:
            return str(e)

# Тестовий виклик
if __name__ == "__main__":
    fm = FileModule()
    fm.show_diff("test.py", "print(1)", "print(2)")