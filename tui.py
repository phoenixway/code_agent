import os
import asyncio
import shlex
from textual.app import App, ComposeResult
from textual.widgets import Header, Footer, Input, Static, LoadingIndicator
from textual.containers import Container, VerticalScroll, Horizontal
from agent import AngelicaAgent
from modules.tui_ui import TuiUI
from modules.ui_components.history_input import HistoryInput
from modules.ui_components.status_bar import StatusBar

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
            yield StatusBar(id="loading-container")
            yield Horizontal(
                Static("> "),
                HistoryInput(placeholder="Your message...", id="input"),
                id="input-container"
            )
        yield Footer()

    async def on_mount(self) -> None:
        self.ui = TuiUI(self, self.query_one("#history", VerticalScroll), self.query_one(StatusBar))
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
        # await self.ui.print_system("") # Removed extra empty line
        self.query_one("#input", HistoryInput).focus()

    async def _handle_context_command(self):
        """Handles the /context command in a worker to prevent blocking."""
        self.agent.comm_log.info("DEBUG: Worker started for /context")
        self.agent.comm_log.info("`/context` command received.")
        
        options = ["small", "medium", "large"]
        current = self.agent.context_size
        self.agent.comm_log.info("DEBUG: Calling ui.pick_option from worker")
        
        try:
            selection = await self.ui.pick_option(
                "Choose context size (Esc to cancel):", 
                options,
                current_value=current
            )
            self.agent.comm_log.info(f"DEBUG: pick_option returned: {selection}")
            
            if selection:
                self.agent.set_context_size(selection)
            else:
                 await self.ui.print_system("Selection cancelled.")
        except Exception as e:
            self.agent.comm_log.error(f"ERROR in _handle_context_command: {e}")

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
        
        # --- COMMANDS ---

        if user_input.startswith("/add"):
            self.agent.comm_log.info(f"`/add` command received: {user_input}")
            try:
                parts = shlex.split(user_input)
                paths = parts[1:]
                if not paths:
                    await self.ui.print_error("Usage: /add <path1> [path2 ...]")
                    return
                
                total_added = 0
                for path in paths:
                    count = self.agent.context_manager.add_path(path)
                    total_added += count
                    
                await self.ui.print_system(f"✅ Added {total_added} file(s) to context.")
            except Exception as e:
                await self.ui.print_error(f"Error adding paths: {e}")
            return

        if user_input.startswith("/drop"):
            self.agent.comm_log.info(f"`/drop` command received: {user_input}")
            try:
                parts = shlex.split(user_input)
                paths = parts[1:]
                
                if not paths:
                    # Clear all
                    self.agent.context_manager.clear()
                    await self.ui.print_system("🗑️ Context cleared (all files removed).")
                else:
                    total_removed = 0
                    for path in paths:
                        count = self.agent.context_manager.remove_path(path)
                        total_removed += count
                    await self.ui.print_system(f"🗑️ Removed {total_removed} file(s) from context.")
            except Exception as e:
                await self.ui.print_error(f"Error removing paths: {e}")
            return

        if user_input == "/models":
            self.agent.comm_log.info("`/models` command received.")
            
            # Fetch models
            available_models = self.agent.settings.get("available_models", [])
            if not available_models:
                await self.ui.print_error("No available models configured in settings.")
                return

            # Helper to run model selection in a worker
            async def _select_model_worker():
                self.agent.comm_log.info("DEBUG: Starting model selection worker")
                # Identify current model
                current = self.agent.chat.model_name
                
                # Show picker with current value
                selection = await self.ui.pick_option(
                    f"Select AI Model (Current: {current})", 
                    available_models,
                    current_value=current
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
            self.agent.comm_log.info("DEBUG: Scheduling _handle_context_command worker")
            self.run_worker(self._handle_context_command(), exclusive=True)
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