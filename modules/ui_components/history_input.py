from textual.widgets import TextArea
from textual.binding import Binding
from textual.message import Message
from textual.events import Key
from modules.config_loader import CONFIG_DIR

HISTORY_FILE = CONFIG_DIR / "history.txt"

class HistoryInput(TextArea):
    """
    An extended input field with support for command history and multi-line input.
    Use Ctrl+Up / Ctrl+Down for navigation.
    Use Shift+Enter or Ctrl+D to insert a newline.
    Use Enter to submit.
    """

    class Submitted(Message):
        """Posted when the user presses enter."""
        def __init__(self, sender: "HistoryInput", text: str) -> None:
            self.sender = sender
            self.text = text
            super().__init__()
            
    class Suggestion(Message):
        """Posted when there are suggestions."""
        def __init__(self, sender: "HistoryInput", suggestions: list[str]) -> None:
            self.sender = sender
            self.suggestions = suggestions
            super().__init__()

    BINDINGS = [
        Binding("ctrl+up", "history_up", "Previous Command", show=False),
        Binding("ctrl+down", "history_down", "Next Command", show=False),
        Binding("ctrl+q", "app.quit", "Quit App", show=False),
        Binding("ctrl+d", "insert_newline", "Insert Newline", show=False),
        Binding("shift+enter", "insert_newline", "Insert Newline", show=False),
        Binding("tab", "autocomplete", "Autocomplete", show=False),
        Binding("down", "next_suggestion", "Next Suggestion", show=False),
        Binding("up", "previous_suggestion", "Previous Suggestion", show=False),
    ]

    def __init__(self, *args, **kwargs):
        # TextArea doesn't have a placeholder, so we pop it.
        kwargs.pop("placeholder", None)
        self.slash_commands = kwargs.pop("slash_commands", [])
        self.logger = kwargs.pop("logger", None)
        
        super().__init__(*args, **kwargs)
        self.show_line_numbers = False
        self._history: list[str] = []
        self._history_index: int = -1
        self._draft: str = ""
        self._load_history()
        self.suggestions = []
        self.suggestion_index = -1

    def _log(self, message):
        if self.logger:
            self.logger.info(message)

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

        self._reset_pointer()

    def _reset_pointer(self):
        self._history_index = -1
        self._draft = ""

    def watch_text(self, old_text: str, new_text: str) -> None:
        self._log(f"watch_text: old='{old_text}', new='{new_text}'")
        if new_text.startswith("/"):
            command_part = new_text.split(" ")[0]
            self.suggestions = [
                command for command in self.slash_commands if command.startswith(command_part)
            ]
            self._log(f"Suggestions: {self.suggestions}")
            self.post_message(self.Suggestion(self, self.suggestions))
        else:
            self.suggestions = []
            self.post_message(self.Suggestion(self, []))

    def on_key(self, event: Key) -> None:
        if event.key == "enter":
            event.stop()
            if self.suggestion_index != -1:
                self.action_autocomplete()
            else:
                self.action_submit()

    def action_autocomplete(self) -> None:
        self._log("action_autocomplete")
        if self.suggestions and self.suggestion_index != -1:
            self.text = self.suggestions[self.suggestion_index]
            self.move_cursor((len(self.text), 0))
            self.suggestions = []
            self.suggestion_index = -1
            self.post_message(self.Suggestion(self, []))

    def action_next_suggestion(self) -> None:
        self._log("action_next_suggestion")
        if self.suggestions:
            self.suggestion_index = (self.suggestion_index + 1) % len(self.suggestions)
            self.post_message(self.Suggestion(self, self.suggestions))

    def action_previous_suggestion(self) -> None:
        self._log("action_previous_suggestion")
        if self.suggestions:
            self.suggestion_index = (self.suggestion_index - 1) % len(self.suggestions)
            self.post_message(self.Suggestion(self, self.suggestions))

    def action_history_up(self) -> None:
        """Go to the previous command in history."""
        if not self._history:
            return

        if self._history_index == -1:
            self._draft = self.text
            self._history_index = len(self._history) - 1
        elif self._history_index > 0:
            self._history_index -= 1

        self.text = self._history[self._history_index]
        self.move_cursor((len(self.text), 0))

    def action_history_down(self) -> None:
        """Go to the next command in history."""
        if self._history_index == -1:
            return

        if self._history_index < len(self._history) - 1:
            self._history_index += 1
            self.text = self._history[self._history_index]
        else:
            self._history_index = -1
            self.text = self._draft

        self.move_cursor((len(self.text), 0))

    def action_submit(self) -> None:
        """Post a Submitted message with the current text."""
        self.post_message(self.Submitted(self, self.text))

    def action_insert_newline(self) -> None:
        """Insert a newline character."""
        self.insert("\n")
