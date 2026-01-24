from pathlib import Path
import subprocess

from textual.widgets import TextArea
from textual.binding import Binding
from textual.events import Key
from textual.message import Message

try:
    from modules.logger import get_debug_logger
    logger = get_debug_logger()
except ImportError:
    logger = None


# ---------------------------------------------------------------------
# History file
# ---------------------------------------------------------------------

try:
    from modules.config_loader import CONFIG_DIR
    HISTORY_FILE = CONFIG_DIR / "history.txt"
except (ImportError, FileNotFoundError):
    HISTORY_FILE = Path.home() / ".config" / "angelica" / "history.txt"
    HISTORY_FILE.parent.mkdir(parents=True, exist_ok=True)


class HistoryAwareTextArea(TextArea):
    """
    TextArea з історією команд і гарантованою обробкою Enter (Termux-safe).
    """

    class Submitted(Message):
        """Повідомлення про відправку тексту."""
        def __init__(self, text_area: "HistoryAwareTextArea", value: str) -> None:
            super().__init__()
            self.text_area = text_area
            self.value = value
            
        @property
        def control(self) -> "HistoryAwareTextArea":
            """Compatibility property."""
            return self.text_area

    BINDINGS = [
        Binding("ctrl+up", "history_up", show=False),
        Binding("ctrl+down", "history_down", show=False),
    ]

    def __init__(self, *args, **kwargs):
        max_lines = kwargs.pop("max_lines", None)
        soft_wrap = kwargs.pop("wrap", False)
        self._placeholder = kwargs.pop("placeholder", "")

        kwargs.setdefault("language", None)
        super().__init__(*args, soft_wrap=soft_wrap, **kwargs)

        if max_lines:
            self.styles.max_height = max_lines

        self._history: list[str] = []
        self._history_index = -1
        self._draft = ""

        self._load_history()
        self.show_line_numbers = False

        if not self.text and self._placeholder:
            self._show_placeholder()

    # ------------------------------------------------------------------
    # Placeholder
    # ------------------------------------------------------------------

    def _show_placeholder(self) -> None:
        self.styles.color = "gray"
        self.text = self._placeholder

    def _hide_placeholder(self) -> None:
        self.styles.color = None
        self.text = ""

    def on_focus(self) -> None:
        if self.text == self._placeholder:
            self._hide_placeholder()

    def on_blur(self) -> None:
        if not self.text and self._placeholder:
            self._show_placeholder()

    # ------------------------------------------------------------------
    # History
    # ------------------------------------------------------------------

    def _load_history(self) -> None:
        if HISTORY_FILE.exists():
            try:
                with open(HISTORY_FILE, "r", encoding="utf-8") as f:
                    self._history = [l.strip() for l in f if l.strip()]
            except Exception:
                pass

    def add_entry(self, text: str) -> None:
        text = text.strip()
        if not text or text == self._placeholder:
            return

        if not self._history or self._history[-1] != text:
            self._history.append(text)
            try:
                with open(HISTORY_FILE, "a", encoding="utf-8") as f:
                    f.write(text + "\n")
            except Exception:
                pass

        self._history_index = -1
        self._draft = ""

    def action_history_up(self) -> None:
        if not self._history:
            return

        if self._history_index == -1:
            self._draft = self.text
            self._history_index = len(self._history) - 1
        elif self._history_index > 0:
            self._history_index -= 1
        else:
            return

        self.text = self._history[self._history_index]
        self.move_cursor_to_end()

    def action_history_down(self) -> None:
        if self._history_index == -1:
            return

        if self._history_index < len(self._history) - 1:
            self._history_index += 1
            self.text = self._history[self._history_index]
        else:
            self._history_index = -1
            self.text = self._draft

        self.move_cursor_to_end()

    # ------------------------------------------------------------------
    # KEY HANDLERS
    # ------------------------------------------------------------------

    def on_key(self, event: Key) -> None:
        """Перехоплюємо всі варіанти Enter для Android/Termux."""
        # Логуємо кожне натискання клавіші (можна вимкнути після налаштування)
        if logger:
            logger.info(f"--- KEY PRESSED ---\nkey: {event.key!r}\ncharacter: {event.character!r}\nname: {event.name!r}\n")
        
        # Shift+Enter або Ctrl+Enter - новий рядок
        # В Termux Ctrl+Enter приходить як 'ctrl+j'
        if event.key in ("ctrl+enter", "shift+enter", "ctrl+return", "shift+return", "ctrl+j"):
            event.prevent_default()
            event.stop()
            
            if logger:
                logger.info(f"--- SHIFT/CTRL+ENTER DETECTED ---\nInserting newline\n")
            
            if self.text == self._placeholder:
                self._hide_placeholder()
            self.insert("\n")
            return
        
        # Звичайний Enter - відправка
        if event.key in ("enter", "return", "\n", "\r"):
            event.prevent_default()
            event.stop()
            
            if logger:
                logger.info(f"--- ENTER DETECTED ---\nSubmitting text: {self.text!r}\n")
            
            value = self.text
            if value == self._placeholder:
                value = ""
            
            if logger:
                logger.info(f"--- POSTING SUBMITTED MESSAGE ---\nvalue: {value!r}\n")
            
            self.post_message(self.Submitted(self, value))

    # ------------------------------------------------------------------
    # Actions
    # ------------------------------------------------------------------

    def action_new_line(self) -> None:
        """Action для Shift/Ctrl+Enter - додає новий рядок."""
        if self.text == self._placeholder:
            self._hide_placeholder()
        self.insert("\n")

    def move_cursor_to_end(self) -> None:
        row = len(self.document.lines) - 1
        col = len(self.document.get_line(row))
        self.cursor_location = (row, col)

    # ------------------------------------------------------------------
    # Clipboard (Termux)
    # ------------------------------------------------------------------

    def _get_clipboard_text(self) -> str:
        try:
            result = subprocess.run(
                ["termux-clipboard-get"],
                capture_output=True,
                text=True,
                timeout=1,
            )
            if result.returncode == 0:
                return result.stdout
        except Exception:
            pass
        return ""

    def action_paste(self) -> None:
        text = self._get_clipboard_text()
        if text:
            self.insert(text)

    def paste(self) -> None:
        self.action_paste()