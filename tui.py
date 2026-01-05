import asyncio
from textual.app import App, ComposeResult
from textual.widgets import Header, Footer, Input, Static, LoadingIndicator, Button
from textual.containers import Container, Horizontal, Vertical, VerticalScroll
from textual.screen import Screen
from textual.worker import Worker, WorkerState

from agent import AngelicaAgent
from modules.tui_ui import TuiUI

class InputBox(Input):
    """A custom input box for user messages."""
    pass

class TUI(App):
    """The main Textual application for Angelica-AI."""

    CSS_PATH = "tui.css"
    BINDINGS = [("q", "quit", "Quit")]

    # tui.py

    def compose(self) -> ComposeResult:
        yield Header()
        yield Container(
            VerticalScroll(id="history"),
            Horizontal(
                LoadingIndicator(),
                Static("", id="loading-label"), # Лейбл для тексту статусу
                id="loading-container"
            ),
            InputBox(id="input", placeholder="Type your message..."),
            id="app-grid"
        )
        yield Footer()


    async def on_mount(self) -> None:
        history_widget = self.query_one("#history", VerticalScroll)
        loading_container = self.query_one("#loading-container")
        loading_label = self.query_one("#loading-label", Static)
        
        # Використовуємо self.ui, щоб мати доступ з усіх методів класу
        self.ui = TuiUI(self, history_widget, loading_container, loading_label)
        self.agent = AngelicaAgent(self.ui)
        
        self.query_one(InputBox).focus()
        await self.ui.print_system("✨ Angelica-AI TUI is ready.")

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
    app = TUI()
    app.run()
