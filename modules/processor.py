# modules/processor.py
import json

class ResponseProcessor:
    def __init__(self, ui, tool_manager, chat, policy, history=None):
        self.ui = ui
        self.tools = tool_manager
        self.chat = chat
        self.policy = policy
        self.history = history

    MAX_OUTPUT_LENGTH = 3000
    LARGE_FILE_THRESHOLD = 2000000  # ~2 MB in characters
    OMITTED_PAYLOAD_MARKERS = (
        "[content omitted:",
        "[content omitted in ui:",
    )
    FILE_TOOLS = {"create_file", "write_file", "edit_file", "replace"}

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

        # 4.1. Recovery for malformed file-tool payloads:
        # models sometimes put proper file args inside `command` as JSON string/object.
        normalize_error = self._normalize_file_tool_args_from_command(action_type, command_dict, args)
        if normalize_error:
            return normalize_error

        # 5. Перевірка політики (MiniPicker)
        file_payload_error = self._validate_file_tool_payload(action_type, command_dict, args)
        if file_payload_error:
            return file_payload_error

        payload_error = self._reject_sanitized_payload(action_type, args)
        if payload_error:
            return payload_error

        # Internal marker used only for validation/recovery logic.
        args.pop("_normalized_from_command", None)

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
                meta = self.history.add_file_version(file_path, content, return_metadata=True)
                if isinstance(meta, dict):
                    version = meta.get("version")
                    is_new_version = bool(meta.get("is_new_version"))
                else:
                    version = meta
                    is_new_version = bool(version)
                if version:
                    if is_new_version:
                        self.history.add_transient_file_content(file_path, version, content)
                        result['output'] = f"Read file '{file_path}' and added to history as v{version}."
                    else:
                        ensure_transient = getattr(self.history, "ensure_transient_file_content", None)
                        if callable(ensure_transient):
                            ensure_transient(file_path, version, content)
                        else:
                            # Fallback for tests/mocks: refresh transient to keep context visible.
                            self.history.add_transient_file_content(file_path, version, content)
                        result['output'] = (
                            f"Read file '{file_path}' (unchanged, already in history as v{version})."
                        )

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

    def _reject_sanitized_payload(self, action_type: str, args: dict) -> dict | None:
        """Block destructive actions if model tries to write sanitized history/UI placeholders."""
        if action_type not in {"create_file", "write_file", "edit_file", "replace"}:
            return None

        candidate_fields = []
        if action_type in {"create_file", "write_file"}:
            candidate_fields.append(("content", args.get("content")))
        if action_type in {"edit_file", "replace"}:
            candidate_fields.append(("replace_text", args.get("replace_text")))
            candidate_fields.append(("content", args.get("content")))

        for field_name, raw_value in candidate_fields:
            if not isinstance(raw_value, str):
                continue
            normalized = raw_value.strip().lower()
            if any(marker in normalized for marker in self.OMITTED_PAYLOAD_MARKERS):
                return {
                    "status": "failed",
                    "error_code": "VALIDATION_ERROR",
                    "recoverable": True,
                    "output": (
                        f"Refusing to execute {action_type}: field '{field_name}' contains a "
                        "sanitized placeholder ('content omitted') instead of real code. "
                        "Regenerate the full file content and retry."
                    ),
                    "next_actions": ["read_file", "write_file", "edit_file"],
                }
        return None

    def _validate_file_tool_payload(self, action_type: str, command_dict: dict, args: dict) -> dict | None:
        """Reject malformed file-tool payloads early with explicit guidance."""
        if action_type not in self.FILE_TOOLS:
            return None

        if "command" in command_dict and not bool(args.get("_normalized_from_command", False)):
            return {
                "status": "failed",
                "error_code": "VALIDATION_ERROR",
                "recoverable": True,
                "output": (
                    f"Refusing to execute {action_type}: nested 'command' payload is not allowed for file tools. "
                    "Pass file arguments directly in the action JSON."
                ),
                "next_actions": ["read_file", "create_file", "write_file", "edit_file"],
            }

        if action_type in {"create_file", "write_file"}:
            if not isinstance(args.get("path"), str) or not args.get("path"):
                return {
                    "status": "failed",
                    "error_code": "VALIDATION_ERROR",
                    "recoverable": True,
                    "output": f"{action_type} requires 'path' (string).",
                    "next_actions": ["list_directory", "search_files"],
                }
            if not isinstance(args.get("content"), str):
                return {
                    "status": "failed",
                    "error_code": "VALIDATION_ERROR",
                    "recoverable": True,
                    "output": f"{action_type} requires 'content' (string) with full file text.",
                    "next_actions": ["read_file", "write_file"],
                }
            return None

        # edit_file / replace
        if not isinstance(args.get("path"), str) or not args.get("path"):
            return {
                "status": "failed",
                "error_code": "VALIDATION_ERROR",
                "recoverable": True,
                "output": f"{action_type} requires 'path' (string).",
                "next_actions": ["list_directory", "search_files", "read_file"],
            }
        if not isinstance(args.get("search_text"), str) or not isinstance(args.get("replace_text"), str):
            return {
                "status": "failed",
                "error_code": "VALIDATION_ERROR",
                "recoverable": True,
                "output": f"{action_type} requires both 'search_text' and 'replace_text' as strings.",
                "next_actions": ["read_file", "edit_file"],
            }
        return None

    def _normalize_file_tool_args_from_command(
        self, action_type: str, command_dict: dict, args: dict
    ) -> dict | None:
        """Try to recover file-tool arguments from nested `command` JSON payload."""
        if action_type not in self.FILE_TOOLS:
            return None
        if "command" not in command_dict:
            return None

        nested = command_dict.get("command")
        payload = None
        if isinstance(nested, dict):
            payload = nested
        elif isinstance(nested, str):
            text = nested.strip()
            if text.startswith("{") and text.endswith("}"):
                try:
                    payload = json.loads(text)
                except Exception:
                    payload = None

        if payload is None:
            return {
                "status": "failed",
                "error_code": "VALIDATION_ERROR",
                "recoverable": True,
                "output": (
                    f"Malformed {action_type} payload: nested `command` could not be parsed as JSON object. "
                    "Provide `path`/`content` (or `search_text`/`replace_text`) directly in action JSON."
                ),
                "next_actions": ["read_file", "create_file", "write_file", "edit_file"],
            }

        if not isinstance(payload, dict):
            return {
                "status": "failed",
                "error_code": "VALIDATION_ERROR",
                "recoverable": True,
                "output": f"Malformed {action_type} payload: nested `command` must be a JSON object.",
                "next_actions": ["read_file", "create_file", "write_file", "edit_file"],
            }

        # Merge recovered keys only when direct args are missing.
        for key in ("path", "content", "search_text", "replace_text"):
            if key not in args and key in payload:
                args[key] = payload[key]

        args["_normalized_from_command"] = True
        return None

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
