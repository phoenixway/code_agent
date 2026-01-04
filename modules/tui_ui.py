# modules/tui_ui.py

import threading
import asyncio
from textual.widgets import ListView, Static
from textual.containers import Container
from rich.markdown import Markdown
from rich.panel import Panel
from rich.text import Text
from rich.console import Group

# Import ConfirmationScreen - this will create a circular import, but Textual handles it
from tui import ConfirmationScreen


class TuiUI:
    def __init__(self, app, history_widget: ListView, loading_container: Container, loading_label: Static):
        self.app = app
        self.history = history_widget
        self.loading_container = loading_container
        self.loading_label = loading_label
        self.main_thread = threading.main_thread()

    async def _call_ui(self, func, *args, **kwargs):
        """Safely call a UI update or action from any thread, awaiting result if needed."""
        if threading.current_thread() is self.main_thread:
            # If already on main thread, call directly
            result = func(*args, **kwargs)
        else:
            # From worker thread, schedule on main thread and await result
            result = await self.app.call_from_thread(func, *args, **kwargs)
        return result

    # --- Private methods for actual UI updates (always run on main thread) ---

    def _add_message(self, renderable, classes="chat-message"):
        self.history.mount(Static(renderable, classes=classes))
        self.history.scroll_end(animate=False)

    def _start_thinking(self):
        self.loading_label.update("Thinking...")
        self.loading_container.display = True

    def _start_action(self, text: str):
        self.loading_label.update(text)
        self.loading_container.display = True

    def _stop_loading(self):
        self.loading_container.display = False

    async def _confirm_action_main_thread(self, action_details: dict) -> bool:
        """Pushes the confirmation screen on the main thread and awaits result."""
        result = await self.app.push_screen(ConfirmationScreen(action_details))
        return result

    # --- Public methods to be called from the agent ---

    def start_thinking(self):
        self._call_ui(self._start_thinking)

    def start_action(self, text: str):
        self._call_ui(self._start_action, text)

    def stop_loading(self):
        self._call_ui(self._stop_loading)

    async def confirm_action(self, action_details: dict) -> bool:
        """Asks the user for confirmation for a sensitive action."""
        return await self._call_ui(self._confirm_action_main_thread, action_details)

    def print_system(self, text):
        self._call_ui(self._add_message, f"[bold blue]ℹ[/] {text}")

    def print_error(self, text):
        self._call_ui(self._add_message, f"[bold red]✘ Error:[/] {text}")

    def print_message(self, text, role="assistant"):
        if role == "assistant":
            renderable = Group(
                Text.from_markup("[bold white]🤖 Angelica:[/bold white]"),
                Markdown(text)
            )
            self._call_ui(self._add_message, renderable)
        else: # user
            self._call_ui(self._add_message, f"[bold green]👤 You:[/bold green] {text}")

    def print_thought(self, text):
        if text.strip():
            self._call_ui(self._add_message, 
                          f"[grey37][italic]💭 {text.strip()}[/italic][/grey37]", 
                          classes="chat-message thought-message")

    def print_plan(self, text):
        self._call_ui(self._add_message, f"\n[bold cyan]🤖 Plan:[/] {text}")
    
    def print_command_result(self, text):
        self._call_ui(self._add_message, f"SYSTEM RESULT:\n{text}")

    def print_confirmation(self, text):
        self._call_ui(self._add_message, f"[bold green]✅ {text}[/]")
