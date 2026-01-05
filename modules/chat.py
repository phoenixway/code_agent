import os
import httpx
import json
from modules.defaults import DEFAULT_SYSTEM_PROMPT

class ProviderAPIError(Exception):
    """Custom exception for API errors from chat providers."""
    pass

class BaseChat:
    """Базовий клас для всіх провайдерів."""
    def __init__(self, model_name):
        self.model_name = model_name

    def _prepare_messages(self, prompt, history):
        """Уніфікована підготовка історії повідомлень."""
        messages = [{"role": "system", "content": DEFAULT_SYSTEM_PROMPT}]
        messages.extend(history)
        if prompt: # Don't add an empty user prompt
            messages.append({"role": "user", "content": prompt})
        return messages

class OpenAICompatibleChat(BaseChat):
    """Для OpenAI, DeepSeek та інших OpenAI-сумісних сервісів."""
    def __init__(self, model_name, base_url, api_key_env):
        super().__init__(model_name)
        self.base_url = base_url
        self.api_key = os.getenv(api_key_env)
        if not self.api_key:
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
                    async for line in response.aiter_lines():
                        if line.startswith('data: '):
                            line_text = line[6:]
                            if line_text == '[DONE]':
                                break
                            try:
                                data = json.loads(line_text)
                                content = data['choices'][0]['delta'].get('content', '')
                                if content:
                                    yield content
                            except json.JSONDecodeError:
                                continue
        except Exception as e:
            raise ProviderAPIError(f"OpenAICompatibleChat Error: {str(e)}")

class OllamaChat(BaseChat):
    """Для локального запуску через Ollama."""
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
                    async for line in response.aiter_lines():
                        if line:
                            data = json.loads(line)
                            if 'message' in data:
                                yield data['message'].get('content', '')
                            if data.get('done'):
                                break
        except Exception as e:
            raise ProviderAPIError(f"Ollama Connection Error: {str(e)}")

class GeminiRestChat(BaseChat):
    """Полегшена версія Gemini з підтримкою стрімінгу через REST."""
    def __init__(self, model_name):
        super().__init__(model_name)
        self.api_key = os.getenv("GEMINI_API_KEY")
        if not self.api_key:
            raise ValueError(f"Missing API key for Gemini. Please set the GEMINI_API_KEY environment variable.")
        self.url = f"https://generativelanguage.googleapis.com/v1beta/models/{model_name}:streamGenerateContent?key={self.api_key}"

    async def get_streaming_response(self, prompt, history):
        contents = []
        for m in history:
            # Gemini expects "model" for assistant role
            role = "user" if m["role"] == "user" else "model"
            contents.append({"role": role, "parts": [{"text": m["content"]}]})
        if prompt:
            contents.append({"role": "user", "parts": [{"text": prompt}]})

        payload = {
            "contents": contents,
            "system_instruction": {"parts": [{"text": DEFAULT_SYSTEM_PROMPT}]}
        }
        
        try:
            async with httpx.AsyncClient(timeout=300) as client:
                async with client.stream("POST", self.url, json=payload) as response:
                    async for line in response.aiter_lines():
                        if line.startswith('data: '):
                            line_text = line[6:]
                            try:
                                data = json.loads(line_text)
                                yield data['candidates'][0]['content']['parts'][0]['text']
                            except (json.JSONDecodeError, KeyError, IndexError):
                                continue
        except Exception as e:
            raise ProviderAPIError(f"Gemini Stream Error: {str(e)}")

# A dictionary to map model name keywords to provider classes and their arguments
PROVIDERS = {
    "gemini": (GeminiRestChat, []),
    "deepseek": (OpenAICompatibleChat, ["https://api.deepseek.com", "DEEPSEEK_API_KEY"]),
    "gpt": (OpenAICompatibleChat, ["https://api.openai.com/v1", "OPENAI_API_KEY"]),
    "ollama": (OllamaChat, []),
    "qwen": (OllamaChat, []),
}

def get_chat_provider(model_name):
    """Factory function to get the appropriate chat provider."""
    m_lower = model_name.lower()
    
    for keyword, (provider_class, args) in PROVIDERS.items():
        if keyword in m_lower:
            try:
                if keyword in ["ollama", "qwen"]:
                    clean_name = model_name.split('/')[-1] if '/' in model_name else model_name
                    return provider_class(clean_name)
                return provider_class(model_name, *args)
            except ValueError as e:
                print(f"Error initializing chat provider for {model_name}: {e}")
                return None
            
    # Default fallback provider
    try:
        return GeminiRestChat("gemini-1.5-pro")
    except ValueError as e:
        print(f"Error initializing default Gemini chat provider: {e}")
        return None