import json
import re
import subprocess
from modules.files import EditBlock

class ResponseProcessor:
    def __init__(self, ui, files, chat, policy):
        self.ui = ui
        self.files = files
        self.chat = chat
        self.policy = policy

    def process_response(self, response):
        """
        Послідовно знаходить та виконує JSON-інструкції, 
        зберігаючи контекст тексту між ними.
        """
        # Шукаємо всі блоки ```json ... ```
        # Ми використовуємо finditer, щоб обробляти їх у порядку появи
        matches = list(re.finditer(r"```json\s*\n(.*?)\n\s*```", response, re.DOTALL))
        
        if not matches:
            return None

        all_results = []

        for match in matches:
            json_str = match.group(1).strip()
            try:
                data = json.loads(json_str)
                # Перетворюємо одиничну дію в список для уніфікації
                actions = data if isinstance(data, list) else [data]
                
                for action in actions:
                    result = self._execute_action(action)
                    if result:
                        all_results.append(result)
                        
            except json.JSONDecodeError as e:
                err_msg = f"Помилка JSON у блоці: {str(e)}"
                self.ui.print_error(err_msg)
                all_results.append(err_msg)

        return "\n---\n".join(all_results) if all_results else None

    def _execute_action(self, action):
        """Визначає тип дії та викликає відповідний обробник."""
        action_type = action.get("type")

        if action_type == "create_file":
            return self._handle_create(action)
        
        elif action_type == "edit_file":
            return self._handle_edit(action)
        
        elif action_type == "run_command":
            return self._handle_command(action)
        
        else:
            msg = f"Unknown action type: {action_type}"
            self.ui.print_error(msg)
            return msg

    def _handle_create(self, action):
        path = action.get("file_path")
        content = action.get("content", "")
        
        self.ui.print_system(f"🆕 [bold green]CREATE[/]: {path}")
        
        if self.policy.should_ask():
            if input(f"Створити файл {path}? (y/n): ").lower() != 'y':
                return f"Creation of {path} cancelled by user."

        res = self.files.create_file(path, content)
        if res.success:
            return f"Successfully created file: {path}"
        else:
            self.ui.print_error(res.message)
            return f"Error creating {path}: {res.message}"

    def _handle_edit(self, action):
        path = action.get("file_path")
        edits = action.get("edits", [])
        
        self.ui.print_system(f"📝 [bold yellow]EDIT[/]: {path} ({len(edits)} blocks)")
        
        if self.policy.should_ask():
            if input(f"Застосувати зміни до {path}? (y/n): ").lower() != 'y':
                return f"Edits to {path} cancelled by user."

        results = []
        for edit in edits:
            block = EditBlock(
                file_path=path,
                search_text=edit.get("search", ""),
                replace_text=edit.get("replace", "")
            )
            res = self.files.apply_edit(block)
            if res.success:
                results.append(f"Successfully patched block in {path}")
            else:
                self.ui.print_error(f"Patch failed in {path}: {res.message}")
                results.append(f"FAILED to patch {path}: {res.message}")
        
        return "\n".join(results)

    def _handle_command(self, action):
        command = action.get("command")
        reason = action.get("reason", "No reason")
        
        self.ui.print_system(f"🐚 [bold magenta]RUN[/]: {command}")
        self.ui.console.print(f"[grey62]Reason: {reason}[/]")
        
        if self.policy.should_ask():
            if input(f"Виконати команду? (y/n): ").lower() != 'y':
                return "Command execution cancelled by user."

        try:
            # Виконуємо команду в Termux/Linux
            process = subprocess.run(
                command,
                shell=True,
                capture_output=True,
                text=True,
                timeout=300 # 5 хвилин для довгих операцій (наприклад, збірка Gradle)
            )
            
            output = f"Command: {command}\nExit Code: {process.returncode}\n"
            if process.stdout:
                output += f"STDOUT:\n{process.stdout}\n"
            if process.stderr:
                output += f"STDERR:\n{process.stderr}\n"
                
            if process.returncode == 0:
                self.ui.print_system("✅ Команда виконана успішно.")
            else:
                self.ui.print_error(f"Команда завершилася з помилкою (код {process.returncode})")
                
            return output

        except subprocess.TimeoutExpired:
            msg = "Error: Command timed out after 300 seconds."
            self.ui.print_error(msg)
            return msg
        except Exception as e:
            msg = f"System Error executing command: {str(e)}"
            self.ui.print_error(msg)
            return msg