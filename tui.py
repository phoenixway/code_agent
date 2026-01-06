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
        
        # Check if we are in the middle of a model selection
        if self.agent.is_awaiting_model_selection:
            # ... (keep existing logic) ...
            available_models = self.agent.settings.get("available_models", [])
            try:
                choice_index = int(user_input) - 1
                if 0 <= choice_index < len(available_models):
                    selected_model = available_models[choice_index]
                    self.agent.comm_log.info(f"User selected model choice {user_input} -> '{selected_model}'.")
                    self.run_worker(self.agent.switch_model(selected_model), exclusive=True)
                else:
                    await self.ui.print_error("Invalid selection. Please try again.")
                    self.agent.comm_log.warning(f"Invalid model selection index: {choice_index}")
            except ValueError:
                await self.ui.print_error(f"Invalid input. Please enter a number or 'cancel'.")
                self.agent.comm_log.warning(f"Non-integer input received for model selection: '{user_input}'")

            if user_input.lower() == 'cancel' or 'c':
                self.agent.is_awaiting_model_selection = False
                await self.ui.print_system("Model selection cancelled.")
            return

        if user_input == "/models":
            # ... (keep existing logic) ...
            self.agent.comm_log.info("`/models` command received. Displaying list.")
            available_models = self.agent.settings.get("available_models", [])
            if not available_models:
                self.agent.comm_log.error("No available models found in settings.")
                await self.ui.print_error("No available models configured.")
                return

            message_lines = ["Available models:"]
            for i, model in enumerate(available_models):
                is_current = model.split('/')[-1] == self.agent.chat.model_name.split('/')[-1]
                message_lines.append(f"  {i+1}: {model} {'(current)' if is_current else ''}")
            message_lines.append("\nEnter the number of the model to switch to, or 'cancel' to abort.")
            
            await self.ui.print_system("\n".join(message_lines))
            self.agent.is_awaiting_model_selection = True
            return

        if user_input == "/context":
            self.log("DEBUG: Scheduling _handle_context_command worker")
            self.run_worker(self._handle_context_command(), exclusive=True)
            return

        # Default behavior: process as a prompt
        await self.ui.print_message(user_input, role="user")
        self.run_worker(self.agent.process_user_input(user_input), exclusive=True)

    async def action_interrupt_agent(self) -> None:
        """Interrupts the agent's current operation."""
        await self.agent.interrupt()

if __name__ == "__main__":
    agent = AngelicaAgent() # Instantiate agent without ui
    app = TUI(agent) # Pass the agent to TUI
    app.run()