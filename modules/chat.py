import os
import requests
import json
from modules.defaults import DEFAULT_SYSTEM_PROMPT

class BaseChat:
    """Базовий клас для всіх провайдерів."""
    def __init__(self, model_name):
        self.model_name = model_name

    def _prepare_messages(self, prompt, history):
        """Уніфікована підготовка історії повідомлень."""
        messages = [{"role": "system", "content": DEFAULT_SYSTEM_PROMPT}]
        # Додаємо історію (крім останнього системного повідомлення, якщо воно є)
        messages.extend(history)
        # Додаємо поточний запит
        messages.append({"role": "user", "content": prompt})
        return messages

class OpenAICompatibleChat(BaseChat):
    """Для OpenAI, DeepSeek та інших OpenAI-сумісних сервісів."""
    def __init__(self, model_name, base_url, api_key_env):
        super().__init__(model_name)
        self.base_url = base_url
        self.api_key = os.getenv(api_key_env)

    def get_streaming_response(self, prompt, history):
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
            response = requests.post(f"{self.base_url}/chat/completions", headers=headers, json=payload, stream=True)
            for line in response.iter_lines():
                if line:
                    line_text = line.decode('utf-8').replace('data: ', '')
                    if line_text == '[DONE]': break
                    try:
                        data = json.loads(line_text)
                        content = data['choices'][0]['delta'].get('content', '')
                        if content: yield content
                    except: continue
        except Exception as e:
            yield f"Error: {str(e)}"

class OllamaChat(BaseChat):
    """Для локального запуску через Ollama (Termux)."""
    def __init__(self, model_name):
        super().__init__(model_name)
        # Використовуємо /api/chat для Ollama
        self.url = os.getenv("OLLAMA_BASE_URL", "http://localhost:11434/api/chat")

    def get_streaming_response(self, prompt, history):
        payload = {
            "model": self.model_name,
            "messages": self._prepare_messages(prompt, history),
            "stream": True
        }

        try:
            response = requests.post(self.url, json=payload, stream=True)
            for line in response.iter_lines():
                if line:
                    data = json.loads(line.decode('utf-8'))
                    if 'message' in data:
                        yield data['message'].get('content', '')
                    if data.get('done'): break
        except Exception as e:
            yield f"Ollama Connection Error: {str(e)}"

class GeminiRestChat(BaseChat):
    """Полегшена версія Gemini з підтримкою стрімінгу через REST."""
    def __init__(self, model_name):
        super().__init__(model_name)
        self.api_key = os.getenv("GEMINI_API_KEY")
        # Використовуємо streamGenerateContent замість generateContent
        self.url = f"https://generativelanguage.googleapis.com/v1beta/models/{model_name}:streamGenerateContent?key={self.api_key}"

    def get_streaming_response(self, prompt, history):
        contents = []
        for m in history:
            contents.append({
                "role": "user" if m["role"] == "user" else "model",
                "parts": [{"text": m["content"]}]
            })
        contents.append({"role": "user", "parts": [{"text": prompt}]})

        payload = {
            "contents": contents,
            "system_instruction": {"parts": [{"text": DEFAULT_SYSTEM_PROMPT}]}
        }
        
        try:
            response = requests.post(self.url, json=payload, stream=True)
            # Gemini повертає JSON масив частин
            for line in response.iter_lines():
                if line:
                    line_text = line.decode('utf-8').strip()
                    # Прибираємо коми та дужки масиву, які додає REST API Gemini в стрімі
                    if line_text.startswith(','): line_text = line_text[1:]
                    if line_text.startswith('[') or line_text.startswith(']'): continue
                    
                    try:
                        data = json.loads(line_text)
                        yield data['candidates'][0]['content']['parts'][0]['text']
                    except: continue
        except Exception as e:
            yield f"Gemini Stream Error: {str(e)}"

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