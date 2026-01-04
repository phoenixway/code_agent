import sys
import os
import re
import json
import warnings
import argparse

# Приховуємо системні попередження для чистого інтерфейсу
warnings.filterwarnings("ignore")

# Імпорт модулів Angelica-AI
from modules.ui import UI
from modules.chat import get_chat_provider
from modules.storage import Storage
from modules.files import FileModule, EditBlock
from modules.project import ProjectModule
from modules.config_loader import load_settings, CONFIG_DIR

def apply_changes_logic(ui, files, response):
    """
    Мультиформатний диспетчер. Автоматично розпізнає формат відповіді ШІ.
    Порядок перевірки: JSON -> Diff -> XML -> SEARCH/REPLACE -> Markdown (Нові файли).
    """
    
    # --- 1. Формат: STRUCTURED JSON (Tooling) ---
    if response.strip().startswith("{") or "```json" in response:
        try:
            # Очищення від Markdown-обгорток
            clean_json = response.strip()
            if "```json" in clean_json:
                clean_json = clean_json.split("```json")[1].split("```")[0].strip()
            elif "```" in clean_json:
                clean_json = clean_json.split("```")[1].split("```")[0].strip()
            
            data = json.loads(clean_json)
            edits = data if isinstance(data, list) else [data]
            
            for item in edits:
                if item.get("type") == "edit_file":
                    file_path = item.get("file_path")
                    ui.print_system(f"🛠️  JSON Edit Request: [bold]{file_path}[/]")
                    if input("Apply changes? (y/n): ").lower() == 'y':
                        for e in item.get("edits", []):
                            block = EditBlock(file_path, e['search'], e['replace'])
                            res = files.apply_edit(block)
                            ui.print_system(res.message) if res.success else ui.print_error(res.message)
            return 
        except Exception:
            pass # Якщо не JSON, перевіряємо наступні формати

    # --- 2. Формат: UNIFIED DIFF (--- a/ +++ b/) ---
    if "--- a/" in response and "+++ b/" in response:
        ui.print_system("🔍 Detected Unified Diff format.")
        diff_pattern = r"(--- a/.*?\n\+\+\+ b/.*?\n@@.*?\n.*?)(?=\n--- a/|\Z)"
        diffs = re.findall(diff_pattern, response, re.DOTALL)
        
        for diff in diffs:
            if input("Apply this Git-style patch? (y/n): ").lower() == 'y':
                res = files.apply_unified_diff(diff)
                ui.print_system(res.message) if res.success else ui.print_error(res.message)
        return

    # --- 3. Формат: XML TAGS (Claude Style) ---
    if "<file_edit>" in response:
        xml_pattern = r"<file_edit>\s*<file>(.*?)</file>\s*<search>(.*?)</search>\s*<replace>(.*?)</replace>"
        xml_matches = re.findall(xml_pattern, response, re.DOTALL)
        
        for f, s, r in xml_matches:
            file_path = f.strip()
            ui.print_system(f"📦 XML Edit Request: [bold]{file_path}[/]")
            if input("Apply? (y/n): ").lower() == 'y':
                res = files.apply_edit(EditBlock(file_path, s, r))
                ui.print_system(res.message) if res.success else ui.print_error(res.message)
        return

    # --- 4. Формат: SEARCH/REPLACE (DeepSeek/Aider style) ---
    sr_pattern = r"([\w\.\-/]+)\n<<<<<<< SEARCH\n(.*?)\n=======\n(.*?)\n>>>>>>> REPLACE"
    sr_matches = re.findall(sr_pattern, response, re.DOTALL)
    
    if sr_matches:
        for f, s, r in sr_matches:
            file_path = f.strip()
            ui.print_system(f"📝 SEARCH/REPLACE Request: [bold]{file_path}[/]")
            if input("Apply? (y/n): ").lower() == 'y':
                res = files.apply_edit(EditBlock(file_path, s, r))
                ui.print_system(res.message) if res.success else ui.print_error(res.message)
        return

    # --- 5. НОВІ ФАЙЛИ: Markdown блоки з коментарем-назвою ---
    code_blocks = re.findall(r"```(?:\w+)?\n(.*?)\n```", response, re.DOTALL)
    for block in code_blocks:
        first_line = block.split('\n')[0]
        file_match = re.search(r"(?:#|//|--)\s*([\w\.\-/]+)", first_line)
        if file_match:
            suggested_name = file_match.group(1).strip()
            ui.console.print()
            if input(f"💾 Detected code for new file '{suggested_name}'. Create? (y/n): ").lower() == 'y':
                success = files.write_file(suggested_name, block)
                if success is True:
                    ui.print_system(f"🚀 File '{suggested_name}' successfully created.")
                else:
                    ui.print_error(f"Error creating file: {success}")

def main():
    # 1. Налаштування (Пріоритет: CLI > Config > Default)
    settings = load_settings()
    default_model = settings.get("default_model", "ollama/deepseek-coder:6.7b")

    parser = argparse.ArgumentParser(description="Angelica-AI: Pro Coding Agent")
    parser.add_argument("-m", "--model", type=str, default=default_model,
                        help=f"Model ID (e.g., cloud/deepseek). Default: {default_model}")
    args = parser.parse_args()

    # 2. Ініціалізація сервісів
    ui = UI()
    storage = Storage()
    files = FileModule()
    project = ProjectModule()
    
    try:
        # Провайдер ініціалізується з вибраною моделлю та системним промптом
        chat = get_chat_provider(args.model)
    except Exception as e:
        ui.print_error(f"Initialization failed: {e}")
        return

    # 3. Стартовий банер
    ui.print_system("✨ Angelica-AI is online.")
    ui.print_system(f"🤖 Active Model: [bold cyan]{args.model}[/]")
    ui.print_system(f"📂 Config Directory: [grey62]{CONFIG_DIR}[/]")
    ui.print_system("Use 'analyze <path>' to start or ask a question. 'exit' to quit.")
    print()

    # 4. Основний цикл чату
    while True:
        try:
            user_input = input("You > ").strip()
            
            if not user_input: continue
            if user_input.lower() in ['exit', 'quit', 'вихід']:
                ui.print_system("Goodbye!")
                break

            # Очищення вводу для візуального стилю Rich
            sys.stdout.write("\033[F\033[K")
            sys.stdout.flush()
            ui.print_message(user_input, role="user")
            storage.save_message("user", user_input)

            # Обробка аналізу проєкту
            if user_input.startswith("analyze "):
                target_path = user_input.replace("analyze ", "").strip()
                ui.print_system(f"Scanning directory: {target_path}")
                tree = project.get_project_tree(target_path)
                # Перетворюємо команду в контекстний промпт
                user_input = f"This is my current project structure at {target_path}:\n\n{tree}\n\nKeep this in context for future requests."

            ui.console.print()

            # Отримання відповіді ШІ
            with ui.console.status(f"[bold grey37]Thinking ({args.model})...", spinner="dots"):
                response = chat.get_response(user_input)

            # Вивід відповіді ШІ
            ui.print_message(response, role="assistant")
            storage.save_message("assistant", response)

            # Аналіз та застосування змін
            apply_changes_logic(ui, files, response)

        except KeyboardInterrupt:
            ui.print_system("\nSession interrupted. Exiting...")
            break
        except Exception as e:
            ui.print_error(f"Fatal error: {str(e)}")

if __name__ == "__main__":
    main()