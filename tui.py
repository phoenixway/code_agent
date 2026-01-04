import asyncio
from textual.app import App, ComposeResult
from textual.widgets import Header, Footer, Input, ListView, Static, LoadingIndicator, Button
from textual.containers import Container, Horizontal, Vertical
from textual.screen import Screen
from textual.worker import Worker, WorkerState

from agent import AngelicaAgent
from modules.tui_ui import TuiUI

class InputBox(Input):
    """A custom input box for user messages."""
    pass

class ConfirmationScreen(Screen[bool]):
    """Screen to ask the user for confirmation for sensitive actions."""

    def __init__(self, action_details: dict, name: str | None = None, id: str | None = None, classes: str | None = None) -> None:
        super().__init__(name, id, classes)
        self.action_details = action_details

    def compose(self) -> ComposeResult:
        action_type = self.action_details.get("type", "Unknown")
        details = ""
        if action_type == "run_command":
            details = self.action_details.get("command", "")
        elif action_type in ["write_file", "create_file", "edit_file"]:
            details = self.action_details.get("path") or self.action_details.get("file_path", "")

        yield Vertical(
            Static(f"[bold yellow]⚠️  ALLOW this action? ⚠️[/bold yellow]", classes="confirmation-title"),
            Static(f"   - Type: [bold cyan]{action_type}[/bold cyan]", classes="confirmation-detail"),
            Static(f"   - Details: [bold red]{details}[/bold red]", classes="confirmation-detail"),
            Horizontal(
                Button("Allow", id="allow_button", variant="success"),
                Button("Deny", id="deny_button", variant="error"),
                classes="confirmation-buttons"
            ),
            classes="confirmation-panel"
        )

    def on_button_pressed(self, event: Button.Pressed) -> None:
        if event.button.id == "allow_button":
            self.dismiss(True)
        elif event.button.id == "deny_button":
            self.dismiss(False)

class TUI(App):
    """The main Textual application for Angelica-AI."""

    CSS_PATH = "tui.css"
    BINDINGS = [("q", "quit", "Quit")]

    def compose(self) -> ComposeResult:
        """Create child widgets for the app."""
        yield Header()
        yield Container(
            ListView(id="history"),
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
        """Called when the app is first mounted."""
        history_widget = self.query_one(ListView)
        loading_container = self.query_one("#loading-container")
        loading_label = self.query_one("#loading-label", Static)
        
        tui_ui = TuiUI(self, history_widget, loading_container, loading_label)
        self.agent = AngelicaAgent(tui_ui)
        self.query_one(InputBox).focus()
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
