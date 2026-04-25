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
        action_type = command_dict.get("action") or command_dict.get("type")

        if not action_type and "command" in command_dict:
            cmd_text = command_dict["command"]
            if isinstance(cmd_text, str) and (" " in cmd_text or "|" in cmd_text or "&&" in cmd_text):
                action_type = "run_shell"
            else:
                action_type = cmd_text

        if not action_type:
            return {
                "status": "failed",
                "error_code": "VALIDATION_ERROR",
                "recoverable": True,
                "output": "Error: Could not identify tool name.",
            }

        args = {}
        for nested in ["params", "arguments", "parameters"]:
            if isinstance(command_dict.get(nested), dict):
                args.update(command_dict[nested])

        service_fields = {
            "action", "type", "command", "params", "arguments", "parameters",
            "before_execution", "during_execution", "after_execution", "return_control"
        }

        for k, v in command_dict.items():
            if k not in service_fields:
                args[k] = v

        if action_type == "run_shell" and "command" in command_dict:
            args["command"] = command_dict["command"]

        normalize_error = self._normalize_file_tool_args_from_command(action_type, command_dict, args)
        if normalize_error:
            return normalize_error

        read_payload_error = self._validate_read_tool_payload(action_type, args)
        if read_payload_error:
            return read_payload_error

        file_payload_error = self._validate_file_tool_payload(action_type, command_dict, args)
        if file_payload_error:
            return file_payload_error

        payload_error = self._reject_sanitized_payload(action_type, args)
        if payload_error:
            return payload_error

        args.pop("_normalized_from_command", None)

        normalized_cmd = {"type": action_type, **args}
        policy_decision = await self.policy.check(normalized_cmd)
        if policy_decision is False:
            return {"status": "denied", "output": "Action denied by user."}
        force_truncate = isinstance(policy_decision, str) and policy_decision in {"allow_truncated", "truncated"}
        force_full_output = isinstance(policy_decision, str) and policy_decision in {"allow_full", "full"}

        result = await self.tools.call(action_type, ui=self.ui, **args)

        if action_type in {"read_file", "read_chunk", "extract_kotlin_function", "extract_symbol"} and result.get("status") == "success":
            file_path = result.get("file_path") or args.get("path")
            content = result.get("file_content") or result.get("output")
            has_history_api = (
                self.history is not None
                and hasattr(self.history, "add_file_version")
            )
            should_track_full_file_version = action_type == "read_file"
            if file_path and content and has_history_api and should_track_full_file_version:
                meta = self.history.add_file_version(file_path, content, return_metadata=True)
                if isinstance(meta, dict):
                    version = meta.get("version")
                    is_new_version = bool(meta.get("is_new_version"))
                else:
                    version = meta
                    is_new_version = bool(version)
                if version:
                    if action_type == "read_chunk":
                        start_line = result.get("start_line", args.get("start_line"))
                        end_line = result.get("end_line", args.get("end_line"))
                        start_byte = result.get("start_byte", args.get("start_byte"))
                        end_byte = result.get("end_byte", args.get("end_byte"))

                        if start_line is not None and end_line is not None:
                            read_label = f"Read chunks ({start_line}, {end_line}) from {file_path}"
                        else:
                            read_label = f"Read chunks ({start_byte}, {end_byte}) from {file_path}"

                        result["output"] = (
                            f"{read_label}"
                            f"{' and added to history as ' if is_new_version else ' (already in history as '}v{version}"
                            f"{'' if is_new_version else ')'}."
                        )
                    else:
                        if is_new_version:
                            result["output"] = f"Read file '{file_path}' and added to history as v{version}."
                        else:
                            result["output"] = (
                                f"Read file '{file_path}' (unchanged, already in history as v{version})."
                            )
            elif file_path and content and action_type == "read_chunk":
                start_line = result.get("start_line", args.get("start_line"))
                end_line = result.get("end_line", args.get("end_line"))
                start_byte = result.get("start_byte", args.get("start_byte"))
                end_byte = result.get("end_byte", args.get("end_byte"))

                if start_line is not None and end_line is not None:
                    result["output"] = f"Read chunks ({start_line}, {end_line}) from {file_path}."
                else:
                    result["output"] = f"Read chunks ({start_byte}, {end_byte}) from {file_path}."
            elif file_path and action_type in {"extract_kotlin_function", "extract_symbol"}:
                symbol_name = (
                    result.get("symbol_name")
                    or result.get("function_name")
                    or args.get("symbol_name")
                    or args.get("function_name")
                    or "symbol"
                )
                symbol_kind = result.get("symbol_kind") or ("function" if action_type == "extract_kotlin_function" else "symbol")
                class_name = (
                    result.get("container_name")
                    or result.get("class_name")
                    or args.get("container_name")
                    or args.get("class_name")
                )
                start_line = result.get("start_line")
                end_line = result.get("end_line")
                owner = f" from {class_name}." if isinstance(class_name, str) and class_name else ""
                if start_line is not None and end_line is not None:
                    result["output"] = (
                        f"Extracted Kotlin {symbol_kind} '{symbol_name}' "
                        f"({start_line}-{end_line}) from {file_path}{owner}"
                    )
                else:
                    result["output"] = f"Extracted Kotlin {symbol_kind} '{symbol_name}' from {file_path}{owner}"

        from modules.types import ChangeProposal

        if isinstance(result, ChangeProposal):
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

        if not result.get("skip_truncation"):
            if isinstance(result, dict) and "output" in result and isinstance(result["output"], str):
                if action_type in ["read_file", "read_chunk", "extract_kotlin_function", "extract_symbol", "run_shell"]:
                    threshold = self.LARGE_FILE_THRESHOLD
                else:
                    threshold = self.MAX_OUTPUT_LENGTH

                if len(result["output"]) > threshold:
                    if force_full_output:
                        pass
                    elif force_truncate or action_type == "run_shell":
                        result["output"] = self._truncate_output(result["output"], threshold)
                    elif await self.ui.confirm_truncation(action_type, len(result["output"])):
                        result["output"] = self._truncate_output(result["output"], threshold)

        return result

    def _validate_read_tool_payload(self, action_type: str, args: dict) -> dict | None:
        if action_type not in {"read_file", "read_file_skeleton", "read_chunk"}:
            return None

        if not isinstance(args.get("path"), str) or not args.get("path"):
            code = {
                "read_file": "MALFORMED_READ_FILE_PAYLOAD",
                "read_file_skeleton": "MALFORMED_READ_FILE_SKELETON_PAYLOAD",
                "read_chunk": "MALFORMED_READ_CHUNK_PAYLOAD",
            }[action_type]
            return {
                "status": "failed",
                "error_code": code,
                "recoverable": True,
                "output": f"{action_type} requires top-level 'path' (string).",
                "next_actions": [action_type],
            }

        if action_type == "read_chunk":
            sl = args.get("start_line")
            el = args.get("end_line")
            sb = args.get("start_byte")
            eb = args.get("end_byte")

            has_line_mode = sl is not None or el is not None
            has_byte_mode = sb is not None or eb is not None

            if has_line_mode and has_byte_mode:
                return {
                    "status": "failed",
                    "error_code": "MALFORMED_READ_CHUNK_PAYLOAD",
                    "recoverable": True,
                    "output": (
                        "read_chunk accepts either a line range "
                        "('start_line'/'end_line') or a byte range "
                        "('start_byte'/'end_byte'), but not both at once."
                    ),
                    "next_actions": ["read_chunk"],
                }

            if has_line_mode:
                if not isinstance(sl, int) or not isinstance(el, int) or sl < 1 or el < sl:
                    return {
                        "status": "failed",
                        "error_code": "MALFORMED_READ_CHUNK_PAYLOAD",
                        "recoverable": True,
                        "output": (
                            "read_chunk requires top-level 'start_line' and 'end_line' "
                            "integers with 1 <= start_line <= end_line."
                        ),
                        "next_actions": ["read_chunk"],
                    }
                return None

            if has_byte_mode:
                if not isinstance(sb, int) or not isinstance(eb, int) or eb <= sb or sb < 0:
                    return {
                        "status": "failed",
                        "error_code": "MALFORMED_READ_CHUNK_PAYLOAD",
                        "recoverable": True,
                        "output": (
                            "read_chunk requires top-level 'start_byte' and 'end_byte' "
                            "integers with 0 <= start_byte < end_byte."
                        ),
                        "next_actions": ["read_chunk"],
                    }
                return None

            return {
                "status": "failed",
                "error_code": "MALFORMED_READ_CHUNK_PAYLOAD",
                "recoverable": True,
                "output": (
                    "read_chunk requires either top-level line range fields "
                    "('start_line'/'end_line') or byte range fields "
                    "('start_byte'/'end_byte')."
                ),
                "next_actions": ["read_chunk"],
            }
        return None

    def _reject_sanitized_payload(self, action_type: str, args: dict) -> dict | None:
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

        for key in ("path", "content", "search_text", "replace_text"):
            if key not in args and key in payload:
                args[key] = payload[key]

        args["_normalized_from_command"] = True
        return None

    def _normalize_error_payload(self, result: dict) -> None:
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
