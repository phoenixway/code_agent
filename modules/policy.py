import inspect
import shlex
from rich.prompt import Confirm
from modules.config_loader import load_settings

class PermissionPolicy:
    def __init__(self, ui, mode="ask"):
        self.ui = ui
        self.mode = mode
        settings = load_settings()
        self.allow_side_effect_tools = settings.get("allow_side_effect_tools", True)
        self.auto_allow_read_only_actions = settings.get("auto_allow_read_only_actions", True)
        self.auto_allow_safe_shell_read_only = settings.get("auto_allow_safe_shell_read_only", True)
        self._read_only_actions = {
            "read_file",
            "read_chunk",
            "read_file_skeleton",
            "extract_kotlin_function",
            "extract_symbol",
            "list_directory",
            "search_files",
            "search_content",
            "find_files",
            "search_in_files",
            "git_diff",
        }
        self._side_effect_actions = {
            "run_shell",
            "create_file",
            "write_file",
            "write_file_block",
            "append_file_block",
            "edit_file",
            "replace",
            "delete_file",
            "git_add",
            "git_commit",
            "git_checkout",
        }

    async def check(self, action): # Make it async
        """Checks if the action is allowed based on the current policy."""
        action_type = action.get("type")
        force_truncated_readonly = {
            "search_content",
            "search_files",
            "list_directory",
            "read_file_skeleton",
            "extract_kotlin_function",
            "extract_symbol",
        }
        is_recovery_probe = bool(action.get("_recovery_context"))

        if self.mode == "ask" and is_recovery_probe and action_type in {
            "search_content",
            "search_files",
            "list_directory",
            "read_file",
            "read_chunk",
            "read_file_skeleton",
            "extract_kotlin_function",
            "extract_symbol",
        }:
            return "allow_truncated"

        if self.mode == "ask" and action_type in force_truncated_readonly:
            return "allow_truncated"

        if self.mode == "ask" and self.auto_allow_read_only_actions:
            if action_type in self._read_only_actions:
                return True
            if (
                action_type == "run_shell"
                and self.auto_allow_safe_shell_read_only
                and self._is_safe_read_only_shell(action.get("command", ""))
            ):
                return True

        if (not self.allow_side_effect_tools) and action_type in self._side_effect_actions:
            if hasattr(self.ui, "print_error") and inspect.iscoroutinefunction(self.ui.print_error):
                await self.ui.print_error("Action blocked by config: side-effect tools are disabled.")
            return False

        if self.mode == "always":
            return True
        if self.mode == "never":
            return False
        
        # Default to "ask"
        details = ""
        if action_type == "run_command":
            details = action.get("command")
        elif action_type in ["write_file", "write_file_block", "append_file_block", "create_file", "edit_file"]:
            details = action.get("path") or action.get("file_path")
        
        if hasattr(self.ui, 'confirm_action') and inspect.iscoroutinefunction(self.ui.confirm_action):
          return await self.ui.confirm_action(action)
        else:
            # Fallback to synchronous confirmation for old CLI
            return Confirm.ask(
                f"[bold yellow]⚠️  ALLOW this action? ⚠️[/bold yellow]\n"
                f"   - Type: [bold cyan]{action_type}[/bold cyan]\n"
                f"   - Details: [bold red]{details}[/bold red]\n"
            )

    def _is_safe_read_only_shell(self, command: str) -> bool:
        """Conservative read-only shell detector to reduce unnecessary prompts."""
        if not isinstance(command, str) or not command.strip():
            return False

        # Reject shell constructs that could chain or redirect writes.
        unsafe_tokens = ["|", "&&", "||", ";", ">", "<", "$(", "`"]
        if any(token in command for token in unsafe_tokens):
            return False

        try:
            parts = shlex.split(command)
        except Exception:
            return False
        if not parts:
            return False

        # Allowlist only clearly read-only commands.
        cmd = parts[0]
        read_only_cmds = {"ls", "pwd", "cat", "head", "tail", "grep", "rg", "find", "git"}
        if cmd not in read_only_cmds:
            return False

        # git is safe only for status/log/show/diff operations.
        if cmd == "git":
            if len(parts) < 2:
                return False
            safe_git_subcommands = {"status", "log", "show", "diff", "branch"}
            return parts[1] in safe_git_subcommands

        return True
