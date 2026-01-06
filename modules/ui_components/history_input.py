from textual.widgets import Input
from textual.binding import Binding

class HistoryInput(Input):
    """
    Розширене поле вводу з підтримкою історії команд.
    Використовуйте Ctrl+Up / Ctrl+Down для навігації.
    """
    
    BINDINGS = [
        Binding("ctrl+up", "history_up", "Previous Command", show=False),
        Binding("ctrl+down", "history_down", "Next Command", show=False),
    ]

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._history: list[str] = []
        self._history_index: int = -1
        self._draft: str = ""

    def add_entry(self, text: str) -> None:
        """Додає текст до історії, якщо він не пустий і не дублює останній запис."""
        text = text.strip()
        if not text:
            return
            
        # Не додаємо, якщо це те саме, що й остання команда
        if not self._history or self._history[-1] != text:
            self._history.append(text)
        
        # Скидаємо вказівник
        self._reset_pointer()

    def _reset_pointer(self):
        self._history_index = -1
        self._draft = ""

    def action_history_up(self) -> None:
        """Перехід до попередньої команди в історії."""
        if not self._history:
            return

        # Якщо ми починаємо навігацію (були внизу), зберігаємо поточний ввід як чернетку
        if self._history_index == -1:
            self._draft = self.value
            self._history_index = len(self._history) - 1
        elif self._history_index > 0:
            self._history_index -= 1
        
        # Оновлюємо значення та переміщуємо курсор в кінець
        self.value = self._history[self._history_index]
        self.action_end()

    def action_history_down(self) -> None:
        """Перехід до наступної команди в історії."""
        if self._history_index == -1:
            return # Ми вже в самому низу (на чернетці)

        if self._history_index < len(self._history) - 1:
            self._history_index += 1
            self.value = self._history[self._history_index]
        else:
            # Повертаємось до чернетки
            self._history_index = -1
            self.value = self._draft
        
        self.action_end()

    async def on_key(self, event) -> None:
        if event.key == "enter":
            event.stop()
            self.post_message(self.Submitted(self, self.value))
