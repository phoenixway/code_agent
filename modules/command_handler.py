import os
import shlex
import asyncio
import tempfile
from datetime import datetime
from pathlib import Path
import re
from modules.config_loader import update_settings
from modules.logger import get_log_files

class CommandHandler:
    def __init__(self, app):
        """
        Initializes the CommandHandler.
        :param app: The main TUI App instance (provides access to agent, ui, theme, etc.)
        """
        self.app = app
        self.session_started_at = datetime.now()
        self.handlers = {
            "/add": self._handle_add,
            "/drop": self._handle_drop,
            "/cd": self._handle_cd,
            "/export": self._handle_export,
            "/dump": self._handle_dump,
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
        file_cleared = self.agent.session_manager.clear_session()

        # Also clear runtime state to avoid immediate post-clear summarization
        # due to stale in-memory history/context.
        if hasattr(self.agent, "history") and hasattr(self.agent.history, "clear_history"):
            self.agent.history.clear_history()
        if hasattr(self.agent, "context_manager") and hasattr(self.agent.context_manager, "clear"):
            self.agent.context_manager.clear()
        if hasattr(self.agent, "state"):
            self.agent.state.session_tokens = 0
            if hasattr(self.agent.state, "confirmation_count"):
                self.agent.state.confirmation_count = 0
            if hasattr(self.agent.state, "suppress_step_limit_warning"):
                self.agent.state.suppress_step_limit_warning = False
            if hasattr(self.agent.state, "consecutive_same_action_count"):
                self.agent.state.consecutive_same_action_count = 0
            if hasattr(self.agent.state, "last_completed_fingerprint"):
                self.agent.state.last_completed_fingerprint = None
            if hasattr(self.agent.state, "last_error_fingerprint"):
                self.agent.state.last_error_fingerprint = None
            if hasattr(self.agent.state, "consecutive_same_error_count"):
                self.agent.state.consecutive_same_error_count = 0
            if hasattr(self.agent.state, "pending_loop_stop_info"):
                self.agent.state.pending_loop_stop_info = None
            if hasattr(self.agent.state, "malformed_recovery_grace_remaining"):
                self.agent.state.malformed_recovery_grace_remaining = 0
            if hasattr(self.agent.state, "set_retry_budgets") and hasattr(self.agent, "config"):
                self.agent.state.set_retry_budgets(
                    getattr(self.agent.config, "RECOVERABLE_ERROR_RETRY_BUDGET", 2),
                    getattr(self.agent.config, "CRITICAL_ERROR_RETRY_BUDGET", 1),
                )

        # Reset dump session window after hard reset.
        self.session_started_at = datetime.now()

        # Refresh token indicator immediately after reset.
        if hasattr(self.ui, "update_token_status"):
            await self.ui.update_token_status(
                history_tokens=self.agent.history.current_token_count,
                max_tokens=self.agent.history.max_tokens,
                session_tokens=getattr(self.agent.state, "session_tokens", 0),
            )

        if file_cleared:
            await self.ui.print_system(
                "✅ Saved session removed and runtime context reset."
            )
        else:
            await self.ui.print_system(
                "✅ Runtime context reset. No saved session file was found."
            )

    async def _handle_add(self, user_input):
        try:
            parts = shlex.split(user_input)
            paths = parts[1:]
            if not paths:
                await self.ui.print_error("Usage: /add <path1> [path2 ...]")
                return

            total_added = 0
            for path_str in paths:
                try:
                    count = self.agent.context_manager.add_path(path_str)
                    if count == 0:
                        await self.ui.print_error(f"Path not found or empty: {path_str}")
                    total_added += count
                except Exception as e:
                    await self.ui.print_error(f"Error adding path {path_str}: {e}")
            
            if total_added > 0:
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
                if hasattr(self.agent.history, "clear_file_state"):
                    self.agent.history.clear_file_state()
                await self.ui.print_system("🗑️ Context cleared (all files removed).")
            else:
                total_removed = 0
                for path in paths:
                    count = self.agent.context_manager.remove_path(path)
                    if not isinstance(count, int):
                        count = 0
                    if hasattr(self.agent.history, "remove_file_state"):
                        history_count = self.agent.history.remove_file_state(path)
                        if isinstance(history_count, int):
                            count += history_count
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

    def _rotate_dump_files(self, dump_dir: Path, keep_last: int = 10) -> None:
        """Keep only the most recent dump files."""
        dump_files = sorted(
            dump_dir.glob("agent_dump_*.txt"),
            key=lambda p: p.stat().st_mtime,
            reverse=True,
        )
        for old_file in dump_files[keep_last:]:
            try:
                old_file.unlink()
            except Exception:
                # Rotation should never break the command.
                pass

    @staticmethod
    def _parse_log_timestamp(line: str) -> datetime | None:
        """Extract timestamp from log line prefix: YYYY-MM-DD HH:MM:SS,mmm - ..."""
        match = re.match(r"^(\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}),\d{3}\s+-\s+", line)
        if not match:
            return None
        try:
            return datetime.strptime(match.group(1), "%Y-%m-%d %H:%M:%S")
        except Exception:
            return None

    def _filter_log_for_session(self, path: Path, content: str) -> str:
        """Keep only current-session records using timestamped log entries."""
        lines = content.splitlines()
        if not lines:
            return ""

        kept: list[str] = []
        current_record_allowed = False
        saw_timestamped_line = False

        for line in lines:
            ts = self._parse_log_timestamp(line)
            if ts is not None:
                saw_timestamped_line = True
                current_record_allowed = ts >= self.session_started_at
                if current_record_allowed:
                    kept.append(line)
            else:
                # Continuation line of previous record (multiline log message)
                if not saw_timestamped_line:
                    # File without timestamps -> fallback to keeping content.
                    kept.append(line)
                elif current_record_allowed:
                    kept.append(line)

        return "\n".join(kept).strip()

    async def _handle_dump(self, user_input):
        """
        Save a full diagnostics dump from runtime logs.
        Usage: /dump [--full] [filename]
        """
        try:
            parts = shlex.split(user_input)
            full_dump = "--full" in parts
            user_paths = [p for p in parts[1:] if p != "--full"]
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            dump_dir = Path("dumps")
            dump_dir.mkdir(parents=True, exist_ok=True)

            if user_paths:
                dump_path = Path(user_paths[0])
            else:
                dump_path = dump_dir / f"agent_dump_{timestamp}.txt"

            dump_path.parent.mkdir(parents=True, exist_ok=True)

            log_files = get_log_files(include_rotated=True)
            with open(dump_path, "w", encoding="utf-8") as out:
                out.write(f"Angelica dump generated: {datetime.now().isoformat()}\n")
                out.write(f"CWD: {os.getcwd()}\n")
                out.write(f"Dump mode: {'full' if full_dump else 'session-only'}\n")
                out.write(f"Session started at: {self.session_started_at.isoformat()}\n")
                out.write(f"Log files found: {len(log_files)}\n\n")

                if not log_files:
                    out.write("No log files were found.\n")
                else:
                    included_files = 0
                    skipped_empty = []
                    for path in log_files:
                        raw_text = ""
                        try:
                            raw_text = path.read_text(encoding="utf-8")
                        except Exception as read_error:
                            out.write("=" * 80 + "\n")
                            out.write(f"FILE: {path}\n")
                            out.write("=" * 80 + "\n")
                            out.write(f"[ERROR READING FILE: {read_error}]\n\n")
                            continue

                        text = raw_text if full_dump else self._filter_log_for_session(path, raw_text)
                        if not text.strip():
                            skipped_empty.append(str(path))
                            continue

                        out.write("=" * 80 + "\n")
                        out.write(f"FILE: {path}\n")
                        out.write("=" * 80 + "\n")
                        out.write(text)
                        out.write("\n\n")
                        included_files += 1

                    if skipped_empty:
                        out.write("Skipped empty log files:\n")
                        for skipped in skipped_empty:
                            out.write(f"- {skipped}\n")
                        out.write("\n")
                    out.write(f"Included log files: {included_files}\n")

            self._rotate_dump_files(dump_dir)
            await self.ui.print_system(f"✅ Log dump saved to [bold cyan]{dump_path}[/]")
        except Exception as e:
            await self.ui.print_error(f"Error saving dump: {e}")

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
        available_models = self.agent.config.settings.get("available_models", [])
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
            "  /dump [--full] [file] - Save logs dump (default: current session only)\n"
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
