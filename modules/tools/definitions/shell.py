import asyncio
from ..base import BaseTool

class ShellCommandTool(BaseTool):
    @property
    def name(self) -> str:
        return "run_shell"

    @property
    def description(self) -> str:
        return "Executes a shell command in the terminal. Params: 'command' (str). Returns stdout and stderr."

    async def execute(self, command: str) -> dict:
        try:
            # Запускаем команду в подоболочке
            process = await asyncio.create_subprocess_shell(
                command,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE
            )

            # Ждем завершения и получаем вывод
            stdout, stderr = await process.communicate()
            
            output = ""
            if stdout:
                output += stdout.decode(errors='replace')
            if stderr:
                output += f"\nSTDERR:\n{stderr.decode(errors='replace')}"

            return {
                "status": "success",
                "output": output.strip() if output else "Command executed with no output."
            }
        except Exception as e:
            return {
                "status": "error",
                "output": f"Failed to execute command: {str(e)}"
            }
