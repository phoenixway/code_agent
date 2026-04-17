"""Оркестратор основного циклу."""

from __future__ import annotations

import asyncio
from dataclasses import dataclass

from .lifecycle import TurnLifecycle
from .parsing import IntentResponseParser
from .policy import IntentGuard
from .prompting import OrchestratorPromptBuilder
from .recovery import RecoveryCoordinator


@dataclass
class LoopContext:
    user_input: str
    tools_prompt: str
    ctx_prompt: str
    state_machine: object
    current_query: str
    consecutive_calls: int
    malformed_action_retries: int
    audit_marker_retries: int
    active_loop: bool
    session_started_at: float


@dataclass
class ModelStepResult:
    response: str
    intent_payload: dict | None
    intent_error: str | None


class Orchestrator:
    def __init__(self, agent):
        self.agent = agent
        self.ui = agent.ui
        self.state = agent.state
        self.history = agent.history
        self.model = agent.model_client
        self.dispatcher = agent.action_dispatcher
        self.parser = agent.parser
        self.config = agent.config
        self.memory_board_store = getattr(agent, "memory_board_store", None)
        self.memory_board_engine = getattr(agent, "memory_board_engine", None)

        self.intent_guard = IntentGuard()
        self.intent_response_parser = IntentResponseParser()
        self.prompt_builder = OrchestratorPromptBuilder(agent)
        self.recovery = RecoveryCoordinator(agent, self.prompt_builder)
        self.turn_lifecycle = TurnLifecycle(agent)

    def _build_system_message(self, tools_prompt: str, ctx_prompt: str) -> str:
        return self.prompt_builder.build_system_message(tools_prompt, ctx_prompt)

    def _build_memory_board_protocol_prompt(self) -> str:
        return self.prompt_builder.build_memory_board_protocol_prompt()

    def _current_active_intent_id(self) -> str | None:
        return self.prompt_builder._current_active_intent_id()

    def _is_rootish_path(self, path: object) -> bool:
        return self.intent_guard._is_rootish_path(path)

    def _is_read_only_shell(self, command: str) -> bool:
        return self.intent_guard._is_read_only_shell(command)

    def _user_task_requires_intent(self, user_input: str) -> bool:
        return self.intent_guard._user_task_requires_intent(user_input)

    def _action_requires_intent(
        self,
        command: dict,
        state,
        *,
        batch_size: int,
        current_user_input: str,
    ) -> tuple[bool, str]:
        return self.intent_guard.action_requires_intent(
            command,
            state,
            batch_size=batch_size,
            current_user_input=current_user_input,
        )

    def _extract_intent_update_and_strip(self, response_text: str) -> tuple[str, dict | None, str | None]:
        return self.intent_response_parser.extract_intent_update_and_strip(response_text)

    def _build_intent_required_prompt(self, reason: str, allowed_actions: list[str] | None = None) -> str:
        return self.prompt_builder.build_intent_required_prompt(reason, allowed_actions)

    def _build_reuse_current_intent_prompt(
        self,
        reason: str,
        allowed_actions: list[str] | None = None,
        *,
        goal: str | None = None,
    ) -> str:
        return self.prompt_builder.build_reuse_current_intent_prompt(reason, allowed_actions, goal=goal)

    def _current_active_intent(self):
        return self.prompt_builder._current_active_intent()

    def _current_intent_allowed_actions(self) -> list[str]:
        return self.prompt_builder._current_intent_allowed_actions()

    def _current_intent_goal(self) -> str:
        return self.prompt_builder._current_intent_goal()

    def _current_intent_type(self) -> str:
        return self.prompt_builder._current_intent_type()

    def _render_recovery_message(self, message_key: str, default: str, *, next_hint: str = "") -> str:
        return self.prompt_builder._render_recovery_message(message_key, default, next_hint=next_hint)

    def _build_keep_current_intent_recovery_prompt(self, stop_info: dict | None) -> str:
        return self.prompt_builder.build_keep_current_intent_recovery_prompt(stop_info)

    def _build_suspect_intent_change_message(self, stop_info: dict | None) -> str:
        return self.prompt_builder.build_suspect_intent_change_message(stop_info)

    async def _choose_suspect_intent_change_action(self, stop_info: dict | None) -> str:
        return await self.recovery.choose_suspect_intent_change_action(stop_info)

    def _build_intent_overrun_message(self, stop_info: dict | None) -> str:
        return self.prompt_builder.build_intent_overrun_message(stop_info)

    async def _choose_intent_overrun_action(self, stop_info: dict | None) -> str | None:
        return await self.recovery.choose_intent_overrun_action(stop_info)

    async def _handle_defect_detector_stop(self, stop_info: dict | None) -> tuple[bool, str | None]:
        return await self.recovery.handle_defect_detector_stop(stop_info)

    def _build_action_format_recovery_prompt(
        self,
        header: str,
        *,
        forbid_audit_markers: bool = False,
        state_changing_only: bool = False,
        single_readonly_action_only: bool = False,
    ) -> str:
        return self.prompt_builder.build_action_format_recovery_prompt(
            header,
            forbid_audit_markers=forbid_audit_markers,
            state_changing_only=state_changing_only,
            single_readonly_action_only=single_readonly_action_only,
        )

    def _extract_visible_non_action_text(self, response: str) -> str:
        return self.intent_response_parser.extract_visible_non_action_text(response)

    def _needs_action_or_answer_recovery(self, response: str, segments) -> bool:
        return self.intent_response_parser.needs_action_or_answer_recovery(response, segments)

    def _build_missing_action_or_answer_prompt(self) -> str:
        return self.prompt_builder.build_missing_action_or_answer_prompt()

    def _is_intent_only_response(self, response: str, segments) -> bool:
        return self.intent_response_parser.is_intent_only_response(response, segments)

    def _build_intent_only_deadend_prompt(self) -> str:
        return self.prompt_builder.build_intent_only_deadend_prompt()

    def _typed_recovery_header(self, stop_info: dict | None) -> str:
        return self.prompt_builder.typed_recovery_header(stop_info)

    def _build_typed_stop_recovery_prompt(self, stop_info: dict | None) -> str:
        return self.prompt_builder.build_typed_stop_recovery_prompt(stop_info)

    def _inspection_can_finish_with_text(self, sm, stop_info: dict | None) -> bool:
        return self.recovery.inspection_can_finish_with_text(sm, stop_info)

    def _build_plain_text_completion_prompt(self, sm, stop_info: dict | None) -> str:
        return self.prompt_builder.build_plain_text_completion_prompt(sm, stop_info)

    def _build_orchestrated_recovery_prompt(self, stop_info: dict | None) -> str:
        return self.prompt_builder.build_orchestrated_recovery_prompt(stop_info)

    def _build_intent_transition_rejected_prompt(self, reason, allowed_actions=None, goal=""):
        return self.prompt_builder.build_intent_transition_rejected_prompt(reason, allowed_actions, goal=goal)

    def _build_intent_completed_prompt(self) -> str:
        return self.prompt_builder.build_intent_completed_prompt()

    def _start_turn(self, user_input: str):
        return self.turn_lifecycle.start_turn(user_input)

    def _create_loop_context(self, user_input: str) -> LoopContext:
        loop = asyncio.get_running_loop()
        return LoopContext(
            user_input=user_input,
            tools_prompt=self.agent.tool_manager.get_tools_prompt(),
            ctx_prompt=self.agent.context_manager.get_context_prompt(),
            state_machine=self._start_turn(user_input),
            current_query=user_input,
            consecutive_calls=0,
            malformed_action_retries=0,
            audit_marker_retries=0,
            active_loop=True,
            session_started_at=loop.time(),
        )

    async def _run_pre_step(self, ctx: LoopContext) -> bool:
        try:
            await self.history.check_and_summarize(self.ui, self.state)
        except Exception as exc:
            if self.agent.log:
                self.agent.log.warning(f"Pre-step summarization check failed: {exc}")

        if self.agent.log:
            self.agent.log.debug(
                f"Loop iteration={ctx.consecutive_calls + 1} "
                f"history_tokens={self.history.current_token_count}/{self.history.max_tokens}"
            )

        loop = asyncio.get_running_loop()
        if loop.time() - ctx.session_started_at > self.config.MAX_SESSION_SECONDS:
            await self.ui.print_error(
                f"Session time limit reached ({self.config.MAX_SESSION_SECONDS}s). Stopping."
            )
            ctx.active_loop = False
            return False

        ctx.consecutive_calls += 1
        if ctx.consecutive_calls > self.config.MAX_CONSECUTIVE_CALLS:
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
                    ctx.active_loop = False
                    return False
                if decision == "continue_silent":
                    self.state.suppress_step_limit_warning = True

        await self.ui.start_thinking()
        return True

    async def _run_model_step(self, ctx: LoopContext) -> ModelStepResult | None:
        system_msg = self._build_system_message(ctx.tools_prompt, ctx.ctx_prompt)

        self.state.current_task = asyncio.create_task(
            self.model.get_streaming_response(
                ctx.current_query,
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
            ctx.active_loop = False
            return None

        response, intent_payload, intent_error = self._extract_intent_update_and_strip(response)
        if self.agent.log:
            self.agent.log.debug(
                "Orchestrator.step.response_received raw_chars=%s has_intent_payload=%s intent_error=%s",
                len(response or ""),
                intent_payload is not None,
                intent_error or "",
            )
            self.agent.log.debug("Orchestrator.step.response.after_initial_extract\n%s", response)
        return ModelStepResult(
            response=response,
            intent_payload=intent_payload,
            intent_error=intent_error,
        )

    async def _handle_intent_payload(self, ctx: LoopContext, step: ModelStepResult) -> bool:
        if step.intent_error and getattr(self.state, "intent_required_until_activated", False):
            ctx.current_query = self._build_intent_required_prompt(step.intent_error)
            return True

        if step.intent_payload is None:
            return False

        ok, intent_msg = self.state.apply_intent_contract(step.intent_payload, self.config)
        warning = ""
        if getattr(self.state, "intent_runtime", None) is not None:
            warning = getattr(self.state.intent_runtime, "last_apply_warning", "")
        if self.agent.log:
            self.agent.log.debug(
                f"Intent.apply ok={ok} msg={intent_msg} warning={warning} "
                f"summary={getattr(self.state, 'active_intent_summary', lambda: '')()}"
            )
            self.agent.log.debug("Intent.apply.payload=%s", step.intent_payload)
        if not ok:
            runtime = getattr(self.state, "intent_runtime", None)
            runtime_info = getattr(runtime, "last_transition_info", {}) if runtime is not None else {}
            stop_info = getattr(self.state, "last_defect_info", None) or {
                "reason": intent_msg,
                "recoverable": True,
                "next_actions": (
                    getattr(getattr(self.state, "active_intent", None), "allowed_actions", None) or []
                ),
            }
            if isinstance(runtime_info, dict) and runtime_info.get("transition") == "policy_rejected":
                stop_info = {
                    **stop_info,
                    "reason": runtime_info.get("reason", intent_msg),
                    "recoverable": True,
                    "error_code": runtime_info.get("error_code", ""),
                    "message_key": runtime_info.get("message_key", ""),
                    "policy_metadata": runtime_info.get("metadata", {}) or {},
                }
            handled, next_query = await self._handle_defect_detector_stop(stop_info)
            if handled:
                if next_query:
                    ctx.current_query = next_query
                    self.state.pending_loop_stop_info = None
                else:
                    ctx.active_loop = False
                return True
            ctx.current_query = self._build_intent_transition_rejected_prompt(
                intent_msg,
                getattr(getattr(self.state, "active_intent", None), "allowed_actions", None) or [],
                goal=getattr(getattr(self.state, "active_intent", None), "goal", ""),
            )
            return True

        if ctx.state_machine is not None:
            ctx.state_machine.intent_runtime = getattr(self.state, "intent_runtime", None)

        if not step.response.strip():
            if hasattr(self.state, "note_intent_only_response"):
                self.state.note_intent_only_response()
            if intent_msg == "intent_completed":
                ctx.current_query = self._build_intent_completed_prompt()
            else:
                ctx.current_query = (
                    "SYSTEM: Intent accepted. Now return the next valid step. "
                    "If tool use is needed, return the next <action>. "
                    "Do not repeat the same intent unless you are explicitly retrying, replacing, or formally completing it."
                )
            return True

        return False

    async def _apply_memory_board_response(self, ctx: LoopContext, response: str) -> tuple[str, bool]:
        board_result = None
        if self.memory_board_engine is not None:
            try:
                board_result = self.memory_board_engine.apply_response_text(
                    response,
                    active_intent_id=self._current_active_intent_id(),
                    current_user_input=ctx.user_input,
                    source="model",
                )
                if board_result.parsed_count:
                    response = board_result.clean_text
                    if self.agent.log:
                        self.agent.log.debug(
                            "MemoryBoard.apply parsed=%s accepted=%s rejected=%s",
                            board_result.parsed_count,
                            board_result.accepted_count,
                            board_result.rejected_count,
                        )
            except Exception as exc:
                if self.agent.log:
                    self.agent.log.warning(f"Memory board apply failed: {exc}")

        if board_result is not None and board_result.parsed_count > 0 and not str(response or "").strip():
            ctx.current_query = (
                "SYSTEM: Memory updates were recorded. Now continue the current task. "
                "Return the next valid <action> if tool use is needed, or answer plainly if enough is already known."
            )
            return response, True

        if self.agent.log and board_result is not None:
            self.agent.log.debug(
                "Orchestrator.memory_board_processed parsed=%s accepted=%s rejected=%s clean_chars=%s",
                board_result.parsed_count,
                board_result.accepted_count,
                board_result.rejected_count,
                len(response or ""),
            )
            self.agent.log.debug("Orchestrator.step.response.after_memory_board\n%s", response)

        return response, False

    def _enforce_action_intent_requirement(self, ctx: LoopContext, segments, intent_payload: dict | None) -> bool:
        action_segments_only = [seg for seg in segments if seg.type == "action" and isinstance(seg.content, dict)]
        if not action_segments_only or intent_payload is not None:
            return False

        intent_required = False
        intent_reason = ""
        for seg in action_segments_only:
            required, reason = self._action_requires_intent(
                seg.content,
                self.state,
                batch_size=len(action_segments_only),
                current_user_input=ctx.user_input,
            )
            if required:
                intent_required = True
                intent_reason = reason
                break
        if intent_required:
            ctx.current_query = self._build_intent_required_prompt(
                intent_reason,
                [
                    "read_file",
                    "read_chunk",
                    "read_file_skeleton",
                    "search_content",
                    "search_files",
                    "list_directory",
                    "find_files",
                    "git_diff",
                    "run_shell",
                ],
            )
            return True
        return False

    async def _handle_response_recovery(self, ctx: LoopContext, response: str, segments) -> bool:
        has_action_tag = "<action" in response.lower()
        has_action_segment = any(seg.type == "action" for seg in segments)
        if has_action_tag and not has_action_segment:
            ctx.malformed_action_retries += 1
            if self.agent.log:
                self.agent.log.warning(
                    f"Malformed action response detected (retry {ctx.malformed_action_retries}/1)."
                )
            if ctx.malformed_action_retries > 1:
                await self.ui.print_error(
                    "Execution stopped: model returned malformed action format repeatedly."
                )
                ctx.active_loop = False
                return True
            ctx.current_query = (
                self._build_action_format_recovery_prompt(
                    "Your last response contained malformed <action> content."
                )
                + "\nIf the edit payload is large, prefer write_file.\n"
                "If using edit_file, keep search_text/replace_text short and exact."
            )
            self.state.set_malformed_grace(self.config.MALFORMED_ACTION_GRACE_STEPS)
            self.state.forbid_next_action_fingerprint(
                getattr(self.state, "last_completed_fingerprint", None)
            )
            return True
        ctx.malformed_action_retries = 0

        response_lower = response.lower()
        contains_audit_marker = (
            "system_tool_audit:" in response_lower
            or response_lower.strip().startswith("tool_history ")
            or "<previously_performed_action" in response_lower
        )
        if contains_audit_marker and not has_action_segment:
            ctx.audit_marker_retries += 1
            if self.agent.log:
                self.agent.log.warning(
                    f"Audit-marker echo without action detected (retry {ctx.audit_marker_retries}/1)."
                )
            if ctx.audit_marker_retries > 1:
                await self.ui.print_error(
                    "Execution stopped: model repeatedly echoed audit trail without a valid action."
                )
                ctx.active_loop = False
                return True
            ctx.current_query = self._build_action_format_recovery_prompt(
                "Your last response echoed an internal audit marker instead of a tool call.",
                forbid_audit_markers=True,
            )
            return True
        ctx.audit_marker_retries = 0

        if self._needs_action_or_answer_recovery(response, segments):
            ctx.current_query = self._build_missing_action_or_answer_prompt()
            return True

        if self._is_intent_only_response(response, segments):
            ctx.current_query = self._build_intent_only_deadend_prompt()
            return True

        return False

    async def _dispatch_segments(self, ctx: LoopContext, segments):
        if ctx.state_machine is not None:
            ctx.state_machine.intent_runtime = getattr(self.state, "intent_runtime", None)
        self.state.current_task = asyncio.create_task(
            self.dispatcher.dispatch_segments(segments, self.state)
        )
        return await self.state.current_task

    async def _handle_dispatch_outcome(
        self,
        ctx: LoopContext,
        processed_segs,
        sys_results,
        should_stop: bool,
    ) -> bool:
        recon_msg = self.parser.reconstruct(processed_segs)
        if recon_msg:
            self.history.add_message("assistant", recon_msg)

        if not sys_results:
            await self.ui.print_system("Execution finished: no further actions returned by the model.")
            ctx.active_loop = False
            return True

        if self.agent.log:
            self.agent.log.debug(f"System results count={len(sys_results)} should_stop={should_stop}")
        for res in sys_results:
            self.history.add_message("system", res)

        if should_stop:
            stop_info = getattr(self.state, "pending_loop_stop_info", None)
            decision = await self.recovery.handle_dispatch_stop(stop_info, ctx.state_machine)
            if decision.handled:
                if decision.clear_pending_stop:
                    self.state.pending_loop_stop_info = None
                if decision.next_query:
                    ctx.current_query = decision.next_query
                if decision.stop_loop:
                    ctx.active_loop = False
                return True

            await self.ui.print_system(
                "Execution stopped by control policy (for example, denied action)."
            )
            ctx.active_loop = False
            return True

        if ctx.state_machine is not None:
            sm_decision = ctx.state_machine.decide()
            if sm_decision.decision.name == "MODEL_DIAGNOSTIC":
                ctx.current_query = sm_decision.prompt
                return True
            if sm_decision.decision.name == "USER_HANDOFF":
                decision = await self.ui.confirm_loop_recovery(
                    "Detected repeated read-only stagnation. Choose next step."
                )
                if decision in {"retry_recovery", "continue_diagnosis"}:
                    if hasattr(ctx.state_machine, "on_user_recovery_choice"):
                        ctx.state_machine.on_user_recovery_choice(decision)
                    ctx.current_query = ctx.state_machine.build_diagnostic_prompt()
                    return True
                if decision == "open_search":
                    if hasattr(ctx.state_machine, "on_user_recovery_choice"):
                        ctx.state_machine.on_user_recovery_choice(decision)
                    ctx.current_query = (
                        "SYSTEM: Switch strategy.\n"
                        "Do not call read_file with the same path/arguments.\n"
                        "Use search_content, read_chunk, read_file_skeleton, or edit_file with exact targeted arguments."
                    )
                    return True
                if decision == "pin_target_edit":
                    if hasattr(ctx.state_machine, "on_user_recovery_choice"):
                        ctx.state_machine.on_user_recovery_choice(decision)
                    if hasattr(ctx.state_machine, "build_pin_target_prompt"):
                        ctx.current_query = ctx.state_machine.build_pin_target_prompt()
                        return True
                await self.ui.print_system("Execution stopped by user after stagnation warning.")
                ctx.active_loop = False
                return True

        ctx.current_query = "\n---\n".join(sys_results)
        return False

    def _log_iteration_health(self, ctx: LoopContext, action_count: int):
        if self.agent.log:
            elapsed = asyncio.get_running_loop().time() - ctx.session_started_at
            self.agent.log.info(
                "Health.iteration "
                f"step={ctx.consecutive_calls} "
                f"elapsed_sec={elapsed:.2f} "
                f"history_tokens={self.history.current_token_count}/{self.history.max_tokens} "
                f"actions_in_step={action_count} "
                f"batch_actions_executed={getattr(self.state, 'last_batch_actions_executed', 0)}/"
                f"{getattr(self.state, 'last_batch_actions_total', 0)} "
                f"same_action_streak={getattr(self.state, 'consecutive_same_action_count', 0)} "
                f"confirmations={self.state.confirmation_count} "
                f"session_tokens={self.state.session_tokens}"
            )

    async def process(self, user_input):
        """Головний цикл: Think -> Act -> Loop."""
        if self.agent.log:
            self.agent.log.info("Orchestrator.start")
            self.agent.log.debug(f"User input: {user_input[:300]}")

        ctx = self._create_loop_context(user_input)

        try:
            while ctx.active_loop:
                if not await self._run_pre_step(ctx):
                    break

                step = await self._run_model_step(ctx)
                if step is None:
                    break

                if await self._handle_intent_payload(ctx, step):
                    continue

                response = step.response
                if getattr(self.state, "intent_required_until_activated", False) and "<action" in response.lower():
                    ctx.current_query = self._build_intent_required_prompt(
                        getattr(self.state, "intent_required_reason", "intent_required")
                    )
                    continue

                response, consumed_by_memory_board = await self._apply_memory_board_response(ctx, response)
                if consumed_by_memory_board:
                    continue

                segments = self.parser.parse(response)
                if self.agent.log:
                    self.agent.log.debug(f"Parsed segments count={len(segments)}")
                parsed_action_count = sum(1 for seg in segments if seg.type == "action")

                if self._enforce_action_intent_requirement(ctx, segments, step.intent_payload):
                    continue

                if await self._handle_response_recovery(ctx, response, segments):
                    continue

                processed_segs, sys_results, should_stop = await self._dispatch_segments(ctx, segments)
                action_count = parsed_action_count

                await self._handle_dispatch_outcome(ctx, processed_segs, sys_results, should_stop)
                self._log_iteration_health(ctx, action_count)

            try:
                await self.history.check_and_summarize(self.ui, self.state)
            except Exception as exc:
                if self.agent.log:
                    self.agent.log.warning(f"Summarization error: {exc}")
        except asyncio.CancelledError:
            if self.agent.log:
                self.agent.log.info("Orchestrator interrupted by user.")
        finally:
            if self.agent.log:
                total_elapsed = asyncio.get_running_loop().time() - ctx.session_started_at
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
