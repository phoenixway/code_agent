# modules/tui_ui.py

from textual.widgets import ListView, Static
from rich.markdown import Markdown
from rich.panel import Panel

class TuiUI:
    def __init__(self, history_widget: ListView):
        self.history = history_widget

    def _add_message(self, renderable):
        self.history.mount(Static(renderable, classes="chat-message"))
        self.history.scroll_end(animate=False)

    def print_system(self, text):
        self._add_message(f"[bold blue]ℹ[/] {text}")

    def print_error(self, text):
        self._add_message(f"[bold red]✘ Error:[/] {text}")

    def print_message(self, text, role="assistant"):
        if role == "assistant":
            md = Markdown(text)
            self._add_message(Panel(md, title="🤖 Angelica", border_style="cyan", expand=False))
        else: # user
            self._add_message(f"[bold green]👤 You:[/bold green] {text}")

    def print_thought(self, text):
        if text.strip():
            md = Markdown(text)
            self._add_message(Panel(md, title="💭 Reasoning", border_style="grey37", expand=False))

    def print_plan(self, text):
        self._add_message(f"\n[bold cyan]🤖 Plan:[/] {text}")
    
    def print_command_result(self, text):
        self._add_message(f"SYSTEM RESULT:\n{text}")

    def print_confirmation(self, text):
         self._add_message(f"[bold green]✅ {text}[/]")
