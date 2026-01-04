import os
from google import genai

# Переконайтеся, що ключ встановлено
api_key = os.getenv("GOOGLE_API_KEY")
if not api_key:
    print("Помилка: GOOGLE_API_KEY не знайдено.")
    exit()

client = genai.Client(api_key=api_key)

print("🔍 Доступні моделі для вашого ключа:")
print("-" * 50)

try:
    for model in client.models.list():
        # У 2026 році використовуємо supported_actions
        actions = getattr(model, 'supported_actions', 'actions unknown')
        # Виводимо назву моделі (id) та що вона вміє
        print(f"ID: {model.name}")
        print(f"Дії: {actions}")
        print("-" * 50)
except Exception as e:
    print(f"Помилка при отриманні списку: {e}")