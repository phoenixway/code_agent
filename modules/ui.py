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
        """Prints a message to the console in a chat history format."""
        if role == "assistant":
            self.console.print(f"\n[bold white]🤖 Angelica:[/]\n", end="")
            md = Markdown(text)
            self.console.print(md)
        else: # user
            self.console.print(f"[bold green]👤 You:[/bold green] {text}")
            
    def prompt_user(self, stats):
        """Displays a styled prompt and gets user input."""
        prompt_text = f" [dim]Files in context:{stats[0]} | Tokens: ~{stats[1]}tk[/dim]"
        self.console.print("")
        self.console.print(
            Panel(
                prompt_text,
                title="[bold green]Your turn[/bold green]",
                border_style="green",
                padding=(0, 1),
                expand=False
            )
        )
        return self.console.input("❯ ")

    def print_horizontal_rule(self):
        self.console.print("—" * 50)

    def print_thought(self, text):
        """Renders the AI's thoughts in a subtle, italic style."""
        if text.strip():
            self.console.print(f"[grey37][italic]💭 {text.strip()}[/italic][/grey37]")