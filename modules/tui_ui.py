import threading
import asyncio
from textual.widgets import Static
from textual.containers import Vertical, VerticalScroll, Container, Horizontal
from textual.app import ComposeResult
from rich.markdown import Markdown as RichMarkdown
from rich.text import Text

class MiniPicker(Static, can_focus=True):
    """Мінімалістичний CLI-пайкер для підтвердження."""
    def __init__(self, prompt: str, options: list, future: asyncio.Future):
        super().__init__()
        self.prompt = prompt
        self.options = options
        self.future = future
        self.index = 0 

    def render(self) -> Text:
        lines = [Text(f"{self.prompt}", style="bold yellow")]
        for i, opt in enumerate(self.options):
            if i == self.index:
                lines.append(Text(f" > {opt}", style="bold cyan"))
            else:
                lines.append(Text(f"   {opt}", style="dim"))
        return Text("\n").join(lines)

    def on_key(self, event) -> None:
        if event.key in ("up", "k"):
            self.index = (self.index - 1) % len(self.options)
            self.refresh()
        elif event.key in ("down", "j"):
            self.index = (self.index + 1) % len(self.options)
            self.refresh()
        elif event.key == "enter":
            self.future.set_result(self.index == 0)
        elif event.key == "y":
            self.future.set_result(True)
        elif event.key == "n":
            self.future.set_result(False)

class TuiUI:
    def __init__(self, app, history_widget: VerticalScroll, loading_container: Container, loading_label: Static):
        self.app = app
        self.history = history_widget
        self.loading_container = loading_container
        self.loading_label = loading_label
        self.main_thread = threading.main_thread()

    async def _call_ui(self, func, *args, **kwargs):
        if threading.current_thread() is self.main_thread:
            res = func(*args, **kwargs)
            return await res if asyncio.iscoroutine(res) else res
        else:
            return await self.app.call_from_thread(func, *args, **kwargs)

    # --- Методи керування станом індикатора ---

    def _start_thinking(self):
        self.loading_label.update("Thinking...")
        self.loading_container.display = True

    def _start_action(self, text: str):
        self.loading_label.update(text if text else "Processing...")
        self.loading_container.display = True

    def _stop_loading(self):
        self.loading_container.display = False

    def _update_header_main_thread(self, text: str):
        self.app.title = text

    # --- Методи виклику Picker ---

    async def _show_picker_main_thread(self, prompt: str, options: list) -> bool:
        loop = asyncio.get_running_loop()
        future = loop.create_future()
        picker = MiniPicker(prompt, options, future)

        input_container = self.app.query_one("#input-container")
        await self.app.mount(picker, before=input_container)
        
        picker.focus()
        try:
            return await future
        finally:
            await picker.remove()
            self.app.query_one("#input").focus()

    # --- Public API для Agent ---

    async def start_thinking(self):
        await self._call_ui(self._start_thinking)

    async def start_action(self, text: str):
        await self._call_ui(self._start_action, text)

    async def stop_loading(self):
        await self._call_ui(self._stop_loading)

    async def update_header(self, text: str):
        await self._call_ui(self._update_header_main_thread, text)

    async def confirm_action(self, action_details: dict) -> bool:
        action_type = action_details.get("type", "action")
        target = action_details.get("path") or action_details.get("command") or ""
        prompt = f"Allow {action_type} on {target}?"
        return await self._call_ui(self._show_picker_main_thread, prompt, ["y (Allow)", "n (Deny)"])

    async def confirm_continue(self, prompt: str) -> bool:
        return await self._call_ui(self._show_picker_main_thread, prompt, ["Continue", "Stop"])

    # --- Методи друку ---

    def _add_message(self, renderable=None, classes="chat-message", widget=None):
        if widget is None:
            widget = Static(renderable, classes=classes, expand=False)
            widget.can_focus = False 
        self.history.mount(widget)
        self.history.scroll_end(animate=False)

    async def print_system(self, text):
        await self._call_ui(self._add_message, f" {text} ", classes="chat-message system-message")

    async def print_error(self, text):
        await self._call_ui(self._add_message, f"[bold red]✘ Error:[/] {text}")

    async def print_message(self, text, role="assistant"):
        if role == "assistant":
            await self._call_ui(self._add_message, RichMarkdown(text.strip()), classes="chat-message assistant-message")
        else:
            await self._call_ui(self._add_message, Text(f"> {text.strip()}", style="rgb(100,200,100)"), classes="chat-message user-message")

    async def print_thought(self, text):
        if text.strip():
            await self._call_ui(self._add_message, f"[grey37][italic]{text.strip()}[/italic][/grey37]", classes="chat-message thought-message")

    async def print_plan(self, text):
        await self._call_ui(self._add_message, f"[bold cyan]🤖 Plan:[/] {text.strip()}")

    async def print_command_result(self, text):
        await self._call_ui(self._add_message, f"[bold white]SYSTEM RESULT:[/] {text.strip()}")

    async def print_confirmation(self, text):
        await self._call_ui(self._add_message, f"[bold green]✅ {text.strip()}[/]")
