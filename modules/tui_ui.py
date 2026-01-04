# modules/tui_ui.py

from rich.markdown import Markdown
from rich.panel import Panel

class TuiUI:
    def __init__(self, history_widget):
        self.history = history_widget

    def print_system(self, text):
        self.history.write(f"[bold blue]ℹ[/] {text}")

    def print_error(self, text):
        self.history.write(f"[bold red]✘ Error:[/] {text}")

    def print_message(self, text, role="assistant"):
        """Prints a message to the console in a compact, borderless format."""
        if role == "assistant":
            # No panel, just a title and the markdown content
            self.history.write("\n[bold white]🤖 Angelica:[/]")
            md = Markdown(text)
            self.history.write(md)
        else: # user
            # User message is already simple
            self.history.write(f"[bold green]👤 You:[/bold green] {text}")

    def print_thought(self, text):
        """Renders the AI's thoughts in a simple, italic style."""
        if text.strip():
            self.history.write(f"[grey37][italic]💭 {text.strip()}[/italic][/grey37]")

    def print_plan(self, text):
        self.history.write(f"\n[bold cyan]🤖 Plan:[/] {text}")
    
    def print_command_result(self, text):
        self.history.write(f"SYSTEM RESULT:\n{text}")

    def print_confirmation(self, text):
         self.history.write(f"[bold green]✅ {text}[/]")
