from rich.console import Console
from rich.markdown import Markdown

class UI:
    def __init__(self):
        # soft_wrap=False допомагає Markdown не ламатися на вузьких екранах
        self.console = Console(soft_wrap=False)
        self.bg_style = "on grey15"

    def _print_ai_block(self, text):
        """Малює блок ШІ із суцільною заливкою фону."""
        bg_full_style = f"white {self.bg_style}"
        
        # 1. Верхній padding (смуга фону)
        # Примітка: пустий рядок ПЕРЕД цим блоком тепер контролюється в agent.py
        self.console.print(" " * self.console.width, style=self.bg_style)
        
        # 2. Контент ШІ (Markdown)
        md = Markdown(text)
        self.console.print(md, style=bg_full_style, justify="left", width=self.console.width)
            
        # 3. Нижній padding (смуга фону)
        self.console.print(" " * self.console.width, style=self.bg_style)
        
        # Порожній рядок-розділювач ПІСЛЯ блоку (щоб You > не прилипав)
        self.console.print()

    def print_message(self, text, role="assistant"):
        """Виводить повідомлення користувача або ШІ."""
        if role == "user":
            self.console.print(f"[bold blue]▌ [/bold blue]{text}")
        else:
            self._print_ai_block(text)

    def print_system(self, text):
        """Виводить системні повідомлення (завантаження, статус)."""
        self.console.print(f"[italic cyan]ℹ {text}[/italic cyan]")

    def print_error(self, text):
        """Виводить повідомлення про помилки."""
        self.console.print(f"[bold red]✘ Error:[/bold red] {text}")