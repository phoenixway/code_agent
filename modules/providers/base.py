from abc import ABC, abstractmethod
from modules.defaults import DEFAULT_SYSTEM_PROMPT

class ProviderAPIError(Exception):
    """Custom exception for API errors from chat providers."""
    pass

class BaseChatProvider(ABC):
    """Abstract base class for all chat providers."""
    
    def __init__(self, model_name: str):
        self.model_name = model_name

    def _prepare_messages(self, prompt: str, history: list) -> list:
        """Common logic to prepare messages list from history."""
        messages = [{"role": "system", "content": DEFAULT_SYSTEM_PROMPT}]
        
        # Add only non-empty messages
        for msg in history:
            content = msg.get("content", "").strip()
            if content:
                messages.append({"role": msg["role"], "content": content})
                
        # Add current prompt if valid
        if prompt and prompt.strip():
            messages.append({"role": "user", "content": prompt.strip()})
            
        return messages

    @abstractmethod
    async def get_streaming_response(self, prompt: str, history: list):
        """Generator that yields chunks of the response."""
        pass
