import os
import asyncio
from textual.app import App, ComposeResult
from textual.widgets import Header, Footer, Input, Static, LoadingIndicator
from textual.containers import Container, VerticalScroll, Horizontal
from agent import AngelicaAgent
from modules.tui_ui import TuiUI

class TUI(App):
    CSS_PATH = "tui.css"
    BINDINGS = [
        ("d", "toggle_dark", "Toggle dark mode"),
        ("q", "quit", "Quit"),
    ]
    VERSION = "0.1.0" # Define version here

    def __init__(self, agent: AngelicaAgent):
        super().__init__()
        self.agent = agent

    def compose(self) -> ComposeResult:
        yield Header()
        with Container():
            yield VerticalScroll(id="history")
            yield Container(
                Horizontal(
                    LoadingIndicator(),
                    Static("Thinking...", id="loading-label"),
                    classes="loading-spinner-container"
                ),
                id="loading-container",
            )
            yield Input(placeholder="Your message...", id="input")
        yield Footer()

    async def on_mount(self) -> None:
        self.ui = TuiUI(self, self.query_one("#history", VerticalScroll), self.query_one("#loading-container"), self.query_one("#loading-label"))
        self.agent.ui = self.ui # Передаємо UI до агента
        
        # Construct the new startup message
        # Check if self.agent.chat is None, if so, get_chat_provider failed during agent init
        model_name = self.agent.chat.model_name if self.agent.chat else "N/A (Provider initialization failed)"
        current_directory = os.getcwd()
        
        startup_message = (
            f"✨ Angelica-AI (v{self.VERSION})\n"
            f"Model: {model_name}\n"
            f"Directory: {current_directory}"
        )
        await self.ui.print_system(startup_message)

    async def on_input_submitted(self, message: Input.Submitted) -> None:
        """Called when the user submits a message."""
        user_input = message.value.strip()
        if not user_input:
            return

        # ВИПРАВЛЕНО: Додано await. Тепер ваше повідомлення з'явиться!
        await self.ui.print_message(user_input, role="user")
        
        # Очищуємо поле вводу через об'єкт повідомлення (це надійніше)
        message.input.value = ""
        
        # Запускаємо обробку агентом у фоновому режимі
        # Тут await не потрібен, бо run_worker сам керує корутиною
        self.run_worker(self.agent.process_user_input(user_input), exclusive=True)

if __name__ == "__main__":
    agent = AngelicaAgent() # Instantiate agent without ui
    app = TUI(agent) # Pass the agent to TUI
    app.run()
