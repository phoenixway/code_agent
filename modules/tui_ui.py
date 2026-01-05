# modules/tui_ui.py

import threading
import asyncio
from textual.widgets import ListView, Static
from textual.containers import Container
from rich.markdown import Markdown
from rich.panel import Panel
from rich.text import Text
from rich.console import Group
import threading
import asyncio
from textual.widgets import ListView, Static, Button
from textual.containers import Container, Horizontal, Vertical
from textual.containers import VerticalScroll
from textual.screen import Screen
from textual.app import ComposeResult

# Import ConfirmationScreen - this will create a circular import, but Textual handles it
# from tui import ConfirmationScreen

# ВИДАЛІТЬ ЦЕЙ РЯДОК: from tui import ConfirmationScreen

class ConfirmationScreen(Screen[bool]):
    """Screen to ask the user for confirmation for sensitive actions."""
    def __init__(self, action_details: dict, **kwargs) -> None:
        super().__init__(**kwargs)
        self.action_details = action_details

    def compose(self) -> ComposeResult:
        action_type = self.action_details.get("type", "Unknown")
        details = ""
        if action_type == "run_command":
            details = self.action_details.get("command", "")
        elif action_type in ["write_file", "create_file", "edit_file"]:
            details = self.action_details.get("path") or self.action_details.get("file_path", "")

        yield Vertical(
            Static(f"[bold yellow]⚠️  ALLOW this action? ⚠️[/bold yellow]", classes="confirmation-title"),
            Static(f"   - Type: [bold cyan]{action_type}[/bold cyan]", classes="confirmation-detail"),
            Static(f"   - Details: [bold red]{details}[/bold red]", classes="confirmation-detail"),
            Horizontal(
                Button("Allow", id="allow_button", variant="success"),
                Button("Deny", id="deny_button", variant="error"),
                classes="confirmation-buttons"
            ),
            classes="confirmation-panel"
        )

    def on_button_pressed(self, event: Button.Pressed) -> None:
        if event.button.id == "allow_button":
            self.dismiss(True)
        elif event.button.id == "deny_button":
            self.dismiss(False)

class TuiUI:
    # ... (весь інший код TuiUI залишається без змін) ...
    async def _confirm_action_main_thread(self, action_details: dict) -> bool:
        """Pushes the confirmation screen on the main thread and awaits result."""
        # Тепер ConfirmationScreen знаходиться в цьому ж файлі
        result = await self.app.push_screen(ConfirmationScreen(action_details))
        return result
    # ...


class TuiUI:
    def __init__(self, app, history_widget: VerticalScroll, loading_container: Container, loading_label: Static):
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
        # Створюємо новий віджет
        new_message = Static(renderable, classes=classes)
        # Монтуємо його в контейнер історії
        self.history.mount(new_message)
        # Прокручуємо до кінця (з невеликою затримкою, щоб Textual встиг обробити новий віджет)
        new_message.scroll_visible() 

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
