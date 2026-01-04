import asyncio
from textual.app import App, ComposeResult
from textual.widgets import Header, Footer, Input, RichLog
from textual.containers import Container

from agent import AngelicaAgent
from modules.tui_ui import TuiUI

class ChatHistory(RichLog):
    """A widget to display the chat history."""
    pass

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
            ChatHistory(id="history", wrap=True),
            InputBox(id="input", placeholder="Type your message..."),
            id="app-grid"
        )
        yield Footer()

    def on_mount(self) -> None:
        """Called when the app is first mounted."""
        history_widget = self.query_one(ChatHistory)
        tui_ui = TuiUI(history_widget)
        self.agent = AngelicaAgent(tui_ui)
        self.query_one(InputBox).focus()
        tui_ui.print_system("✨ Angelica-AI TUI is ready.")

    async def on_input_submitted(self, message: Input.Submitted) -> None:
        """Called when the user submits a message."""
        user_input = message.value
        if not user_input:
            return

        # The TuiUI will handle printing the user's message
        self.query_one(InputBox).value = ""
        
        # Run the agent processing in a background worker
        self.run_worker(self.agent.process_user_input(user_input), exclusive=True)


if __name__ == "__main__":
    app = TUI()
    app.run()
