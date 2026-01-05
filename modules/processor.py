class ResponseProcessor:
    def __init__(self, ui, tool_manager, chat, policy):
        self.ui = ui
        self.tools = tool_manager
        self.chat = chat     # Може знадобитися інструментам для "розумних" операцій
        self.policy = policy # Твій механізм підтвердження дій (ask/always/never)

    async def process_single_action(self, command: dict) -> dict:
        action_type = command.get("type")
        if not action_type:
            return {"status": "failed", "output": "Missing 'type' in JSON."}

        # --- КРИТИЧНИЙ МОМЕНТ: ПЕРЕВІРКА ПРАВ ---
        # Викликаємо твій PermissionPolicy перед тим, як лізти у файлову систему
        if not await self.policy.check(command):
            return {"status": "failed", "output": "Action denied by user policy."}

        # Витягуємо аргументи
        args = {k: v for k, v in command.items() if k != "type"}
        
        # Виконуємо інструмент через менеджер
        result = await self.tools.call(action_type, **args)
        
        status = "success" if result["status"] == "success" else "failed"
        return {"status": status, "output": result["output"]}
