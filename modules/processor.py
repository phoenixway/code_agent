# modules/processor.py

class ResponseProcessor:
    def __init__(self, ui, tool_manager, chat, policy):
        self.ui = ui
        self.tools = tool_manager
        self.chat = chat
        self.policy = policy

    async def process_single_action(self, command_dict: dict) -> dict:
        # 1. Спроба знайти назву інструмента
        action_type = command_dict.get("action") or command_dict.get("type")
        
        # 2. ФОЛБЕК-ЛОГІКА: Якщо назви немає, але є ключ 'command'
        if not action_type and "command" in command_dict:
            cmd_text = command_dict["command"]
            # Якщо там довгий рядок або є спецсимволи (&&, |, >) - це 100% run_shell
            if isinstance(cmd_text, str) and (" " in cmd_text or "|" in cmd_text or "&&" in cmd_text):
                action_type = "run_shell"
            else:
                # Якщо коротке слово (наприклад, "ls") - теж вважаємо це назвою інструмента
                action_type = cmd_text

        if not action_type:
            return {"status": "failed", "output": "Error: Could not identify tool name."}

        # 3. Збираємо аргументи
        args = {}
        # Розгортаємо вкладені параметри
        for nested in ["params", "arguments", "parameters"]:
            if isinstance(command_dict.get(nested), dict):
                args.update(command_dict[nested])
        
        # Всі інші ключі (крім службових)
        service_fields = {"action", "type", "command", "params", "arguments", "parameters", 
                         "before_execution", "during_execution", "after_execution", "return_control"}
        
        for k, v in command_dict.items():
            if k not in service_fields:
                args[k] = v

        # 4. Спеціальна обробка для run_shell: 
        # переконуємося, що текст команди потрапив у args['command']
        if action_type == "run_shell" and "command" in command_dict:
            args["command"] = command_dict["command"]

        # 5. Перевірка політики (MiniPicker)
        normalized_cmd = {"type": action_type, **args}
        if not await self.policy.check(normalized_cmd):
            return {"status": "failed", "output": "Action denied by user."}

        # 6. Виклик через ToolManager
        result = await self.tools.call(action_type, **args)
        
        # 7. Check for ChangeProposal (Diff Preview)
        from modules.types import ChangeProposal
        
        if isinstance(result, ChangeProposal):
            # Show diff UI
            approved = await self.ui.show_diff_preview(result)
            
            if approved:
                try:
                    result.apply()
                    return {"status": "success", "output": f"Changes applied to {result.file_path}"}
                except Exception as e:
                    return {"status": "error", "output": f"Failed to apply changes: {e}"}
            else:
                return {"status": "error", "output": "User rejected the file changes."}
                
        return result
