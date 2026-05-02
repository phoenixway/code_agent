"""Pre-dispatch action policy gate for parsed model actions."""

from __future__ import annotations

from .decision_models import ActionPolicyDecision
from .responses.stage_logging import OrchestrationStageLogger


class ActionPolicyHandler:
    STATE_CHANGING_FILE_ACTIONS = {
        "write_file",
        "write_file_block",
        "append_file_block",
        "create_file",
        "edit_file",
        "delete_file",
        "replace",
    }

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

    def _set_reuse_only_intent_required(self, value: bool, blocked_action: str = "") -> None:
        try:
            setattr(self.state, "reuse_only_intent_required", bool(value))
            setattr(self.state, "reuse_only_blocked_action", str(blocked_action or "").strip() if value else "")
        except Exception:
            pass

    def _set_transition_only_intent_required(self, value: bool, blocked_action: str = "") -> None:
        try:
            setattr(self.state, "transition_only_intent_required", bool(value))
            setattr(
                self.state,
                "transition_only_blocked_action",
                str(blocked_action or "").strip() if value else "",
            )
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

    def _is_state_changing_file_action(self, content: dict) -> bool:
        if not isinstance(content, dict):
            return False
        action_type = str(content.get("type") or content.get("action") or "").strip().lower()
        return action_type in self.STATE_CHANGING_FILE_ACTIONS

    def _is_compiler_targeted_read(self, content: dict) -> bool:
        if not isinstance(content, dict):
            return False
        action_type = str(content.get("type") or content.get("action") or "").strip().lower()
        if action_type not in {"read_file", "read_chunk", "read_file_skeleton", "extract_symbol", "extract_kotlin_function"}:
            return False
        checker = getattr(self.state, "compiler_mentioned_file_allowed", None)
        if not callable(checker):
            return False
        try:
            return bool(checker(str(content.get("path") or "").strip()))
        except Exception:
            return False

    def _is_build_verify_action(self, content: dict) -> bool:
        if not isinstance(content, dict):
            return False
        action_type = str(content.get("type") or content.get("action") or "").strip().lower()
        if action_type != "run_shell":
            return False
        command = str(content.get("command") or "").strip()
        return "./gradlew :app:assembleDebug" in command

    def _build_fix_mode_blocks_action(self, content: dict) -> bool:
        if not bool(getattr(self.state, "is_build_fix_intent_active", lambda: False)()):
            return False
        if self._is_compiler_targeted_read(content) or self._is_build_verify_action(content):
            return False
        if self._is_state_changing_file_action(content):
            path = str(content.get("path") or "").strip()
            checker = getattr(self.state, "compiler_mentioned_file_allowed", None)
            if callable(checker):
                try:
                    return not bool(checker(path))
                except Exception:
                    return True
        return False

    def _board_subgoal_count(self) -> int:
        board = getattr(self.state, "task_board", None)
        if not isinstance(board, dict):
            return 0
        steps = board.get("steps")
        if not isinstance(steps, list):
            return 0
        count = 0
        for step in steps:
            if not isinstance(step, dict):
                continue
            title = str(step.get("title") or "").strip()
            if title:
                count += 1
        return count

    def _user_task_implies_multi_file_generation(self, user_input: str) -> bool:
        text = str(user_input or "").strip().lower()
        if not text:
            return False
        phrases = (
            "multiple files",
            "several files",
            "many files",
            "create files",
            "generate files",
            "set of",
            "series of",
            "lesson set",
            "lessons set",
            "structured lessons",
            "kotlin lessons",
            "код урок",
            "серію файлів",
            "кілька файлів",
            "набір уроків",
            "уроки kotlin",
        )
        return any(phrase in text for phrase in phrases)

    def _formal_intent_required_for_multi_write_flow(self, action_segments, *, current_user_input: str) -> bool:
        if getattr(self.state, "active_intent", None) is not None:
            return False
        if not action_segments:
            return False
        if not any(self._is_state_changing_file_action(seg.content) for seg in action_segments):
            return False
        if any(not self._is_state_changing_file_action(seg.content) for seg in action_segments):
            return False

        prior_writes = int(getattr(self.state, "intentless_state_changing_file_write_count", 0) or 0)
        if prior_writes >= 2:
            return True

        if int(getattr(self.state, "last_plan_subgoal_create_count", 0) or 0) >= 2:
            return True

        if self._board_subgoal_count() >= 3:
            return True

        return self._user_task_implies_multi_file_generation(current_user_input)

    async def decide(self, ctx, segments, *, intent_payload: dict | None) -> ActionPolicyDecision:
        action_segments = [
            seg for seg in segments if getattr(seg, "type", "") == "action" and isinstance(getattr(seg, "content", None), dict)
        ]
        parsed_action_count = len(action_segments)

        if not action_segments:
            self._set_reuse_only_intent_required(False)
            self._set_transition_only_intent_required(False)
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

        if bool(getattr(self.state, "build_fix_mode_requires_intent", lambda: False)()):
            require_intent = getattr(self.state, "require_intent", None)
            if callable(require_intent):
                require_intent("build_failure_requires_formal_intent")
            self.stage_logger.log(
                "action_policy",
                "continue",
                reason="build_failure_requires_formal_intent",
                source="action_policy",
                action_count=parsed_action_count,
            )
            return ActionPolicyDecision.continue_with(
                self.prompt_builder.build_build_fix_intent_required_prompt(
                    goal=str(getattr(self.state, "build_fix_error_summary", "") or "")
                ),
                reason="build_failure_requires_formal_intent",
                source="action_policy",
                parsed_action_count=parsed_action_count,
            )

        if self._formal_intent_required_for_multi_write_flow(
            action_segments,
            current_user_input=getattr(ctx, "user_input", ""),
        ):
            require_intent = getattr(self.state, "require_intent", None)
            if callable(require_intent):
                require_intent("formal_intent_required_for_multi_step_state_change")
            goal = str(getattr(ctx, "user_input", "") or "").strip()
            next_query = self.prompt_builder.build_formal_intent_required_for_multi_step_state_change_prompt(goal=goal)
            self.stage_logger.log(
                "action_policy",
                "continue",
                reason="formal_intent_required_for_multi_step_state_change",
                source="action_policy",
                action_count=parsed_action_count,
            )
            return ActionPolicyDecision.continue_with(
                next_query,
                reason="formal_intent_required_for_multi_step_state_change",
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
            if self._build_fix_mode_blocks_action(seg.content):
                self.stage_logger.log(
                    "action_policy",
                    "continue",
                    reason="build_fix_mode_blocks_feature_expansion",
                    source="action_policy",
                    action_count=parsed_action_count,
                )
                return ActionPolicyDecision.continue_with(
                    self.prompt_builder.build_build_fix_mode_blocks_feature_expansion_prompt(
                        allowed_files=list(getattr(self.state, "build_fix_compiler_mentioned_files", []) or [])
                    ),
                    reason="build_fix_mode_blocks_feature_expansion",
                    source="action_policy",
                    parsed_action_count=parsed_action_count,
                )
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
                    self._set_transition_only_intent_required(True, blocked_action=blocked_action)
                    self._set_reuse_only_intent_required(
                        effective_reason == "repeated_disallowed_action",
                        blocked_action=blocked_action,
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
        self._set_reuse_only_intent_required(False)
        self._set_transition_only_intent_required(False)
        self._clear_disallowed_action_repeat()
        return ActionPolicyDecision.pass_through(
            reason="actions_allowed_to_proceed",
            source="action_policy",
            parsed_action_count=parsed_action_count,
        )
