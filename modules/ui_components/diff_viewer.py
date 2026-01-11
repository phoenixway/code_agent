from textual.app import ComposeResult
from textual.widgets import Static, Button, Label
from textual.containers import Vertical, Horizontal
from textual.screen import ModalScreen
from rich.syntax import Syntax

class DiffViewer(ModalScreen[bool]):
    """Screen to review file changes (Diff) before applying."""

    CSS = """
    DiffViewer {
        align: center middle;
        background: rgba(0, 0, 0, 0.8);
    }
    
    .diff-panel {
        width: 90%;
        height: 80%;
        background: $surface;
        border: thick $primary;
        padding: 1 2;
    }
    
    .diff-title {
        text-align: center;
        text-style: bold;
        color: $warning;
        margin-bottom: 1;
    }
    
    .diff-content {
        height: 1fr;
        border: solid $secondary;
        background: $background;
        margin-bottom: 1;
        overflow: auto;
    }
    
    .diff-buttons {
        height: auto;
        align: center middle;
    }
    
    Button {
        margin: 0 1;
        height: 1;
        min-width: 10;
        border: none;
    }
    """

    def __init__(self, proposal, name: str | None = None, id: str | None = None, classes: str | None = None) -> None:
        super().__init__(name, id, classes)
        self.proposal = proposal

    def compose(self) -> ComposeResult:
        diff_text = self.proposal.diff
        # Use Rich Syntax for colored diffs
        syntax = Syntax(diff_text, "diff", theme="monokai", line_numbers=True)
        
        yield Vertical(
            Label(f"📝 Review Changes: {self.proposal.file_path}", classes="diff-title"),
            Static(syntax, classes="diff-content"),
            Horizontal(
                Button("Apply Changes", variant="success", id="btn_apply"),
                Button("Reject", variant="error", id="btn_reject"),
                classes="diff-buttons"
            ),
            classes="diff-panel"
        )

    def on_button_pressed(self, event: Button.Pressed) -> None:
        if event.button.id == "btn_apply":
            self.dismiss(True)
        else:
            self.dismiss(False)
