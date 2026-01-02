from rich.console import Console
from rich.markdown import Markdown
from rich.panel import Panel
from rich.syntax import Syntax

class UI:
    def __init__(self):
        self.console = Console()

    def print_message(self, text, title="AI Agent", style="green"):
        # Виводить Markdown повідомлення в рамці
        md = Markdown(text)
        self.console.print(Panel(md, title=title, border_style=style))

    def print_code(self, code, language="python"):
        # Підсвітка коду
        syntax = Syntax(code, language, theme="monokai", line_numbers=True)
        self.console.print(syntax)

    def print_error(self, text):
        self.console.print(f"[bold red]Error:[/bold red] {text}")

# Тестовий виклик
if __name__ == "__main__":
    ui = UI()
    ui.print_message("# Test\nThis is a **bold** message.")
    ui.print_code("print('hello world')", "python")