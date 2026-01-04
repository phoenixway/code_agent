# modules/ui.py
from rich.console import Console
from rich.panel import Panel
from rich.markdown import Markdown
from rich.syntax import Syntax

class UI:
    def __init__(self):
        self.console = Console()

    def print_system(self, text):
        self.console.print(f"[bold blue]ℹ[/] {text}")

    def print_error(self, text):
        self.console.print(f"[bold red]✘ Error:[/] {text}")

    def print_message(self, text, role="assistant"):
        color = "cyan" if role == "assistant" else "green"
        title = "🤖 Angelica" if role == "assistant" else "👤 You"
        self.console.print(Panel(Markdown(text), title=title, border_style=color))

    def print_horizontal_rule(self):
        self.console.print("—" * 50)
