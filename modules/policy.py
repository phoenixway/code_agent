from rich.prompt import Confirm

class PermissionPolicy:
    def __init__(self, ui, mode="ask"):
        self.ui = ui
        self.mode = mode

    def check(self, action):
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
        
        # Using rich.prompt for a better user experience
        return Confirm.ask(
            f"[bold yellow]⚠️  ALLOW this action? ⚠️[/bold yellow]\n"
            f"   - Type: [bold cyan]{action_type}[/bold cyan]\n"
            f"   - Details: [bold red]{details}[/bold red]\n"
        )