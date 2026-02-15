"""Диспетчер виконання дій з оптимізацією контексту."""

import ast
import asyncio
import hashlib

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
        
        for segment in segments:
            if segment.type == 'thought':
                await self.ui.print_thought(segment.content)
                processed_segments.append(segment)
                
            elif segment.type == 'text':
                await self.ui.print_message(segment.content, role="assistant")
                processed_segments.append(segment)
                
            elif segment.type == 'action':
                # Виконання дії
                cmd_copy, result_text, stop_flag = await self._execute_action(segment.content, state)
                
                # Додаємо команду в історію
                segment.content = cmd_copy
                processed_segments.append(segment)
                
                system_results.append(result_text)
                
                # Якщо хоч одна дія вимагає зупинки (наприклад, denied), ми зупиняємось
                if stop_flag:
                    should_stop = True
        
        return processed_segments, system_results, should_stop

    async def _execute_action(self, command, state):
        """Виконує одну дію, керує UI та повертає результат."""
        cmd_type = command.get("type") or command.get("action", "unknown")
        command_for_history = self._sanitize_command_for_history(command)
        sm = getattr(state, "state_machine", None)

        if sm is not None:
            pre_decision = sm.pre_action_policy(command)
            if not pre_decision.allow:
                output_text = pre_decision.recovery_prompt or "Action blocked by state machine policy."
                state.pending_loop_stop_info = {
                    "reason": pre_decision.stop_reason or "policy_denied",
                    "recoverable": True,
                    "error_code": "STATE_MACHINE_POLICY_DENY",
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
        """Replace large create_file content with compact metadata for chat/history."""
        safe = command.copy()
        content = safe.get("content")
        if not isinstance(content, str):
            return safe
        size = len(content)
        digest = hashlib.sha256(content.encode("utf-8")).hexdigest()[:12]
        preview = content[:80].replace("\n", "\\n")
        safe["content"] = (
            f"[content omitted: {size} chars, sha256:{digest}, preview:'{preview}']"
        )
        return safe

    def _sanitize_command_for_history(self, command: dict) -> dict:
        cmd_type = command.get("type") or command.get("action", "unknown")
        if cmd_type == "create_file":
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
