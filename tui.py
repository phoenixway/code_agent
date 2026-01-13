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

    async def _handle_history_size_command(self):
        """Handles the /history-size command in a worker to prevent blocking."""
        self.agent.comm_log.info("DEBUG: Worker started for /history-size")
        self.agent.comm_log.info("`/history-size` command received.")
        
        options = ["small", "medium", "large"]
        current = self.agent.history_size
        self.agent.comm_log.info("DEBUG: Calling ui.pick_option from worker")
        
        try:
            selection = await self.ui.pick_option(
                "Choose history limit (Esc to cancel):", 
                options,
                current_value=current
            )
            self.agent.comm_log.info(f"DEBUG: pick_option returned: {selection}")
            
            if selection:
                self.agent.set_history_size(selection)
                # Persist to config
                try:
                    update_settings({"history_size": selection})
                    await self.ui.print_system(f"💾 History size preference saved: {selection}")
                except Exception as e:
                    await self.ui.print_error(f"History size set, but failed to save config: {e}")
            else:
                 await self.ui.print_system("Selection cancelled.")
        except Exception as e:
            self.agent.comm_log.error(f"ERROR in _handle_history_size_command: {e}")

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

        if user_input.startswith("/cd"):
            self.agent.comm_log.info(f"`/cd` command received: {user_input}")
            try:
                parts = shlex.split(user_input)
                if len(parts) < 2:
                    await self.ui.print_error("Usage: /cd <path>")
                    return
                
                new_path = parts[1]
                os.chdir(os.path.expanduser(new_path))
                
                current_dir = os.getcwd()
                await self.ui.print_system(f"📁 Working directory changed to: [bold cyan]{current_dir}[/]")
                
                # Optionally clear context as it might be irrelevant now
                # self.agent.context_manager.clear()
                # await self.ui.print_system("🗑️ Context cleared due to directory change.")
                
            except Exception as e:
                await self.ui.print_error(f"Error changing directory: {e}")
            return

        if user_input.startswith("/export"):
            self.agent.comm_log.info(f"`/export` command received: {user_input}")
            try:
                parts = shlex.split(user_input)
                filename = parts[1] if len(parts) > 1 else "chat_history.md"
                
                # Записуємо історію
                with open(filename, "w", encoding="utf-8") as f:
                    for msg in self.agent.history.messages:
                        role = msg.get("role", "unknown")
                        content = msg.get("content", "")
                        # Записуємо з розділювачем
                        f.write(f"## Role: {role}\n{content}\n\n")
                
                await self.ui.print_system(f"✅ Chat history exported to [bold cyan]{filename}[/]")
            except Exception as e:
                await self.ui.print_error(f"Error exporting history: {e}")
            return

        if user_input.startswith("/import"):
            self.agent.comm_log.info(f"`/import` command received: {user_input}")
            try:
                parts = shlex.split(user_input)
                if len(parts) < 2:
                    await self.ui.print_error("Usage: /import <filename>")
                    return
                
                filename = parts[1]
                if not os.path.exists(filename):
                    await self.ui.print_error(f"File not found: {filename}")
                    return

                with open(filename, "r", encoding="utf-8") as f:
                    content = f.read()
                
                # Простий парсинг
                import re
                # Шукаємо блоки: ## Role: <role>\n<content>
                # Використовуємо split, щоб розділити по заголовках
                chunks = re.split(r"## Role: (\w+)\n", content)
                # chunks[0] - це текст до першого заголовка (зазвичай порожній)
                # Далі йдуть пари: [role, content, role, content...]
                
                new_messages = []
                # Починаємо з індексу 1, бо split повертає роздільник у групі
                if len(chunks) > 1:
                    for i in range(1, len(chunks), 2):
                        role = chunks[i].strip()
                        msg_content = chunks[i+1].strip()
                        new_messages.append({"role": role, "content": msg_content})
                
                count = 0
                for msg in new_messages:
                    self.agent.history.add_message(msg["role"], msg["content"])
                    # Відображаємо в UI, щоб користувач бачив, що додалося
                    role = msg["role"]
                    text = msg["content"]
                    if role == "user":
                        await self.ui.print_message(text, role="user")
                    elif role == "assistant":
                        await self.ui.print_message(text, role="assistant")
                    elif role == "system":
                         # Системні повідомлення можна показати як thoughts або system
                         # Якщо це довгий промпт, краще не спамити.
                         # Але користувач просив "те що бачу".
                         # Часто system messages це промпти або результати tool call.
                         # Tool call results:
                         if text.startswith("SYSTEM RESULT:"):
                             await self.ui.print_command_result(text.replace("SYSTEM RESULT:", "").strip())
                         else:
                             # Не показуємо великі системні промпти, якщо вони не є "видимими"
                             # Але якщо це імпорт, можливо користувач хоче знати.
                             pass
                    count += 1
                
                await self.ui.print_system(f"✅ Imported {count} messages from [bold cyan]{filename}[/]")

            except Exception as e:
                await self.ui.print_error(f"Error importing history: {e}")
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
                    # Persist to config
                    try:
                        update_settings({"default_model": selection})
                        await self.ui.print_system(f"💾 Model preference saved: {selection}")
                    except Exception as e:
                        await self.ui.print_error(f"Model switched, but failed to save config: {e}")
                else:
                    await self.ui.print_system("Model selection cancelled.")

            # Run in worker to avoid blocking
            self.run_worker(_select_model_worker(), exclusive=True)
            return

        if user_input == "/theme":
            self.agent.comm_log.info("`/theme` command received.")
            
            async def _select_theme_worker():
                self.agent.comm_log.info("DEBUG: Starting theme selection worker")
                # Get available themes from Textual app registry
                themes = list(self.available_themes.keys())
                themes.sort()
                
                current = self.theme
                
                selection = await self.ui.pick_option(
                    f"Select Interface Theme (Current: {current})", 
                    themes,
                    current_value=current
                )
                
                if selection:
                    self.theme = selection
                    # Persist theme to config
                    try:
                        update_settings({"theme": selection})
                        await self.ui.print_system(f"🎨 Theme switched to: {selection} (Saved)")
                    except Exception as e:
                        await self.ui.print_error(f"Theme set, but failed to save config: {e}")
                else:
                    await self.ui.print_system("Theme selection cancelled.")

            self.run_worker(_select_theme_worker(), exclusive=True)
            return

        if user_input == "/history-size":
            self.agent.comm_log.info("DEBUG: Scheduling _handle_history_size_command worker")
            self.run_worker(self._handle_history_size_command(), exclusive=True)
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