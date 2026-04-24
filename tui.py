import os
from datetime import datetime

from modules.agent.core import AngelicaAgent
from textual.app import App, ComposeResult
from textual.widgets import Header, Footer, Static
from textual.containers import Container, VerticalScroll, Horizontal


from modules.tui_ui import TuiUI
from modules.ui_components.history_aware_textarea import HistoryAwareTextArea, SuggestionWidget
from modules.ui_components.status_bar import StatusBar
from modules.ui_components.token_status_bar import TokenStatusBar
from modules.version import __version__
from modules.theme import HACKER_THEME
from modules.command_handler import CommandHandler
from modules.ui_components.command_completer import CommandCompleter
from modules.providers.base import ProviderAPIError


class TUI(App):
    CSS_PATH = "tui.css"
    BINDINGS = [
        ("d", "toggle_dark", "Toggle dark mode"),
        ("q", "quit", "Quit"),
        ("ctrl+q", "quit", "Quit"),
        ("escape", "interrupt_agent", "Interrupt"),
    ]

    def __init__(self, agent: AngelicaAgent):
        super().__init__()
        self.agent = agent
        self.command_handler = CommandHandler(self)
        self.command_completer = CommandCompleter(self.command_handler.command_names)

    def compose(self) -> ComposeResult:
        yield Header()
        with Container():
            yield VerticalScroll(id="history")
            yield StatusBar(id="loading-container")
            yield SuggestionWidget(id="suggestion")
            yield Horizontal(
                Static("> "),
                HistoryAwareTextArea(
                    id="input",
                    placeholder="Enter a prompt or /command...",
                ),
                id="input-container",
            )
        yield TokenStatusBar(id="token-status-bar")
        yield Footer()

    def _provider_error_ui_message(self, error: ProviderAPIError) -> str:
        provider = error.provider_name or "provider"

        if error.kind in {"quota_exceeded", "rate_limit"}:
            if error.retry_after_seconds is not None:
                seconds = max(0.0, float(error.retry_after_seconds))
                return f"{provider}: rate limit / quota reached for this turn. Retry after ~{seconds:.0f}s."
            return f"{provider}: rate limit / quota reached for this turn."

        if error.kind == "provider_unavailable":
            return f"{provider}: temporarily unavailable."

        if error.kind == "auth_error":
            return f"{provider}: authentication or permission error."

        if error.kind == "provider_init_error":
            return error.user_message or f"{provider}: provider initialization failed."

        return error.user_message or f"{provider}: provider error."

    async def _run_agent_prompt(self, user_input: str) -> None:
        try:
            self.agent.log.info(f"DEBUG: Processing regular prompt: '{user_input}'")
            await self.ui.print_message(user_input, role="user")
            self.agent.log.info("DEBUG: Message printed to UI, starting agent")
            await self.agent.process_user_input(user_input)
            self.agent.log.info("DEBUG: Agent prompt finished")
        except ProviderAPIError as e:
            self.agent.log.warning("ProviderAPIError during prompt processing: %s", e.to_dict())
            await self.ui.print_error(self._provider_error_ui_message(e))
        except Exception as e:
            self.agent.log.error(f"ERROR in prompt processing: {e}")
            await self.ui.print_error(f"Critical error: {e}")
        finally:
            if self.app._running:
                self.query_one("#input").focus()

    async def on_mount(self) -> None:
        self.register_theme(HACKER_THEME)

        target_theme = self.agent.config.settings.get("theme", "hacker-green")
        theme_mode = str(target_theme or "").strip().lower()
        if theme_mode in {"auto", "day-night", "by-time"}:
            hour = datetime.now().hour
            target_theme = "textual-light" if 7 <= hour < 19 else "hacker-green"

        try:
            self.theme = target_theme
        except Exception:
            self.agent.log.warning(f"Theme '{target_theme}' not found. Falling back to 'hacker-green'.")
            self.theme = "hacker-green"

        self.ui = TuiUI(self, self.query_one("#history", VerticalScroll), self.query_one(StatusBar))
        self.agent.ui = self.ui

        model_name = self.agent.chat.model_name if self.agent.chat else "N/A (Provider initialization failed)"

        await self.ui.update_header(f"{model_name}")
        current_directory = os.getcwd()

        startup_message = (
            f"✨ Angelica AI (v{__version__})\n"
            f"Model: {model_name}\n"
            f"Working Directory: {current_directory}"
        )
        await self.ui.print_initial_system_message(startup_message)

        input_area = self.query_one("#input", HistoryAwareTextArea)
        suggestion_widget = self.query_one("#suggestion", SuggestionWidget)

        input_area._commands = list(self.command_handler.command_names)
        input_area._suggestion_widget = suggestion_widget

        input_area.focus()

        try:
            initial_history_tokens = self.agent.history.current_token_count
            max_tokens = self.agent.history.max_tokens
            token_bar = self.query_one(TokenStatusBar)
            token_bar.update_tokens(
                history_tokens=initial_history_tokens,
                max_tokens=max_tokens,
                session_tokens=self.agent.state.session_tokens,
            )
        except Exception as e:
            self.agent.log.error(f"Initial token status update failed: {e}")

    async def on_history_aware_text_area_submitted(self, message: HistoryAwareTextArea.Submitted) -> None:
        user_input = message.value.strip()

        self.agent.log.info(f"DEBUG: on_history_aware_text_area_submitted called with: '{user_input}'")

        input_widget = self.query_one(HistoryAwareTextArea)

        if user_input:
            input_widget.add_entry(user_input)

        input_widget.text = ""

        if not user_input:
            return

        if user_input.startswith("/"):
            self.agent.log.info(f"DEBUG: detected command '{user_input}', spawning worker")

            async def run_command():
                try:
                    await self.command_handler.handle(user_input)
                except ProviderAPIError as e:
                    self.agent.log.warning("ProviderAPIError during command handling: %s", e.to_dict())
                    await self.ui.print_error(self._provider_error_ui_message(e))
                except Exception as e:
                    self.agent.log.error(f"Command execution error: {e}")
                    await self.ui.print_error(f"Command failed: {e}")
                finally:
                    if self.app._running and not user_input.startswith("/quit"):
                        self.query_one("#input").focus()

            self.run_worker(run_command())
            return

        try:
            self.agent.log.info("DEBUG: Scheduling regular prompt worker")
            self.run_worker(self._run_agent_prompt(user_input), exclusive=True)
            self.agent.log.info("DEBUG: Agent worker scheduled")
        except Exception as e:
            self.agent.log.error(f"ERROR scheduling prompt processing: {e}")
            await self.ui.print_error(f"Critical error: {e}")

    async def action_interrupt_agent(self) -> None:
        await self.agent.interrupt()

    async def action_quit(self) -> None:
        self.agent.log.info("DEBUG: action_quit called. Saving session...")
        self.agent.session_manager.save_session()
        self.agent.log.info("DEBUG: Session saved. Exiting...")
        self.exit()


if __name__ == "__main__":
    agent = AngelicaAgent()
    app = TUI(agent)
    app.run()