from textual.theme import Theme

# Define the "Hacker Green" theme mapping
HACKER_THEME = Theme(
    name="hacker-green",
    primary="#009944",          # Darker Green (less bright)
    secondary="#006600",        # Even darker Green
    accent="#009944",           # Using primary as accent
    foreground="#c0d0c0",       # Muted pale green
    background="#050505",       # Almost Pure Black ($bg-main)
    surface="#050505",          # Same as background for uniform look
    error="#cc3333",            # Muted red
    warning="#999900",          # Muted yellow/gold
    success="#009944",          # Same as primary
)
