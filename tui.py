import asyncio
from textual.app import App, ComposeResult
from textual.widgets import Header, Footer, Input, ListView, Static, LoadingIndicator
from textual.containers import Container
from textual.worker import Worker, WorkerState

from agent import AngelicaAgent
from modules.tui_ui import TuiUI


class InputBox(Input):
    """A custom input box for user messages."""
    pass

class TUI(App):
    """The main Textual application for Angelica-AI."""

    CSS_PATH = "tui.css"
    BINDINGS = [("q", "quit", "Quit")]

    def compose(self) -> ComposeResult:
        """Create child widgets for the app."""
        yield Header()
        yield Container(
            ListView(id="history"),
            InputBox(id="input", placeholder="Type your message..."),
            LoadingIndicator(id="loading"),
            id="app-grid"
        )
        yield Footer()

    def on_mount(self) -> None:
        """Called when the app is first mounted."""
        history_widget = self.query_one(ListView)
        tui_ui = TuiUI(history_widget)
        self.agent = AngelicaAgent(tui_ui)
        self.query_one(InputBox).focus()
        tui_ui.print_system("✨ Angelica-AI TUI is ready.")

    async def on_input_submitted(self, message: Input.Submitted) -> None:
        """Called when the user submits a message."""
        user_input = message.value
        if not user_input:
            return

        self.agent.ui.print_message(user_input, role="user")
        self.query_one(InputBox).value = ""
        
        self.query_one("#loading").display = True
        self.run_worker(self.agent.process_user_input(user_input), exclusive=True)

    def on_worker_state_changed(self, event: WorkerState) -> None:
        """Called when the worker state changes."""
        if event.worker.state == "success":
            self.query_one("#loading").display = False


if __name__ == "__main__":
    app = TUI()
    app.run()
