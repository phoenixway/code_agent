# modules/chat.py
import ollama
from openai import OpenAI
import google.generativeai as genai
import os
from modules.config_loader import load_system_prompt

class BaseChat:
    def __init__(self):
        # Завантажуємо промпт з файлу користувача
        self.system_prompt = load_system_prompt()
        self.examples = [] # Можна теж винести в окремий файл за бажанням

    def _prepare_messages(self, user_input):
        return [
            {"role": "system", "content": self.system_prompt},
            {"role": "user", "content": user_input}
        ]

class OllamaProvider(BaseChat):
    def __init__(self, model_id):
        super().__init__()
        self.model_id = model_id

    def get_response(self, user_input):
        try:
            response = ollama.chat(
                model=self.model_id,
                messages=self._prepare_messages(user_input),
                options={'temperature': 0.1}
            )
            return response['message']['content']
        except Exception as e:
            return f"❌ Ollama Error: {str(e)}"

class OpenAICompatibleProvider(BaseChat):
    def __init__(self, model_id, api_key, base_url=None):
        super().__init__()
        self.client = OpenAI(api_key=api_key, base_url=base_url)
        self.model_id = model_id

    def get_response(self, user_input):
        try:
            resp = self.client.chat.completions.create(
                model=self.model_id,
                messages=self._prepare_messages(user_input),
                temperature=0.1
            )
            return resp.choices[0].message.content
        except Exception as e:
            return f"❌ API Error: {str(e)}"

class GeminiProvider(BaseChat):
    def __init__(self, model_id):
        super().__init__()
        genai.configure(api_key=os.getenv("GEMINI_API_KEY"))
        self.model = genai.GenerativeModel(
            model_name=model_id,
            system_instruction=self.system_prompt # Gemini підтримує system_instruction окремо
        )

    def get_response(self, user_input):
        try:
            # Для Gemini додаємо приклади як історію чату або частину промпту
            response = self.model.generate_content(user_input)
            return response.text
        except Exception as e:
            return f"❌ Gemini Error: {str(e)}"

# Фабрика залишається без змін, але тепер вона ініціалізує класи з промптами
def get_chat_provider(model_string):
    if model_string.startswith("ollama/"):
        return OllamaProvider(model_string.replace("ollama/", ""))
    
    if "deepseek" in model_string:
        return OpenAICompatibleProvider(
            model_id="deepseek-chat",
            api_key=os.getenv("DEEPSEEK_API_KEY"),
            base_url="https://api.deepseek.com"
        )
    
    if "openai" in model_string:
        return OpenAICompatibleProvider(
            model_id=model_string.split('/')[-1],
            api_key=os.getenv("OPENAI_API_KEY")
        )

    if "gemini" in model_string:
        return GeminiProvider(model_string.split('/')[-1])
        
    raise ValueError(f"Unknown model format: {model_string}")