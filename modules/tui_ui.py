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
            # Якщо функція асинхронна (як _confirm_action_main_thread), чекаємо її
            if asyncio.iscoroutine(result):
                return await result
            return result
        else:
            # З іншого потоку плануємо в головному циклі Textual
            return await self.app.call_from_thread(func, *args, **kwargs)

    def _add_message(self, renderable=None, classes="chat-message", widget=None):
        """Цей метод виконується в головному потоці (Main Thread)"""
        
        # Add a separator before the message, but only if history is not empty
        if self.history.children:
            separator = Static(classes="message-separator")
            self.history.mount(separator)

        if widget is None:
            # Створюємо віджет з явним розширенням
            widget = Static(renderable, classes=classes, expand=True)
        
        # Монтуємо в контейнер
        self.history.mount(widget)
        
        # Важливо: прокручуємо до кінця саме контейнер історії
        # scroll_end гарантує, що ми побачимо нове повідомлення
        self.history.scroll_end(animate=False)


    def _start_thinking(self):
        self.loading_label.update("Thinking...") # Оновлюємо текст
        self.loading_container.display = True   # Показуємо весь блок

    def _start_action(self, text: str):
        # Якщо тексту немає, ставимо стандартний статус
        status_text = text if text else "Processing..."
        self.loading_label.update(status_text)   # Оновлюємо текст на статус операції
        self.loading_container.display = True    # Показуємо блок

    def _stop_loading(self):
        self.loading_container.display = False   # Ховаємо блок, коли операцію завершено

    async def _confirm_action_main_thread(self, action_details: dict) -> bool:
        return await self.app.push_screen(ConfirmationScreen(action_details))

    async def _confirm_continue_main_thread(self, prompt: str) -> bool:
        return await self.app.push_screen(ContinueConfirmationScreen(prompt))

    # --- Публічні методи для агента (всі ASYNC) ---

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
        # ВИПРАВЛЕНО: додано async та await
        await self._call_ui(self._add_message, f"[bold red]✘ Error:[/] {text}")

   # modules/tui_ui.py

    async def print_message(self, text, role="assistant"):
        if role == "assistant":
            # ВИПРАВЛЕНО: замість MarkdownWidget використовуємо Static + RichMarkdown
            # Це прибирає порожні рядки, які додає стандартний віджет Textual
            clean_text = text.strip()
            markdown_renderable = RichMarkdown(clean_text)
            await self._call_ui(self._add_message, markdown_renderable, classes="chat-message assistant-message")
        else:
            # For User, just the text with a '>' prefix
            renderable = Text(f"> {text.strip()}", style="rgb(100,200,100)")
            await self._call_ui(self._add_message, renderable, classes="chat-message user-message")


    async def print_thought(self, text):
        if text.strip():
            # Додаємо .strip() для впевненості
            await self._call_ui(self._add_message, 
                                f"[grey37][italic]💭 {text.strip()}[/italic][/grey37]", 
                                classes="chat-message thought-message")

    async def print_plan(self, text):
        # ВИПРАВЛЕНО: видалено \n перед текстом
        await self._call_ui(self._add_message, f"[bold cyan]🤖 Plan:[/] {text.strip()}")

        async def print_command_result(self, text):

            # Додано пробіл після "RESULT:" для кращого вигляду

            await self._call_ui(self._add_message, f"[bold white]SYSTEM RESULT:[/] {text.strip()}")

    async def print_confirmation(self, text):
        await self._call_ui(self._add_message, f"[bold green]✅ {text.strip()}[/]")
