"""Оркестратор основного циклу."""

import asyncio
import json
import re
from modules.defaults import DEFAULT_SYSTEM_PROMPT

class Orchestrator:

    _READ_ONLY_TOOLS = {
        "read_file", "read_file_skeleton", "search_content", "search_files",
        "list_directory", "find_files", "git_diff", "run_shell"
    }

    def _build_system_message(self, tools_prompt: str, ctx_prompt: str) -> str:
        prompt = DEFAULT_SYSTEM_PROMPT.replace("__TOOLS_DESCRIPTION__", tools_prompt)
        return f"{prompt}\n\n{ctx_prompt}"

    def _is_rootish_path(self, path: object) -> bool:
        return isinstance(path, str) and path.strip() in {"", ".", "./", "/"}

    def _is_read_only_shell(self, command: str) -> bool:
        if not isinstance(command, str):
            return False
        lowered = command.strip().lower()
        if not lowered:
            return False
        if any(tok in lowered for tok in (">", "| tee", ">>", "sed -i", "perl -i", "mkdir ", "rm ", "mv ", "cp ", "touch ")):
            return False
        bins = ("find ", "rg ", "grep ", "ls ", "cat ", "head ", "tail ", "wc ", "stat ", "file ")
        return lowered.startswith(bins)

    def _user_task_requires_intent(self, user_input: str) -> bool:
        text = (user_input or "").lower()
        keywords = (
            "знайти", "з’ясувати", "з'ясувати", "встановити", "порівняти", "перевірити",
            "класифікувати", "дослідити", "структур", "залежност", "точк", "entrypoint",
            "використання файлів", "file usage", "dependencies", "structure", "verify",
            "classify", "investigate", "find", "determine", "establish", "compare",
        )
        cleanup = ("cleanup", "stale", "obsolete", "delete", "remove", "застар", "видалити", "прибрати")
        return any(k in text for k in keywords) or any(k in text for k in cleanup)

    def _action_requires_intent(self, command: dict, state, *, batch_size: int, current_user_input: str) -> tuple[bool, str]:
        cmd_type = command.get("type") or command.get("action") or "unknown"
        path = command.get("path")
        active_intent = getattr(state, "active_intent", None)

        # Hard requirement set by defect detector still wins.
        if getattr(state, "intent_required_until_activated", False):
            return True, getattr(state, "intent_required_reason", "intent_required")

        # If a formal intent is already active and this action is allowed by that intent,
        # do NOT ask for another intent again. This is the core anti-loop fix.
        if active_intent is not None:
            allowed = set(getattr(active_intent, "allowed_actions", []) or [])
            if cmd_type in allowed:
                return False, ""

        # No active intent yet: these are the situations where we require one.
        if cmd_type in self._READ_ONLY_TOOLS and self._user_task_requires_intent(current_user_input):
            return True, "investigation_task_requires_formal_intent"

        if cmd_type in self._READ_ONLY_TOOLS:
            if batch_size > 2:
                return True, "read_only_multi_step_requires_intent"
            if batch_size > 1:
                return True, "read_only_batch_requires_intent"
            if getattr(state, "readonly_steps_this_turn", 0) > 0:
                return True, "not_first_read_only_step_requires_intent"

        if cmd_type == "list_directory" and self._is_rootish_path(path):
            return True, "broad_root_listing_requires_intent"
        if cmd_type == "search_content" and self._is_rootish_path(path):
            return True, "broad_search_content_requires_intent"
        if cmd_type == "search_files" and self._is_rootish_path(path):
            return True, "broad_search_files_requires_intent"
        if cmd_type == "run_shell" and self._is_read_only_shell(command.get("command", "")):
            cmd = str(command.get("command") or "").lower()
            if any(tok in cmd for tok in ("find .", "rg ", "grep -r", "grep -rn", "grep -r ", "grep -R")):
                return True, "broad_shell_search_requires_intent"

        # Failure context does not require a brand new intent if the current one can continue.
        if getattr(state, "has_retry_context", None) and state.has_retry_context():
            if active_intent is None:
                return True, "retry_or_continuation_after_failure"
            if not getattr(state, "can_continue_current_intent_after_failure", lambda: False)():
                return True, "retry_or_continuation_after_failure"

        return False, ""

    _INTENT_TAG_RE = re.compile(r"<intent>(.*?)</intent>", re.IGNORECASE | re.DOTALL)

    def _extract_intent_update_and_strip(self, response_text: str) -> tuple[str, dict | None, str | None]:
        if not isinstance(response_text, str) or not response_text:
            return response_text, None, None
        matches = list(self._INTENT_TAG_RE.finditer(response_text))
        if not matches:
            return response_text, None, None
        last_block = matches[-1].group(1).strip()
        clean_text = self._INTENT_TAG_RE.sub("", response_text).strip()
        if not last_block:
            return clean_text, None, "empty_intent_block"
        try:
            payload = json.loads(last_block)
        except json.JSONDecodeError:
            return clean_text, None, "invalid_intent_json"
        return clean_text, payload, None

    def _build_intent_required_prompt(self, reason: str, allowed_actions: list[str] | None = None) -> str:
        next_hint = ""
        if allowed_actions:
            next_hint = f"\nAllowed actions for the next intent: {', '.join(allowed_actions)}."
        return (
            "SYSTEM: A formal intent contract is required before further tool use.\n"
            f"Reason: {reason}.{next_hint}\n"
            "Return EXACTLY ONE <intent> JSON block first.\n"
            "Optional schema fields:\n"
            "- intent_id\n"
            "- intent_type\n"
            "- goal\n"
            "- allowed_actions\n"
            "- safe_steps_limit\n"
            "- retry_limit\n"
            "- mode\n"
            "If you also need an action now, place the <intent> block before the action."
        )

    async def _handle_defect_detector_stop(self, stop_info: dict | None) -> tuple[bool, str | None]:
        stop_info = stop_info or {}
        reason = str(stop_info.get("reason") or "")
        reason_map = {
            "defect_repeated_action_cycle": "Defect detector: модель повторює 3 кроки в циклі. Продовжити?",
            "defect_same_action_repeat": "Defect detector: модель кілька разів повторює одну й ту саму дію. Продовжити?",
            "intent_step_limit_exceeded": "Defect detector: агент перевищив safe_steps_limit поточного intent. Продовжити?",
            "intent_retry_limit_exceeded": "Defect detector: агент перевищив retry_limit поточного intent. Продовжити?",
            "intent_action_not_allowed": "Defect detector: модель намагається виконати дію поза allowed_actions поточного intent. Продовжити?",
        }
        message = reason_map.get(reason)
        if not message:
            return False, None
        decision = await self.ui.confirm_continue(message)
        if decision in (False, "stop", None):
            await self.ui.print_system("Execution stopped by defect detector.")
            return True, None
        self.state.add_confirmation(1)
        if bool(getattr(self.config, "INTENT_REQUIRE_ON_DEFECT", True)):
            self.state.require_intent(reason)
            return True, self._build_intent_required_prompt(reason, stop_info.get("next_actions") or [])
        return True, self._build_typed_stop_recovery_prompt(stop_info)

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
        

    def _inspection_can_finish_with_text(self, sm, stop_info: dict | None) -> bool:
        if sm is None:
            return False
        task_kind = getattr(sm, "task_kind", None)
        task_kind_value = getattr(task_kind, "value", str(task_kind))
        if task_kind_value != "INSPECTION":
            return False
        reason = str((stop_info or {}).get("reason") or "")
        return reason in {
            "broad_recon_budget_exhausted",
            "observe_budget_exhausted",
            "inspection_task_write_blocked",
            "list_directory_budget_exhausted",
            "directory_descent_budget_exhausted",
            "root_listing_budget_exhausted",
            "action_not_allowed_in_phase",
        }

    def _build_plain_text_completion_prompt(self, sm, stop_info: dict | None) -> str:
        task_kind = getattr(sm, "task_kind", None)
        kind = getattr(task_kind, "value", str(task_kind or "UNKNOWN"))
        phase = getattr(sm, "phase", None)
        phase_value = getattr(phase, "value", str(phase or "UNKNOWN"))
        reason = str((stop_info or {}).get("reason") or "")
        target = getattr(sm, "target_file", None) or "<unknown>"
        route_hint = ""
        if hasattr(sm, "_inspection_route_hint"):
            try:
                route_hint = sm._inspection_route_hint() or ""
            except Exception:
                route_hint = ""
        parts = [
            "SYSTEM: Stop tool use now.",
            f"Task kind: {kind}. Current phase: {phase_value}.",
            f"Recovery reason: {reason}.",
            f"Current target: {target}.",
            "Return a concise plain-text answer in the user's language using only the evidence already gathered.",
            "Do not output any <action> block.",
            "Do not ask to inspect more files.",
            "Answer the user's question directly and, if relevant, give one concrete next step.",
        ]
        if route_hint:
            parts.append(route_hint)
        return "\n".join(parts)

    async def process(self, user_input):
        """Головний цикл: Think -> Act -> Loop."""
        if self.agent.log:
            self.agent.log.info("Orchestrator.start")
            self.agent.log.debug(f"User input: {user_input[:300]}")
        
        # 1. Підготовка контексту
        tools_prompt = self.agent.tool_manager.get_tools_prompt()
        ctx_prompt = self.agent.context_manager.get_context_prompt()
        system_msg = self._build_system_message(tools_prompt, ctx_prompt)

        self.history.add_message("user", user_input)
        sm = getattr(self.state, "state_machine", None)
        if sm is not None:
            sm.start_turn(user_input)
            sm.intent_runtime = getattr(self.state, "intent_runtime", None)
            if self.agent.log:
                self.agent.log.debug(f"Task contract: kind={getattr(sm, 'task_kind', None)} phase={getattr(sm, 'phase', None)}")
        if hasattr(self.state, 'clear_intent_requirement'):
            self.state.clear_intent_requirement()
        if hasattr(self.state, 'start_turn_runtime'):
            self.state.start_turn_runtime()
        
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
                
                response, intent_payload, intent_error = self._extract_intent_update_and_strip(response)
                if intent_error and getattr(self.state, "intent_required_until_activated", False):
                    current_query = self._build_intent_required_prompt(intent_error)
                    continue
                if intent_payload is not None:
                    ok, intent_msg = self.state.apply_intent_contract(intent_payload, self.config)
                    warning = ""
                    if getattr(self.state, "intent_runtime", None) is not None:
                        warning = getattr(self.state.intent_runtime, "last_apply_warning", "")
                    if self.agent.log:
                        self.agent.log.debug(
                            f"Intent.apply ok={ok} msg={intent_msg} warning={warning} "
                            f"summary={getattr(self.state, 'active_intent_summary', lambda: '')()}"
                        )
                    if not ok:
                        stop_info = getattr(self.state, "last_defect_info", None) or {
                            "reason": intent_msg,
                            "recoverable": True,
                            "next_actions": (getattr(getattr(self.state, 'active_intent', None), 'allowed_actions', None) or []),
                        }
                        handled, next_query = await self._handle_defect_detector_stop(stop_info)
                        if handled:
                            if next_query:
                                current_query = next_query
                                self.state.pending_loop_stop_info = None
                                continue
                            active_loop = False
                            continue
                        current_query = self._build_intent_required_prompt(intent_msg)
                        continue

                    if not response.strip():
                        if hasattr(self.state, "note_intent_only_response"):
                            self.state.note_intent_only_response()
                        current_query = (
                            "SYSTEM: Intent activated. Now return the next valid step. "
                            "If tool use is needed, return the next <action>. "
                            "Do not repeat the same intent unless you are explicitly retrying or replacing it."
                        )
                        continue

                if getattr(self.state, "intent_required_until_activated", False) and "<action" in response.lower():
                    current_query = self._build_intent_required_prompt(
                        getattr(self.state, "intent_required_reason", "intent_required")
                    )
                    continue

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

                action_segments_only = [seg for seg in segments if seg.type == "action" and isinstance(seg.content, dict)]
                if action_segments_only and intent_payload is None:
                    intent_required = False
                    intent_reason = ""
                    for seg in action_segments_only:
                        required, reason = self._action_requires_intent(
                            seg.content,
                            self.state,
                            batch_size=len(action_segments_only),
                            current_user_input=user_input,
                        )
                        if required:
                            intent_required = True
                            intent_reason = reason
                            break
                    if intent_required:
                        current_query = self._build_intent_required_prompt(
                            intent_reason,
                            ["read_file", "read_file_skeleton", "search_content", "search_files", "list_directory", "find_files", "git_diff", "run_shell"],
                        )
                        continue

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
                if sm is not None:
                    sm.intent_runtime = getattr(self.state, "intent_runtime", None)
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
                        handled_defect, next_query = await self._handle_defect_detector_stop(stop_info)
                        if handled_defect:
                            if next_query:
                                current_query = next_query
                                should_stop = False
                                self.state.pending_loop_stop_info = None
                                continue
                            active_loop = False
                            continue
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

                        if stop_info and self._inspection_can_finish_with_text(sm, stop_info):
                            current_query = self._build_plain_text_completion_prompt(sm, stop_info)
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