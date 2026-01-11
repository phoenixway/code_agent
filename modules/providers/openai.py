import os
import json
import httpx
from .base import BaseChatProvider, ProviderAPIError

class OpenAICompatibleProvider(BaseChatProvider):
    """Provider for OpenAI, DeepSeek, and other compatible APIs."""
    
    def __init__(self, model_name, base_url, api_key_env):
        super().__init__(model_name)
        self.base_url = base_url
        self.api_key = os.getenv(api_key_env)
        if not self.api_key:
            # We don't raise error immediately to allow instantiation, 
            # but methods will fail if called. Or we can raise. 
            # Original code raised ValueError.
            raise ValueError(f"Missing API key for {model_name}. Please set the {api_key_env} environment variable.")

    async def get_streaming_response(self, prompt, history):
        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json"
        }
        payload = {
            "model": self.model_name,
            "messages": self._prepare_messages(prompt, history),
            "temperature": 0.2,
            "stream": True
        }

        try:
            async with httpx.AsyncClient(timeout=300) as client:
                async with client.stream("POST", f"{self.base_url}/chat/completions", headers=headers, json=payload) as response:
                    # Check for HTTP errors first
                    if response.status_code != 200:
                        error_text = await response.aread()
                        raise ProviderAPIError(f"API Error {response.status_code}: {error_text.decode('utf-8')}")

                    async for line in response.aiter_lines():
                        if line.startswith('data: '):
                            line_text = line[6:]
                            if line_text == '[DONE]':
                                break
                            try:
                                data = json.loads(line_text)
                                choices = data.get('choices', [])
                                if choices:
                                    content = choices[0]['delta'].get('content', '')
                                    if content:
                                        yield content
                            except json.JSONDecodeError:
                                continue
        except httpx.RequestError as e:
             raise ProviderAPIError(f"Network error: {str(e)}")
        except Exception as e:
            raise ProviderAPIError(f"OpenAI/DeepSeek Error: {str(e)}")
