import threading
import asyncio
import json

from textual.widgets import Static
from textual.containers import VerticalScroll
from rich.markdown import Markdown as RichMarkdown
from rich.text import Text
from rich.markup import escape

from modules.ui_components.selection_widget import SelectionScreen
from modules.ui_components.status_bar import StatusBar
from modules.ui_components.diff_viewer import DiffViewer


class TuiUI:
    def __init__(self, app, history_widget: VerticalScroll, status_bar: StatusBar):
        self.app = app
        self.history = history_widget
        self.status_bar = status_bar
        self.main_thread = threading.main_thread()

    # ---------------------------------------------------------------------
    # Thread-safe UI dispatcher
    # ---------------------------------------------------------------------

    async def _call_ui(self, func, *args, **kwargs):
        if threading.current_thread() is self.main_thread:
            result = func(*args, **kwargs)
            return await result if asyncio.iscoroutine(result) else result
        return await self.app.call_from_thread(func, *args, **kwargs)

    # ---------------------------------------------------------------------
    # Status bar control
    # ---------------------------------------------------------------------

    def _start_thinking(self):
        self.status_bar.start_thinking()

    def _start_action(self, text: str):
        self.status_bar.start_action(text)

    def _stop_loading(self):
        self.status_bar.stop()

    def _update_header_main_thread(self, text: str):
        self.app.title = text

    async def start_thinking(self):
        await self._call_ui(self._start_thinking)

    async def start_action(self, text: str):
        await self._call_ui(self._start_action, text)

    async def stop_loading(self):
        await self._call_ui(self._stop_loading)

    async def update_header(self, text: str):
        await self._call_ui(self._update_header_main_thread, text)

    # ---------------------------------------------------------------------
    # Screens & confirmations
    # ---------------------------------------------------------------------

    async def _pick_screen_main_thread(self, screen):
        loop = asyncio.get_running_loop()
        future = loop.create_future()

        def callback(result):
            if not future.done():
                future.set_result(result)

        self.app.push_screen(screen, callback=callback)
        return await future

    async def pick_option(self, prompt: str, options: list, current_value: str | None = None) -> str:
        screen = SelectionScreen(prompt, options, current_value=current_value)
        return await self._call_ui(self._pick_screen_main_thread, screen)

    async def confirm_action(self, action_details: dict) -> bool:
        action_type = action_details.get("type", "unknown")
        details = (
            action_details.get("command")
            or action_details.get("path")
            or action_details.get("file_path")
            or ""
        )

        prompt = (
            "[bold yellow]⚠ Action confirmation[/]\n\n"
            f"[bold]Type:[/] {action_type}\n"
            f"[bold]Details:[/] {details}"
        )

        screen = SelectionScreen(prompt, ["Allow", "Deny"])
        result = await self._call_ui(self._pick_screen_main_thread, screen)
        return result == "Allow"

    async def confirm_continue(self, prompt: str) -> bool:
        screen = SelectionScreen(prompt, ["Continue", "Stop"])
        result = await self._call_ui(self._pick_screen_main_thread, screen)
        return result == "Continue"

    async def confirm_truncation(self, action_type: str, output_length: int) -> bool:
        prompt = (
            f"The output of '{action_type}' is very long "
            f"({output_length} characters).\nWhat would you like to do?"
        )
        screen = SelectionScreen(prompt, ["Truncate", "Show Full Output"])
        result = await self._call_ui(self._pick_screen_main_thread, screen)
        return result == "Truncate"

    async def show_diff_preview(self, proposal) -> bool:
        screen = DiffViewer(proposal)
        return await self._call_ui(self._pick_screen_main_thread, screen)

    # ---------------------------------------------------------------------
    # Message mounting
    # ---------------------------------------------------------------------

    def _add_message(self, renderable=None, classes="chat-message", widget=None):
        if widget is None:
            widget = Static(renderable, classes=classes, expand=False)
            widget.can_focus = False

        self.history.mount(widget)
        self.history.scroll_end(animate=False)

    # ---------------------------------------------------------------------
    # Printing helpers
    # ---------------------------------------------------------------------

    async def print_system(self, text: str):
        await self._call_ui(
            self._add_message,
            f" {text} ",
            classes="chat-message system-message",
        )

    async def print_error(self, text: str):
        await self._call_ui(
            self._add_message,
            f"[bold red]✘ Error:[/] {text}",
            classes="chat-message error-message",
        )

    async def print_message(self, text: str, role: str = "assistant"):
        if role == "assistant":
            await self._call_ui(
                self._add_message,
                RichMarkdown(text.strip()),
                classes="chat-message assistant-message",
            )
        else:
            await self._call_ui(
                self._add_message,
                Text(f"> {text.strip()}"),
                classes="chat-message user-message",
            )

    async def print_thought(self, text: str):
        if text.strip():
            await self._call_ui(
                self._add_message,
                f"[italic grey37]{text.strip()}[/]",
                classes="chat-message thought-message",
            )

    async def print_plan(self, text: str):
        await self._call_ui(
            self._add_message,
            f"[bold cyan]🤖 Plan:[/] {text.strip()}",
            classes="chat-message plan-message",
        )

    async def print_confirmation(self, text: str):
        await self._call_ui(
            self._add_message,
            f"[bold green]✅ {text.strip()}[/]",
            classes="chat-message confirmation-message",
        )

    # ---------------------------------------------------------------------
    # Tool call rendering
    # ---------------------------------------------------------------------

    def _render_tool_call_widget(self, command: dict) -> Static:
        tool_name = command.get("type") or command.get("action", "unknown")

        args = {
            k: v for k, v in command.items()
            if k not in {
                "type",
                "action",
                "before_execution",
                "during_execution",
                "after_execution",
                "return_control",
            }
        }

        md_lines = [f"**🔧 Tool Call: {tool_name}**"]
        if args:
            try:
                args_json = json.dumps(args, indent=2, ensure_ascii=False)
                md_lines.append(f"```json\n{args_json}\n```")
            except Exception:
                md_lines.append(f"```\n{str(args)}\n```")
        
        renderable = RichMarkdown("\n\n".join(md_lines))
        widget = Static(renderable, classes="chat-message tool-call-message")
        widget.command = command # Attach command for later use
        return widget

    async def print_tool_call(self, command: dict) -> Static:
        widget = self._render_tool_call_widget(command)
        await self._call_ui(self._add_message, widget=widget)
        return widget

    async def print_shell_start(self, command: dict) -> Static:
        """Prints the initial state for a shell command and returns the widget."""
        before_text = command.get('before_execution', 'Starting shell command...')
        renderable = RichMarkdown(f"🤖 {before_text}")
        widget = Static(renderable, classes="chat-message plan-message")
        widget.command = command
        await self._call_ui(self._add_message, widget=widget)
        return widget

    def _render_shell_result(self, command: dict, result: dict) -> RichMarkdown:
        shell_command = command.get('command', '')
        after_execution = command.get('after_execution')
        output = result.get('output', '')
        status = result.get('status')

        md_parts = []

        # 1. Add after_execution text first, if it exists
        if status == 'success' and after_execution:
            after_exec_plain = f"✅ {after_execution.strip()}"
            md_parts.append(after_exec_plain)

        # 2. Add the result box
        if status == 'success':
            icon_char = '✔'
        else:
            icon_char = '✘'
        
        result_box = f"""```sh
{icon_char} run_shell: {shell_command}
---
{escape(output.strip())}
```
"""
        md_parts.append(result_box)

        # 3. Join them with newlines
        md_content = "\n\n".join(md_parts)

        return RichMarkdown(md_content)

    async def update_shell_result(self, widget: Static, result: dict):
        """Updates the shell command widget with the final result."""
        command = getattr(widget, 'command', {})
        new_renderable = self._render_shell_result(command, result)
        await self._call_ui(widget.update, new_renderable)

    # ---------------------------------------------------------------------
    # Tool result rendering
    # ---------------------------------------------------------------------

    def _render_tool_result(self, text: str, truncated: bool = False) -> Static:
        subtitle = " (truncated)" if truncated else ""
        md_lines = [f"**✅ Result**{subtitle}"]
        
        # Avoids creating an empty code block if there's no text
        if text and text.strip():
            md_lines.append(f"```\n{escape(text.strip())}\n```")

        renderable = RichMarkdown("\n\n".join(md_lines))
        return Static(renderable, classes="chat-message tool-result-message")

    async def print_command_result(self, text: str, truncated: bool = False):
        widget = self._render_tool_result(text, truncated)
        await self._call_ui(self._add_message, widget=widget)
