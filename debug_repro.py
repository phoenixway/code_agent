import asyncio
from textual.app import App, ComposeResult
from textual.widgets import Header, Footer, Input, Static
from textual.containers import VerticalScroll, Container, Horizontal
from modules.ui_components.selection_widget import SelectionScreen
from modules.ui_components.history_input import HistoryInput
from modules.ui_components.status_bar import StatusBar
from modules.theme import HACKER_THEME

# Mock Agent
class MockAgent:
    def __init__(self):
        self.comm_log = self
        self.settings = {"theme": "hacker-green"}
        self.chat = type('obj', (object,), {'model_name': 'MockModel'})
    
    def info(self, msg):
        pass
    def warning(self, msg):
        print(f"[WARN] {msg}")
    def error(self, msg):
        print(f"[ERROR] {msg}")

class DebugReproApp(App):
    CSS_PATH = "tui.css"
    
    def __init__(self):
        super().__init__()
        self.agent = MockAgent()

    def compose(self) -> ComposeResult:
        yield Header()
        with Container():
            yield VerticalScroll(id="history")
            yield StatusBar(id="loading-container")
            yield Horizontal(
                Static("> "),
                HistoryInput(placeholder="Type /test NO AWAIT...", id="input"),
                id="input-container"
            )
        yield Footer()

    def on_mount(self):
        self.register_theme(HACKER_THEME)
        self.theme = "hacker-green"
        self.query_one("#input").focus()

    async def on_input_submitted(self, message: Input.Submitted):
        val = message.value
        message.input.value = ""
        
        if val == "/test":
            self.show_selection_no_wait()
        elif val == "/quit":
            self.exit()

    def show_selection_no_wait(self):
        options = ["Option 1", "Option 2", "Option 3"]
        screen = SelectionScreen("Select something:", options)
        
        # Callback style instead of await
        def on_complete(result):
            self.query_one("#history").mount(Static(f"Selected (Callback): {result}", classes="chat-message"))
            self.query_one("#input").focus() # Return focus

        self.push_screen(screen, callback=on_complete)
        print("Screen pushed (no await).")

if __name__ == "__main__":
    app = DebugReproApp()
    app.run()