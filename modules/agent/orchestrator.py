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
                        "SYSTEM: Your last response contained a malformed <action> block.\n"
                        "Return EXACTLY ONE valid <action> JSON block for the next step.\n"
                        "No prose outside <action>."
                    )
                    self.state.set_malformed_grace(self.config.MALFORMED_ACTION_GRACE_STEPS)
                    continue
                else:
                    malformed_action_retries = 0
                
                # 4. Виконання дій (через Dispatcher)
                processed_segs, sys_results, should_stop = await self.dispatcher.dispatch_segments(
                    segments, self.state
                )
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
                        if stop_info and stop_info.get("reason") == "repeating_failure":
                            decision = await self.ui.confirm_loop_recovery(
                                "Detected repeated no-progress failures. Choose next step."
                            )
                            if decision == "retry_recovery":
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

                        await self.ui.print_system(
                            "Execution stopped by control policy (for example, denied action)."
                        )
                        active_loop = False
                    else:
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
