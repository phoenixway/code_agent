from textual.app import App, ComposeResult
from textual.widgets import Label, Button, Footer, Header
from textual.containers import Container
from modules.ui_components.selection_widget import SelectionScreen
import logging

# Mock Logger
class MockLogger:
    def info(self, msg):
        print(f"[INFO] {msg}")
    
    def warning(self, msg):
        print(f"[WARN] {msg}")
    
    def error(self, msg):
        print(f"[ERROR] {msg}")

# Mock Agent
class MockAgent:
    def __init__(self):
        self.comm_log = MockLogger()

class DebugSelectionApp(App):
    CSS = """
    Screen {
        align: center middle;
    }
    """
    BINDINGS = [("q", "quit", "Quit"), ("s", "show_selection", "Show Selection")]

    def __init__(self):
        super().__init__()
        self.agent = MockAgent()

    def compose(self) -> ComposeResult:
        yield Header()
        yield Container(
            Label("Press 's' to show the Selection Screen.\nPress 'q' to quit."),
            Button("Show Selection", id="btn_show")
        )
        yield Footer()

    def on_button_pressed(self, event: Button.Pressed) -> None:
        if event.button.id == "btn_show":
            self.action_show_selection()

    def action_show_selection(self) -> None:
        options = ["Model A", "Model B", "Model C", "GPT-4", "Claude 3"]
        
        def on_dismiss(result):
            self.agent.comm_log.info(f"Dialog closed with result: {result}")
            self.query_one(Label).update(f"Last selection: {result}")

        self.push_screen(SelectionScreen(
            prompt="Select an AI Model:",
            options=options,
            current_value="Model A"
        ), on_dismiss)

if __name__ == "__main__":
    app = DebugSelectionApp()
    app.run()
