# modules/tui_ui.py

import threading
import asyncio
from textual.widgets import Static, Button, Markdown as MarkdownWidget
from textual.containers import Horizontal, Vertical, VerticalScroll, Container
from textual.screen import Screen
from textual.app import ComposeResult
from rich.markdown import Markdown, Markdown as RichMarkdown
from rich.text import Text
from rich.console import Group
from rich.table import Table

class ConfirmationScreen(Screen[bool]):
    """Екран підтвердження для небезпечних дій."""
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

class ContinueConfirmationScreen(Screen[bool]):
    """A generic confirmation screen."""
    def __init__(self, prompt: str, **kwargs) -> None:
        super().__init__(**kwargs)
        self.prompt = prompt

    def compose(self) -> ComposeResult:
        yield Vertical(
            Static(f"[bold yellow]⚠️  Confirmation Required ⚠️[/bold yellow]", classes="confirmation-title"),
            Static(self.prompt, classes="confirmation-detail"),
            Horizontal(
                Button("Continue", id="continue_button", variant="success"),
                Button("Stop", id="stop_button", variant="error"),
                classes="confirmation-buttons"
            ),
            classes="confirmation-panel"
        )

    def on_button_pressed(self, event: Button.Pressed) -> None:
        if event.button.id == "continue_button":
            self.dismiss(True)
        elif event.button.id == "stop_button":
            self.dismiss(False)


class ModelSelectionScreen(Screen[str]):
    """A screen to allow the user to select a model."""
    def __init__(self, models: list[str], current_model: str, **kwargs) -> None:
        super().__init__(**kwargs)
        self.models = models
        self.current_model = current_model

    def compose(self) -> ComposeResult:
        yield Vertical(
            Static("[bold cyan]Select a Model[/bold cyan]", classes="confirmation-title"),
            *[
                Button(
                    f"{'>> ' if model == self.current_model else ''}{model}{' <<' if model == self.current_model else ''}",
                    id=f"model_{model.replace('/', '_').replace(':', '__').replace('-', '_')}", # Sanitize ID for Textual
                    variant="primary" if model == self.current_model else "default"
                ) for model in self.models
            ],
            Button("Cancel", id="cancel_button", variant="error"),
            classes="confirmation-panel"
        )

    def on_button_pressed(self, event: Button.Pressed) -> None:
        if event.button.id == "cancel_button":
            self.dismiss("")
        else:
            # We need to map the button ID back to the original model name
            # The simplest way is to find the model name from the list
            # A more robust solution might involve storing a map, but for now this is fine.
            # Assuming button.id starts with "model_"
            selected_id_prefix = "model_"
            if event.button.id.startswith(selected_id_prefix):
                # Reverse the sanitization
                original_model_candidate = event.button.id[len(selected_id_prefix):].replace('__', ':').replace('_', '/')
                # Find the actual model from the list
                selected_model = next((m for m in self.models if m == original_model_candidate), "")
                self.dismiss(selected_model)
            else:
                self.dismiss("") # Should not happen for model buttons

class TuiUI:
    def __init__(self, app, history_widget: VerticalScroll, loading_container: Container, loading_label: Static):
        self.app = app
        self.history = history_widget
        self.loading_container = loading_container
        self.loading_label = loading_label
        self.main_thread = threading.main_thread()

    async def _call_ui(self, func, *args, **kwargs):
        """Безпечний виклик оновлення UI з будь-якого потоку."""
        if threading.current_thread() is self.main_thread:
            result = func(*args, **kwargs)
            if asyncio.iscoroutine(result):
                return await result
            return result
        else:
            return await self.app.call_from_thread(func, *args, **kwargs)

    def _add_message(self, renderable=None, classes="chat-message", widget=None):
        """Додає повідомлення в історію."""
        if widget is None:
            widget = Static(renderable, classes=classes, expand=False)
            widget.can_focus = False 
        
        self.history.mount(widget)
        self.history.scroll_end(animate=False)


    def _start_thinking(self):
        self.loading_label.update("Thinking...")
        self.loading_container.display = True

    def _start_action(self, text: str):
        status_text = text if text else "Processing..."
        self.loading_label.update(status_text)
        self.loading_container.display = True

    def _stop_loading(self):
        self.loading_container.display = False

    async def _confirm_action_main_thread(self, action_details: dict) -> bool:
        return await self.app.push_screen(ConfirmationScreen(action_details))

    async def _confirm_continue_main_thread(self, prompt: str) -> bool:
        return await self.app.push_screen(ContinueConfirmationScreen(prompt))

    async def _select_model_main_thread(self, models: list[str], current_model: str) -> str:
        return await self.app.push_screen(ModelSelectionScreen(models, current_model))

    # --- Public methods for the agent ---

    async def select_model(self, models: list[str], current_model: str) -> str:
        return await self._call_ui(self._select_model_main_thread, models, current_model)

    async def start_thinking(self):
        await self._call_ui(self._start_thinking)
        
    async def start_action(self, text: str):
        await self._call_ui(self._start_action, text)

    async def stop_loading(self):
        await self._call_ui(self._stop_loading)

    async def confirm_action(self, action_details: dict) -> bool:
        return await self._call_ui(self._confirm_action_main_thread, action_details)

    async def confirm_continue(self, prompt: str) -> bool:
        return await self._call_ui(self._confirm_continue_main_thread, prompt)

    async def print_system(self, text):
        await self._call_ui(self._add_message, f" {text} ", classes="chat-message system-message")


    async def print_error(self, text):
        await self._call_ui(self._add_message, f"[bold red]✘ Error:[/] {text}")

    async def print_message(self, text, role="assistant"):
        if role == "assistant":
            clean_text = text.strip()
            markdown_renderable = RichMarkdown(clean_text)
            await self._call_ui(self._add_message, markdown_renderable, classes="chat-message assistant-message")
        else:
            renderable = Text(f"> {text.strip()}", style="rgb(100,200,100)")
            await self._call_ui(self._add_message, renderable, classes="chat-message user-message")


    async def print_thought(self, text):
        if text.strip():
            await self._call_ui(self._add_message, 
                                f"[grey37][italic]💭 {text.strip()}[/italic][/grey37]", 
                                classes="chat-message thought-message")

    async def print_plan(self, text):
        await self._call_ui(self._add_message, f"[bold cyan]🤖 Plan:[/] {text.strip()}")

    async def print_command_result(self, text):
        await self._call_ui(self._add_message, f"[bold white]SYSTEM RESULT:[/] {text.strip()}")

    async def print_confirmation(self, text):
        await self._call_ui(self._add_message, f"[bold green]✅ {text.strip()}[/]")

