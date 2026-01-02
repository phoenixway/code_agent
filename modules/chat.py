class ChatModule:
    def __init__(self):
        self.model_name = "Mock-Model-v1"

    def get_response(self, user_input):
        # Тут пізніше буде call до Gemini/Ollama
        # Поки повертаємо імітацію коду для тестування files.py
        if "edit" in user_input.lower():
            return "Ось змінений код:\n```python\nprint('Hello from AI edited file')\n```"
        return f"AI відповідає на: {user_input}\nЯ можу допомогти тобі з кодом."

# Тестовий виклик
if __name__ == "__main__":
    chat = ChatModule()
    print(chat.get_response("Привіт!"))