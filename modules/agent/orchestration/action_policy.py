"""Pre-dispatch action policy gate for parsed model actions."""

from __future__ import annotations

from .decision_models import ActionPolicyDecision
from .stage_logging import OrchestrationStageLogger


class ActionPolicyHandler:
    def __init__(self, agent, intent_guard, prompt_builder):
        self.agent = agent
        self.state = agent.state
        self.intent_guard = intent_guard
        self.prompt_builder = prompt_builder
        self.stage_logger = OrchestrationStageLogger(getattr(agent, "log", None), self.state)

    def _note_disallowed_action_repeat(self, action_type: str) -> int:
        normalized = str(action_type or "").strip().lower()
        active_intent = getattr(self.state, "active_intent", None)
        intent_id = str(getattr(active_intent, "intent_id", "") or "").strip()
        current_type = str(getattr(self.state, "disallowed_action_repeat_type", "") or "").strip().lower()
        current_intent = str(getattr(self.state, "disallowed_action_repeat_intent_id", "") or "").strip()
        count = int(getattr(self.state, "disallowed_action_repeat_count", 0) or 0)
        if normalized != current_type or intent_id != current_intent:
            count = 0
        count += 1
        try:
            setattr(self.state, "disallowed_action_repeat_type", normalized)
            setattr(self.state, "disallowed_action_repeat_intent_id", intent_id)
            setattr(self.state, "disallowed_action_repeat_count", count)
        except Exception:
            pass
        return count

    def _clear_disallowed_action_repeat(self) -> None:
        try:
            setattr(self.state, "disallowed_action_repeat_type", "")
            setattr(self.state, "disallowed_action_repeat_intent_id", "")
            setattr(self.state, "disallowed_action_repeat_count", 0)
            setattr(self.state, "last_blocked_action_type", "")
            setattr(self.state, "last_blocked_action_path", "")
        except Exception:
            pass

    def _mark_terminal_plaintext_handoff(self, text: str, reason: str) -> None:
        normalized_text = str(text or "").strip()
        if not normalized_text:
            return
        try:
            setattr(self.state, "terminal_plaintext_completion_pending", True)
            setattr(self.state, "terminal_plaintext_completion_text", normalized_text)
        except Exception:
            pass
        marker = getattr(self.state, "mark_pending_forced_plaintext_completion_close", None)
        if callable(marker):
            try:
                marker(str(reason or "terminal_plaintext_completion").strip(), "action_policy")
            except Exception:
                pass

    def _current_active_intent_id(self) -> str:
        active_intent = getattr(self.state, "active_intent", None)
        return str(getattr(active_intent, "intent_id", "") or "").strip()

    def _record_blocked_action(self, action_type: str, path: str = "") -> None:
        try:
            setattr(self.state, "last_blocked_action_type", str(action_type or "").strip())
            setattr(self.state, "last_blocked_action_path", str(path or "").strip())
        except Exception:
            pass

    def _has_pending_edit_mismatch_for_path(self, path: str) -> bool:
        normalized_path = str(path or "").strip()
        if not normalized_path:
            return False
        pending_path = str(getattr(self.state, "pending_edit_mismatch_path", "") or "").strip()
        pending_intent = str(getattr(self.state, "pending_edit_mismatch_intent_id", "") or "").strip()
        return bool(
            pending_path
            and normalized_path == pending_path
            and pending_intent == self._current_active_intent_id()
        )

    async def decide(self, ctx, segments, *, intent_payload: dict | None) -> ActionPolicyDecision:
        action_segments = [
            seg for seg in segments if getattr(seg, "type", "") == "action" and isinstance(getattr(seg, "content", None), dict)
        ]
        parsed_action_count = len(action_segments)

        if not action_segments or intent_payload is not None:
            self._clear_disallowed_action_repeat()
            self.stage_logger.log(
                "action_policy",
                "pass",
                action_count=parsed_action_count,
                reason="no_action_gate_needed",
            )
            return ActionPolicyDecision.pass_through(
                reason="no_action_gate_needed",
                source="action_policy",
                parsed_action_count=parsed_action_count,
            )

        hard_exhausted_checker = getattr(self.state, "has_hard_exhausted_active_intent", None)
        hard_exhausted = False
        if callable(hard_exhausted_checker):
            try:
                hard_exhausted = bool(hard_exhausted_checker())
            except Exception:
                hard_exhausted = False

        if hard_exhausted:
            require_intent = getattr(self.state, "require_intent", None)
            if callable(require_intent):
                require_intent("exhausted_intent_requires_reuse_or_completion")
            next_query = self.prompt_builder.build_limit_aware_reuse_prompt(
                "exhausted_intent_requires_reuse_or_completion",
                getattr(getattr(self.state, "active_intent", None), "allowed_actions", None) or [],
                goal=getattr(getattr(self.state, "active_intent", None), "goal", ""),
            )
            self.stage_logger.log(
                "action_policy",
                "continue",
                reason="exhausted_intent_normal_action_blocked",
                source="action_policy",
                action_count=parsed_action_count,
            )
            return ActionPolicyDecision.continue_with(
                next_query,
                reason="exhausted_intent_normal_action_blocked",
                source="action_policy",
                parsed_action_count=parsed_action_count,
            )

        for seg in action_segments:
            action_type = str(seg.content.get("type") or seg.content.get("action") or "").strip().lower()
            if action_type == "intent":
                self.stage_logger.log(
                    "action_policy",
                    "continue",
                    reason="intent_payload_inside_action",
                    source="action_policy",
                    action_count=parsed_action_count,
                )
                return ActionPolicyDecision.continue_with(
                    self.prompt_builder.build_intent_payload_inside_action_prompt(),
                    reason="intent_payload_inside_action",
                    source="action_policy",
                    parsed_action_count=parsed_action_count,
                )

            if action_type == "edit_file":
                search_text = seg.content.get("search_text")
                replace_text = seg.content.get("replace_text")
                if isinstance(search_text, str) and isinstance(replace_text, str) and search_text == replace_text:
                    self.stage_logger.log(
                        "action_policy",
                        "continue",
                        reason="noop_edit",
                        source="action_policy",
                        action_count=parsed_action_count,
                    )
                    return ActionPolicyDecision.continue_with(
                        self.prompt_builder.build_noop_edit_prompt(),
                        reason="noop_edit",
                        source="action_policy",
                        parsed_action_count=parsed_action_count,
                    )

                if self._has_pending_edit_mismatch_for_path(str(seg.content.get("path") or "")):
                    self.stage_logger.log(
                        "action_policy",
                        "continue",
                        reason="edit_retry_requires_fresh_read",
                        source="action_policy",
                        action_count=parsed_action_count,
                    )
                    return ActionPolicyDecision.continue_with(
                        self.prompt_builder.build_edit_retry_requires_fresh_read_prompt(
                            path=str(seg.content.get("path") or "").strip(),
                            allowed_actions=list(
                                getattr(getattr(self.state, "active_intent", None), "allowed_actions", []) or []
                            ),
                        ),
                        reason="edit_retry_requires_fresh_read",
                        source="action_policy",
                        parsed_action_count=parsed_action_count,
                    )

            required, reason = self.intent_guard.action_requires_intent(
                seg.content,
                self.state,
                batch_size=parsed_action_count,
                current_user_input=ctx.user_input,
            )
            if required:
                active_intent = getattr(self.state, "active_intent", None)
                if reason in {"intent_action_not_allowed", "repeated_disallowed_action"} and active_intent is not None:
                    blocked_action = str(seg.content.get("type") or seg.content.get("action") or "").strip()
                    blocked_path = str(seg.content.get("path") or "").strip()
                    self._record_blocked_action(blocked_action, blocked_path)
                    repeat_count = self._note_disallowed_action_repeat(blocked_action)
                    allowed_actions = list(getattr(active_intent, "allowed_actions", []) or [])
                    intent_id = str(getattr(active_intent, "intent_id", "") or "").strip()
                    intent_type = str(getattr(active_intent, "intent_type", "") or "").strip().upper()
                    if repeat_count >= 3:
                        self._mark_terminal_plaintext_handoff(
                            self.prompt_builder.build_terminal_repeated_disallowed_action_handoff_text(
                                blocked_action=blocked_action,
                                intent_id=intent_id,
                                intent_type=intent_type,
                                allowed_actions=allowed_actions,
                            ),
                            "terminal_repeated_disallowed_action_handoff",
                        )
                        self.stage_logger.log(
                            "action_policy",
                            "stop",
                            reason="terminal_repeated_disallowed_action_handoff",
                            source="intent_guard",
                            action_count=parsed_action_count,
                            blocked_action=blocked_action,
                            repeat_count=repeat_count,
                        )
                        return ActionPolicyDecision(
                            handled=True,
                            continue_loop=False,
                            next_query=None,
                            reason="terminal_repeated_disallowed_action_handoff",
                            source="intent_guard",
                            parsed_action_count=parsed_action_count,
                        )
                    effective_reason = "repeated_disallowed_action" if repeat_count >= 2 else "intent_action_not_allowed"
                    next_query = self.prompt_builder.build_intent_action_not_allowed_prompt(
                        blocked_action=blocked_action,
                        intent_id=intent_id,
                        intent_type=intent_type,
                        allowed_actions=allowed_actions,
                        repeated=effective_reason == "repeated_disallowed_action",
                    )
                    self.stage_logger.log(
                        "action_policy",
                        "continue",
                        reason=effective_reason,
                        source="intent_guard",
                        action_count=parsed_action_count,
                        blocked_action=blocked_action,
                        repeat_count=repeat_count,
                    )
                    return ActionPolicyDecision.continue_with(
                        next_query,
                        reason=effective_reason,
                        source="intent_guard",
                        parsed_action_count=parsed_action_count,
                    )
                if active_intent is None and hasattr(self.state, "require_intent"):
                    self.state.require_intent(reason)
                next_query = self.prompt_builder.build_intent_required_prompt(
                    reason,
                    [
                        "read_file",
                        "read_chunk",
                        "read_file_skeleton",
                        "extract_kotlin_function",
                        "extract_symbol",
                        "search_content",
                        "search_files",
                        "list_directory",
                        "find_files",
                        "git_diff",
                        "run_shell",
                    ],
                )
                self.stage_logger.log(
                    "action_policy",
                    "continue",
                    reason=reason,
                    source="intent_guard",
                    action_count=parsed_action_count,
                )
                return ActionPolicyDecision.continue_with(
                    next_query,
                    reason=reason,
                    source="intent_guard",
                    parsed_action_count=parsed_action_count,
                )

        self.stage_logger.log(
            "action_policy",
            "pass",
            action_count=parsed_action_count,
            reason="actions_allowed_to_proceed",
        )
        self._clear_disallowed_action_repeat()
        return ActionPolicyDecision.pass_through(
            reason="actions_allowed_to_proceed",
            source="action_policy",
            parsed_action_count=parsed_action_count,
        )
