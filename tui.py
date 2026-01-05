import asyncio
from textual.app import App, ComposeResult
from textual.widgets import Header, Footer, Input, ListView, Static, LoadingIndicator, Button
from textual.containers import Container, Horizontal, Vertical, VerticalScroll
from textual.screen import Screen
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
        yield Header()
        yield Container(
            VerticalScroll(id="history"), # Змінено з ListView на VerticalScroll
            Horizontal(
                LoadingIndicator(),
                Static("", id="loading-label"),
                id="loading-container"
            ),
            InputBox(id="input", placeholder="Type your message..."),
            id="app-grid"
        )
        yield Footer()

    def on_mount(self) -> None:
        # Отримуємо VerticalScroll замість ListView
        history_widget = self.query_one("#history", VerticalScroll)
        loading_container = self.query_one("#loading-container")
        loading_label = self.query_one("#loading-label", Static)
        
        tui_ui = TuiUI(self, history_widget, loading_container, loading_label)
        self.agent = AngelicaAgent(tui_ui)
        self.query_one(InputBox).focus()
        # Тепер це має спрацювати
        tui_ui.print_system("✨ Angelica-AI TUI is ready.")

    async def on_input_submitted(self, message: Input.Submitted) -> None:
        """Called when the user submits a message."""
        user_input = message.value
        if not user_input:
            return

        # Use the thread-safe UI method to print the user's message
        self.agent.ui.print_message(user_input, role="user")
        
        self.query_one(InputBox).value = ""
        
        # Run the agent processing in a background worker
        self.run_worker(self.agent.process_user_input(user_input), exclusive=True)


if __name__ == "__main__":
    app = TUI()
    app.run()
