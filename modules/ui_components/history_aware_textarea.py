from pathlib import Path
import subprocess

from textual.widgets import TextArea, Static
from textual.binding import Binding
from textual.events import Key
from textual.message import Message
from textual.reactive import reactive

try:
    from modules.logger import get_debug_logger
    logger = get_debug_logger()
except ImportError:
    logger = None

try:
    from modules.config_loader import load_settings
    _settings = load_settings()
    DEBUG_LOG_KEYPRESSES = bool(_settings.get("debug_log_keypresses", False))
except Exception:
    DEBUG_LOG_KEYPRESSES = False

from modules.ui_components.history_aware_input import escape_multiline, unescape_multiline


# ---------------------------------------------------------------------
# History file
# ---------------------------------------------------------------------

try:
    from modules.config_loader import CONFIG_DIR
    HISTORY_FILE = CONFIG_DIR / "history.txt"
except (ImportError, FileNotFoundError):
    HISTORY_FILE = Path.home() / ".config" / "angelica" / "history.txt"
    HISTORY_FILE.parent.mkdir(parents=True, exist_ok=True)


class SuggestionWidget(Static):
    """Віджет для відображення автопідказок."""
    
    suggestion = reactive("")
    
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.styles.color = "gray"
        self.styles.height = 1
    
    def watch_suggestion(self, new_suggestion: str) -> None:
        """Оновлює текст підказки."""
        if new_suggestion:
            self.update(f"💡 {new_suggestion} [dim](Tab для прийняття)[/dim]")
        else:
            self.update("")


class HistoryAwareTextArea(TextArea):
    """
    TextArea з історією команд і autosuggestion для команд.
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
        Binding("up", "history_up", show=False),
        Binding("down", "history_down", show=False),
        Binding("ctrl+up", "history_up", show=False),
        Binding("ctrl+down", "history_down", show=False),
        Binding("tab", "accept_suggestion", show=False),
    ]

    def __init__(self, *args, commands=None, suggestion_widget=None, **kwargs):
        max_lines = kwargs.pop("max_lines", None)
        soft_wrap = kwargs.pop("wrap", True)  # Увімкнено за замовчуванням
        self._placeholder = kwargs.pop("placeholder", "")

        kwargs.setdefault("language", None)
        super().__init__(*args, soft_wrap=soft_wrap, **kwargs)

        if max_lines:
            self.styles.max_height = max_lines

        self._history: list[str] = []
        self._history_index = -1
        self._draft = ""
        self._commands = commands or []  # Список доступних команд
        self._suggestion_widget = suggestion_widget  # Віджет для відображення підказок

        self._load_history()
        self.show_line_numbers = False

        if not self.text and self._placeholder:
            self._show_placeholder()

    # ------------------------------------------------------------------
    # Autosuggestion
    # ------------------------------------------------------------------

    def _update_suggestion(self) -> None:
        """Оновлює підказку на основі поточного тексту."""
        current = self.text
        
        # Очищаємо підказку якщо текст порожній або це placeholder
        if not current or current == self._placeholder:
            self._set_suggestion("")
            return
        
        # Шукаємо підказку тільки для команд (що починаються з /)
        if not current.startswith("/"):
            self._set_suggestion("")
            return
        
        # Шукаємо першу команду, що підходить
        current_lower = current.lower()
        for cmd in self._commands:
            if cmd.lower().startswith(current_lower) and cmd != current:
                self._set_suggestion(cmd)
                return
        
        self._set_suggestion("")

    def _set_suggestion(self, suggestion: str) -> None:
        """Оновлює віджет підказки."""
        if self._suggestion_widget:
            self._suggestion_widget.suggestion = suggestion
        self._current_suggestion = suggestion

    def _get_current_suggestion(self) -> str:
        """Повертає поточну підказку."""
        return getattr(self, '_current_suggestion', "")

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
                    self._history = [
                        unescape_multiline(line.rstrip("\n"))
                        for line in f
                        if line.rstrip("\n").strip()
                    ]
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
                    f.write(escape_multiline(text) + "\n")
            except Exception:
                pass

        self._history_index = -1
        self._draft = ""

    def action_history_up(self) -> None:
        # Keep native multiline cursor navigation unless we are at the first line
        # or already browsing history.
        if self._history_index == -1 and self.cursor_location[0] > 0:
            if hasattr(super(), "action_cursor_up"):
                super().action_cursor_up()
            return

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
        # If history browsing is not active, preserve native cursor navigation.
        if self._history_index == -1:
            if hasattr(super(), "action_cursor_down"):
                super().action_cursor_down()
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
        if logger and DEBUG_LOG_KEYPRESSES:
            logger.info(f"--- KEY PRESSED ---\nkey: {event.key!r}\ncharacter: {event.character!r}\nname: {event.name!r}\n")
        
        # Shift+Enter або Ctrl+Enter - новий рядок
        # В Termux Ctrl+Enter приходить як 'ctrl+j'
        if event.key in ("ctrl+enter", "shift+enter", "ctrl+return", "shift+return", "ctrl+j"):
            event.prevent_default()
            event.stop()
            
            if logger and DEBUG_LOG_KEYPRESSES:
                logger.info(f"--- SHIFT/CTRL+ENTER DETECTED ---\nInserting newline\n")
            
            if self.text == self._placeholder:
                self._hide_placeholder()
            self.insert("\n")
            return
        
        # Звичайний Enter - відправка
        if event.key in ("enter", "return", "\n", "\r"):
            event.prevent_default()
            event.stop()
            
            if logger and DEBUG_LOG_KEYPRESSES:
                logger.info(f"--- ENTER DETECTED ---\nSubmitting text: {self.text!r}\n")
            
            value = self.text
            if value == self._placeholder:
                value = ""
            
            if logger and DEBUG_LOG_KEYPRESSES:
                logger.info(f"--- POSTING SUBMITTED MESSAGE ---\nvalue: {value!r}\n")
            
            self.post_message(self.Submitted(self, value))
            return
        
        # Оновлюємо підказку після будь-якої клавіші
        self._update_suggestion()
    
    def watch_text(self, new_text: str) -> None:
        """Викликається при зміні тексту."""
        self._update_suggestion()

    # ------------------------------------------------------------------
    # Actions
    # ------------------------------------------------------------------

    def action_accept_suggestion(self) -> None:
        """Приймає поточну підказку (Tab)."""
        suggestion = self._get_current_suggestion()
        if suggestion:
            self.text = suggestion
            self.move_cursor_to_end()
            self._set_suggestion("")

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
