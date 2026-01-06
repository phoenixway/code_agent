from textual.screen import Screen
from textual.widgets import ListView, ListItem, Label
from textual.app import ComposeResult


class ContextScreen(Screen[int]):
    BINDINGS = [
        ("escape", "cancel", "Cancel"),
    ]

    CONTEXT_SIZES = [4096, 8192, 16384, 32768]

    def compose(self) -> ComposeResult:
        yield Label("Select context size", id="title")

        items = [
            ListItem(
                Label(str(size)),
                id=f"ctx_{size}",
            )
            for size in self.CONTEXT_SIZES
        ]

        yield ListView(*items)

    def on_list_view_selected(self, event: ListView.Selected) -> None:
        size = int(event.item.id.split("_")[1])
        self.dismiss(size)

    def action_cancel(self) -> None:
        self.dismiss(None)

