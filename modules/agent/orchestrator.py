"""Оркестратор основного циклу."""

import asyncio
import re
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

    @staticmethod
    def _normalize_model_response(response: str) -> str:
        """Best-effort normalization for near-valid model outputs before parsing."""
        if not isinstance(response, str) or not response:
            return response
        text = response
        # Common case: model wraps action JSON body with ```json ... ```
        text = re.sub(
            r"(<action[^>]*>\s*)```(?:json)?\s*(.*?)\s*```\s*(</action>)",
            r"\1\2\3",
            text,
            flags=re.IGNORECASE | re.DOTALL,
        )
        return text
        
    async def process(self, user_input):
        """Головний цикл: Think -> Act -> Loop."""
        if self.agent.log:
            self.agent.log.info("Orchestrator.start")
            self.agent.log.debug(f"User input: {user_input[:300]}")
        
        # 1. Підготовка контексту
        tools_prompt = self.agent.tool_manager.get_tools_prompt()
        ctx_prompt = self.agent.context_manager.get_context_prompt()
        system_msg = f"{DEFAULT_SYSTEM_PROMPT.format(tools_description=tools_prompt)}\n\n{ctx_prompt}"
        planner = getattr(self.agent, "planner", None)
        planner_enabled = bool(planner and planner.enabled)
        if planner_enabled:
            self.state.taskboard_missing_streak = 0
            system_msg = f"{system_msg}\n\n{planner.build_protocol_instructions()}"
            planner_state_msg = f"Планувальник увімкнено (режим: {planner.mode})."
            await self.ui.print_plan(planner_state_msg)
            self.history.add_message("system", planner_state_msg)

        self.history.add_message("user", user_input)
        sm = getattr(self.state, "state_machine", None)
        if sm is not None:
            sm.start_turn(user_input)
        
        active_loop = True
        consecutive_calls = 0
        malformed_action_retries = 0
        current_query = user_input
        loop = asyncio.get_running_loop()
        session_started_at = loop.time()
        
        try:
            while active_loop:
                try:
                    # Keep context under control before next model call.
                    await self.history.check_and_summarize(self.ui)
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
                effective_query = current_query
                if planner_enabled and getattr(self.state, "task_board_enabled", False):
                    board = getattr(self.state, "task_board", None)
                    snapshot = planner.render_runtime_snapshot(board) if board else ""
                    if snapshot:
                        effective_query = f"{snapshot}\n\n{current_query}"
                
                # 2. Запит до AI
                self.state.current_task = asyncio.create_task(
                    self.model.get_streaming_response(
                        effective_query,
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

                normalized_response = self._normalize_model_response(response)
                if normalized_response != response and self.agent.log:
                    self.agent.log.debug("Normalized model response before parsing.")
                response = normalized_response

                if planner_enabled:
                    response, board_update, board_error = planner.extract_update_and_strip(response)
                    if board_error:
                        planner_err = "Оновлення плану пропущено: формат відповіді некоректний."
                        await self.ui.print_plan(planner_err)
                        self.history.add_message("system", planner_err)
                        if self.agent.log:
                            self.agent.log.warning(f"Planner update ignored: {board_error}")
                    if board_update:
                        self.state.taskboard_missing_streak = 0
                        _applied, planner_msg = planner.apply_update(self.state, board_update)
                        await self.ui.print_plan(planner_msg)
                        self.history.add_message("system", planner_msg)
                        board_text = planner.render_board_for_chat(getattr(self.state, "task_board", None))
                        await self.ui.print_plan(board_text)
                        self.history.add_message("system", board_text)
                        if not response.strip():
                            current_query = (
                                "SYSTEM: Taskboard accepted. Return EXACTLY ONE valid <action> for the current active step."
                            )
                            continue
                    elif planner.mode == "always":
                        self.state.taskboard_missing_streak = int(
                            getattr(self.state, "taskboard_missing_streak", 0)
                        ) + 1
                        miss_limit = max(
                            1, int(getattr(self.config, "PLANNER_ALWAYS_MISSING_RETRY_LIMIT", 2))
                        )
                        planner_miss_msg = (
                            "План у відповіді відсутній, повторюю запит у строгому форматі "
                            f"({self.state.taskboard_missing_streak}/{miss_limit})."
                        )
                        await self.ui.print_plan(planner_miss_msg)
                        self.history.add_message("system", planner_miss_msg)
                        if self.state.taskboard_missing_streak >= miss_limit:
                            await self.ui.print_error(
                                "Execution stopped: planner_mode=always but model repeatedly omitted <taskboard>."
                            )
                            break
                        current_query = (
                            "SYSTEM: planner_mode=always is enforced.\n"
                            "Return EXACTLY one <taskboard> JSON block and EXACTLY one valid <action>.\n"
                            "No prose outside <think>, <taskboard>, and <action>."
                        )
                        continue
                    
                # 3. Парсинг
                segments = self.parser.parse(response)
                if self.agent.log:
                    self.agent.log.debug(f"Parsed segments count={len(segments)}")

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
                    required_tags = "<think>,<action>"
                    response_template = (
                        "<think>Short reasoning.</think>\n"
                        "<action type=\"TOOL_NAME\">{\"before_execution\":\"...\",\"during_execution\":\"...\","
                        "\"after_execution\":\"...\", \"...tool_args...\"}</action>"
                    )
                    if planner_enabled and planner.mode == "always":
                        required_tags = "<think>,<taskboard>,<action>"
                        response_template = (
                            "<think>Short reasoning.</think>\n"
                            "<taskboard>{\"version\":1,\"goal\":\"...\",\"planner_enabled\":true,"
                            "\"active_step_id\":\"s1\",\"steps\":[{\"id\":\"s1\",\"title\":\"...\","
                            "\"status\":\"in_progress\",\"notes\":\"\"}]}</taskboard>\n"
                            "<action type=\"TOOL_NAME\">{\"before_execution\":\"...\",\"during_execution\":\"...\","
                            "\"after_execution\":\"...\", \"...tool_args...\"}</action>"
                        )
                    current_query = (
                        "SYSTEM: Your last response contained malformed action format.\n"
                        "[FORMAT_CONTRACT]\n"
                        f"required_tags={required_tags}\n"
                        "required_action_fields=type,before_execution,during_execution,after_execution,tool_arguments\n"
                        "forbidden_patterns=markdown_fences_inside_action,nested_json_in_command_for_file_tools\n"
                        "instruction=Return exactly one valid step matching the template below.\n"
                        f"response_template=\n{response_template}"
                    )
                    self.state.set_malformed_grace(self.config.MALFORMED_ACTION_GRACE_STEPS)
                    # Prevent immediate repetition only for previous state-changing action.
                    last_fp = getattr(self.state, "last_completed_fingerprint", None)
                    last_type = getattr(self.state, "last_completed_action_type", None)
                    if last_fp and last_type in self.config.STATE_CHANGING_OPS:
                        self.state.forbid_next_action_fingerprint(last_fp)
                    continue
                else:
                    malformed_action_retries = 0
                
                # 4. Виконання дій (через Dispatcher)
                self.state.current_task = asyncio.create_task(
                    self.dispatcher.dispatch_segments(segments, self.state)
                )
                processed_segs, sys_results, should_stop = await self.state.current_task
                action_count = sum(1 for seg in processed_segs if seg.type == "action")
                
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
                        }:
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
                        f"same_action_streak={getattr(self.state, 'consecutive_same_action_count', 0)} "
                        f"confirmations={self.state.confirmation_count} "
                        f"session_tokens={self.state.session_tokens}"
                    )
            
            # 6. Summarization
            try:
                await self.history.check_and_summarize(self.ui)
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
