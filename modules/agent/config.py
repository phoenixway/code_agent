"""Конфігурація та налаштування агента."""

from modules.config_loader import load_settings


class AgentConfig:
    """Клас для зберігання незмінної конфігурації агента."""
    
    def __init__(self):
        self.settings = load_settings()
        
        # Константи поведінки
        self.MAX_CONSECUTIVE_CALLS = 1000000  # Вимкнено попередження про завелику кількість кроків
        
        # Операції, що змінюють стан (викликають зупинку циклу для підтвердження або роздумів)
        self.STATE_CHANGING_OPS = {
            "run_shell", "create_file", "replace", 
            "edit_file", "git_add", "git_commit", 
            "git_checkout", "delete_file"
        }
        
    @property
    def default_model(self) -> str:
        return self.settings.get("default_model", "ollama/qwen2.5-coder:7b")
    
    @property
    def max_history_tokens(self) -> int:
        return self.settings.get("max_history_tokens", 4000)
    
    @property
    def permission_policy(self) -> str:
        return self.settings.get("permission_policy", "ask")
    
    @property
    def history_size(self) -> str:
        return self.settings.get("history_size", "small")
