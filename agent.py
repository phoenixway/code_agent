import os
import sys
import shlex
import json
from modules.config_loader import load_settings, CONFIG_DIR
from modules.ui import UI
from modules.files import FileModule
from modules.context import ContextManager
from modules.history import HistoryManager
from modules.session import SessionManager
from modules.processor import ResponseProcessor
from modules.policy import PermissionPolicy
from modules.chat import get_chat_provider

# Припустимо, цей модуль повертає об'єкт чату

def handle_commands(command_str, context_manager, history_manager, session_manager, ui):
    """Обробник слеш-команд (не йдуть у ШІ)."""
    try:
        parts = shlex.split(command_str)
        cmd = parts[0].lower()
        args = parts[1:]

        if cmd == "/add":
            for path in args:
                if context_manager.add_file(path):
                    ui.print_system(f"➕ Додано в контекст: {path}")
                else:
                    ui.print_error(f"Файл не знайдено: {path}")

        elif cmd == "/drop":
            if not args:
                context_manager.clear()
                ui.print_system("🗑️ Кошик контексту очищено.")
            else:
                for path in args:
                    if context_manager.remove_file(path):
                        ui.print_system(f"➖ Видалено з контексту: {path}")
                    else:
                        ui.print_error(f"Файл не знайдено в кошику: {path}")

        elif cmd == "/list":
            files = context_manager.list_files()
            if files:
                ui.print_system(f"📁 Поточний контекст: {', '.join(files)}")
            else:
                ui.print_system("🌑 Кошик контексту порожній.")

        elif cmd == "/save":
            name = args[0] if args else "default"
            session_manager.save_session(name)

        elif cmd == "/load":
            name = args[0] if args else "default"
            session_manager.load_session(name)

        elif cmd == "/sessions":
            sessions = session_manager.list_sessions()
            ui.print_system(f"💾 Доступні сесії: {', '.join(sessions) if sessions else 'порожньо'}")

        elif cmd in ["/exit", "/quit"]:
            ui.print_system("👋 Завершення роботи...")
            sys.exit(0)

        else:
            ui.print_error(f"Невідома команда: {cmd}")

    except Exception as e:
        ui.print_error(f"Помилка команди: {e}")

def main():
    # 1. Ініціалізація базових налаштувань та UI
    settings = load_settings()
    ui = UI()
    ui.print_system("✨ Angelica-AI: Запуск системи...")

    # 2. Ініціалізація модулів
    files = FileModule()
    context_manager = ContextManager(files)
    
    # Вибір моделі та провайдера
    model_name = settings.get("default_model", "gemini-1.5-pro")
    chat = get_chat_provider(model_name)
    
    # Історія та сесії
    history = HistoryManager(chat, max_tokens=settings.get("max_history_tokens", 4000))
    session_manager = SessionManager(CONFIG_DIR, history, context_manager, ui)
    
    # Політика дозволів та процесор
    policy = PermissionPolicy(settings.get("permission_policy", "ask"))
    processor = ResponseProcessor(ui, files, chat, policy)

    ui.print_system(f"🤖 Модель: [bold cyan]{model_name}[/]")
    ui.print_system("Команди: /add, /drop, /list, /save, /load, /sessions, /exit")
    ui.print_horizontal_rule()

    while True:
        try:
            # Вивід статистики в рядку вводу
            file_count, tokens = context_manager.get_stats()
            prompt_label = f"You [Files:{file_count} | ~{tokens}tk] > "
            
            user_input = input(prompt_label).strip()
            if not user_input: continue

            # Перевірка на команди
            if user_input.startswith("/"):
                handle_commands(user_input, context_manager, history, session_manager, ui)
                continue

            # Додаємо запит користувача в історію
            history.add_message("user", user_input)

            # Формуємо запит (Контекст файлів + Питання)
            context_data = context_manager.get_context_prompt()
            full_query = context_data + user_input

            # Запит до ШІ
            with ui.console.status("[bold grey37]Думаю..."):
                response = chat.get_response_with_history(full_query, history.get_history_for_api())

            # Вивід відповіді та збереження в історію
            ui.print_message(response, role="assistant")
            history.add_message("assistant", response)

            # --- ОБРОБКА ДІЙ (JSON) ---
            # Якщо були команди виконання (run_command), процесор може повернути результат
            command_feedback = processor.process_response(response)

            # --- LOOPBACK (Зворотний зв'язок від команд) ---
            while command_feedback:
                ui.print_system("🔄 Відправка результату команди назад в ШІ...")
                history.add_message("system", f"Result of command execution:\n{command_feedback}")
                
                with ui.console.status("[bold magenta]Аналіз результату..."):
                    response = chat.get_response_with_history(
                        "Analyze the command output and proceed.", 
                        history.get_history_for_api()
                    )
                
                ui.print_message(response, role="assistant")
                history.add_message("assistant", response)
                command_feedback = processor.process_response(response)

            # Перевірка на необхідність сумаризації
            history.check_and_summarize(ui)

        except KeyboardInterrupt:
            ui.print_system("\n👋 Роботу перервано користувачем.")
            break
        except Exception as e:
            ui.print_error(f"Критична помилка: {e}")

if __name__ == "__main__":
    main()
