from textual.widgets import TextArea
from textual.binding import Binding
from textual.events import Key
from pathlib import Path

# This logic was previously in history_input.py
# We assume the CONFIG_DIR is available in a similar way.
# A more robust solution would be to pass this path in, but for now, this should work.
try:
    from modules.config_loader import CONFIG_DIR
    HISTORY_FILE = CONFIG_DIR / "history.txt"
except (ImportError, FileNotFoundError):
    HISTORY_FILE = Path.home() / ".config" / "angelica" / "history.txt"
    HISTORY_FILE.parent.mkdir(parents=True, exist_ok=True)


class HistoryAwareTextArea(TextArea):
    """
    A TextArea widget that remembers command history and allows navigation
    with Ctrl+Up and Ctrl+Down. Enter key submits instead of creating new line.
    """

    BINDINGS = [
        Binding("ctrl+up", "history_up", "Previous Command", show=False),
        Binding("ctrl+down", "history_down", "Next Command", show=False),
        Binding("enter", "submit", "Submit", show=False),
        Binding("ctrl+enter", "new_line", "New Line", show=False),
    ]

    def __init__(self, *args, **kwargs):
        # Extract suggester if provided
        self.suggester = kwargs.pop("suggester", None)
        
        # Initialize TextArea with single-line mode disabled
        kwargs.setdefault("language", None)  # No syntax highlighting
        kwargs.setdefault("wrap", False)  # No word wrap
        # Limit height to 3 lines maximum
        kwargs.setdefault("max_lines", 3)
        super().__init__(*args, **kwargs)
        self._history: list[str] = []
        self._history_index: int = -1
        self._draft: str = ""
        self._load_history()
        
        # Disable multiline by default, but allow user to enable with Ctrl+Enter
        self.show_line_numbers = False
        
        # Store placeholder text if provided
        self._placeholder = kwargs.get("placeholder", "")
        
        # Initialize with placeholder if no text
        if not self.text and self._placeholder:
            self._show_placeholder()
    
    def _show_placeholder(self) -> None:
        """Show placeholder text."""
        # Store original styles
        self._original_styles = self.styles
        # Apply placeholder style (gray text)
        self.styles.color = "gray"
        self.text = self._placeholder
    
    def _hide_placeholder(self) -> None:
        """Hide placeholder text."""
        if hasattr(self, "_original_styles"):
            self.styles = self._original_styles
        self.text = ""
    
    def on_focus(self) -> None:
        """Handle focus event."""
        if self.text == self._placeholder:
            self._hide_placeholder()
        super().on_focus()
    
    def on_blur(self) -> None:
        """Handle blur event."""
        if not self.text and self._placeholder:
            self._show_placeholder()
        super().on_blur()
        
    def _load_history(self):
        """Loads history from a file."""
        if HISTORY_FILE.exists():
            try:
                with open(HISTORY_FILE, "r", encoding="utf-8") as f:
                    self._history = [line.strip() for line in f if line.strip()]
            except Exception:
                pass  # Ignore reading errors

    def _append_to_file(self, text: str):
        """Appends a new command to the file."""
        try:
            with open(HISTORY_FILE, "a", encoding="utf-8") as f:
                f.write(text + "\n")
        except Exception:
            pass

    def add_entry(self, text: str) -> None:
        """Adds text to history if it's not empty and doesn't duplicate the last entry."""
        text = text.strip()
        if not text:
            return

        if not self._history or self._history[-1] != text:
            self._history.append(text)
            self._append_to_file(text)

        self._history_index = -1
        self._draft = ""

    def action_history_up(self) -> None:
        """Go to the previous command in history."""
        if not self._history:
            return

        if self._history_index == -1:
            self._draft = self.text
            new_index = len(self._history) - 1
        elif self._history_index > 0:
            new_index = self._history_index - 1
        else:
            return  # Already at the oldest entry

        self._history_index = new_index
        self.text = self._history[self._history_index]
        self.move_cursor_to_end()

    def action_history_down(self) -> None:
        """Go to the next command in history."""
        if self._history_index == -1:
            return

        if self._history_index < len(self._history) - 1:
            self._history_index += 1
            self.text = self._history[self._history_index]
            self.move_cursor_to_end()
        else:
            self._history_index = -1
            self.text = self._draft
            self.move_cursor_to_end()
    
    def action_submit(self) -> None:
        """Submit the current text (Enter key)."""
        # Trigger the submit event
        self.post_message(self.Submitted(self, self.text))
    
    def action_new_line(self) -> None:
        """Insert a new line (Ctrl+Enter)."""
        self.insert("\n")
    
    def move_cursor_to_end(self) -> None:
        """Move cursor to the end of the text."""
        # For TextArea, cursor_location is (row, column)
        # Since we're treating it as single-line, row is always 0
        text_length = len(self.text)
        self.cursor_location = (0, text_length)
    
    def on_key(self, event: Key) -> None:
        """Handle key events."""
        # Handle placeholder
        if self.text == self._placeholder and event.key not in ["enter", "ctrl+enter", "escape", "tab"]:
            self._hide_placeholder()
        
        # Prevent default Enter behavior (new line)
        if event.key == "enter" and not event.ctrl:
            event.prevent_default()
            self.action_submit()
            return
        
        # Allow Ctrl+Enter for new line
        if event.key == "enter" and event.ctrl:
            event.prevent_default()
            self.action_new_line()
            return
        
        # Handle autocomplete/suggestions
        if self.suggester and event.key == "tab":
            event.prevent_default()
            self._handle_suggestion()
            return
        
        super().on_key(event)
    
    def _handle_suggestion(self) -> None:
        """Handle tab completion."""
        if not self.suggester:
            return
        
        # Get current text
        current_text = self.text
        if current_text == self._placeholder:
            current_text = ""
        
        # Get suggestion from suggester
        suggestion = self.suggester.get_suggestion(current_text)
        if suggestion:
            self.text = suggestion
            self.move_cursor_to_end()
    
    def _get_clipboard_text(self) -> str:
        """Get text from clipboard, trying multiple methods."""
        clipboard_text = ""
        
        # Method 1: Try Termux clipboard (Android/Termux)
        try:
            import subprocess
            result = subprocess.run(['termux-clipboard-get'], 
                                  capture_output=True, text=True, timeout=1)
            if result.returncode == 0 and result.stdout:
                return result.stdout
        except (FileNotFoundError, subprocess.TimeoutExpired, Exception):
            pass
        
        # Method 2: Try Textual's clipboard
        try:
            from textual.clipboard import Clipboard
            clipboard = Clipboard()
            clipboard_text = clipboard.get_text() or ""
            if clipboard_text:
                return clipboard_text
        except Exception:
            pass
        
        # Method 3: Try pyperclip
        try:
            import pyperclip
            clipboard_text = pyperclip.paste()
            if clipboard_text:
                return clipboard_text
        except ImportError:
            pass
        
        # Method 4: Try xclip (Linux/X11)
        try:
            import subprocess
            result = subprocess.run(['xclip', '-selection', 'clipboard', '-o'],
                                  capture_output=True, text=True, timeout=1)
            if result.returncode == 0 and result.stdout:
                return result.stdout
        except (FileNotFoundError, subprocess.TimeoutExpired, Exception):
            pass
        
        # Method 5: Try xsel (Linux/X11 alternative)
        try:
            import subprocess
            result = subprocess.run(['xsel', '--clipboard', '--output'],
                                  capture_output=True, text=True, timeout=1)
            if result.returncode == 0 and result.stdout:
                return result.stdout
        except (FileNotFoundError, subprocess.TimeoutExpired, Exception):
            pass
        
        # Method 6: Try pbpaste (macOS)
        try:
            import subprocess
            result = subprocess.run(['pbpaste'], 
                                  capture_output=True, text=True, timeout=1)
            if result.returncode == 0 and result.stdout:
                return result.stdout
        except (FileNotFoundError, subprocess.TimeoutExpired, Exception):
            pass
        
        return clipboard_text
    
    def action_paste(self) -> None:
        """
        Handle pasting of text when Ctrl+V is pressed.
        When multiline text is pasted, it will be preserved.
        """
        clipboard_text = self._get_clipboard_text()
        
        if clipboard_text:
            # Insert the text at the cursor position
            self.insert(clipboard_text)
    
    def paste(self) -> None:
        """
        Handle pasting of text (called by Textual's internal paste handling).
        """
        # Call our action_paste method to handle the paste
        self.action_paste()