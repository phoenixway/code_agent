# modules/tools/definitions/shell.py
import asyncio
import os
import signal
from modules.tools.base import BaseTool
from modules.config_loader import load_settings

class ShellTool(BaseTool):
    name = "run_shell"
    description = (
        "Executes a shell command in the current environment. "
        "Use mainly for shell-native inspection or git/build tasks, not as the first choice for reading large files. "
        "Long stdout may be expensive for context; prefer read_file, read_file_skeleton, search_content, or search_files when applicable. "
        "Params: 'command' (str), 'timeout' (int, optional, seconds)"
    )

    async def _terminate_process(self, process) -> None:
        """Stops shell process and, where possible, its whole process group."""
        if process is None or process.returncode is not None:
            return

        pid = getattr(process, "pid", None)
        killed_group = False
        if isinstance(pid, int):
            try:
                pgid = os.getpgid(pid)
                os.killpg(pgid, signal.SIGKILL)
                killed_group = True
            except Exception:
                killed_group = False

        if not killed_group:
            process.kill()

        await process.communicate()

    async def execute(self, command: str, timeout: int = 30):
        if not command:
            return {
                "status": "error",
                "error_code": "VALIDATION_ERROR",
                "recoverable": True,
                "output": "No command provided.",
            }
        if not isinstance(timeout, int) or timeout <= 0:
            timeout = 30

        settings = load_settings()
        max_command_length = settings.get("max_shell_command_length", 1000)
        if isinstance(max_command_length, int) and len(command) > max_command_length:
            return {
                "status": "error",
                "error_code": "VALIDATION_ERROR",
                "recoverable": False,
                "output": f"Command blocked: length exceeds {max_command_length} characters.",
            }

        blocked_patterns = settings.get("shell_blocklist", []) or []
        for pattern in blocked_patterns:
            if isinstance(pattern, str) and pattern and pattern.lower() in command.lower():
                return {
                    "status": "error",
                    "error_code": "PERMISSION_DENIED",
                    "recoverable": False,
                    "output": f"Command blocked by policy pattern: {pattern}",
                }

        allowlist_prefixes = settings.get("shell_allowlist_prefixes", []) or []
        if allowlist_prefixes:
            normalized = command.strip()
            if not any(
                isinstance(prefix, str) and prefix and normalized.startswith(prefix)
                for prefix in allowlist_prefixes
            ):
                return {
                    "status": "error",
                    "error_code": "PERMISSION_DENIED",
                    "recoverable": False,
                    "output": "Command blocked: not allowed by shell allowlist prefixes.",
                }
            
        process = None
        try:
            # Виконуємо команду в підпроцесі
            preexec_fn = os.setsid if hasattr(os, "setsid") else None
            process = await asyncio.create_subprocess_shell(
                command,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
                preexec_fn=preexec_fn,
            )
            stdout, stderr = await asyncio.wait_for(process.communicate(), timeout=timeout)
            
            output = stdout.decode().strip() or stderr.decode().strip()
            if not output and process.returncode == 0:
                output = "Command executed successfully (no output)."
                
            return {
                "status": "success" if process.returncode == 0 else "error",
                "error_code": None if process.returncode == 0 else "INTERNAL",
                "recoverable": bool(process.returncode != 0),
                "output": output,
            }
        except asyncio.TimeoutError:
            await self._terminate_process(process)
            return {
                "status": "error",
                "error_code": "TRANSIENT_IO",
                "recoverable": True,
                "output": f"Command timed out after {timeout} seconds.",
            }
        except asyncio.CancelledError:
            await self._terminate_process(process)
            raise
        except Exception as e:
            return {
                "status": "error",
                "error_code": "INTERNAL",
                "recoverable": True,
                "output": str(e),
            }
