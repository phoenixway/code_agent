# modules/tui_ui.py

from textual.widgets import RichLog
from rich.markdown import Markdown
from rich.panel import Panel

class TuiUI:
    def __init__(self, history_widget: RichLog):
        self.history = history_widget

    def print_system(self, text):
        self.history.write(f"[bold blue]ℹ[/] {text}")

    def print_error(self, text):
        self.history.write(f"[bold red]✘ Error:[/] {text}")

    def print_message(self, text, role="assistant"):
        if role == "assistant":
            md = Markdown(text)
            self.history.write(Panel(md, title="🤖 Angelica", border_style="cyan", expand=False))
        else: # user
            self.history.write(f"[bold green]👤 You:[/bold green] {text}")

    def print_thought(self, text):
        if text.strip():
            md = Markdown(text)
            self.history.write(Panel(md, title="💭 Reasoning", border_style="grey37", expand=False))

    def print_plan(self, text):
        self.history.write(f"\n[bold cyan]🤖 Plan:[/] {text}")
    
    def print_command_result(self, text):
        self.history.write(f"SYSTEM RESULT:\n{text}")

    def print_confirmation(self, text):
         self.history.write(f"[bold green]✅ {text}[/]")
