from textual.containers import Container, Horizontal
from textual.widgets import LoadingIndicator, Static
from rich.text import Text
import time


class StatusBar(Container):
    """
    Компонент, що відображає статус роботи агента (спіннер + текст).
    """

    def compose(self):
        yield Horizontal(
            LoadingIndicator(),
            Static("", id="loading-label"),
            Static("", id="loading-elapsed"),
            classes="loading-spinner-container"
        )
        self._step_started_at = None
        self._elapsed_timer = None

    def _ensure_timer(self):
        if self._elapsed_timer is None:
            self._elapsed_timer = self.set_interval(0.2, self._update_elapsed, pause=True)

    def _start_step_timer(self):
        self._step_started_at = time.monotonic()
        self._ensure_timer()
        if self._elapsed_timer is not None:
            self._elapsed_timer.resume()
        self._update_elapsed()

    def _update_elapsed(self):
        elapsed_widget = self.query_one("#loading-elapsed", Static)
        if self._step_started_at is None:
            elapsed_widget.update("")
            return
        elapsed = time.monotonic() - self._step_started_at
        elapsed_widget.update(Text(f"{elapsed:.1f}s", style="dim"))

    def start_thinking(self):
        """Вмикає режим 'Thinking...'"""
        label = Text()
        label.append("thinking", style="bold")
        self.query_one("#loading-label", Static).update(label)
        self._start_step_timer()
        self.display = True

    def start_action(self, text: str):
        """Вмикає режим відображення конкретної дії."""
        label_text = text.strip() if text else "processing"

        # Split "verb path" so path is dim
        parts = label_text.split(" ", 1)
        label = Text()
        if len(parts) == 2:
            label.append(parts[0], style="bold")
            label.append("  ", style="")
            label.append(parts[1], style="dim")
        else:
            label.append(label_text, style="bold")

        self.query_one("#loading-label", Static).update(label)
        self._start_step_timer()
        self.display = True

    def stop(self):
        """Приховує статус бар."""
        self._step_started_at = None
        if self._elapsed_timer is not None:
            self._elapsed_timer.pause()
        self.query_one("#loading-elapsed", Static).update("")
        self.display = False