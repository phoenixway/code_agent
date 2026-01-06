from textual.containers import Container, Horizontal
from textual.widgets import LoadingIndicator, Static

class StatusBar(Container):
    """
    Компонент, що відображає статус роботи агента (спіннер + текст).
    """

    def compose(self):
        yield Horizontal(
            LoadingIndicator(),
            Static("Thinking...", id="loading-label"),
            classes="loading-spinner-container"
        )

    def start_thinking(self):
        """Вмикає режим 'Thinking...'"""
        self.query_one("#loading-label", Static).update("Thinking...")
        self.display = True

    def start_action(self, text: str):
        """Вмикає режим відображення конкретної дії."""
        label_text = text if text else "Processing..."
        self.query_one("#loading-label", Static).update(label_text)
        self.display = True

    def stop(self):
        """Приховує статус бар."""
        self.display = False
