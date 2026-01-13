import os
import asyncio
import shlex
from textual.app import App, ComposeResult
from textual.widgets import Header, Footer, Input, Static, LoadingIndicator
from textual.containers import Container, VerticalScroll, Horizontal
from agent import AngelicaAgent
from textual.suggester import SuggestFromList
from modules.tui_ui import TuiUI
from modules.ui_components.history_input import HistoryInput
from modules.ui_components.status_bar import StatusBar
from modules.version import __version__
from modules.theme import HACKER_THEME
from modules.config_loader import update_settings
from modules.command_handler import CommandHandler

class TUI(App):
    CSS_PATH = "tui.css"
    BINDINGS = [
        ("d", "toggle_dark", "Toggle dark mode"),
        ("q", "quit", "Quit"),
        ("escape", "interrupt_agent", "Interrupt"),
    ]
    
    # List of available slash commands for autocomplete
    COMMANDS = ["/add", "/drop", "/models", "/theme", "/history-size", "/cd", "/export", "/import", "/help", "/quit"]
    
    def __init__(self, agent: AngelicaAgent):
        super().__init__()
        self.agent = agent

    def compose(self) -> ComposeResult:
        yield Header()
        with Container():
            yield VerticalScroll(id="history")
            yield StatusBar(id="loading-container")
            yield Horizontal(
                Static("> "),
                HistoryInput(
                    placeholder="Your message...", 
                    id="input",
                    suggester=SuggestFromList(self.COMMANDS, case_sensitive=False)
                ),
                id="input-container"
            )
        yield Footer()

    async def on_mount(self) -> None:
        # Register custom themes
        self.register_theme(HACKER_THEME)
        
        # Apply theme from config (default to 'hacker-green')
        target_theme = self.agent.settings.get("theme", "hacker-green")
        try:
            self.theme = target_theme
        except Exception:
            self.agent.comm_log.warning(f"Theme '{target_theme}' not found. Falling back to 'hacker-green'.")
            self.theme = "hacker-green"
        
        self.ui = TuiUI(self, self.query_one("#history", VerticalScroll), self.query_one(StatusBar))
        self.agent.ui = self.ui # Передаємо UI до агента
        
        # Initialize Command Handler
        self.command_handler = CommandHandler(self)
        
        # Check if self.agent.chat is None, if so, get_chat_provider failed during agent init
        model_name = self.agent.chat.model_name if self.agent.chat else "N/A (Provider initialization failed)"
        # Set the full title including the model name
        await self.ui.update_header(f"{model_name}")
        current_directory = os.getcwd()
        
        startup_message = (
            f"✨ Angelica AI (v{__version__})\n"
            f"Model: {model_name}\n"
            f"Working Directory: {current_directory}"
        )
        await self.ui.print_system(startup_message)
        # await self.ui.print_system("") # Removed extra empty line
        self.query_one("#input", HistoryInput).focus()

    async def on_input_submitted(self, message: Input.Submitted) -> None:
        """Called when the user submits a message."""
        user_input = message.value.strip()
        
        self.agent.comm_log.info(f"DEBUG: on_input_submitted called with: '{user_input}'")
        
        # Add to input history if not empty
        if user_input:
            if hasattr(message.input, 'add_entry'):
                message.input.add_entry(user_input)
            else:
                self.agent.comm_log.warning("WARNING: Input widget does not support add_entry")
            
        message.input.value = ""

        if not user_input:
            return
        
        # --- COMMAND HANDLING DELEGATION ---
        if await self.command_handler.handle(user_input):
            return

        # --- DEFAULT: CHAT PROMPT ---
        try:
            self.agent.comm_log.info(f"DEBUG: Processing regular prompt: '{user_input}'")
            await self.ui.print_message(user_input, role="user")
            self.agent.comm_log.info("DEBUG: Message printed to UI, starting agent worker")
            self.run_worker(self.agent.process_user_input(user_input), exclusive=True)
            self.agent.comm_log.info("DEBUG: Agent worker scheduled")
        except Exception as e:
            self.agent.comm_log.error(f"ERROR in prompt processing: {e}")
            await self.ui.print_error(f"Critical error: {e}")

    async def action_interrupt_agent(self) -> None:
        """Interrupts the agent's current operation."""
        await self.agent.interrupt()

if __name__ == "__main__":
    agent = AngelicaAgent() # Instantiate agent without ui
    app = TUI(agent) # Pass the agent to TUI
    app.run()

    async def action_interrupt_agent(self) -> None:
        """Interrupts the agent's current operation."""
        await self.agent.interrupt()

if __name__ == "__main__":
    agent = AngelicaAgent() # Instantiate agent without ui
    app = TUI(agent) # Pass the agent to TUI
    app.run()