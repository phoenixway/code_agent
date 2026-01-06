from textual.app import ComposeResult
from textual.widgets import Static, Button, ListView, ListItem, Label
from textual.containers import Horizontal, Vertical
from textual.screen import ModalScreen

class ConfirmationScreen(ModalScreen[bool]):
    """Screen to ask the user for confirmation for sensitive actions."""

    CSS = """
    ConfirmationScreen {
        align: center middle;
    }
    
    .confirmation-panel {
        width: 60;
        height: auto;
        border: thick $primary;
        background: $surface;
        padding: 1 2;
    }
    
    .confirmation-title {
        text-align: center;
        margin-bottom: 1;
    }
    
    .confirmation-buttons {
        align: center middle;
        margin-top: 1;
    }
    
    Button {
        margin: 0 1;
    }
    """

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

class SelectionScreen(ModalScreen[str | None]):
    """Screen for selecting an option from a list, styled to look like a bottom widget."""

    CSS = """
    SelectionScreen {
        align: center bottom;
        background: 0%; /* Transparent background */
    }
    
    .selection-panel {
        width: 100%;
        height: auto;
        max-height: 50vh;
        margin-bottom: 3; /* Position above the input container */
        border-top: thick $accent;
        background: $surface;
        padding: 1 2;
    }
    
    .selection-prompt {
        text-align: left;
        padding-bottom: 1;
        text-style: bold;
        color: $text;
    }
    
    ListView {
        height: auto;
        max-height: 15;
        border: none;
        margin-top: 1;
        background: $surface;
    }
    
    ListItem {
        padding: 0 1;
    }
    
    ListItem:hover {
        background: $primary-darken-2;
    }
    
    /* Highlight the selected item when list is focused */
    ListView:focus > ListItem.-active {
        background: $primary;
        color: white;
    }
    """

    def __init__(self, prompt: str, options: list[str], name: str | None = None, id: str | None = None, classes: str | None = None) -> None:
        super().__init__(name, id, classes)
        self.prompt = prompt
        self.options = options

    def compose(self) -> ComposeResult:
        yield Vertical(
            Label(self.prompt, classes="selection-prompt"),
            ListView(
                *[ListItem(Label(opt), id=f"opt_{i}") for i, opt in enumerate(self.options)],
                id="options_list"
            ),
            classes="selection-panel"
        )

    def on_mount(self) -> None:
        # Focus the list view immediately
        self.query_one("ListView").focus()

    def on_list_view_selected(self, event: ListView.Selected) -> None:
        # Use the index to get the option from our list
        index = event.list_view.index
        if index is not None and 0 <= index < len(self.options):
            self.dismiss(self.options[index])
        else:
            self.dismiss(None)

    def on_key(self, event) -> None:
        if event.key == "escape":
            self.dismiss(None)