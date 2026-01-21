from textual.widgets import Input
from textual.binding import Binding
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


class HistoryAwareInput(Input):
    """
    An Input widget that remembers command history and allows navigation
    with Ctrl+Up and Ctrl+Down.
    """

    BINDINGS = [
        Binding("ctrl+up", "history_up", "Previous Command", show=False),
        Binding("ctrl+down", "history_down", "Next Command", show=False),
    ]

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._history: list[str] = []
        self._history_index: int = -1
        self._draft: str = ""
        self._load_history()

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
            self._draft = self.value
            new_index = len(self._history) - 1
        elif self._history_index > 0:
            new_index = self._history_index - 1
        else:
            return # Already at the oldest entry

        self._history_index = new_index
        self.value = self._history[self._history_index]


    def action_history_down(self) -> None:
        """Go to the next command in history."""
        if self._history_index == -1:
            return

        if self._history_index < len(self._history) - 1:
            self._history_index += 1
            self.value = self._history[self._history_index]
        else:
            self._history_index = -1
            self.value = self._draft
