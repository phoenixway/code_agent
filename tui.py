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
        message.input.value = "" # Clear input immediately

        if not user_input:
            return

        if user_input == "/models":
            self.agent.comm_log.info("`/models` command received. Opening selection screen.")
            available_models = self.agent.settings.get("available_models", [])
            if not available_models:
                self.agent.comm_log.error("No available models found in settings.")
                await self.ui.print_error("No available models configured.")
                return
            
            current_model = self.agent.chat.model_name if self.agent.chat else "unknown"
            selected_model = await self.ui.select_model(available_models, current_model)
            
            # Corrected checking logic
            self.agent.comm_log.info(f"Model selection result: '{selected_model}' (type: {type(selected_model)})")
            
            if selected_model is None:
                self.agent.comm_log.info("Model selection cancelled (None returned).")
                await self.ui.print_system("Model selection cancelled.")
                return

            if selected_model == "":
                self.agent.comm_log.info("Model selection cancelled (empty string returned).")
                await self.ui.print_system("Model selection cancelled.")
                return

            # Normalize current model name for comparison (e.g. qwen:4b from ollama/qwen:4b)
            current_model_normalized = current_model.split('/')[-1] if '/' in current_model else current_model
            selected_model_normalized = selected_model.split('/')[-1] if '/' in selected_model else selected_model

            if selected_model_normalized == current_model_normalized:
                self.agent.comm_log.info(f"Selected model '{selected_model}' is already active.")
                await self.ui.print_system(f"Model {selected_model} is already active.")
            else:
                self.agent.comm_log.info(f"Switching to new model: '{selected_model}'")
                self.run_worker(self.agent.switch_model(selected_model), exclusive=True)
            return
        
        await self.ui.print_message(user_input, role="user")
        self.run_worker(self.agent.process_user_input(user_input), exclusive=True)

    async def action_interrupt_agent(self) -> None:
        """Interrupts the agent's current operation."""
        await self.agent.interrupt()

if __name__ == "__main__":
    agent = AngelicaAgent() # Instantiate agent without ui
    app = TUI(agent) # Pass the agent to TUI
    app.run()
