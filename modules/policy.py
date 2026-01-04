from rich.prompt import Confirm
from modules.tui_ui import TuiUI # Import TuiUI

class PermissionPolicy:
    def __init__(self, ui, mode="ask"):
        self.ui = ui
        self.mode = mode

    async def check(self, action): # Make it async
        """Checks if the action is allowed based on the current policy."""
        if self.mode == "always":
            return True
        if self.mode == "never":
            return False
        
        # Default to "ask"
        action_type = action.get("type")
        details = ""
        if action_type == "run_command":
            details = action.get("command")
        elif action_type in ["write_file", "create_file", "edit_file"]:
            details = action.get("path") or action.get("file_path")
        
        if isinstance(self.ui, TuiUI):
            # Use async confirmation for TUI
            return await self.ui.confirm_action(action)
        else:
            # Fallback to synchronous confirmation for old CLI
            return Confirm.ask(
                f"[bold yellow]⚠️  ALLOW this action? ⚠️[/bold yellow]\n"
                f"   - Type: [bold cyan]{action_type}[/bold cyan]\n"
                f"   - Details: [bold red]{details}[/bold red]\n"
            )