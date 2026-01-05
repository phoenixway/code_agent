from abc import ABC, abstractmethod

class BaseTool(ABC):
    @property
    @abstractmethod
    def name(self) -> str:
        """Назва, за якою ШІ буде викликати інструмент."""
        pass

    @property
    @abstractmethod
    def description(self) -> str:
        """Опис інструмента для системного промпту."""
        pass

    @abstractmethod
    async def execute(self, **kwargs) -> dict:
        """Логіка виконання. Має повертати словник з ключами 'status' та 'output'."""
        pass
