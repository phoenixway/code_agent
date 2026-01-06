from textual.app import App, ComposeResult
from textual.containers import Vertical, Container
from textual.widgets import Input, ListView, ListItem, Label
from textual.reactive import reactive


class ContextPicker(Container):
    visible = reactive(False)

    CONTEXT_SIZES = [4096, 8192, 16384, 32768]

    def compose(self) -> ComposeResult:
        yield ListView(
            *[
                ListItem(Label(str(size)), id=f"ctx_{size}")
                for size in self.CONTEXT_SIZES
            ],
            id="context-list",
        )

    def show(self) -> None:
        self.styles.display = "block"
        self.visible = True

    def hide(self) -> None:
        self.styles.display = "none"
        self.visible = False


class DemoApp(App):
    CSS = """
    Screen {
        layout: vertical;
    }

    #main {
        height: 1fr;
    }

    #context-picker {
        background: #1e1e1e;
        border: solid #3a3a3a;
        width: 32;
        max-height: 6;
        layer: overlay;
        dock: bottom;
        margin-bottom: 1;
        display: none;
    }

    #command-input {
        dock: bottom;
    }
    """

    def compose(self) -> ComposeResult:
        with Container(id="main"):
            yield ContextPicker(id="context-picker")
        yield Input(
            placeholder="Type /context",
            id="command-input",
        )

    def on_input_submitted(self, event: Input.Submitted) -> None:
        if event.value.strip() == "/context":
            self.query_one("#context-picker", ContextPicker).show()

    def on_list_view_selected(self, event: ListView.Selected) -> None:
        size = int(event.item.id.split("_")[1])
        picker = self.query_one("#context-picker", ContextPicker)
        picker.hide()
        self.notify(f"Selected context: {size}")

    def on_key(self, event) -> None:
        if event.key == "escape":
            self.query_one("#context-picker", ContextPicker).hide()


if __name__ == "__main__":
    DemoApp().run()

