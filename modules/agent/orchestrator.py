"""Оркестратор основного циклу."""

import asyncio
from modules.defaults import DEFAULT_SYSTEM_PROMPT

class Orchestrator:
    def __init__(self, agent):
        self.agent = agent
        # Скорочення для зручності
        self.ui = agent.ui
        self.state = agent.state
        self.history = agent.history
        self.model = agent.model_client
        self.dispatcher = agent.action_dispatcher
        self.parser = agent.parser
        self.config = agent.config

    def _build_action_format_recovery_prompt(self, header: str, *, forbid_audit_markers: bool = False, state_changing_only: bool = False) -> str:
        lines = [
            f"SYSTEM: {header}",
            "Return only valid <action> content for the next step.",
        ]
        if state_changing_only:
            lines.extend([
                "For this recovery step, return exactly one valid state-changing <action>.",
                "Do not return read-only batching here.",
            ])
        else:
            lines.extend([
                "For read-only investigation, multiple separate <action>...</action> blocks are allowed.",
                "Compatible format: one <action>...</action> block may contain a JSON array of read-only action objects.",
                "For any state-changing step, return only one valid <action>.",
                "Do not use JSON arrays for state-changing actions.",
            ])
        lines.extend([
            "No prose outside <action>.",
            "If unsure, prefer separate <action> blocks.",
        ])
        if forbid_audit_markers:
            lines.append("Do not output audit markers like SYSTEM_TOOL_AUDIT, TOOL_HISTORY, or <previously_performed_action>.")
        return "\n".join(lines)

    def _typed_recovery_header(self, stop_info: dict | None) -> str:
        stop_info = stop_info or {}
        reason = str(stop_info.get("reason") or "").strip()
        code = str(stop_info.get("error_code") or "").strip()
        next_actions = stop_info.get("next_actions") or []
        if not isinstance(next_actions, list):
            next_actions = []
        next_hint = f"\nAllowed next actions: {', '.join(next_actions)}." if next_actions else ""

        headers = {
            "reread_after_summary": "You just summarized context and then tried to re-read a file already in history without a specific reason. Use existing context instead.",
            "reread_already_in_history": "You tried to re-read a file that is already available in history without a specific reason.",
            "observe_budget_exhausted": "OBSERVE phase budget is exhausted. Transition to EDIT_PLAN now.",
            "action_not_allowed_in_phase": "The requested action is not allowed in the current phase.",
            "root_listing_budget_exhausted": "Root-level directory listing budget is exhausted for this turn.",
            "list_directory_budget_exhausted": "list_directory budget is exhausted for this turn.",
            "directory_descent_budget_exhausted": "Directory descent budget is exhausted. Stop walking folders one level at a time.",
            "broad_recon_budget_exhausted": "Broad reconnaissance budget is exhausted. Narrow the search or move to editing.",
            "cross_target_read_without_reason": "Target file is pinned. Reading another file now requires an explicit reason.",
            "recover_repeated_fingerprint": "You repeated the same action fingerprint after recovery.",
            "malformed_read_file_payload": "Your last read_file call used an invalid payload.",
            "list_directory_missing_path": "Your last list_directory call omitted the required path.",
            "repeating_no_progress": "You are repeating actions without measurable progress.",
            "repeating_failure": "You are repeating failing actions without changing strategy.",
        }
        if reason in headers:
            return headers[reason] + next_hint
        if code == "FILE_ALREADY_AVAILABLE_USE_EXISTING_CONTEXT":
            return "This file is already available in history at the current version. Re-reading it without a specific reason is blocked." + next_hint
        if code == "LIST_DIRECTORY_MISSING_PATH":
            return "list_directory requires an explicit path. Root fallback is blocked in recovery." + next_hint
        if code == "MALFORMED_READ_FILE_PAYLOAD":
            return "read_file requires a top-level path field in valid JSON." + next_hint
        return "Previous action violated orchestration policy. Choose a different strategy and follow the required next actions." + next_hint

    def _build_typed_stop_recovery_prompt(self, stop_info: dict | None) -> str:
        stop_info = stop_info or {}
        reason = str(stop_info.get("reason") or "").strip()
        state_changing_only = reason in {"repeating_failure", "repeating_no_progress", "observe_budget_exhausted"}
        return self._build_action_format_recovery_prompt(
            self._typed_recovery_header(stop_info),
            forbid_audit_markers=True,
            state_changing_only=state_changing_only,
        )
        
    async def process(self, user_input):
        """Головний цикл: Think -> Act -> Loop."""
        if self.agent.log:
            self.agent.log.info("Orchestrator.start")
            self.agent.log.debug(f"User input: {user_input[:300]}")
        
        # 1. Підготовка контексту
        tools_prompt = self.agent.tool_manager.get_tools_prompt()
        ctx_prompt = self.agent.context_manager.get_context_prompt()
        system_msg = f"{DEFAULT_SYSTEM_PROMPT.format(tools_description=tools_prompt)}\n\n{ctx_prompt}"

        self.history.add_message("user", user_input)
        sm = getattr(self.state, "state_machine", None)
        if sm is not None:
            sm.start_turn(user_input)
            if self.agent.log:
                self.agent.log.debug(f"Task contract: kind={getattr(sm, 'task_kind', None)} phase={getattr(sm, 'phase', None)}")
        
        active_loop = True
        consecutive_calls = 0
        malformed_action_retries = 0
        audit_marker_retries = 0
        malformed_read_file_retries = 0
        current_query = user_input
        consecutive_single_readonly_steps = 0
        loop = asyncio.get_running_loop()
        session_started_at = loop.time()
        
        try:
            while active_loop:
                try:
                    # Keep context under control before next model call.
                    await self.history.check_and_summarize(self.ui, self.state)
                except Exception as e:
                    if self.agent.log:
                        self.agent.log.warning(f"Pre-step summarization check failed: {e}")

                if self.agent.log:
                    self.agent.log.debug(
                        f"Loop iteration={consecutive_calls + 1} "
                        f"history_tokens={self.history.current_token_count}/{self.history.max_tokens}"
                    )
                if loop.time() - session_started_at > self.config.MAX_SESSION_SECONDS:
                    await self.ui.print_error(
                        f"Session time limit reached ({self.config.MAX_SESSION_SECONDS}s). Stopping."
                    )
                    break

                consecutive_calls += 1
                if consecutive_calls > self.config.MAX_CONSECUTIVE_CALLS:
                    suspected_loop = (
                        getattr(self.state, "consecutive_same_error_count", 0)
                        >= max(2, int(getattr(self.config, "LOOP_ERROR_REPEAT_THRESHOLD", 2)))
                    )
                    if suspected_loop and not getattr(self.state, "suppress_step_limit_warning", False):
                        await self.ui.stop_loading()
                        decision = await self.ui.confirm_continue(
                            "Агент зробив багато кроків і є ознаки повторюваного циклу. Продовжити?"
                        )
                        if decision in (False, "stop", None):
                            await self.ui.print_system(
                                f"Execution stopped: reached max consecutive steps ({self.config.MAX_CONSECUTIVE_CALLS})."
                            )
                            break
                        if decision == "continue_silent":
                            self.state.suppress_step_limit_warning = True
                
                await self.ui.start_thinking()
                
                # 2. Запит до AI
                self.state.current_task = asyncio.create_task(
                    self.model.get_streaming_response(
                        current_query,
                        self.history,
                        self.ui,
                        self.state,
                        system_message=system_msg,
                    )
                )
                try:
                    response = await asyncio.wait_for(
                        self.state.current_task,
                        timeout=self.config.MAX_STEP_SECONDS,
                    )
                except asyncio.TimeoutError:
                    self.state.current_task.cancel()
                    await self.ui.print_error(
                        f"Step timed out after {self.config.MAX_STEP_SECONDS}s."
                    )
                    break
                
                if not response or response.startswith("Error:"):
                    if self.agent.log:
                        self.agent.log.warning(f"Model returned terminal response: {response[:200] if response else '<empty>'}")
                    if response and response.startswith("Error:"):
                        await self.ui.print_error(f"Execution stopped due to model error: {response}")
                    else:
                        await self.ui.print_system("Execution finished: model returned no further response.")
                    break
                    
                # 3. Парсинг
                segments = self.parser.parse(response)
                if self.agent.log:
                    self.agent.log.debug(f"Parsed segments count={len(segments)}")
                parsed_action_count = sum(1 for seg in segments if seg.type == "action")

                # Recovery: model returned an <action> tag but parser extracted no action.
                has_action_tag = "<action" in response.lower()
                has_action_segment = any(seg.type == "action" for seg in segments)
                if has_action_tag and not has_action_segment:
                    malformed_action_retries += 1
                    if self.agent.log:
                        self.agent.log.warning(
                            f"Malformed action response detected (retry {malformed_action_retries}/1)."
                        )
                    if malformed_action_retries > 1:
                        await self.ui.print_error(
                            "Execution stopped: model returned malformed action format repeatedly."
                        )
                        break
                    current_query = (
                        self._build_action_format_recovery_prompt(
                            "Your last response contained malformed <action> content."
                        )
                        + "\nIf the edit payload is large, prefer write_file.\n"
                        "If using edit_file, keep search_text/replace_text short and exact."
                    )
                    self.state.set_malformed_grace(self.config.MALFORMED_ACTION_GRACE_STEPS)
                    # Prevent immediate repetition of the previous action after malformed retry.
                    self.state.forbid_next_action_fingerprint(
                        getattr(self.state, "last_completed_fingerprint", None)
                    )
                    continue
                else:
                    malformed_action_retries = 0

                # Recovery: model echoed audit trail marker but produced no tool call.
                response_lower = response.lower()
                contains_audit_marker = (
                    "system_tool_audit:" in response_lower
                    or response_lower.strip().startswith("tool_history ")
                    or "<previously_performed_action" in response_lower
                )
                if contains_audit_marker and not has_action_segment:
                    audit_marker_retries += 1
                    if self.agent.log:
                        self.agent.log.warning(
                            f"Audit-marker echo without action detected (retry {audit_marker_retries}/1)."
                        )
                    if audit_marker_retries > 1:
                        await self.ui.print_error(
                            "Execution stopped: model repeatedly echoed audit trail without a valid action."
                        )
                        break
                    current_query = self._build_action_format_recovery_prompt(
                        "Your last response echoed an internal audit marker instead of a tool call.",
                        forbid_audit_markers=True,
                    )
                    continue
                audit_marker_retries = 0
                
                # 4. Виконання дій (через Dispatcher)
                self.state.current_task = asyncio.create_task(
                    self.dispatcher.dispatch_segments(segments, self.state)
                )
                processed_segs, sys_results, should_stop = await self.state.current_task
                action_count = parsed_action_count
                action_commands = [seg.content for seg in segments if seg.type == "action" and isinstance(seg.content, dict)]
                is_read_only_action = getattr(self.dispatcher, "_is_read_only_action", None)
                if not callable(is_read_only_action):
                    def is_read_only_action(cmd):
                        cmd_type = cmd.get("type") or cmd.get("action") or "unknown"
                        return cmd_type in {
                            "read_file",
                            "read_file_skeleton",
                            "search_content",
                            "search_files",
                            "list_directory",
                            "find_files",
                            "git_diff",
                        }
                single_readonly_step = (
                    len(action_commands) == 1
                    and is_read_only_action(action_commands[0])
                )
                if single_readonly_step:
                    consecutive_single_readonly_steps += 1
                else:
                    consecutive_single_readonly_steps = 0
                
                # 5. Оновлення історії
                # Асистент "пам'ятає" свої дії (але create_file може бути стиснутий)
                recon_msg = self.parser.reconstruct(processed_segs)
                if recon_msg:
                    self.history.add_message("assistant", recon_msg)
                
                # Результати системи
                if sys_results:
                    if self.agent.log:
                        self.agent.log.debug(f"System results count={len(sys_results)} should_stop={should_stop}")
                    for res in sys_results:
                        self.history.add_message("system", res)
                    
                    if should_stop:
                        stop_info = getattr(self.state, "pending_loop_stop_info", None)
                        if stop_info and stop_info.get("reason") in {"repeating_failure", "repeating_no_progress"}:
                            decision = await self.ui.confirm_loop_recovery(
                                "Detected repeated no-progress failures. Choose next step."
                            )
                            if decision == "retry_recovery":
                                if sm is not None:
                                    sm.on_user_recovery_choice(decision)
                                self.state.set_retry_budgets(
                                    self.config.RECOVERABLE_ERROR_RETRY_BUDGET,
                                    self.config.CRITICAL_ERROR_RETRY_BUDGET,
                                )
                                self.state.pending_loop_stop_info = None
                                recovery_actions = stop_info.get("next_actions") or []
                                if recovery_actions:
                                    current_query = (
                                        "SYSTEM: Retry with recovery strategy.\n"
                                        f"Preferred actions: {', '.join(recovery_actions)}.\n"
                                        "Do not repeat the previous action with the same arguments."
                                    )
                                else:
                                    current_query = (
                                        "SYSTEM: Retry with a different strategy and different arguments.\n"
                                        "Do not repeat the previous action call."
                                    )
                                continue
                            if decision == "open_search":
                                if sm is not None:
                                    sm.on_user_recovery_choice(decision)
                                self.state.set_retry_budgets(
                                    self.config.RECOVERABLE_ERROR_RETRY_BUDGET,
                                    self.config.CRITICAL_ERROR_RETRY_BUDGET,
                                )
                                self.state.pending_loop_stop_info = None
                                error_details = (
                                    "code="
                                    f"{self.state.last_error_code or 'UNSPECIFIED'}, "
                                    f"msg={self.state.last_error_message or ''}"
                                )
                                current_query = (
                                    "SYSTEM: Use a file discovery recovery step now.\n"
                                    "Call list_directory or search_files before any write operation.\n"
                                    f"Last error: {error_details}"
                                )
                                continue
                        if stop_info and stop_info.get("reason") in {
                            "cross_target_read_without_reason",
                            "recover_repeated_fingerprint",
                            "policy_denied",
                            "malformed_read_file_payload",
                        }:
                            if stop_info.get("reason") == "malformed_read_file_payload":
                                malformed_read_file_retries += 1
                                if malformed_read_file_retries > 1:
                                    await self.ui.print_error(
                                        "Execution stopped: malformed read_file payload repeated."
                                    )
                                    active_loop = False
                                    continue
                                current_query = (
                                    "SYSTEM: Your last read_file call used invalid payload.\n"
                                    "Return EXACTLY ONE valid read_file action now.\n"
                                    "Required format:\n"
                                    '<action type="read_file">{"path":"go_examples/target.go"}</action>\n'
                                    "Do not nest JSON under `command`."
                                )
                                should_stop = False
                                self.state.pending_loop_stop_info = None
                                continue

                            required = stop_info.get("next_actions") or []
                            required_hint = (
                                f"Required next actions: {', '.join(required)}.\n" if required else ""
                            )
                            current_query = (
                                "SYSTEM: Previous action violated orchestration policy.\n"
                                f"{required_hint}"
                                "Choose a different strategy and return EXACTLY ONE valid <action>."
                            )
                            should_stop = False
                            self.state.pending_loop_stop_info = None
                            continue

                        if stop_info and stop_info.get("recoverable"):
                            current_query = self._build_typed_stop_recovery_prompt(stop_info)
                            should_stop = False
                            self.state.pending_loop_stop_info = None
                            continue
                        await self.ui.print_system(
                            "Execution stopped by control policy (for example, denied action)."
                        )
                        active_loop = False
                    else:
                        if sm is not None:
                            sm_decision = sm.decide()
                            if sm_decision.decision.name == "MODEL_DIAGNOSTIC":
                                current_query = sm_decision.prompt
                                continue
                            if sm_decision.decision.name == "USER_HANDOFF":
                                decision = await self.ui.confirm_loop_recovery(
                                    "Detected repeated read-only stagnation. Choose next step."
                                )
                                if decision == "retry_recovery":
                                    sm.on_user_recovery_choice(decision)
                                    current_query = sm.build_diagnostic_prompt()
                                    continue
                                if decision == "continue_diagnosis":
                                    sm.on_user_recovery_choice(decision)
                                    current_query = sm.build_diagnostic_prompt()
                                    continue
                                if decision == "open_search":
                                    sm.on_user_recovery_choice(decision)
                                    current_query = (
                                        "SYSTEM: Switch strategy.\n"
                                        "Do not call read_file with the same path/arguments.\n"
                                        "Use search_content or edit_file with exact targeted arguments."
                                    )
                                    continue
                                if decision == "pin_target_edit":
                                    sm.on_user_recovery_choice(decision)
                                    current_query = sm.build_pin_target_prompt()
                                    continue
                                await self.ui.print_system("Execution stopped by user after stagnation warning.")
                                active_loop = False
                                continue
                        # Продовжуємо цикл з результатами
                        if consecutive_single_readonly_steps >= 3:
                            current_query = (
                                "SYSTEM: You are executing single read-only actions repeatedly.\n"
                                "For this multi-file investigation, return a compact batch of 3-5 read-only <action> blocks now.\n"
                                "Prioritize distinct files/targets; avoid repeating the same file in this batch.\n"
                                "After batching, move to a deterministic edit/write step."
                            )
                        else:
                            current_query = "\n---\n".join(sys_results)
                else:
                    await self.ui.print_system("Execution finished: no further actions returned by the model.")
                    active_loop = False # Немає дій = кінець розмови

                if self.agent.log:
                    elapsed = loop.time() - session_started_at
                    self.agent.log.info(
                        "Health.iteration "
                        f"step={consecutive_calls} "
                        f"elapsed_sec={elapsed:.2f} "
                        f"history_tokens={self.history.current_token_count}/{self.history.max_tokens} "
                        f"actions_in_step={action_count} "
                        f"batch_actions_executed={getattr(self.state, 'last_batch_actions_executed', 0)}/"
                        f"{getattr(self.state, 'last_batch_actions_total', 0)} "
                        f"same_action_streak={getattr(self.state, 'consecutive_same_action_count', 0)} "
                        f"confirmations={self.state.confirmation_count} "
                        f"session_tokens={self.state.session_tokens}"
                    )
            
            # 6. Summarization
            try:
                await self.history.check_and_summarize(self.ui, self.state)
            except Exception as e:
                if self.agent.log: self.agent.log.warning(f"Summarization error: {e}")
        except asyncio.CancelledError:
            if self.agent.log:
                self.agent.log.info("Orchestrator interrupted by user.")
                
        finally:
            if self.agent.log:
                total_elapsed = loop.time() - session_started_at
                self.agent.log.info(
                    "Health.summary "
                    f"elapsed_sec={total_elapsed:.2f} "
                    f"history_tokens={self.history.current_token_count}/{self.history.max_tokens} "
                    f"confirmations={self.state.confirmation_count} "
                    f"session_tokens={self.state.session_tokens}"
                )
                self.agent.log.info("Orchestrator.finish")
            self.state.current_task = None
            await self.ui.stop_loading()
