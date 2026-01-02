import sys
from modules.ui import UI
from modules.chat import ChatModule
from modules.storage import Storage
from modules.files import FileModule

def main():
    # Ініціалізація модулів
    ui = UI()
    chat = ChatModule()
    storage = Storage()
    files = FileModule()

    ui.print_message("# Code Agent MVP\nВведіть `exit` для виходу. Модулі готові.", title="System")

    while True:
        try:
            # Отримуємо ввід користувача
            user_input = input("You > ").strip()
            
            if not user_input:
                continue
            if user_input.lower() in ['exit', 'quit']:
                break

            # 1. Зберігаємо запит
            storage.save_message("user", user_input)

            # 2. Отримуємо відповідь (заглушка)
            response = chat.get_response(user_input)

            # 3. Виводимо відповідь в UI
            ui.print_message(response, title="AI Assistant", style="blue")

            # 4. Зберігаємо відповідь
            storage.save_message("assistant", response)

            # Приклад логіки редагування (якщо у відповіді є код)
            if "```python" in response and "edit" in user_input:
                new_code = response.split("```python")[1].split("```")[0].strip()
                # Для прикладу редагуємо файл 'target.py'
                target_file = "target.py"
                old_content = ""
                if os.path.exists(target_file):
                    with open(target_file, "r") as f: old_content = f.read()
                
                if files.show_diff(target_file, old_content, new_code):
                    confirm = input(f"Apply changes to {target_file}? (y/n): ")
                    if confirm.lower() == 'y':
                        files.write_file(target_file, new_code)
                        ui.print_message(f"Файл {target_file} оновлено!", style="bold green")

        except KeyboardInterrupt:
            print("\nБувай!")
            break
        except Exception as e:
            ui.print_error(str(e))

if __name__ == "__main__":
    main()