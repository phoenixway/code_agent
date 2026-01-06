# modules/tools/definitions/shell.py
import asyncio
from modules.tools.base import BaseTool

class ShellTool(BaseTool):
    name = "run_shell"
    description = "Executes a shell command in the current environment. Params: 'command' (str)"

    async def execute(self, command: str):
        if not command:
            return {"status": "error", "output": "No command provided."}
            
        try:
            # Виконуємо команду в підпроцесі
            process = await asyncio.create_subprocess_shell(
                command,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE
            )
            stdout, stderr = await process.communicate()
            
            output = stdout.decode().strip() or stderr.decode().strip()
            if not output and process.returncode == 0:
                output = "Command executed successfully (no output)."
                
            return {
                "status": "success" if process.returncode == 0 else "error",
                "output": output
            }
        except Exception as e:
            return {"status": "error", "output": str(e)}