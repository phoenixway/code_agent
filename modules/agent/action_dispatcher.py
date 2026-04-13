"""Диспетчер виконання дій з оптимізацією контексту."""

import ast
import asyncio
import hashlib
import json
import re
import shlex
from pathlib import Path
from types import SimpleNamespace

class ActionDispatcher:
    def __init__(self, agent):
        self.agent = agent
        self.ui = agent.ui
        self.processor = agent.processor
        self.config = agent.config
        
        # Мапінг команд до методів відображення/обробки
        self._handlers = {
            'run_shell': self._handle_shell,
            'read_file': self._handle_read_file,
            'edit_file': self._handle_edit_file,
            'create_file': self._handle_create_file,
        }

    async def dispatch_segments(self, segments, state):
        """Обробляє список сегментів, виконує дії та повертає результати."""
        processed_segments = []
        system_results = []
        should_stop = False
        action_segments = [seg for seg in segments if seg.type == "action"]
        action_commands = [seg.content for seg in action_segments]
        execute_indices, batch_notes = self._plan_action_batch(action_commands)
        execute_set = set(execute_indices)
        total_exec = len(execute_indices)
        state.last_batch_actions_executed = 0
        state.last_batch_actions_total = len(action_segments)
        action_ordinal = 0
        if batch_notes:
            system_results.extend(batch_notes)
        sm = getattr(state, "state_machine", None)
        if sm is not None and hasattr(sm, "note_planned_batch"):
            try:
                sm.note_planned_batch([action_commands[i] for i in execute_indices])
            except Exception:
                pass
        
        for segment in segments:
            if segment.type == 'thought':
                await self.ui.print_thought(segment.content)
                processed_segments.append(segment)
                
            elif segment.type == 'text':
                await self.ui.print_message(segment.content, role="assistant")
                processed_segments.append(segment)
                
            elif segment.type == 'action':
                current_idx = action_ordinal
                action_ordinal += 1
                cmd_type = (
                    segment.content.get("type")
                    or segment.content.get("action")
                    or "unknown"
                    if isinstance(segment.content, dict)
                    else "unknown"
                )
                if current_idx not in execute_set:
                    system_results.append(
                        f"SYSTEM RESULT for `{cmd_type}`: Skipped by batch policy."
                    )
                    continue

                # Виконання дії
                cmd_copy, result_text, stop_flag = await self._execute_action(segment.content, state)
                state.last_batch_actions_executed += 1
                if total_exec > 1:
                    batch_pos = execute_indices.index(current_idx) + 1
                    result_text = f"[BATCH {batch_pos}/{total_exec}] {result_text}"
                
                # Do not persist raw tool JSON into model history.
                # Keep only a compact audit line so the model cannot reuse
                # internal metadata fields as tool-call arguments.
                processed_segments.append(
                    SimpleNamespace(type="text", content=self._build_history_audit_line(cmd_copy))
                )
                
                system_results.append(result_text)
                
                # Якщо хоч одна дія вимагає зупинки (наприклад, denied), ми зупиняємось
                if stop_flag:
                    should_stop = True
                    if total_exec > 1 and batch_pos < total_exec:
                        system_results.append(
                            f"SYSTEM RESULT for `{cmd_type}`: Batch aborted after action {batch_pos}/{total_exec} due to stop condition."
                        )
                    break
        
        return processed_segments, system_results, should_stop

    def _plan_action_batch(self, action_commands: list[dict]) -> tuple[list[int], list[str]]:
        if not action_commands:
            return [], []
        if len(action_commands) == 1:
            return [0], []

        notes: list[str] = []
        readonly_indices = [
            idx for idx, cmd in enumerate(action_commands)
            if self._is_read_only_action(cmd)
        ]
        if len(readonly_indices) != len(action_commands):
            first_state_changing = next(
                idx for idx, cmd in enumerate(action_commands)
                if not self._is_read_only_action(cmd)
            )
            notes.append(
                "SYSTEM RESULT for `batch_policy`: Mixed batch detected; executing only the first state-changing action."
            )
            return [first_state_changing], notes

        max_batch = max(1, int(getattr(self.config, "MAX_READONLY_BATCH_ACTIONS", 6)))
        if len(action_commands) > max_batch:
            notes.append(
                f"SYSTEM RESULT for `batch_policy`: Read-only batch limited to {max_batch} actions."
            )
            return list(range(max_batch)), notes

        return list(range(len(action_commands))), notes

    def _is_read_only_action(self, command: dict) -> bool:
        if not isinstance(command, dict):
            return False
        cmd_type = command.get("type") or command.get("action") or "unknown"
        read_only_tools = {
            "read_file",
            "read_file_skeleton",
            "search_content",
            "search_files",
            "list_directory",
            "find_files",
            "git_diff",
        }
        if cmd_type == "run_shell":
            return self._is_read_only_shell_command(command.get("command"))
        return cmd_type in read_only_tools

    def _build_history_audit_line(self, command: dict) -> str:
        cmd_type = command.get("type") or command.get("action", "unknown")
        path = command.get("path") if isinstance(command.get("path"), str) and command.get("path") else None

        payload = {"type": cmd_type}
        if path:
            payload["path"] = path

        if command.get("content_redacted") is True:
            size = command.get("content_size")
            blob = command.get("content_blob_hash")
            blob_short = (str(blob)[:12] + "...") if blob else "unknown"
            payload["content"] = f"REDACTED(size={size}, blob={blob_short})"
        else:
            payload["content"] = "none"

        return "TOOL_HISTORY " + json.dumps(payload, ensure_ascii=False, sort_keys=True)

    def _has_explicit_reread_reason(self, command: dict) -> bool:
        reason_fields = (
            command.get("reason"),
            command.get("because"),
            command.get("before_execution"),
            command.get("note"),
        )
        blob = " ".join(str(x) for x in reason_fields if x).lower()
        return any(token in blob for token in ("exact", "verify", "patch", "edit", "implementation", "точн", "перевір", "патч", "редаг"))

    def _error_code_from_reason(self, reason: str | None, default: str = "STATE_MACHINE_POLICY_DENY") -> str:
        if not isinstance(reason, str) or not reason.strip():
            return default
        code = re.sub(r"[^A-Z0-9]+", "_", reason.upper()).strip("_")
        return code or default

    async def _execute_action(self, command, state):
        """Виконує одну дію, керує UI та повертає результат."""
        cmd_type = command.get("type") or command.get("action", "unknown")
        if cmd_type == "read_file":
            command = self._normalize_read_file_command(command)
            if not command.get("path"):
                output_text = (
                    "SYSTEM: Invalid read_file payload. Provide `path` as a top-level field.\n"
                    "Example:\n"
                    '<action type="read_file">{"path":"relative/or/absolute/path"}</action>'
                )
                state.pending_loop_stop_info = {
                    "reason": "malformed_read_file_payload",
                    "recoverable": True,
                    "error_code": "MALFORMED_READ_FILE_PAYLOAD",
                    "next_actions": ["read_file", "search_content", "list_directory"],
                    "command": command.copy(),
                }
                full_result_text = f"SYSTEM RESULT for `{cmd_type}`: {output_text}"
                if self.agent.log:
                    self.agent.log.debug(
                        "Action.finish type=read_file should_stop=True reason=malformed_read_file_payload"
                    )
                return self._sanitize_command_for_history(command), full_result_text, True
            history = getattr(self.agent, "history", None)
            path = command.get("path") if isinstance(command.get("path"), str) else None
            if history is not None and path and getattr(history, "has_current_file_version", lambda _p: False)(path):
                if not self._has_explicit_reread_reason(command):
                    recently_summarized = bool(getattr(history, "was_recently_summarized", lambda _w=90: False)(getattr(self.config, "RECENT_SUMMARY_REREAD_WINDOW_SEC", 90)))
                    reason = "reread_after_summary" if recently_summarized else "reread_already_in_history"
                    output_text = (
                        "SYSTEM: This file is already available in history at the current version. "
                        "Re-reading it without a specific reason is blocked. Use existing context, "
                        "narrow with search_content, or proceed to edit_file/write_file."
                    )
                    state.pending_loop_stop_info = {
                        "reason": reason,
                        "recoverable": True,
                        "error_code": "FILE_ALREADY_AVAILABLE_USE_EXISTING_CONTEXT",
                        "next_actions": ["search_content", "edit_file", "write_file"],
                        "command": command.copy(),
                    }
                    full_result_text = f"SYSTEM RESULT for `{cmd_type}`: {output_text}"
                    return self._sanitize_command_for_history(command), full_result_text, True

        if cmd_type == "list_directory" and not command.get("path"):
            output_text = (
                "SYSTEM: Invalid list_directory payload: explicit `path` is required. "
                "Do not omit path in read-only batches. Root listing without intent is blocked."
            )
            state.pending_loop_stop_info = {
                "reason": "list_directory_missing_path",
                "recoverable": True,
                "error_code": "LIST_DIRECTORY_MISSING_PATH",
                "next_actions": ["list_directory", "search_files", "search_content"],
                "command": command.copy(),
            }
            full_result_text = f"SYSTEM RESULT for `{cmd_type}`: {output_text}"
            return self._sanitize_command_for_history(command), full_result_text, True

        command_for_history = self._sanitize_command_for_history(command)
        sm = getattr(state, "state_machine", None)

        if sm is not None:
            pre_decision = sm.pre_action_policy(command)
            if not pre_decision.allow:
                output_text = pre_decision.recovery_prompt or "Action blocked by state machine policy."
                state.pending_loop_stop_info = {
                    "reason": pre_decision.stop_reason or "policy_denied",
                    "recoverable": True,
                    "error_code": self._error_code_from_reason(pre_decision.stop_reason),
                    "next_actions": pre_decision.required_next_action_types or [],
                    "command": command.copy(),
                }
                full_result_text = f"SYSTEM RESULT for `{cmd_type}`: {output_text}"
                if self.agent.log:
                    self.agent.log.debug(
                        f"Action.finish type={cmd_type} should_stop=True reason={pre_decision.stop_reason}"
                    )
                return command_for_history, full_result_text, True

        if state.consume_forbidden_action_if_matches(command):
            output_text = (
                "Action blocked: repeating the previous action immediately after malformed-action recovery "
                "is not allowed. Change tool or arguments."
            )
            state.pending_loop_stop_info = {
                "reason": "repeating_no_progress",
                "recoverable": True,
                "error_code": "REPEATED_ACTION_AFTER_MALFORMED",
                "next_actions": ["search_content", "search_files", "edit_file", "write_file"],
                "command": command.copy(),
            }
            full_result_text = f"SYSTEM RESULT for `{cmd_type}`: {output_text}"
            if self.agent.log:
                self.agent.log.debug(f"Action.finish type={cmd_type} should_stop=True")
            return command_for_history, full_result_text, True

        if self.agent.log:
            self.agent.log.debug(f"Action.start type={cmd_type} command={command}")

        # 1. UI Execution Wrapper
        handler = self._handlers.get(cmd_type, self._handle_default)
        result = await handler(command)

        # 2. Post-Processing
        output_text = result.get('output', '')
        status = result.get('status')
        error_code = result.get("error_code")
        recoverable = bool(result.get("recoverable", False))
        next_actions = result.get("next_actions") or []
        if not isinstance(next_actions, list):
            next_actions = []
        if self.agent.log:
            self.agent.log.debug(
                f"Action.result type={cmd_type} status={status} "
                f"error_code={error_code} recoverable={recoverable}"
            )
        state_metrics = state.record_action_result(command, result)
        if sm is not None:
            sm.note_action(command, result, self.config.STATE_CHANGING_OPS)

        # 3. Syntax Check (Linting)
        if cmd_type in ['create_file', 'edit_file'] and status == 'success':
            path = command.get('path', '')
            if path.endswith('.py'):
                lint_error = self._check_python_syntax(path)
                if lint_error:
                    output_text += f"\n\n⚠️ SYSTEM WARNING: Syntax check failed for {path}:\n{lint_error}\nPlease fix this immediately."

        # 4. Smart Stop Logic
        is_state_changing = cmd_type in self.config.STATE_CHANGING_OPS
        execution_failed = status in ["failed", "error"]
        action_denied = status == "denied"
        same_action_repeats = state_metrics.get("same_action_repeats", 0)
        read_only_repeat_threshold = max(
            2, int(getattr(self.config, "READ_ONLY_REPEAT_THRESHOLD", 3))
        )
        repeated_read_file_no_progress = (
            cmd_type == "read_file"
            and status == "success"
            and same_action_repeats >= read_only_repeat_threshold
        )
        search_no_matches = "no matches found" in str(output_text).lower()
        repeated_search_no_match_no_progress = (
            cmd_type == "search_content"
            and status == "success"
            and search_no_matches
            and same_action_repeats >= read_only_repeat_threshold
        )
        repeated_readonly_shell_no_progress = (
            cmd_type == "run_shell"
            and status == "success"
            and same_action_repeats >= read_only_repeat_threshold
            and self._is_read_only_shell_command(command.get("command"))
        )

        should_stop = False
        state.pending_loop_stop_info = None

        if repeated_read_file_no_progress:
            should_stop = True
            output_text += (
                "\n[SYSTEM: Repeated read_file calls detected with no progress. "
                "Stop and switch to a different strategy.]"
            )
            state.pending_loop_stop_info = {
                "reason": "repeating_no_progress",
                "recoverable": True,
                "error_code": "READ_ONLY_LOOP",
                "next_actions": ["search_content", "edit_file", "write_file"],
                "command": command.copy(),
            }
        elif repeated_search_no_match_no_progress:
            should_stop = True
            output_text += (
                "\n[SYSTEM: Repeated search_content calls returned no matches. "
                "Stop and switch to deterministic recovery.]"
            )
            state.pending_loop_stop_info = {
                "reason": "repeating_no_progress",
                "recoverable": True,
                "error_code": "SEARCH_NO_MATCH_LOOP",
                "next_actions": ["search_files", "read_file", "edit_file", "write_file"],
                "command": command.copy(),
            }
        elif repeated_readonly_shell_no_progress:
            should_stop = True
            output_text += (
                "\n[SYSTEM: Repeated read-only run_shell commands detected with no progress. "
                "Stop and switch to deterministic edit/write step.]"
            )
            state.pending_loop_stop_info = {
                "reason": "repeating_no_progress",
                "recoverable": True,
                "error_code": "READONLY_SHELL_LOOP",
                "next_actions": ["read_file", "edit_file", "write_file"],
                "command": command.copy(),
            }
        elif action_denied:
            output_text += "\n[SYSTEM: Action denied by user.]"
            should_stop = True

        elif execution_failed:
            output_text += "\n[SYSTEM: Action failed. Analyze the error in <think> and retry.]"
            same_error_repeats = state_metrics.get("same_error_repeats", 0)
            loop_threshold = max(2, int(getattr(self.config, "LOOP_ERROR_REPEAT_THRESHOLD", 2)))
            threshold_reached = same_error_repeats >= loop_threshold
            is_repeated_edit_search_mismatch = (
                cmd_type == "edit_file"
                and error_code == "VALIDATION_ERROR"
                and "Search block not found" in str(result.get("output", ""))
            )

            if threshold_reached:
                if is_repeated_edit_search_mismatch:
                    should_stop = True
                    output_text += (
                        "\n[SYSTEM: Repeated edit_file search mismatch detected. "
                        "Stop this loop and switch to deterministic recovery.]"
                    )
                    state.pending_loop_stop_info = {
                        "reason": "repeating_failure",
                        "recoverable": recoverable,
                        "error_code": error_code,
                        "next_actions": next_actions,
                        "command": command.copy(),
                    }
                # Do not hard-stop immediately after malformed-action recovery.
                elif state.consume_malformed_grace():
                    output_text += (
                        "\n[SYSTEM: Grace retry granted after malformed action recovery. "
                        "Try a different command/arguments now.]"
                    )
                else:
                    budget_ok = state.consume_retry_budget(recoverable)
                    if not budget_ok:
                        should_stop = True
                        output_text += (
                            "\n[SYSTEM: Repeated no-progress failure detected and retry budget exhausted.]"
                        )
                        state.pending_loop_stop_info = {
                            "reason": "repeating_failure",
                            "recoverable": recoverable,
                            "error_code": error_code,
                            "next_actions": next_actions,
                            "command": command.copy(),
                        }
                    else:
                        output_text += (
                            "\n[SYSTEM: Repeated failure detected. Retry budget remains, "
                            "but you must change strategy/arguments.]"
                        )

            feedback_lines = [
                "[SYSTEM_FEEDBACK]",
                f"last_tool_error_code={error_code or 'UNSPECIFIED'}",
                f"last_tool_error_message={str(result.get('output', ''))[:300]}",
            ]
            if next_actions:
                feedback_lines.append(
                    "suggested_recovery_actions=" + ",".join(str(x) for x in next_actions[:6])
                )
            feedback_lines.append(
                "instruction=Do not repeat the same tool call with the same arguments."
            )
            output_text += "\n" + "\n".join(feedback_lines)

            if cmd_type == "edit_file" and "Search block not found" in str(output_text):
                output_text += (
                    "\n[SYSTEM: edit_file search block mismatch. "
                    "Next step must be deterministic: read the file, copy the exact block, "
                    "then retry edit_file with exact whitespace or use write_file with full updated content.]"
                )

        elif is_state_changing:
            state.reset_retry_budgets(
                self.config.RECOVERABLE_ERROR_RETRY_BUDGET,
                self.config.CRITICAL_ERROR_RETRY_BUDGET,
            )
            should_stop = False
        else:
            state.reset_retry_budgets(
                self.config.RECOVERABLE_ERROR_RETRY_BUDGET,
                self.config.CRITICAL_ERROR_RETRY_BUDGET,
            )

        full_result_text = f"SYSTEM RESULT for `{cmd_type}`: {output_text}"

        if self.agent.log:
            self.agent.log.debug(f"Action.finish type={cmd_type} should_stop={should_stop}")
        return command_for_history, full_result_text, should_stop

    def _is_read_only_shell_command(self, raw_command: object) -> bool:
        if not isinstance(raw_command, str):
            return False
        cmd = raw_command.strip()
        if not cmd:
            return False
        lowered = cmd.lower()
        if any(tok in lowered for tok in (">", "| tee", ">>", "sed -i", "perl -i", "mkdir ", "rm ", "mv ", "cp ", "touch ")):
            return False

        segments = re.split(r"\s*(?:&&|\|\||;|\n)\s*", lowered)
        if not segments:
            return False
        allowed_bins = {"cd", "cat", "head", "tail", "grep", "rg", "wc", "find", "stat", "file", "pwd", "ls", "sed", "awk"}
        saw_reader = False

        for segment in segments:
            segment = segment.strip()
            if not segment:
                continue
            try:
                tokens = shlex.split(segment)
            except Exception:
                return False
            if not tokens:
                continue
            bin_name = tokens[0]
            if bin_name not in allowed_bins:
                return False
            if bin_name == "sed" and "-n" not in tokens:
                return False
            if bin_name != "cd":
                saw_reader = True
        return saw_reader

    def _normalize_read_file_command(self, command: dict) -> dict:
        """Recover malformed read_file payloads where JSON is nested under `command`."""
        if not isinstance(command, dict):
            return {"type": "read_file"}
        if command.get("path"):
            return command

        raw = command.get("command")
        if not isinstance(raw, str):
            return command
        text = raw.strip()
        if not text.startswith("{"):
            return command
        try:
            nested = json.loads(text)
        except Exception:
            return command
        if not isinstance(nested, dict):
            return command

        merged = command.copy()
        for key in ("path", "before_execution", "during_execution", "after_execution"):
            if merged.get(key) in (None, "") and nested.get(key):
                merged[key] = nested.get(key)
        if not merged.get("path"):
            inferred = self._infer_read_file_path(merged)
            if inferred:
                merged["path"] = inferred
        return merged

    def _infer_read_file_path(self, command: dict) -> str | None:
        """Best-effort path inference for malformed read_file payloads."""
        if not isinstance(command, dict):
            return None

        direct_keys = ("path", "file", "file_path", "target", "target_path")
        for key in direct_keys:
            value = command.get(key)
            if isinstance(value, str) and value.strip():
                return value.strip()

        text_parts = []
        for key in ("before_execution", "during_execution", "after_execution", "reason", "note", "command"):
            value = command.get(key)
            if isinstance(value, str) and value.strip():
                text_parts.append(value.strip())
        blob = "\n".join(text_parts)
        if not blob:
            return None

        path_match = re.search(r'([A-Za-z0-9._/\-]+/[A-Za-z0-9._/\-]+\.[A-Za-z0-9]+)', blob)
        if path_match:
            return path_match.group(1)

        filename_matches = re.findall(r'\b([A-Za-z0-9._-]+\.[A-Za-z0-9]+)\b', blob)
        unique_filenames = sorted(set(filename_matches))
        if len(unique_filenames) != 1:
            return None
        filename = unique_filenames[0]
        if re.match(r'^\d{2}_[A-Za-z0-9_-]+\.go$', filename):
            return f"go_examples/{filename}"
        if Path(filename).exists():
            return filename
        return None

    # --- Specific Handlers ---

    async def _handle_shell(self, command):
        widget = await self.ui.print_shell_start(command)
        await self.ui.start_action(command.get("during_execution", "Executing shell..."))
        result = await self.processor.process_single_action(command)
        await self.ui.update_shell_result(widget, result)
        return result

    async def _handle_read_file(self, command):
        widget = await self.ui.print_read_file_start(command)
        await self.ui.start_action(f"Reading {command.get('path', 'file')}...")
        result = await self.processor.process_single_action(command)
        await self.ui.update_read_file_result(widget, result)
        return result

    async def _handle_edit_file(self, command):
        widget = await self.ui.print_edit_file_start(command)
        await self.ui.start_action(f"Editing {command.get('path', 'file')}...")
        result = await self.processor.process_single_action(command)
        await self.ui.update_edit_file_result(widget, result)
        return result
    
    async def _handle_create_file(self, command):
        await self.ui.print_tool_call(self._sanitize_create_file_payload(command))
        await self.ui.start_action(f"Creating {command.get('path')}...")
        result = await self.processor.process_single_action(command)
        
        if result.get("status") == "success":
             await self.ui.print_confirmation(f"File {command.get('path')} created.")
        else:
             await self.ui.print_command_result(result.get('output'))
        return result

    def _sanitize_create_file_payload(self, command: dict) -> dict:
        """Replace large file-content payload with compact metadata for chat/history."""
        safe = command.copy()
        content = safe.get("content")
        if not isinstance(content, str):
            return safe
        if len(content) <= 200:
            return safe

        blob_hash = None
        history = getattr(self.agent, "history", None)
        save_blob = getattr(history, "_save_blob", None)
        if callable(save_blob):
            try:
                blob_hash = save_blob(content)
            except Exception:
                blob_hash = None
        if not blob_hash:
            blob_hash = hashlib.sha256(content.encode("utf-8")).hexdigest()

        safe.pop("content", None)
        safe["content_redacted"] = True
        safe["content_size"] = len(content)
        safe["content_blob_hash"] = blob_hash
        return safe

    def _sanitize_command_for_history(self, command: dict) -> dict:
        cmd_type = command.get("type") or command.get("action", "unknown")
        if cmd_type in {"create_file", "write_file", "edit_file", "replace"}:
            return self._sanitize_create_file_payload(command)
        return command.copy()

    async def _handle_default(self, command):
        await self.ui.print_tool_call(command)
        if command.get("before_execution"):
            await self.ui.print_plan(command['before_execution'])
        
        await self.ui.start_action(command.get("during_execution", "Working..."))
        result = await self.processor.process_single_action(command)
        
        if result.get("status") == "success" and command.get("after_execution"):
            await self.ui.print_confirmation(command['after_execution'])
        
        await self.ui.print_command_result(result.get('output', ''))
        return result

    def _check_python_syntax(self, path):
        """Перевіряє синтаксис Python файлу без його виконання."""
        try:
            with open(path, 'r', encoding='utf-8') as f:
                source = f.read()
            ast.parse(source)
            return None
        except SyntaxError as e:
            return f"Line {e.lineno}: {e.msg}\n{e.text}"
        except Exception as e:
            return str(e)
