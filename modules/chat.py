import os
import requests
import json
from modules.defaults import DEFAULT_SYSTEM_PROMPT

class BaseChat:
    """Базовий клас для всіх провайдерів."""
    def __init__(self, model_name):
        self.model_name = model_name

class OpenAICompatibleChat(BaseChat):
    """Для OpenAI, DeepSeek та інших OpenAI-сумісних сервісів."""
    def __init__(self, model_name, base_url, api_key_env):
        super().__init__(model_name)
        self.base_url = base_url
        self.api_key = os.getenv(api_key_env)

    def get_response_with_history(self, prompt, history):
        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json"
        }
        
        messages = [{"role": "system", "content": DEFAULT_SYSTEM_PROMPT}]
        messages.extend(history[:-1])
        messages.append({"role": "user", "content": prompt})

        payload = {
            "model": self.model_name,
            "messages": messages,
            "temperature": 0.2
        }

        try:
            response = requests.post(f"{self.base_url}/chat/completions", headers=headers, json=payload)
            if response.status_code == 200:
                return response.json()['choices'][0]['message']['content']
            else:
                return f"Error {response.status_code}: {response.text}"
        except Exception as e:
            return f"Request Exception: {str(e)}"

class OllamaChat(BaseChat):
    """Для локального запуску через Ollama (Termux)."""
    def __init__(self, model_name):
        super().__init__(model_name)
        self.base_url = os.getenv("OLLAMA_BASE_URL", "http://localhost:11434/api/chat")

    def get_response_with_history(self, prompt, history):
        messages = [{"role": "system", "content": DEFAULT_SYSTEM_PROMPT}]
        messages.extend(history[:-1])
        messages.append({"role": "user", "content": prompt})

        payload = {
            "model": self.model_name,
            "messages": messages,
            "stream": False
        }

        try:
            response = requests.post(self.base_url, json=payload)
            if response.status_code == 200:
                return response.json()['message']['content']
            return f"Ollama Error: {response.text}"
        except Exception as e:
            return f"Ollama Connection Error: {str(e)}"

class GeminiRestChat(BaseChat):
    """Полегшена версія Gemini без gRPC."""
    def __init__(self, model_name):
        super().__init__(model_name)
        self.api_key = os.getenv("GEMINI_API_KEY")
        self.url = f"https://generativelanguage.googleapis.com/v1beta/models/{model_name}:generateContent?key={self.api_key}"

    def get_response_with_history(self, prompt, history):
        contents = []
        for m in history[:-1]:
            contents.append({
                "role": "user" if m["role"] == "user" else "model",
                "parts": [{"text": m["content"]}]
            })
        # Важливо: prompt додається ПІСЛЯ циклу в окремий об'єкт
        contents.append({"role": "user", "parts": [{"text": prompt}]})

        payload = {
            "contents": contents,
            "system_instruction": {"parts": [{"text": DEFAULT_SYSTEM_PROMPT}]}
        }
        
        try:
            response = requests.post(self.url, json=payload)
            if response.status_code == 200:
                res_data = response.json()
                return res_data['candidates'][0]['content']['parts'][0]['text']
            return f"Gemini Error: {response.text}"
        except Exception as e:
            return f"Gemini Request Error: {str(e)}"

# Ця функція має бути на рівні модуля (без відступів зліва)
def get_chat_provider(model_name):
    """Фабрика провайдерів."""
    m = model_name.lower()
    
    if "gemini" in m:
        return GeminiRestChat(model_name)
    elif "deepseek" in m:
        return OpenAICompatibleChat(model_name, "https://api.deepseek.com", "DEEPSEEK_API_KEY")
    elif "gpt" in m:
        return OpenAICompatibleChat(model_name, "https://api.openai.com/v1", "OPENAI_API_KEY")
    elif "ollama" in m or "qwen" in m:
        clean_name = model_name.split('/')[-1] if '/' in model_name else model_name
        return OllamaChat(clean_name)
    
    return GeminiRestChat("gemini-1.5-pro")