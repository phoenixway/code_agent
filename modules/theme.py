from textual.theme import Theme

# Define the "Hacker Green" theme mapping
HACKER_THEME = Theme(
    name="hacker-green",
    primary="#00ff41",          # Matrix Green ($accent)
    secondary="#008f11",        # Darker Green ($accent-secondary)
    accent="#00ff41",           # Using primary as accent
    foreground="#e0ffe0",       # Pale Greenish White ($text-main)
    background="#050505",       # Almost Pure Black ($bg-main)
    surface="#0d110d",          # Card Background ($bg-card)
    error="#ff4444",            # Soft Red ($error)
    warning="#dfff00",          # Chartreuse ($warning)
    success="#00ff41",          # Matrix Green ($success)
)
