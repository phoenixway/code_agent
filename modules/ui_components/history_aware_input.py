from pathlib import Path
import re

from textual.widgets import Input
from textual.binding import Binding
from textual.events import Paste


# ---------------------------------------------------------------------
# History file resolution
# ---------------------------------------------------------------------

try:
    from modules.config_loader import CONFIG_DIR
    HISTORY_FILE = CONFIG_DIR / "history.txt"
except (ImportError, FileNotFoundError):
    HISTORY_FILE = Path.home() / ".config" / "angelica" / "history.txt"
    HISTORY_FILE.parent.mkdir(parents=True, exist_ok=True)


# ---------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------

def normalize_for_input(text: str) -> str:
    """
    Convert multiline text into a single line suitable for Input.
    """
    text = text.replace("\r\n", "\n").replace("\r", "\n")
    text = text.replace("\t", " ")
    text = text.replace("\n", " ")
    text = re.sub(r"\s+", " ", text)
    return text.strip()


def escape_multiline(text: str) -> str:
    """
    Store multiline text as a single line in history file.
    """
    return text.replace("\\", "\\\\").replace("\n", "\\n")


def unescape_multiline(text: str) -> str:
    """
    Restore multiline text from escaped form.
    """
    return text.replace("\\n", "\n").replace("\\\\", "\\")


# ---------------------------------------------------------------------
# Widget
# ---------------------------------------------------------------------

class HistoryAwareInput(Input):
    """
    Input widget with history and correct multiline paste handling.

    - Input always receives single-line text
    - History stores original multiline text
    """

    BINDINGS = [
        Binding("ctrl+up", "history_up", show=False),
        Binding("ctrl+down", "history_down", show=False),
    ]

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

        self._history: list[str] = []          # original multiline entries
        self._history_index: int = -1
        self._draft: str = ""

        # Stores raw multiline text from last paste
        self._last_paste_raw: str | None = None

        self._load_history()

    # -----------------------------------------------------------------
    # Paste handling (CRITICAL PART)
    # -----------------------------------------------------------------

    def on_paste(self, event: Paste) -> None:
        """
        Intercept paste BEFORE Textual Input truncates multiline text.
        """
        raw_text = event.text
        if not raw_text:
            return

        # Stop default Input paste behavior
        event.stop()

        # Save original multiline text for history
        self._last_paste_raw = raw_text

        # Insert normalized single-line text into input
        single_line = normalize_for_input(raw_text)
        self._insert_text_at_cursor(single_line)

    def _insert_text_at_cursor(self, text: str) -> None:
        """
        Insert text at the current cursor position.
        """
        cursor = self.cursor_position
        value = self.value

        self.value = value[:cursor] + text + value[cursor:]
        self.cursor_position = cursor + len(text)

    # -----------------------------------------------------------------
    # History I/O
    # -----------------------------------------------------------------

    def _load_history(self) -> None:
        if not HISTORY_FILE.exists():
            return

        try:
            with open(HISTORY_FILE, "r", encoding="utf-8") as f:
                for line in f:
                    line = line.rstrip("\n")
                    if not line:
                        continue
                    self._history.append(unescape_multiline(line))
        except Exception:
            pass

    def _append_to_file(self, text: str) -> None:
        try:
            with open(HISTORY_FILE, "a", encoding="utf-8") as f:
                f.write(escape_multiline(text) + "\n")
        except Exception:
            pass

    def add_entry(self, text: str) -> None:
        """
        Add entry to history.

        Priority:
        - original multiline paste (if present)
        - fallback to current input value
        """
        original = self._last_paste_raw or text
        original = original.strip()

        if not original:
            return

        if not self._history or self._history[-1] != original:
            self._history.append(original)
            self._append_to_file(original)

        self._history_index = -1
        self._draft = ""
        self._last_paste_raw = None

    # -----------------------------------------------------------------
    # History navigation
    # -----------------------------------------------------------------

    def action_history_up(self) -> None:
        if not self._history:
            return

        if self._history_index == -1:
            self._draft = self.value
            self._history_index = len(self._history) - 1
        elif self._history_index > 0:
            self._history_index -= 1
        else:
            return

        self.value = normalize_for_input(self._history[self._history_index])

    def action_history_down(self) -> None:
        if self._history_index == -1:
            return

        if self._history_index < len(self._history) - 1:
            self._history_index += 1
            self.value = normalize_for_input(self._history[self._history_index])
        else:
            self._history_index = -1
            self.value = self._draft