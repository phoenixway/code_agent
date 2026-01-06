from textual.app import ComposeResult
from textual.widgets import ListView, ListItem, Label
from textual.containers import Vertical
from textual.screen import ModalScreen

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

    def __init__(self, prompt: str, options: list[str], current_value: str | None = None, name: str | None = None, id: str | None = None, classes: str | None = None) -> None:
        super().__init__(name, id, classes)
        self.prompt = prompt
        self.options = options
        self.current_value = current_value

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
        self.app.agent.comm_log.info("DEBUG: SelectionScreen mounted")
        list_view = self.query_one(ListView)
        # Focus the list view immediately
        list_view.focus()
        
        # If current_value is provided, highlight it
        if self.current_value:
            self.app.agent.comm_log.info(f"DEBUG: Highlighting current_value: {self.current_value}")
            try:
                index = self.options.index(self.current_value)
                list_view.index = index
            except ValueError:
                self.app.agent.comm_log.warning(f"DEBUG: current_value '{self.current_value}' not found in options")
                pass

    def on_list_view_selected(self, event: ListView.Selected) -> None:
        # Use the index to get the option from our list
        index = event.list_view.index
        self.app.agent.comm_log.info(f"DEBUG: ListItem selected at index: {index}")
        if index is not None and 0 <= index < len(self.options):
            val = self.options[index]
            self.app.agent.comm_log.info(f"DEBUG: Dismissing SelectionScreen with value: {val}")
            self.dismiss(val)
        else:
            self.app.agent.comm_log.warning("DEBUG: SelectionScreen index out of bounds")
            self.dismiss(None)

    def on_key(self, event) -> None:
        if event.key == "escape":
            self.app.agent.comm_log.info("DEBUG: Escape key pressed in SelectionScreen")
            self.dismiss(None)