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
        """Виводить текст відповіді, рендерячи Markdown."""
        color = "cyan" if role == "assistant" else "green"
        title = "🤖 Angelica" if role == "assistant" else "👤 You"
        
        # Ми рендеримо весь текст. Rich автоматично підсвітить блоки коду 
        # та прибере зайві символи Markdown.
        md = Markdown(text)
        self.console.print(Panel(md, title=title, border_style=color))

    def print_horizontal_rule(self):
        self.console.print("—" * 50)

    def print_thought(self, text):
        """Рендерить блок міркувань ШІ."""
        if not text.strip(): return
        # Використовуємо спеціальний колір та італік для думок
        self.console.print(f"[bold grey37]💭 Міркування:[/][grey37][italic] {text.strip()}[/]")