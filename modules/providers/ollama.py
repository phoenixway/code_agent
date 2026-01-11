import os
import json
import httpx
from .base import BaseChatProvider, ProviderAPIError

class OllamaProvider(BaseChatProvider):
    """Provider for local Ollama instances."""
    
    def __init__(self, model_name):
        super().__init__(model_name)
        self.url = os.getenv("OLLAMA_BASE_URL", "http://localhost:11434/api/chat")

    async def get_streaming_response(self, prompt, history):
        payload = {
            "model": self.model_name,
            "messages": self._prepare_messages(prompt, history),
            "stream": True
        }

        try:
            async with httpx.AsyncClient(timeout=300) as client:
                async with client.stream("POST", self.url, json=payload) as response:
                    if response.status_code != 200:
                         raise ProviderAPIError(f"Ollama Error {response.status_code}")

                    async for line in response.aiter_lines():
                        if line:
                            try:
                                data = json.loads(line)
                                if 'message' in data:
                                    yield data['message'].get('content', '')
                                if data.get('done'):
                                    break
                            except json.JSONDecodeError:
                                continue
        except Exception as e:
            raise ProviderAPIError(f"Ollama Connection Error: {str(e)}")
