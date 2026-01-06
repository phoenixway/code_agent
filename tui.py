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
        ("escape", "interrupt_agent", "Interrupt"),
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
            yield Horizontal(
                Static("> "),
                Input(placeholder="Your message...", id="input"),
                id="input-container"
            )
        yield Footer()

    async def on_mount(self) -> None:
        self.ui = TuiUI(self, self.query_one("#history", VerticalScroll), self.query_one("#loading-container"), self.query_one("#loading-label"))
        self.agent.ui = self.ui # Передаємо UI до агента
        
        # Check if self.agent.chat is None, if so, get_chat_provider failed during agent init
        model_name = self.agent.chat.model_name if self.agent.chat else "N/A (Provider initialization failed)"
        # Set the full title including the model name
        await self.ui.update_header(f"{model_name}")
        current_directory = os.getcwd()
        
        startup_message = (
            f"✨ Angelica-AI (v{self.VERSION})\n"
            f"Model: {model_name}\n"
            f"Working Directory: {current_directory}"
        )
        await self.ui.print_system(startup_message)
        await self.ui.print_system("") # Add an empty line after the startup message
        self.query_one("#input", Input).focus()

    async def _handle_context_command(self):
        """Handles the /context command in a worker to prevent blocking."""
        self.log("DEBUG: Worker started for /context")
        self.agent.comm_log.info("`/context` command received.")
        
        options = ["small", "medium", "large"]
        self.log("DEBUG: Calling ui.pick_option from worker")
        
        try:
            selection = await self.ui.pick_option("Choose context size (Esc to cancel):", options)
            self.log(f"DEBUG: pick_option returned: {selection}")
            
            if selection:
                self.agent.set_context_size(selection)
            else:
                 await self.ui.print_system("Selection cancelled.")
        except Exception as e:
            self.log(f"ERROR in _handle_context_command: {e}")
            self.agent.comm_log.error(f"Error handling context command: {e}")

    async def on_input_submitted(self, message: Input.Submitted) -> None:
        """Called when the user submits a message."""
        user_input = message.value.strip()
        message.input.value = ""

        self.log(f"DEBUG: Input submitted: '{user_input}'")
        if not user_input:
            return
        
        # --- COMMANDS ---

        if user_input == "/models":
            self.agent.comm_log.info("`/models` command received.")
            
            # Fetch models
            available_models = self.agent.settings.get("available_models", [])
            if not available_models:
                await self.ui.print_error("No available models configured in settings.")
                return

            # Helper to run model selection in a worker
            async def _select_model_worker():
                self.log("DEBUG: Starting model selection worker")
                # Identify current model to maybe highlight it (optional, logic not in Screen yet)
                current = self.agent.chat.model_name
                
                # Show picker
                selection = await self.ui.pick_option(
                    f"Select AI Model (Current: {current})", 
                    available_models
                )
                
                if selection:
                    # Switch model
                    await self.agent.switch_model(selection)
                else:
                    await self.ui.print_system("Model selection cancelled.")

            # Run in worker to avoid blocking
            self.run_worker(_select_model_worker(), exclusive=True)
            return

        if user_input == "/context":
            self.log("DEBUG: Scheduling _handle_context_command worker")
            self.run_worker(self._handle_context_command(), exclusive=True)
            return

        # --- DEFAULT: CHAT PROMPT ---
        await self.ui.print_message(user_input, role="user")
        self.run_worker(self.agent.process_user_input(user_input), exclusive=True)

    async def action_interrupt_agent(self) -> None:
        """Interrupts the agent's current operation."""
        await self.agent.interrupt()

if __name__ == "__main__":
    agent = AngelicaAgent() # Instantiate agent without ui
    app = TUI(agent) # Pass the agent to TUI
    app.run()