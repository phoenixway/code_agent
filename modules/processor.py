# modules/processor.py

class ResponseProcessor:
    def __init__(self, ui, tool_manager, chat, policy, history=None):
        self.ui = ui
        self.tools = tool_manager
        self.chat = chat
        self.policy = policy
        self.history = history

    MAX_OUTPUT_LENGTH = 3000
    LARGE_FILE_THRESHOLD = 2000000  # ~2 MB in characters

    def _truncate_output(self, text: str, threshold: int = None) -> str:
        if not isinstance(text, str):
            return text
        if threshold is None:
            threshold = self.MAX_OUTPUT_LENGTH
        if len(text) > threshold:
            truncated_len = len(text) - threshold
            return text[:threshold] + f"\n... (truncated {truncated_len} characters) ..."
        return text

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
            return {
                "status": "failed",
                "error_code": "VALIDATION_ERROR",
                "recoverable": True,
                "output": "Error: Could not identify tool name.",
            }

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
        policy_decision = await self.policy.check(normalized_cmd)
        if policy_decision is False:
            return {"status": "denied", "output": "Action denied by user."}
        force_truncate = isinstance(policy_decision, str) and policy_decision in {"allow_truncated", "truncated"}
        force_full_output = isinstance(policy_decision, str) and policy_decision in {"allow_full", "full"}

        # 6. Виклик через ToolManager
        result = await self.tools.call(action_type, ui=self.ui, **args)
        
        # 7. Post-processing for specific tools (e.g., read_file)
        if action_type == 'read_file' and result.get('status') == 'success':
            file_path = result.get('file_path') or args.get('path')
            content = result.get('output')
            has_history_api = (
                self.history is not None
                and hasattr(self.history, "add_file_version")
                and hasattr(self.history, "add_transient_file_content")
            )
            if file_path and content and has_history_api:
                version = self.history.add_file_version(file_path, content)
                if version:
                    self.history.add_transient_file_content(file_path, version, content)
                    # Modify the output for the main loop - it no longer needs the full content
                    result['output'] = f"Read file '{file_path}' and added to history as v{version}."

        # 8. Check for ChangeProposal (Diff Preview)
        from modules.types import ChangeProposal
        
        if isinstance(result, ChangeProposal):
            # Show diff UI
            approved = await self.ui.show_diff_preview(result)
            
            if approved:
                try:
                    result.apply()
                    return {"status": "success", "output": f"Changes applied to {result.file_path}"}
                except Exception as e:
                    return {
                        "status": "error",
                        "error_code": "INTERNAL",
                        "recoverable": True,
                        "output": f"Failed to apply changes: {e}",
                    }
            else:
                return {
                    "status": "error",
                    "error_code": "PERMISSION_DENIED",
                    "recoverable": False,
                    "output": "User rejected the file changes.",
                }

        if not isinstance(result, dict):
            result = {"status": "error", "error_code": "INTERNAL", "recoverable": False, "output": str(result)}
        self._normalize_error_payload(result)

        # 9. Output Truncation
        if not result.get("skip_truncation"):
            if isinstance(result, dict) and "output" in result and isinstance(result["output"], str):
                # Визначаємо поріг на основі типу дії
                if action_type in ["read_file", "run_shell"]:
                    threshold = self.LARGE_FILE_THRESHOLD  # ~2 MB
                else:
                    threshold = self.MAX_OUTPUT_LENGTH  # 3000 символів
                
                if len(result["output"]) > threshold:
                    if force_full_output:
                        pass
                    elif force_truncate:
                        result["output"] = self._truncate_output(result["output"], threshold)
                    elif await self.ui.confirm_truncation(action_type, len(result["output"])):
                        result["output"] = self._truncate_output(result["output"], threshold)
                
        return result

    def _normalize_error_payload(self, result: dict) -> None:
        """Ensure action result has consistent error metadata for loop recovery logic."""
        status = result.get("status")
        if status not in {"failed", "error", "denied"}:
            return

        if status == "denied":
            result.setdefault("error_code", "PERMISSION_DENIED")
            result.setdefault("recoverable", False)
            return

        output = str(result.get("output", ""))
        lower_output = output.lower()

        if "error_code" not in result or not result.get("error_code"):
            if "not found" in lower_output:
                result["error_code"] = "NOT_FOUND"
            elif "denied" in lower_output or "permission" in lower_output:
                result["error_code"] = "PERMISSION_DENIED"
            elif "timeout" in lower_output or "timed out" in lower_output:
                result["error_code"] = "TRANSIENT_IO"
            elif "invalid" in lower_output or "missing" in lower_output:
                result["error_code"] = "VALIDATION_ERROR"
            else:
                result["error_code"] = "INTERNAL"

        if "recoverable" not in result:
            result["recoverable"] = result["error_code"] in {
                "NOT_FOUND",
                "VALIDATION_ERROR",
                "TRANSIENT_IO",
            }

        if result["error_code"] == "NOT_FOUND":
            result.setdefault("next_actions", ["list_directory", "search_files", "create_file"])
