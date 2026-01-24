import os
import shlex
import asyncio
import tempfile
from modules.config_loader import update_settings

class CommandHandler:
    def __init__(self, app):
        """
        Initializes the CommandHandler.
        :param app: The main TUI App instance (provides access to agent, ui, theme, etc.)
        """
        self.app = app
        self.handlers = {
            "/add": self._handle_add,
            "/drop": self._handle_drop,
            "/cd": self._handle_cd,
            "/export": self._handle_export,
            "/import": self._handle_import,
            "/models": self._handle_models,
            "/theme": self._handle_theme,
            "/history-size": self._handle_history_size,
            "/compact": self._handle_compact,
            "/quit": self._handle_quit,
            "/help": self._handle_help,
            "/clearsession": self._handle_clear_session,
            "/find": self._handle_find,
            "/f": self._handle_find
        }

    @property
    def command_names(self) -> list[str]:
        """Returns a list of all available command names."""
        return list(self.handlers.keys())

    @property
    def agent(self):
        return self.app.agent

    @property
    def ui(self):
        return self.app.ui

    @property
    def log(self):
        return self.agent.log

    async def handle(self, user_input: str) -> bool:
        """
        Processes a user input string.
        Returns True if the input was a command and was handled.
        Returns False if the input should be treated as a regular chat message.
        """
        # Quick check to avoid processing non-commands
        if not user_input.startswith("/"):
            return False

        command = user_input.split(" ")[0].lower()

        handler = self.handlers.get(command)
        if handler:
            self.log.info(f"Command triggered: {user_input}")
            await handler(user_input)
            return True
        
        return False

    async def _handle_find(self, user_input):
        try:
            with tempfile.NamedTemporaryFile(mode='w+', delete=False) as tmp_file:
                temp_filename = tmp_file.name

            # Command to execute fzf and write output to the temp file
            fzf_command = f'fzf --multi --height=100% > "{temp_filename}"'

            with self.app.suspend():
                process = await asyncio.create_subprocess_shell(fzf_command)
                await process.communicate()

            selected_paths = []
            if os.path.exists(temp_filename) and os.path.getsize(temp_filename) > 0:
                with open(temp_filename, 'r') as f:
                    selected_paths = [line.strip() for line in f if line.strip()]
            
            # Clean up the temporary file
            os.remove(temp_filename)

            if selected_paths:
                total_added = 0
                for path in selected_paths:
                    count = self.agent.context_manager.add_path(path)
                    total_added += count
                await self.ui.print_system(f"✅ Added {total_added} file(s) from fzf to context.")
            else:
                await self.ui.print_system("No files selected from fzf.")

        except FileNotFoundError:
            await self.ui.print_error("fzf command not found. Please install fzf to use this feature.")
        except Exception as e:
            await self.ui.print_error(f"An error occurred with fzf: {e}")

    async def _handle_clear_session(self, user_input):
        if self.agent.session_manager.clear_session():
            await self.ui.print_system("✅ Saved session cleared. It will not be loaded on the next start.")
        else:
            await self.ui.print_system("No saved session found to clear.")

    async def _handle_add(self, user_input):
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

    async def _handle_drop(self, user_input):
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

    async def _handle_cd(self, user_input):
        try:
            parts = shlex.split(user_input)
            if len(parts) < 2:
                await self.ui.print_error("Usage: /cd <path>")
                return
            
            new_path = parts[1]
            os.chdir(os.path.expanduser(new_path))
            
            current_dir = os.getcwd()
            await self.ui.print_system(f"📁 Working directory changed to: [bold cyan]{current_dir}[/]")
            
        except Exception as e:
            await self.ui.print_error(f"Error changing directory: {e}")

    async def _handle_export(self, user_input):
        try:
            parts = shlex.split(user_input)
            filename = parts[1] if len(parts) > 1 else "chat_history.md"
            
            with open(filename, "w", encoding="utf-8") as f:
                for msg in self.agent.history.messages:
                    role = msg.get("role", "unknown")
                    content = msg.get("content", "")
                    f.write(f"## Role: {role}\n{content}\n\n")
            
            await self.ui.print_system(f"✅ Chat history exported to [bold cyan]{filename}[/]")
        except Exception as e:
            await self.ui.print_error(f"Error exporting history: {e}")

    async def _handle_import(self, user_input):
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
            
            import re
            chunks = re.split(r"## Role: (\w+)\n", content)
            
            new_messages = []
            if len(chunks) > 1:
                for i in range(1, len(chunks), 2):
                    role = chunks[i].strip()
                    msg_content = chunks[i+1].strip()
                    new_messages.append({"role": role, "content": msg_content})
            
            count = 0
            for msg in new_messages:
                self.agent.history.add_message(msg["role"], msg["content"])
                role = msg["role"]
                text = msg["content"]
                if role == "user":
                    await self.ui.print_message(text, role="user")
                elif role == "assistant":
                    await self.ui.print_message(text, role="assistant")
                elif role == "system":
                     if text.startswith("SYSTEM RESULT:"):
                         await self.ui.print_command_result(text.replace("SYSTEM RESULT:", "").strip())
                count += 1
            
            await self.ui.print_system(f"✅ Imported {count} messages from [bold cyan]{filename}[/]")

        except Exception as e:
            await self.ui.print_error(f"Error importing history: {e}")

    async def _handle_models(self, user_input):
        available_models = self.agent.settings.get("available_models", [])
        if not available_models:
            await self.ui.print_error("No available models configured in settings.")
            return

        current = self.agent.chat.model_name
        
        selection = await self.ui.pick_option(
            f"Select AI Model (Current: {current})", 
            available_models,
            current_value=current
        )
        
        if selection:
            await self.agent.switch_model(selection)
            try:
                update_settings({"default_model": selection})
                await self.ui.print_system(f"💾 Model preference saved: {selection}")
            except Exception as e:
                await self.ui.print_error(f"Model switched, but failed to save config: {e}")
        else:
            await self.ui.print_system("Model selection cancelled.")

    async def _handle_theme(self, user_input):
        # Accessing available_themes from the App instance
        themes = list(self.app.available_themes.keys())
        themes.sort()
        
        current = self.app.theme
        
        selection = await self.ui.pick_option(
            f"Select Interface Theme (Current: {current})", 
            themes,
            current_value=current
        )
        
        if selection:
            self.app.theme = selection
            try:
                update_settings({"theme": selection})
                await self.ui.print_system(f"🎨 Theme switched to: {selection} (Saved)")
            except Exception as e:
                await self.ui.print_error(f"Theme set, but failed to save config: {e}")
        else:
            await self.ui.print_system("Theme selection cancelled.")

    async def _handle_history_size(self, user_input):
        options = ["small", "medium", "large"]
        current = self.agent.history_size
        
        selection = await self.ui.pick_option(
            "Choose history limit (Esc to cancel):", 
            options,
            current_value=current
        )
        
        if selection:
            self.agent.set_history_size(selection)
            try:
                update_settings({"history_size": selection})
                await self.ui.print_system(f"💾 History size preference saved: {selection}")
            except Exception as e:
                await self.ui.print_error(f"History size set, but failed to save config: {e}")
        else:
                await self.ui.print_system("Selection cancelled.")

    async def _handle_compact(self, user_input):
        await self.agent.history.summarize(self.ui)


    async def _handle_quit(self, user_input):
        await self.app.action_quit()

    async def _handle_help(self, user_input):
        help_text = (
            "Available Commands:\n"
            "  /add <path>       - Add files/dirs to context\n"
            "  /drop <path>      - Remove files/dirs (or all if empty)\n"
            "  /cd <path>        - Change working directory\n"
            "  /export [file]    - Export chat history to markdown\n"
            "  /import <file>    - Import chat history from markdown\n"
            "  /models           - Switch AI model\n"
            "  /theme            - Switch UI theme\n"
            "  /history-size     - Change context window size\n"
            "  /compact - Manually summarize history (compact)\n"
            "  /clearsession     - Clear the saved session data\n"
            "  /f, /find         - Fuzzy find files to add to context\n"
            "  /quit             - Exit application"
        )
        await self.ui.print_system(help_text)
