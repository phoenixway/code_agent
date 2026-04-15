from textual.widgets import Static
from rich.text import Text


class TokenStatusBar(Static):
    def __init__(self, **kwargs):
        super().__init__("History: 0/0 | Session: 0", **kwargs)
        self.history_tokens = 0
        self.max_tokens = 0
        self.session_tokens = 0

    def update_tokens(self, history_tokens: int, max_tokens: int, session_tokens: int):
        self.history_tokens = history_tokens
        self.max_tokens = max_tokens
        self.session_tokens = session_tokens

        # ASCII progress bar (20 chars wide)
        BAR_WIDTH = 20
        if max_tokens > 0:
            filled = min(int((history_tokens / max_tokens) * BAR_WIDTH), BAR_WIDTH)
        else:
            filled = 0
        empty = BAR_WIDTH - filled

        # Colour the bar based on usage level
        ratio = history_tokens / max_tokens if max_tokens > 0 else 0
        if ratio >= 0.85:
            bar_style = "bold red"
        elif ratio >= 0.65:
            bar_style = "yellow"
        else:
            bar_style = "green"

        bar_filled = "█" * filled
        bar_empty = "░" * empty

        result = Text()
        result.append(bar_filled, style=bar_style)
        result.append(bar_empty, style="dim")
        result.append(f"  {history_tokens:,}/{max_tokens:,}", style="dim")
        result.append("  │  ", style="dim")
        result.append(f"session: {session_tokens:,}", style="dim")

        self.update(result)