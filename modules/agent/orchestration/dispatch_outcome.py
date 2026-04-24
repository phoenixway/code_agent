"""Post-dispatch outcome handling for orchestrator tool execution."""

from __future__ import annotations

import re

from .decision_models import DispatchHandlingDecision
from .stage_logging import OrchestrationStageLogger
from .visible_text import contains_control_markup, extract_visible_text_for_user
from ..technical_interruptions import detect_technical_interruption


class DispatchOutcomeHandler:
    THINK_TAG_RE = re.compile(r"<think(?:\s+[^>]*)?>.*?</think>", re.IGNORECASE | re.DOTALL)
    INTENT_TAG_RE = re.compile(r"<intent(?:\s+[^>]*)?>.*?</intent>", re.IGNORECASE | re.DOTALL)
    ACTION_TAG_RE = re.compile(r"<action(?:\s+[^>]*)?>.*?</action>", re.IGNORECASE | re.DOTALL)
    MEMORY_TAG_RE = re.compile(
        r"</?(fact|finding|decision|preference|progress)\b[^>]*>",
        re.IGNORECASE,
    )
    PREVIOUSLY_PERFORMED_ACTION_RE = re.compile(r"<previously_performed_action[^>]*/>", re.IGNORECASE)
    SYSTEM_AUDIT_LINE_RE = re.compile(r"(?im)^\s*system_tool_audit:.*?$")
    TOOL_HISTORY_LINE_RE = re.compile(r"(?im)^\s*tool_history\s+\{.*?$")
    SYSTEM_RESULT_LINE_RE = re.compile(
        r"(?im)^\s*SYSTEM\s+RESULT(?:\s*\([^)]*\))?(?:\s+for\s+`?[^`:\n]+`?)?\s*:\s*.*$"
    )
    SYSTEM_RESULT_BLOCK_RE = re.compile(
        r"(?is)SYSTEM\s+RESULT(?:\s*\([^)]*\))?(?:\s+for\s+`?[^`:\n]+`?)?\s*:\s*.*?(?=(?:\n\s*SYSTEM\s+RESULT|\Z))"
    )
    def __init__(self, agent, parser, recovery):
        self.agent = agent
        self.state = agent.state
        self.history = agent.history
        self.parser = parser
        self.recovery = recovery
        self.stage_logger = OrchestrationStageLogger(getattr(agent, "log", None), self.state)

    @property
    def ui(self):
        return self.agent.ui

    def _completed_actions(self, processed_segs) -> list[dict]:
        actions = []
        for seg in processed_segs or []:
            if getattr(seg, "type", None) != "action":
                continue
            content = getattr(seg, "content", None)
            if isinstance(content, dict):
                actions.append(content)
        return actions

    def _extract_visible_text(self, text: str) -> str:
        return extract_visible_text_for_user(text)

    async def _render_text_reply(self, text: str) -> bool:
        rendered = str(text or "").strip()
        if not rendered:
            return False

        ui = self.ui

        print_message = getattr(ui, "print_message", None)
        if callable(print_message):
            try:
                await print_message(rendered, role="assistant")
                return True
            except Exception:
                if self.agent.log:
                    self.agent.log.warning("Failed to render dispatch text-only reply via print_message", exc_info=True)

        candidate_calls = [
            ("print_assistant", (rendered,), {}),
            ("print_ai", (rendered,), {}),
            ("add_chat_message", (), {"role": "assistant", "text": rendered}),
            ("add_chat_message", ("assistant", rendered), {}),
            ("print_markdown", (rendered,), {}),
            ("print_system", (rendered,), {}),
        ]
        for method_name, args, kwargs in candidate_calls:
            method = getattr(ui, method_name, None)
            if not callable(method):
                continue
            try:
                await method(*args, **kwargs)
                return True
            except TypeError:
                continue
            except Exception:
                if self.agent.log:
                    self.agent.log.warning(
                        "Failed to render dispatch text-only reply via %s",
                        method_name,
                        exc_info=True,
                    )
                continue
        return False

    def _looks_like_technical_text(self, text: str) -> bool:
        return detect_technical_interruption(text) is not None

    def _clear_terminal_plaintext_completion(self) -> None:
        try:
            setattr(self.state, "terminal_plaintext_completion_pending", False)
            setattr(self.state, "terminal_plaintext_completion_text", "")
        except Exception:
            pass

    def _close_active_intent_if_terminal_stop(self, completion_reason: str) -> bool:
        closer = getattr(self.state, "close_active_intent_as_resumable", None)
        if not callable(closer):
            return False
        try:
            return bool(closer(completion_reason))
        except Exception:
            return False

    def _maybe_close_active_intent_for_text_only_stop(self) -> None:
        active_intent = getattr(self.state, "active_intent", None)
        if active_intent is None:
            return

        stop_info = getattr(self.state, "pending_loop_stop_info", None) or {}
        stop_reason = str(stop_info.get("reason") or "").strip()
        force_plaintext = bool(getattr(active_intent, "force_plaintext_completion", False))
        exhausted = False
        exhausted_checker = getattr(self.state, "has_exhausted_active_intent", None)
        if callable(exhausted_checker):
            try:
                exhausted = bool(exhausted_checker())
            except Exception:
                exhausted = False

        if force_plaintext:
            completion_reason = (
                str(getattr(self.state, "pending_finalize_completion_reason", "") or "").strip()
                or stop_reason
                or "forced_plaintext_completion"
            )
            self._close_active_intent_if_terminal_stop(completion_reason)
            return

        if exhausted:
            self._close_active_intent_if_terminal_stop(stop_reason or "exhausted_resumable")


    def _strip_leaked_system_results_from_ui_text(self, text: str) -> tuple[str, bool]:
        value = str(text or "")
        if not value:
            return "", False

        before = value
        value = self.SYSTEM_RESULT_LINE_RE.sub("", value)
        if re.search(r"\bSYSTEM\s+RESULT\b", value, re.IGNORECASE):
            value = self.SYSTEM_RESULT_BLOCK_RE.sub("", value)
        value = re.sub(r"\n{3,}", "\n\n", value).strip()
        return value, value != before

    async def handle(self, ctx, processed_segs, sys_results, should_stop: bool) -> DispatchHandlingDecision:
        recon_msg = self.parser.reconstruct(processed_segs)

        self.stage_logger.log(
            "dispatch_outcome",
            "evaluate",
            system_result_count=len(sys_results or []),
            should_stop=should_stop,
        )

        if not sys_results:
            visible_text = self._extract_visible_text(recon_msg)
            if recon_msg and contains_control_markup(recon_msg) and self.agent.log:
                self.agent.log.info("DispatchOutcome.ui_text_sanitized control_markup_removed=True")
            visible_text, leaked_system_result_removed = self._strip_leaked_system_results_from_ui_text(visible_text)
            if leaked_system_result_removed:
                self.stage_logger.log(
                    "dispatch_outcome",
                    "sanitize",
                    reason="leaked_system_result_removed_from_ui_text",
                    source="dispatch",
                )
            technical_interruption = detect_technical_interruption(visible_text or recon_msg)
            if technical_interruption is not None:
                note = getattr(self.state, "note_technical_interruption", None)
                if callable(note):
                    note(technical_interruption, current_query=ctx.current_query)
                printer = getattr(self.ui, "print_technical_interruption", None)
                if callable(printer):
                    await printer(getattr(self.state, "last_technical_interruption", None) or technical_interruption)
                else:
                    await self.ui.print_error(str(visible_text or recon_msg).strip())
                self._close_active_intent_if_terminal_stop("technical_interruption")
                self._clear_terminal_plaintext_completion()
                ctx.active_loop = False
                return DispatchHandlingDecision.stop(
                    reason="technical_text_suppressed_from_chat_history",
                    source="dispatch",
                )
            if visible_text:
                self.history.add_message("assistant", visible_text)
                rendered = await self._render_text_reply(visible_text)
                if not rendered and self.agent.log:
                    self.agent.log.warning("Text-only response was reconstructed but could not be rendered in UI.")

                # This reply has already been rendered to the user-facing UI.
                # Clear any pending terminal plaintext completion so the outer
                # orchestrator loop does not flush the same assistant text again.
                self._maybe_close_active_intent_for_text_only_stop()
                self._clear_terminal_plaintext_completion()
                ctx.active_loop = False
                return DispatchHandlingDecision.stop(
                    reason="text_only_response_forwarded",
                    source="dispatch",
                )

            await self.ui.print_system("Execution finished: no further actions returned by the model.")
            self._clear_terminal_plaintext_completion()
            ctx.active_loop = False
            return DispatchHandlingDecision.stop(
                reason="invalid_zero_action_dispatch_path",
                source="dispatch",
            )

        if recon_msg:
            self.history.add_message("assistant", recon_msg)

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
                if decision.next_query:
                    return DispatchHandlingDecision.continue_with(
                        decision.next_query,
                        reason=decision.reason,
                        source=decision.source or "dispatch_recovery",
                        clear_pending_stop=bool(decision.clear_pending_stop),
                    )
                return DispatchHandlingDecision(
                    handled=True,
                    continue_loop=False,
                    next_query=decision.next_query,
                    stop_loop=bool(decision.stop_loop),
                    clear_pending_stop=bool(decision.clear_pending_stop),
                    reason=decision.reason,
                    source=decision.source or "dispatch_recovery",
                )

            await self.ui.print_system(
                "Execution stopped by control policy (for example, denied action)."
            )
            ctx.active_loop = False
            return DispatchHandlingDecision.stop(
                reason="control_policy_stop",
                source="dispatch",
            )

        if ctx.state_machine is not None:
            sm_decision = ctx.state_machine.decide()
            if sm_decision.decision.name == "MODEL_DIAGNOSTIC":
                ctx.current_query = sm_decision.prompt
                return DispatchHandlingDecision.continue_with(
                    sm_decision.prompt,
                    reason="model_diagnostic",
                    source="state_machine",
                )
            if sm_decision.decision.name == "USER_HANDOFF":
                decision = await self.ui.confirm_loop_recovery(
                    "Detected repeated read-only stagnation. Choose next step."
                )
                if decision in {"retry_recovery", "continue_diagnosis"}:
                    if hasattr(ctx.state_machine, "on_user_recovery_choice"):
                        ctx.state_machine.on_user_recovery_choice(decision)
                    ctx.current_query = ctx.state_machine.build_diagnostic_prompt()
                    return DispatchHandlingDecision.continue_with(
                        ctx.current_query,
                        reason=str(decision),
                        source="state_machine",
                    )
                if decision == "open_search":
                    if hasattr(ctx.state_machine, "on_user_recovery_choice"):
                        ctx.state_machine.on_user_recovery_choice(decision)
                    ctx.current_query = (
                        "SYSTEM: Switch strategy.\n"
                        "Do not call read_file with the same path/arguments.\n"
                        "Use search_content, read_chunk, read_file_skeleton, or edit_file with exact targeted arguments."
                    )
                    return DispatchHandlingDecision.continue_with(
                        ctx.current_query,
                        reason="open_search",
                        source="state_machine",
                    )
                if decision == "pin_target_edit":
                    if hasattr(ctx.state_machine, "on_user_recovery_choice"):
                        ctx.state_machine.on_user_recovery_choice(decision)
                    if hasattr(ctx.state_machine, "build_pin_target_prompt"):
                        ctx.current_query = ctx.state_machine.build_pin_target_prompt()
                        return DispatchHandlingDecision.continue_with(
                            ctx.current_query,
                            reason="pin_target_edit",
                            source="state_machine",
                        )
                await self.ui.print_system("Execution stopped by user after stagnation warning.")
                ctx.active_loop = False
                return DispatchHandlingDecision.stop(
                    reason="user_stopped_after_stagnation_warning",
                    source="state_machine",
                )

        ctx.current_query = "\n---\n".join(sys_results)

        try:
            already_had_memory_tag = self._previous_response_already_had_memory_tag(ctx)

            if already_had_memory_tag:
                self.state.memory_tag_expected_next_step = False
                self.state.memory_tag_reason = ""
                self.state.memory_tag_expected_intent_id = ""
            else:
                self.state.memory_tag_expected_next_step = True
                self.state.memory_tag_reason = "meaningful_evidence_gain"
                active_intent = getattr(self.state, "active_intent", None)
                self.state.memory_tag_expected_intent_id = str(
                    getattr(active_intent, "intent_id", "") or ""
                )
        except Exception:
            pass

        return DispatchHandlingDecision.pass_through(
            reason="system_results_forwarded",
            source="dispatch",
        )

    def _previous_response_already_had_memory_tag(self, ctx=None) -> bool:
        try:
            if int(getattr(self.state, "last_memory_board_accepted_count", 0) or 0) > 0:
                return True
            if int(getattr(self.state, "last_memory_board_parsed_count", 0) or 0) > 0:
                return True
        except Exception:
            pass

        candidates = []
        for obj in (ctx, self.state):
            if obj is None:
                continue
            for name in (
                "response",
                "response_text",
                "last_response",
                "last_model_response",
                "last_assistant_response",
                "last_raw_response",
                "last_model_output",
            ):
                try:
                    value = getattr(obj, name, "")
                except Exception:
                    value = ""
                if isinstance(value, str) and value:
                    candidates.append(value)

        import re
        memory_re = re.compile(
            r"<(fact|finding|decision|preference|progress)\b",
            re.IGNORECASE,
        )
        return any(memory_re.search(text) for text in candidates)
