import os
import asyncio
import shlex
from textual.app import App, ComposeResult
from textual.widgets import Header, Footer, Static, LoadingIndicator
from textual.containers import Container, VerticalScroll, Horizontal
from agent import AngelicaAgent
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
        ("ctrl+q", "quit", "Quit"),
        ("escape", "interrupt_agent", "Interrupt"),
    ]
    
    # List of available slash commands
    SLASH_COMMANDS = ["/add", "/drop", "/models", "/theme", "/history-size", "/history-summarize", "/cd", "/export", "/import", "/help", "/quit"]
    
    def __init__(self, agent: AngelicaAgent):
        super().__init__()
        self.agent = agent

    def compose(self) -> ComposeResult:
        yield Header()
        with Container():
            yield VerticalScroll(id="history")
            yield Static(id="suggestion-box", classes="hidden")
            yield StatusBar(id="loading-container")
            yield Horizontal(
                Static("> "),
                HistoryInput(id="input", slash_commands=self.SLASH_COMMANDS, logger=self.agent.log),
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
            self.agent.log.warning(f"Theme '{target_theme}' not found. Falling back to 'hacker-green'.")
            self.theme = "hacker-green"
        
        self.ui = TuiUI(self, self.query_one("#history", VerticalScroll), self.query_one(StatusBar))
        self.agent.ui = self.ui # Pass UI to agent
        
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
        await self.ui.print_initial_system_message(startup_message)
        self.query_one("#input", HistoryInput).focus()

    def on_history_input_suggestion(self, message: HistoryInput.Suggestion) -> None:
        suggestion_box = self.query_one("#suggestion-box", Static)
        if message.suggestions:
            
            def highlight(s, i):
                if i == message.sender.suggestion_index:
                    return f"[b white on blue]{s}[/]"
                else:
                    return s
            
            suggestion_text = "  ".join(highlight(s, i) for i, s in enumerate(message.suggestions))
            suggestion_box.update(suggestion_text)
            suggestion_box.remove_class("hidden")
        else:
            suggestion_box.add_class("hidden")

    async def on_history_input_submitted(self, message: HistoryInput.Submitted) -> None:
        """Called when the user submits a message."""
        user_input = message.text.strip()
        
        self.agent.log.info(f"DEBUG: on_history_input_submitted called with: '{user_input}'")
        
        # Add to input history if not empty
        if user_input:
            if hasattr(message.sender, 'add_entry'):
                message.sender.add_entry(user_input)
            else:
                self.agent.log.warning("WARNING: Input widget does not support add_entry")
            
        message.sender.text = ""

        if not user_input:
            return
        
        # --- COMMAND HANDLING DELEGATION ---
        # Check if it's a command (starts with /)
        if user_input.startswith("/"):
            self.agent.log.info(f"DEBUG: detected command '{user_input}', spawning worker")
            
            async def run_command():
                try:
                    await self.command_handler.handle(user_input)
                except Exception as e:
                    self.agent.log.error(f"Command execution error: {e}")
                    await self.ui.print_error(f"Command failed: {e}")
                finally:
                    # Only restore focus if we aren't quitting and app is running
                    if self.app._running and not user_input.startswith("/quit"):
                        self.query_one("#input").focus()
            
            self.run_worker(run_command())
            return

        # --- DEFAULT: CHAT PROMPT ---
        try:
            self.agent.log.info(f"DEBUG: Processing regular prompt: '{user_input}'")
            await self.ui.print_message(user_input, role="user")
            self.agent.log.info("DEBUG: Message printed to UI, starting agent worker")
            self.run_worker(self.agent.process_user_input(user_input), exclusive=True)
            self.agent.log.info("DEBUG: Agent worker scheduled")
        except Exception as e:
            self.agent.log.error(f"ERROR in prompt processing: {e}")
            await self.ui.print_error(f"Critical error: {e}")

    async def action_interrupt_agent(self) -> None:
        """Interrupts the agent's current operation."""
        await self.agent.interrupt()

    async def action_quit(self) -> None:
        """Quit the application immediately."""
        self.agent.log.info("DEBUG: action_quit called. Saving session...")
        self.agent.session_manager.save_session()
        self.agent.log.info("DEBUG: Session saved. Exiting...")
        self.exit()

if __name__ == "__main__":
    agent = AngelicaAgent() # Instantiate agent without ui
    app = TUI(agent) # Pass the agent to TUI
    app.run()
