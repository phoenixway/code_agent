import threading
import asyncio
import functools
import re
import sys
from typing import Any, Optional

from textual.widgets import Static
from textual.containers import VerticalScroll
from rich.markdown import Markdown as RichMarkdown
from rich.text import Text
from rich.markup import escape

from modules.ui_components.selection_widget import SelectionScreen
from modules.ui_components.status_bar import StatusBar
from modules.ui_components.diff_viewer import DiffViewer
from modules.ui_components.token_status_bar import TokenStatusBar
from modules.ui_components.generic_tool_call_card import (
    GenericToolCallCard,
    has_specialized_tool_call_renderer,
)
from modules.ui_components.plan_update_formatter import format_plan_update_compact
from modules.ui_components.technical_interruption_widget import TechnicalInterruptionWidget


class MessageSeparator(Static):
    """A 1-line tall, non-interactive separator widget."""
    def __init__(self):
        super().__init__("", classes="message-separator")


def ui_task(func):
    """Decorator to ensure UI methods run on the main thread and handle async correctly."""
    @functools.wraps(func)
    async def wrapper(self, *args, **kwargs):
        # Якщо ми вже в головному потоці
        if threading.current_thread() is self.main_thread:
            result = func(self, *args, **kwargs)
            # Якщо функція повернула корутину (бо вона async), чекаємо її
            if asyncio.iscoroutine(result):
                return await result
            return result
        
        # Якщо ми в іншому потоці - передаємо виконання в main thread через app.call_from_thread
        return await self.app.call_from_thread(func, self, *args, **kwargs)
    return wrapper


class TuiUI:
    # Centralized configuration for message styles
    STYLES = {
        "system":    {"prefix": "• ", "style": "", "classes": "chat-message system-message"},
        "initial":   {"prefix": "", "style": "center", "classes": "chat-message initial-history-message"},
        "error":     {"prefix": "✘ ", "prefix_style": "bold red", "classes": "chat-message error-message"},
        "thought":   {"prefix": "  ", "style": "italic grey37", "classes": "chat-message thought-message"},
        "plan":      {"prefix": "• ", "prefix_style": "bold cyan", "classes": "chat-message plan-message"},
        "confirmation": {"prefix": "✔ ", "prefix_style": "bold green", "classes": "chat-message confirmation-message"},
        "user":      {"prefix": "", "style": "", "classes": "chat-message user-message"},
    }
    CHAT_OUTPUT_PREVIEW_MAX_CHARS = 4000
    TOOL_ARG_PREVIEW_MAX_CHARS = 1200
    TITLE_SPINNER_FRAMES = (
        "◜",
        "◠",
        "◝",
        "◞",
        "◡",
        "◟",
    )
    TERMINAL_TAB_FRAMES = (
        "·  ",
        "•• ",
        "•••",
        " ••",
        "  •",
    )

    def __init__(self, app, history_widget: VerticalScroll, status_bar: StatusBar):
        self.app = app
        self.history = history_widget
        self.status_bar = status_bar
        self.main_thread = threading.main_thread()
        self._auto_scroll_bottom_threshold = 3
        self._base_header_text = "Angelica"
        self._title_activity_label = ""
        self._title_spinner_index = 0
        self._title_spinner_timer = None

    def _count_confirmation(self):
        """Track how many confirmation dialogs were shown in current session."""
        try:
            agent = getattr(self.app, "agent", None)
            state = getattr(agent, "state", None)
            if state and hasattr(state, "add_confirmation"):
                state.add_confirmation()
        except Exception:
            # Metrics should never break UI flow.
            pass

    # ---------------------------------------------------------------------
    # Helper: Message Mounting
    # ---------------------------------------------------------------------
    
    def _mount_widget(self, widget: Static):
        """Internal helper to mount a widget with a separator."""
        should_follow = self._should_follow_history()
        if self.history.children:
            self.history.mount(MessageSeparator())
        
        self.history.mount(widget)
        if should_follow:
            self.history.scroll_end(animate=False)
        return widget

    def _should_follow_history(self) -> bool:
        """Auto-follow only when the user is already at, or very near, the bottom."""
        try:
            if self.history.is_vertical_scrollbar_grabbed:
                return False
            distance_from_bottom = float(self.history.max_scroll_y) - float(self.history.scroll_target_y)
            return distance_from_bottom <= self._auto_scroll_bottom_threshold
        except Exception:
            return True

    def _create_styled_widget(self, text: str, style_key: str) -> Static:
        """Creates a Static widget based on STYLES config."""
        config = self.STYLES.get(style_key, self.STYLES["system"])
        
        rich_text = Text()
        if config.get("prefix"):
            rich_text.append(config["prefix"], style=config.get("prefix_style", ""))
        
        content_style = config.get("style", "")
        if content_style == "center":
            rich_text = Text(text, justify="center")
        else:
            rich_text.append(text.strip(), style=content_style)

        widget = Static(rich_text, classes=config["classes"], expand=False)
        widget.can_focus = False
        return widget


    def _make_role_label(self, label: str) -> Static:
        widget = Static(Text(label, style="dim bold"), classes="role-label", expand=False)
        widget.can_focus = False
        return widget
    def _truncate_chat_output(self, text: str, limit: int | None = None) -> tuple[str, int]:
        """Returns output preview and number of hidden characters."""
        if not isinstance(text, str):
            text = str(text)
        if limit is None:
            limit = self.CHAT_OUTPUT_PREVIEW_MAX_CHARS
        if len(text) <= limit:
            return text, 0
        hidden = len(text) - limit
        return text[:limit], hidden

    @staticmethod
    def _assistant_text_should_use_markdown(text: str) -> bool:
        if not isinstance(text, str):
            return False
        stripped = text.strip()
        if not stripped:
            return False
        if "\n" in stripped:
            lines = [line.strip() for line in stripped.splitlines() if line.strip()]
            has_heading = any(line.startswith(("# ", "## ", "### ")) for line in lines)
            has_fence = "```" in stripped
            has_blockquote = any(line.startswith("> ") for line in lines)
            has_table = any(line.startswith("|") and line.endswith("|") for line in lines)
            has_bullet = any(line.startswith(("- ", "* ")) for line in lines)
            has_ordered = any(re.match(r"^\d+\.\s", line) for line in lines)
            if has_fence or has_heading or has_blockquote or has_table:
                return True
            if has_bullet or has_ordered:
                return (
                    "\n\n" in stripped
                    or stripped.startswith(("- ", "* "))
                    or bool(re.match(r"^\d+\.\s", stripped))
                )
            return False
        markdown_markers = ("```", "# ", "## ", "### ", "> ", "|", "[")
        if any(marker in stripped for marker in markdown_markers):
            return True
        return True

    @staticmethod
    def sanitize_tool_call_for_display(command: dict, preview_limit: int = 1200) -> dict:
        """Returns a UI-safe copy of tool call payload without mutating original command."""
        if not isinstance(command, dict):
            return {"type": "unknown", "value": str(command)}

        safe = command.copy()
        tool_name = safe.get("type") or safe.get("action", "unknown")

        if tool_name in {"write_file", "write_file_block", "append_file_block"}:
            field_name = "content" if isinstance(safe.get("content"), str) else "file_content"
            content = safe.get(field_name)
            if isinstance(content, str) and len(content) > preview_limit:
                safe[field_name] = (
                    f"[content omitted in UI: {len(content)} chars; preview: {content[:120].replace(chr(10), '\\n')}]"
                )

        return safe

    # ---------------------------------------------------------------------
    # Status bar control
    # ---------------------------------------------------------------------

    @ui_task
    async def start_thinking(self):
        self.status_bar.start_thinking()
        self._set_title_activity("thinking")

    @ui_task
    async def start_action(self, text: str):
        self.status_bar.start_action(text)
        label = str(text or "").strip() or "working"
        self._set_title_activity(label)

    @ui_task
    async def stop_loading(self):
        self.status_bar.stop()
        self._clear_title_activity()

    @ui_task
    async def update_header(self, text: str):
        self._base_header_text = str(text or "").strip() or "Angelica"
        self._render_title()

    def _ensure_title_spinner_timer(self) -> None:
        if self._title_spinner_timer is None:
            self._title_spinner_timer = self.app.set_interval(
                0.24,
                self._advance_title_spinner,
                pause=True,
            )

    def _set_title_activity(self, label: str) -> None:
        self._title_activity_label = self._shorten_title_activity(label)
        self._title_spinner_index = 0
        self._ensure_title_spinner_timer()
        if self._title_spinner_timer is not None:
            self._title_spinner_timer.resume()
        self._render_title()

    def _clear_title_activity(self) -> None:
        self._title_activity_label = ""
        if self._title_spinner_timer is not None:
            self._title_spinner_timer.pause()
        self._render_title()

    def _advance_title_spinner(self) -> None:
        self._title_spinner_index = (self._title_spinner_index + 1) % len(self.TITLE_SPINNER_FRAMES)
        self._render_title()

    @classmethod
    def _shorten_title_activity(cls, label: str, max_chars: int = 32) -> str:
        text = str(label or "").strip()
        if not text:
            return "working"
        compact = re.sub(r"\s+", " ", text)
        if len(compact) <= max_chars:
            return compact
        return compact[: max_chars - 1].rstrip() + "…"

    @classmethod
    def _compose_window_title(
        cls,
        base_header_text: str,
        activity_label: str = "",
        spinner_index: int = 0,
    ) -> str:
        base = str(base_header_text or "").strip() or "Angelica"
        return base

    @classmethod
    def _compose_terminal_tab_title(
        cls,
        base_header_text: str,
        activity_label: str = "",
        spinner_index: int = 0,
    ) -> str:
        base = str(base_header_text or "").strip() or "Angelica"
        activity = str(activity_label or "").strip()
        if not activity:
            return base
        frame = cls.TITLE_SPINNER_FRAMES[spinner_index % len(cls.TITLE_SPINNER_FRAMES)]
        return f"{frame} {base}"

    def _render_title(self) -> None:
        title = self._compose_window_title(
            self._base_header_text,
            self._title_activity_label,
            self._title_spinner_index,
        )
        self.app.title = title
        terminal_title = self._compose_terminal_tab_title(
            self._base_header_text,
            self._title_activity_label,
            self._title_spinner_index,
        )
        self._emit_terminal_title(terminal_title)

    @staticmethod
    def _emit_terminal_title(title: str) -> None:
        text = str(title or "").replace("\x1b", "").replace("\x07", "").strip()
        if not text:
            return
        # OSC 0/1/2 cover common terminal title targets:
        # 0 = icon + window, 1 = icon/tab, 2 = window title.
        payload = f"\033]0;{text}\007\033]1;{text}\007\033]2;{text}\007"
        try:
            stream = getattr(sys, "__stdout__", None) or sys.stdout
            if stream is not None:
                stream.write(payload)
                stream.flush()
        except Exception:
            pass

    @ui_task
    async def update_token_status(self, history_tokens: int, max_tokens: int, session_tokens: int):
        try:
            if hasattr(self.app, 'query_one'): # Safety check
                token_bar = self.app.query_one(TokenStatusBar)
                token_bar.update_tokens(history_tokens, max_tokens, session_tokens)
        except Exception as e:
            if hasattr(self.app, 'agent') and self.app.agent.log:
                self.app.agent.log.error(f"Could not update token status bar: {e}")

    # ---------------------------------------------------------------------
    # Screens & confirmations
    # ---------------------------------------------------------------------

    @ui_task
    async def _push_screen_wait(self, screen):
        """Helper to push screen and await result on main thread."""
        loop = asyncio.get_running_loop()
        future = loop.create_future()

        def callback(result):
            if not future.done():
                future.set_result(result)

        self.app.push_screen(screen, callback=callback)
        return await future

    async def pick_option(self, prompt: str, options: list, current_value: str | None = None) -> str:
        screen = SelectionScreen(prompt, options, current_value=current_value)
        return await self._push_screen_wait(screen)

    async def confirm_action(self, action_details: dict) -> bool | str:
        self._count_confirmation()
        action_type = action_details.get("type", "unknown")
        details = (
            action_details.get("command")
            or action_details.get("path")
            or action_details.get("file_path")
            or ""
        )

        if action_type == "summarize_history":
            prompt = (
                "[bold yellow]History is near context limit[/]\n\n"
                "Choose what to do with automatic summarization."
            )
            screen = SelectionScreen(prompt, ["Summarize now", "Not now", "Do not suggest again"])
            result = await self._push_screen_wait(screen)
            if result == "Summarize now":
                return "summarize"
            if result == "Do not suggest again":
                return "never"
            return "later"

        if action_type == "run_shell":
            prompt = (
                "[bold yellow]⚠ Action confirmation[/]\n\n"
                f"[bold]Type:[/] {action_type}\n"
                f"[bold]Details:[/] {details}"
            )
            screen = SelectionScreen(prompt, ["Allow", "Deny"])
            result = await self._push_screen_wait(screen)
            return result == "Allow"

        if action_type in {"search_content", "search_files", "list_directory", "read_file", "read_chunk", "read_file_skeleton", "extract_kotlin_function", "extract_symbol"}:
            prompt = (
                "[bold yellow]⚠ Action confirmation[/]\n\n"
                f"[bold]Type:[/] {action_type}\n"
                f"[bold]Details:[/] {details}\n\n"
                "Choose output policy."
            )
            options = [
                "Allow truncated",
                "Full allow",
                "Deny",
            ]
            screen = SelectionScreen(prompt, options)
            result = await self._push_screen_wait(screen)
            if result == options[0]:
                return "allow_truncated"
            if result == options[1]:
                return "allow_full"
            return False

        prompt = (
            "[bold yellow]⚠ Action confirmation[/]\n\n"
            f"[bold]Type:[/] {action_type}\n"
            f"[bold]Details:[/] {details}"
        )
        screen = SelectionScreen(prompt, ["Allow", "Deny"])
        result = await self._push_screen_wait(screen)
        return result == "Allow"

    async def confirm_continue(self, prompt: str) -> bool | str:
        self._count_confirmation()
        options = ["Continue", "Continue and don't ask again this session", "Stop"]
        screen = SelectionScreen(prompt, options)
        result = await self._push_screen_wait(screen)
        if result == options[0]:
            return "continue"
        if result == options[1]:
            return "continue_silent"
        return "stop"

    async def confirm_loop_recovery(self, prompt: str) -> str:
        self._count_confirmation()
        options = [
            "Continue with model diagnosis",
            "Pin target file + edit strategy",
            "Open file search",
            "Stop",
        ]
        screen = SelectionScreen(prompt, options)
        result = await self._push_screen_wait(screen)
        if result == options[0]:
            return "continue_diagnosis"
        if result == options[1]:
            return "pin_target_edit"
        if result == options[2]:
            return "open_search"
        return "stop"

    async def confirm_technical_interruption(self, prompt: str, *, allow_retry: bool = True) -> str:
        self._count_confirmation()
        options = ["Retry / Resume work", "Stop"] if allow_retry else ["OK"]
        screen = SelectionScreen(prompt, options)
        result = await self._push_screen_wait(screen)
        if allow_retry and result == options[0]:
            return "retry_resume"
        return "stop"


    async def choose_intent_overrun_action(self, prompt: str) -> str:
        """User handoff for hard intent limit: exactly two choices."""
        self._count_confirmation()
        options = [
            "Approve more steps",
            "Stop and answer from current evidence",
        ]
        screen = SelectionScreen(prompt, options)
        result = await self._push_screen_wait(screen)
        if result == options[0]:
            return "approve_more_steps"
        return "stop_and_answer"


    async def choose_suspect_intent_change_action(self, prompt: str) -> str:
        """User handoff for suspicious same-lineage relabel / goal drift."""
        self._count_confirmation()
        options = [
            "Keep original goal",
            "Allow changed goal",
            "Stop and answer from current evidence",
        ]
        screen = SelectionScreen(prompt, options)
        result = await self._push_screen_wait(screen)
        if result == options[0]:
            return "keep_original_goal"
        if result == options[1]:
            return "allow_changed_goal"
        return "stop_and_answer"

    async def confirm_truncation(self, action_type: str, output_length: int) -> bool:
        self._count_confirmation()
        prompt = (
            f"The output of '{action_type}' is very long "
            f"({output_length} characters).\nWhat would you like to do?"
        )
        screen = SelectionScreen(prompt, ["Truncate", "Show Full Output"])
        result = await self._push_screen_wait(screen)
        return result == "Truncate"

    async def show_diff_preview(self, proposal) -> bool:
        self._count_confirmation()
        screen = DiffViewer(proposal)
        return await self._push_screen_wait(screen)

    # ---------------------------------------------------------------------
    # Printing helpers
    # ---------------------------------------------------------------------

    @ui_task
    async def _print_styled(self, text: str, style_key: str):
        """Generic handler for simple text messages."""
        if not text: return
        widget = self._create_styled_widget(text, style_key)
        self._mount_widget(widget)

    # Public aliases for generic printing
    async def print_system(self, text: str):
        await self._print_styled(text, "system")

    @ui_task
    async def start_system_progress(self, text: str) -> Static:
        """Print a system message and return widget for in-place updates."""
        widget = self._create_styled_widget(text, "system")
        return self._mount_widget(widget)

    @ui_task
    async def update_system_progress(self, widget: Static, text: str):
        """Update previously printed system progress message."""
        if widget is None:
            return
        content = text.strip() if isinstance(text, str) else str(text)
        rich_text = Text()
        rich_text.append("• ")
        rich_text.append(content)
        widget.update(rich_text)

    async def print_initial_system_message(self, text: str):
        await self._print_styled(text, "initial")

    async def print_error(self, text: str):
        await self._print_styled(text, "error")

    @ui_task
    async def print_technical_interruption(self, interruption):
        widget = TechnicalInterruptionWidget(interruption)
        return self._mount_widget(widget)

    async def print_thought(self, text: str):
        if text and text.strip():
            await self._print_styled(text, "thought")

    def _history_width(self) -> int:
        for owner in (self.history, self.app):
            try:
                width = int(getattr(getattr(owner, "size", None), "width", 0) or 0)
                if width > 0:
                    return width
            except Exception:
                continue
        return 40

    def _color_enabled(self) -> bool:
        try:
            no_color = bool(getattr(self.app, "no_color", False))
            if no_color:
                return False
        except Exception:
            pass
        try:
            return not bool(getattr(getattr(self.app, "console", None), "no_color", False))
        except Exception:
            return True

    async def print_plan(self, text: str | dict):
        if isinstance(text, dict) and str(text.get("kind") or "").strip() == "plan_update":
            renderable = format_plan_update_compact(
                text,
                {
                    "width": self._history_width(),
                    "color": self._color_enabled(),
                    "maxBarWidth": 10,
                    "compact": True,
                },
            )
            widget = Static(renderable, classes="chat-message plan-message", expand=False)
            widget.can_focus = False
            self._mount_widget(widget)
            return
        await self._print_styled(str(text), "plan")

    async def print_confirmation(self, text: str):
        await self._print_styled(text, "confirmation")

    @ui_task
    async def print_message(self, text: str, role: str = "assistant"):
        """Handles chat messages which might require Markdown rendering."""
        if not text or not text.strip():
            return

        should_follow = self._should_follow_history()
        if self.history.children:
            self.history.mount(MessageSeparator())

        label_text = "angelica" if role == "assistant" else "you"
        self.history.mount(self._make_role_label(label_text))

        if role == "assistant":
            content = text.strip()
            if self._assistant_text_should_use_markdown(content):
                renderable = RichMarkdown(content)
            else:
                renderable = Text(content)
            widget = Static(
                renderable,
                classes="chat-message assistant-message",
                expand=False,
            )
        else:
            widget = Static(
                Text(text.strip()),
                classes="chat-message user-message",
                expand=False,
            )

        widget.can_focus = False
        self.history.mount(widget)
        if should_follow:
            self.history.scroll_end(animate=False)

    # ---------------------------------------------------------------------
    # Tool call rendering (Must be Async for ActionDispatcher)
    # ---------------------------------------------------------------------

    @ui_task
    async def print_tool_call(self, command: dict) -> Static:
        display_command = self.sanitize_tool_call_for_display(
            command,
            preview_limit=self.TOOL_ARG_PREVIEW_MAX_CHARS,
        )
        if has_specialized_tool_call_renderer(display_command):
            return await self._print_specialized_tool_call(display_command)
        return await self._print_generic_tool_call(display_command)

    async def _print_specialized_tool_call(self, command: dict) -> Static:
        tool_name = command.get("type") or command.get("action", "unknown")
        if tool_name == "run_shell":
            return await self.print_shell_start(command)
        if tool_name == "read_file":
            return await self.print_read_file_start(command)
        if tool_name == "edit_file":
            return await self.print_edit_file_start(command)
        return await self._print_generic_tool_call(command)

    async def _print_generic_tool_call(self, command: dict) -> Static:
        widget = GenericToolCallCard(command)
        widget.command = command
        return self._mount_widget(widget)

    @ui_task
    async def update_tool_call(self, widget: Static, command: dict, result: dict):
        display_command = self.sanitize_tool_call_for_display(
            command,
            preview_limit=self.TOOL_ARG_PREVIEW_MAX_CHARS,
        )
        if has_specialized_tool_call_renderer(display_command):
            tool_name = display_command.get("type") or display_command.get("action", "unknown")
            if tool_name == "run_shell":
                await self.update_shell_result(widget, result)
                return
            if tool_name == "read_file":
                await self.update_read_file_result(widget, result)
                return
            if tool_name == "edit_file":
                await self.update_edit_file_result(widget, result)
                return

        if isinstance(widget, GenericToolCallCard):
            widget.update_presentation(display_command, result)
            return

        fallback = GenericToolCallCard(display_command, result)
        widget.update(fallback.build_renderable())

    @ui_task
    async def print_shell_start(self, command: dict) -> Static:
        before_text = command.get('before_execution', 'Starting shell command...')
        renderable = RichMarkdown(f"🤖 {before_text}")
        widget = Static(renderable, classes="chat-message plan-message", expand=False)
        widget.command = command
        widget.can_focus = False
        return self._mount_widget(widget)

    @ui_task
    async def update_shell_result(self, widget: Static, result: dict):
        command = getattr(widget, 'command', {})
        shell_command = command.get('command', '')
        after_execution = command.get('after_execution')
        output = result.get('output', '')
        status = result.get('status')
        output_preview, hidden = self._truncate_chat_output(output)

        md_parts = []
        if status == 'success' and after_execution:
            md_parts.append(f"✔ {after_execution.strip()}")

        icon_char = '✔' if status == 'success' else '✘'
        result_box = f"```sh\n{icon_char} run_shell: {shell_command}\n---\n{escape(output_preview.strip())}\n```"
        md_parts.append(result_box)
        if hidden > 0:
            md_parts.append(f"[dim]... output truncated in chat: {hidden} chars hidden.[/dim]")

        new_renderable = RichMarkdown("\n\n".join(md_parts))
        widget.update(new_renderable)

    @ui_task
    async def print_read_file_start(self, command: dict) -> Static:
        file_path = command.get('path', '...')
        renderable = Text()
        renderable.append("↓ ", style="dim")
        renderable.append("read ", style="dim")
        renderable.append(escape(file_path), style="dim italic")
        widget = Static(renderable, classes="read-file-message", expand=False)
        widget.file_path = file_path
        widget.can_focus = False
        return self._mount_widget(widget)

    @ui_task
    async def update_read_file_result(self, widget: Static, result: dict):
        file_path = getattr(widget, 'file_path', '...')
        status = result.get('status')
        content = result.get('content', '')
        line_count = len(content.splitlines()) if isinstance(content, str) and content else None

        if status == 'success':
            icon = '✓'
            icon_style = 'green'
        else:
            icon = '✗'
            icon_style = 'red'

        new_renderable = Text()
        new_renderable.append(f"{icon} ", style=icon_style)
        new_renderable.append("read ", style="dim")
        new_renderable.append(escape(file_path), style="dim italic")
        if line_count is not None and status == 'success':
            new_renderable.append(f"  {line_count} lines", style="dim")
        widget.update(new_renderable)

    @ui_task
    async def print_edit_file_start(self, command: dict) -> Static:
        file_path = command.get('path', '...')
        renderable = Text()
        renderable.append("✎ ", style="dim")
        renderable.append("edit ", style="dim")
        renderable.append(escape(file_path), style="dim italic")
        widget = Static(renderable, classes="edit-file-message", expand=False)
        widget.file_path = file_path
        widget.can_focus = False
        return self._mount_widget(widget)

    @ui_task
    async def update_edit_file_result(self, widget: Static, result: dict):
        file_path = getattr(widget, 'file_path', '...')
        status = result.get('status')
        icon = '✓' if status == 'success' else '✗'
        icon_style = 'green' if status == 'success' else 'red'

        new_renderable = Text()
        new_renderable.append(f"{icon} ", style=icon_style)
        new_renderable.append("edit ", style="dim")
        new_renderable.append(escape(file_path), style="dim italic")
        widget.update(new_renderable)

    @ui_task
    async def print_command_result(self, text: str, truncated: bool = False):
        content_raw = text if text is not None else ""
        content_preview, hidden = self._truncate_chat_output(content_raw)
        if hidden > 0:
            truncated = True

        subtitle = " (truncated)" if truncated else ""
        md_lines = [f"**✔ Result**{subtitle}"]
        
        content = content_preview.strip() if content_preview and content_preview.strip() else "(empty)"
        md_lines.append(f"```\n{escape(content)}\n```")
        if hidden > 0:
            md_lines.append(f"[dim]... output truncated in chat: {hidden} chars hidden.[/dim]")

        renderable = RichMarkdown("\n\n".join(md_lines))
        widget = Static(renderable, classes="chat-message tool-result-message", expand=False)
        widget.can_focus = False
        self._mount_widget(widget)
