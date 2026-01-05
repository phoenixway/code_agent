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
        
        # Construct the new startup message
        # Check if self.agent.chat is None, if so, get_chat_provider failed during agent init
        model_name = self.agent.chat.model_name if self.agent.chat else "N/A (Provider initialization failed)"
        self.query_one("Header").sub_title = f"Model: {model_name}"
        current_directory = os.getcwd()
        
        startup_message = (
            f"✨ Angelica-AI (v{self.VERSION})\n"
            f"Directory: {current_directory}"
        )
        await self.ui.print_system(startup_message)
        self.query_one("#input", Input).focus()

    async def on_input_submitted(self, message: Input.Submitted) -> None:
        """Called when the user submits a message."""
        user_input = message.value.strip()
        message.input.value = ""

        if not user_input:
            return
        
        # Check if we are in the middle of a model selection
        if self.agent.is_awaiting_model_selection:
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

            # Always reset the state after an attempt
            if user_input.lower() == 'cancel' or 'c':
                self.agent.is_awaiting_model_selection = False
                await self.ui.print_system("Model selection cancelled.")
            return

        if user_input == "/models":
            self.agent.comm_log.info("`/models` command received. Displaying list.")
            available_models = self.agent.settings.get("available_models", [])
            if not available_models:
                self.agent.comm_log.error("No available models found in settings.")
                await self.ui.print_error("No available models configured.")
                return

            # Build the message to show the user
            message_lines = ["Available models:"]
            for i, model in enumerate(available_models):
                is_current = model.split('/')[-1] == self.agent.chat.model_name.split('/')[-1]
                message_lines.append(f"  {i+1}: {model} {'(current)' if is_current else ''}")
            message_lines.append("\nEnter the number of the model to switch to, or 'cancel' to abort.")
            
            await self.ui.print_system("\n".join(message_lines))
            
            # Set the state to wait for the user's choice
            self.agent.is_awaiting_model_selection = True
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
