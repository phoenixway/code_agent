from textual.app import ComposeResult
from textual.widgets import ListView, ListItem, Label
from textual.containers import Vertical
from textual.screen import ModalScreen

class SelectionScreen(ModalScreen[str | None]):
    """Screen for selecting an option from a list, styled to look like a bottom widget."""

    CSS = """
    SelectionScreen {
        align: center bottom;
        background: rgba(0, 0, 0, 0.5);
    }
    
    .selection-panel {
        width: 100%;
        height: auto;
        max-height: 50vh;
        margin-bottom: 5; /* Positioned higher to not obscure input */
        border-top: thick $primary;
        border-bottom: thick $primary;
        background: $surface;
        padding: 1 2;
    }
    
    .selection-prompt {
        text-align: left;
        padding-bottom: 1;
        text-style: bold;
        color: $primary;
    }
    
    ListView {
        height: auto;
        max-height: 15;
        border: none;
        margin-top: 1;
        background: $surface;
        scrollbar-color: $primary;
    }
    
    ListItem {
        padding: 0 1;
        background: $surface;
        color: $text;
    }
    
    ListItem:hover {
        background: $secondary;
        color: white;
    }
    
    /* Highlight the selected item when list is focused */
    ListView > ListItem.--highlight {
        background: $primary 30%;
        color: $primary;
        text-style: bold;
    }

    ListView:focus > ListItem.--highlight {
        background: $primary;
        color: $background;
        text-style: bold;
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

    def _update_markers(self, active_index: int | None) -> None:
        """Adds a '❯ ' marker to the active item and removes it from others."""
        items = self.query("ListItem")
        for i, item in enumerate(items):
            label = item.query_one(Label)
            base_text = self.options[i]
            if i == active_index:
                label.update(f"❯ {base_text}")
            else:
                label.update(f"  {base_text}")

    def on_mount(self) -> None:
        self.app.agent.comm_log.info("DEBUG: SelectionScreen mounted")
        list_view = self.query_one(ListView)
        list_view.focus()
        
        initial_index = 0
        if self.current_value:
            try:
                initial_index = self.options.index(self.current_value)
                list_view.index = initial_index
            except ValueError:
                pass
        
        self._update_markers(initial_index)

    def on_list_view_highlighted(self, event: ListView.Highlighted) -> None:
        """Update markers when the selection changes."""
        self._update_markers(event.list_view.index)

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