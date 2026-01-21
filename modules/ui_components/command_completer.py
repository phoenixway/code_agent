from textual.suggester import Suggester

class CommandCompleter(Suggester):
    """A suggester for slash commands."""

    def __init__(self, commands: list[str]):
        super().__init__(use_cache=False)
        self.commands = commands

    async def get_suggestion(self, value: str) -> str | None:
        """Gets a single autocomplete suggestion for the user."""
        if not value.startswith("/") or " " in value:
            return None

        # Find the first command that starts with the current input value
        for command in self.commands:
            if command.startswith(value):
                return command  # Return the first match

        return None
