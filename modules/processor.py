import asyncio

# modules/processor.py

class ResponseProcessor:
    def __init__(self, ui, tool_manager, chat, policy):
        self.ui = ui
        self.tools = tool_manager
        self.chat = chat
        self.policy = policy

    async def process_single_action(self, command: dict) -> dict:
        # ШІ може помилитися і замість 'type' надіслати 'command'
        # Робимо обробку обох варіантів
        action_type = command.get("type") or command.get("command")
        
        if not action_type:
            return {
                "status": "failed", 
                "output": "Error: No action type found in JSON (expected 'type' or 'command')."
            }

        # Створюємо нормалізовану копію для policy, щоб вона завжди бачила 'type'
        normalized_command = command.copy()
        normalized_command["type"] = action_type

        # 1. КРИТИЧНО: Перевірка дозволу (твій MiniPicker)
        if not await self.policy.check(normalized_command):
            return {
                "status": "failed", 
                "output": "Action denied by user."
            }

        # 2. Підготовка аргументів (все, крім службових полів)
        service_fields = {"type", "command", "before_execution", "during_execution", "after_execution", "return_control"}
        args = {k: v for k, v in command.items() if k not in service_fields}
        
        # 3. Виклик інструмента через ToolManager
        # Метод call тепер має бути в ToolManager (ми його виправили минулого разу)
        result = await self.tools.call(action_type, **args)
        
        # Повертаємо уніфікований результат
        if result.get("status") == "success":
            return {"status": "success", "output": result.get("output", "")}
        else:
            return {"status": "failed", "output": result.get("output", "Unknown tool error.")}
