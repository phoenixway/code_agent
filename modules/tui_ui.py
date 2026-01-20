import threading
import asyncio
from textual.widgets import Static
from textual.containers import Vertical, VerticalScroll, Container, Horizontal
from textual.app import ComposeResult
from rich.markdown import Markdown as RichMarkdown
from rich.text import Text

from modules.ui_components.selection_widget import SelectionScreen
from modules.ui_components.status_bar import StatusBar
from modules.ui_components.diff_viewer import DiffViewer

class TuiUI:
    def __init__(self, app, history_widget: VerticalScroll, status_bar: StatusBar):
        self.app = app
        self.history = history_widget
        self.status_bar = status_bar
        self.main_thread = threading.main_thread()

    async def _call_ui(self, func, *args, **kwargs):
        if threading.current_thread() is self.main_thread:
            res = func(*args, **kwargs)
            return await res if asyncio.iscoroutine(res) else res
        else:
            return await self.app.call_from_thread(func, *args, **kwargs)

    # --- Методи керування станом індикатора ---

    def _start_thinking(self):
        self.status_bar.start_thinking()

    def _start_action(self, text: str):
        self.status_bar.start_action(text)

    def _stop_loading(self):
        self.status_bar.stop()

    def _update_header_main_thread(self, text: str):
        self.app.title = text

    # --- Public API для Agent ---

    async def start_thinking(self):
        await self._call_ui(self._start_thinking)

    async def start_action(self, text: str):
        await self._call_ui(self._start_action, text)

    async def stop_loading(self):
        await self._call_ui(self._stop_loading)

    async def update_header(self, text: str):
        await self._call_ui(self._update_header_main_thread, text)

    async def _pick_screen_main_thread(self, screen):
        # Manually manage future to work around push_screen_wait worker requirement
        self.app.agent.log.info(f"DEBUG: Entering _pick_screen_main_thread with screen: {screen}")
        loop = asyncio.get_running_loop()
        future = loop.create_future()

        def callback(result):
            self.app.agent.log.info(f"DEBUG: Screen callback triggered with result: {result}")
            if not future.done():
                future.set_result(result)

        self.app.push_screen(screen, callback=callback)
        self.app.agent.log.info("DEBUG: Screen pushed, awaiting future")
        res = await future
        self.app.agent.log.info(f"DEBUG: Future resolved in _pick_screen_main_thread: {res}")
        return res

    async def pick_option(self, prompt: str, options: list, current_value: str | None = None) -> str:
        """Показує меню вибору і повертає вибрану строку."""
        self.app.agent.log.info(f"DEBUG: pick_option called with prompt: '{prompt}'")
        screen = SelectionScreen(prompt, options, current_value=current_value)
        return await self._call_ui(self._pick_screen_main_thread, screen)

    async def confirm_action(self, action_details: dict) -> bool:
        self.app.agent.log.info(f"DEBUG: confirm_action called for: {action_details.get('type')}")
        
        # Build a descriptive prompt
        action_type = action_details.get("type", "Unknown")
        details = ""
        if action_type == "run_command":
            details = action_details.get("command", "")
        elif action_type in ["write_file", "create_file", "edit_file"]:
            details = action_details.get("path") or action_details.get("file_path", "")
            
        prompt = f"ALLOW ACTION?\nType: {action_type}\nDetails: {details}"
        screen = SelectionScreen(prompt, ["Allow", "Deny"])
        result = await self._call_ui(self._pick_screen_main_thread, screen)
        return result == "Allow"

    async def show_diff_preview(self, proposal) -> bool:
        """Shows the DiffViewer and returns True if approved."""
        self.app.agent.log.info(f"DEBUG: show_diff_preview for {proposal.file_path}")
        screen = DiffViewer(proposal)
        return await self._call_ui(self._pick_screen_main_thread, screen)

    async def confirm_continue(self, prompt: str) -> bool:
        self.app.agent.log.info(f"DEBUG: confirm_continue called with prompt: '{prompt}'")
        options = ["Continue", "Stop"]
        screen = SelectionScreen(prompt, options)
        result = await self._call_ui(self._pick_screen_main_thread, screen)
        return result == "Continue"

    async def confirm_truncation(self, action_type: str, output_length: int) -> bool:
        """Asks the user if they want to truncate the output."""
        self.app.agent.log.info(f"DEBUG: confirm_truncation called for: {action_type}")
        
        prompt = f"The output of '{action_type}' is very long ({output_length} characters). What would you like to do?"
        options = ["Truncate", "Show Full Output"]
        screen = SelectionScreen(prompt, options)
        result = await self._call_ui(self._pick_screen_main_thread, screen)
        return result == "Truncate"

    # --- Методи друку ---

    def _add_message(self, renderable=None, classes="chat-message", widget=None):
        self.app.agent.log.info(f"DEBUG: _add_message called with classes: {classes}")
        if widget is None:
            widget = Static(renderable, classes=classes, expand=False)
            widget.can_focus = False 
        self.history.mount(widget)
        self.history.scroll_end(animate=False)
        self.app.agent.log.info("DEBUG: Message mounted and scrolled")

    async def print_system(self, text):
        self.app.agent.log.info(f"DEBUG: print_system: '{text}'")
        await self._call_ui(self._add_message, f" {text} ", classes="chat-message system-message")

    async def print_error(self, text):
        self.app.agent.log.info(f"DEBUG: print_error: '{text}'")
        await self._call_ui(self._add_message, f"[bold red]✘ Error:[/] {text}")

    async def print_message(self, text, role="assistant"):
        self.app.agent.log.info(f"DEBUG: print_message (role={role}): '{text[:50]}...'")
        if role == "assistant":
            await self._call_ui(self._add_message, RichMarkdown(text.strip()), classes="chat-message assistant-message")
        else:
            # Removed hardcoded style="rgb(100,200,100)" to use theme from CSS
            await self._call_ui(self._add_message, Text(f"> {text.strip()}"), classes="chat-message user-message")
        self.app.agent.log.info("DEBUG: print_message completed")

    async def print_thought(self, text):
        if text.strip():
            await self._call_ui(self._add_message, f"[grey37][italic]{text.strip()}[/italic][/grey37]", classes="chat-message thought-message")

    async def print_plan(self, text):
        await self._call_ui(self._add_message, f"[bold cyan]🤖 Plan:[/] {text.strip()}")

    async def print_command_result(self, text, command_name=None):
        prefix = f"[dim]❯ {command_name}[/]\n" if command_name else ""
        await self._call_ui(self._add_message, f"{prefix}{text.strip()}", classes="chat-message result-message")

    async def print_confirmation(self, text):
        await self._call_ui(self._add_message, f"[bold green]✅ {text.strip()}[/]")