"""Pre-dispatch action policy gate for parsed model actions."""

from __future__ import annotations

from dataclasses import dataclass

from ...intent_runtime import IntentRuntime
from .action_policy_state import ActionPolicyStateAdapter
from ..responses.stage_logging import OrchestrationStageLogger
from ..shared.decision_models import ActionPolicyDecision


@dataclass
class AtomicBundleActionValidationResult:
    ok: bool
    reason: str = ""
    details: dict | None = None


class _AtomicBundlePreviewState:
    def __init__(self, base_state, *, active_intent):
        self._base_state = base_state
        self.active_intent = active_intent
        self.intent_required_until_activated = False
        self.intent_required_reason = ""

    def __getattr__(self, name):
        return getattr(self._base_state, name)


class ActionPolicyHandler:
    INTENTLESS_READ_ACTIONS = [
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
    ]
    STATE_CHANGING_FILE_ACTIONS = {
        "write_file",
        "write_file_block",
        "append_file_block",
        "create_file",
        "edit_file",
        "delete_file",
        "replace",
    }
    FILE_BODY_ACTIONS = {
        "create_file",
        "write_file",
        "write_file_block",
        "append_file_block",
    }

    def __init__(self, agent, intent_guard, prompt_builder):
        self.agent = agent
        self.state = agent.state
        self.state_view = ActionPolicyStateAdapter(agent.state)
        self.intent_guard = intent_guard
        self.prompt_builder = prompt_builder
        self.stage_logger = OrchestrationStageLogger(getattr(agent, "log", None), self.state)

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
        return self.state_view.compiler_mentioned_file_allowed(str(content.get("path") or "").strip())

    def _is_build_verify_action(self, content: dict) -> bool:
        if not isinstance(content, dict):
            return False
        action_type = str(content.get("type") or content.get("action") or "").strip().lower()
        if action_type != "run_shell":
            return False
        command = str(content.get("command") or "").strip()
        return "./gradlew :app:assembleDebug" in command

    def _build_fix_mode_blocks_action(self, content: dict) -> bool:
        if not self.state_view.is_build_fix_intent_active():
            return False
        if self._is_compiler_targeted_read(content) or self._is_build_verify_action(content):
            return False
        if self._is_state_changing_file_action(content):
            path = str(content.get("path") or "").strip()
            return not self.state_view.compiler_mentioned_file_allowed(path)
        return False

    def _board_subgoal_count(self) -> int:
        board = self.state_view.task_board()
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
        if self.state_view.active_intent() is not None:
            return False
        if not action_segments:
            return False
        if not any(self._is_state_changing_file_action(seg.content) for seg in action_segments):
            return False
        if any(not self._is_state_changing_file_action(seg.content) for seg in action_segments):
            return False

        prior_writes = self.state_view.intentless_state_changing_write_count()
        if prior_writes >= 2:
            return True

        if self.state_view.last_plan_subgoal_create_count() >= 2:
            return True

        if self._board_subgoal_count() >= 3:
            return True

        return self._user_task_implies_multi_file_generation(current_user_input)

    def _continue_with(
        self,
        next_query: str,
        *,
        reason: str,
        source: str,
        parsed_action_count: int,
        blocked_action: str = "",
        repeat_count: int = 0,
    ) -> ActionPolicyDecision:
        log_kwargs = {
            "reason": reason,
            "source": source,
            "action_count": parsed_action_count,
        }
        if blocked_action:
            log_kwargs["blocked_action"] = blocked_action
        if repeat_count:
            log_kwargs["repeat_count"] = repeat_count
        self.stage_logger.log("action_policy", "continue", **log_kwargs)
        return ActionPolicyDecision.continue_with(
            next_query,
            reason=reason,
            source=source,
            parsed_action_count=parsed_action_count,
        )

    def _handle_build_fix_intent_requirement(self, parsed_action_count: int) -> ActionPolicyDecision | None:
        if not self.state_view.build_fix_mode_requires_intent():
            return None
        self.state_view.require_intent("build_failure_requires_formal_intent")
        return self._continue_with(
            self.prompt_builder.build_build_fix_intent_required_prompt(
                goal=self.state_view.build_fix_error_summary()
            ),
            reason="build_failure_requires_formal_intent",
            source="action_policy",
            parsed_action_count=parsed_action_count,
        )

    def _handle_multi_write_intent_requirement(self, ctx, action_segments, parsed_action_count: int) -> ActionPolicyDecision | None:
        if not self._formal_intent_required_for_multi_write_flow(
            action_segments,
            current_user_input=getattr(ctx, "user_input", ""),
        ):
            return None
        self.state_view.require_intent("formal_intent_required_for_multi_step_state_change")
        goal = str(getattr(ctx, "user_input", "") or "").strip()
        return self._continue_with(
            self.prompt_builder.build_formal_intent_required_for_multi_step_state_change_prompt(goal=goal),
            reason="formal_intent_required_for_multi_step_state_change",
            source="action_policy",
            parsed_action_count=parsed_action_count,
        )

    def _handle_hard_exhausted_intent(self, parsed_action_count: int) -> ActionPolicyDecision | None:
        if not self.state_view.has_hard_exhausted_active_intent():
            return None
        self.state_view.require_intent("exhausted_intent_requires_reuse_or_completion")
        next_query = self.prompt_builder.build_limit_aware_reuse_prompt(
            "exhausted_intent_requires_reuse_or_completion",
            getattr(self.state_view.active_intent(), "allowed_actions", None) or [],
            goal=getattr(self.state_view.active_intent(), "goal", ""),
        )
        return self._continue_with(
            next_query,
            reason="exhausted_intent_normal_action_blocked",
            source="action_policy",
            parsed_action_count=parsed_action_count,
        )

    def _handle_action_shape_guard(self, seg, parsed_action_count: int) -> ActionPolicyDecision | None:
        if self._build_fix_mode_blocks_action(seg.content):
            return self._continue_with(
                self.prompt_builder.build_build_fix_mode_blocks_feature_expansion_prompt(
                    allowed_files=self.state_view.build_fix_compiler_mentioned_files()
                ),
                reason="build_fix_mode_blocks_feature_expansion",
                source="action_policy",
                parsed_action_count=parsed_action_count,
            )
        action_type = str(seg.content.get("type") or seg.content.get("action") or "").strip().lower()
        if action_type == "intent":
            return self._continue_with(
                self.prompt_builder.build_intent_payload_inside_action_prompt(),
                reason="intent_payload_inside_action",
                source="action_policy",
                parsed_action_count=parsed_action_count,
            )

        if action_type != "edit_file":
            return None

        search_text = seg.content.get("search_text")
        replace_text = seg.content.get("replace_text")
        if isinstance(search_text, str) and isinstance(replace_text, str) and search_text == replace_text:
            return self._continue_with(
                self.prompt_builder.build_noop_edit_prompt(),
                reason="noop_edit",
                source="action_policy",
                parsed_action_count=parsed_action_count,
            )

        if not self.state_view.has_pending_edit_mismatch_for_path(str(seg.content.get("path") or "")):
            return None

        return self._continue_with(
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

    def _handle_disallowed_action_with_active_intent(
        self,
        seg,
        *,
        parsed_action_count: int,
        reason: str,
        active_intent,
    ) -> ActionPolicyDecision | None:
        if reason not in {"intent_action_not_allowed", "repeated_disallowed_action"} or active_intent is None:
            return None
        blocked_action = str(seg.content.get("type") or seg.content.get("action") or "").strip()
        blocked_path = str(seg.content.get("path") or "").strip()
        self.state_view.record_blocked_action(blocked_action, blocked_path)
        repeat_count = self.state_view.note_disallowed_action_repeat(blocked_action)
        allowed_actions = list(getattr(active_intent, "allowed_actions", []) or [])
        intent_id = str(getattr(active_intent, "intent_id", "") or "").strip()
        intent_type = str(getattr(active_intent, "intent_type", "") or "").strip().upper()
        if repeat_count >= 3:
            self.state_view.mark_terminal_plaintext_handoff(
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
        self.state_view.set_transition_only_intent_required(True, blocked_action=blocked_action)
        self.state_view.set_reuse_only_intent_required(
            effective_reason == "repeated_disallowed_action",
            blocked_action=blocked_action,
        )
        return self._continue_with(
            next_query,
            reason=effective_reason,
            source="intent_guard",
            parsed_action_count=parsed_action_count,
            blocked_action=blocked_action,
            repeat_count=repeat_count,
        )

    def _handle_intent_guard_requirement(self, seg, ctx, *, parsed_action_count: int) -> ActionPolicyDecision | None:
        required, reason = self.intent_guard.action_requires_intent(
            seg.content,
            self.state,
            batch_size=parsed_action_count,
            current_user_input=ctx.user_input,
        )
        if not required:
            return None

        active_intent = self.state_view.active_intent()
        disallowed = self._handle_disallowed_action_with_active_intent(
            seg,
            parsed_action_count=parsed_action_count,
            reason=reason,
            active_intent=active_intent,
        )
        if disallowed is not None:
            return disallowed

        if active_intent is None:
            self.state_view.require_intent(reason)
        return self._continue_with(
            self.prompt_builder.build_intent_required_prompt(
                reason,
                self.INTENTLESS_READ_ACTIONS,
            ),
            reason=reason,
            source="intent_guard",
            parsed_action_count=parsed_action_count,
        )

    def _bundle_file_body_validation(self, command: dict) -> AtomicBundleActionValidationResult:
        if not isinstance(command, dict):
            return AtomicBundleActionValidationResult(False, "invalid_action_payload", {})
        action_type = str(command.get("type") or command.get("action") or "").strip().lower()
        if action_type not in self.FILE_BODY_ACTIONS:
            return AtomicBundleActionValidationResult(True)
        if action_type in {"write_file_block", "append_file_block"}:
            if not isinstance(command.get("file_content"), str):
                return AtomicBundleActionValidationResult(
                    False,
                    "missing_file_content_block",
                    {
                        "message": f"{action_type} requires a complete <file_content>...</file_content> block immediately after </action>.",
                        "blocked_action": action_type,
                    },
                )
            return AtomicBundleActionValidationResult(True)
        if isinstance(command.get("content"), str) or isinstance(command.get("file_content"), str):
            return AtomicBundleActionValidationResult(True)
        return AtomicBundleActionValidationResult(
            False,
            "missing_file_content_block",
            {
                "message": f"{action_type} requires file body content, either inline JSON content or a following <file_content> block.",
                "blocked_action": action_type,
            },
        )

    def validate_atomic_bundle_action(
        self,
        ctx,
        segments,
        *,
        proposed_active_intent,
    ) -> AtomicBundleActionValidationResult:
        action_segments = [
            seg for seg in (segments or []) if getattr(seg, "type", "") == "action" and isinstance(getattr(seg, "content", None), dict)
        ]
        if len(action_segments) != 1:
            return AtomicBundleActionValidationResult(
                False,
                "atomic_bundle_requires_exactly_one_action",
                {"message": "Atomic intent/action bundle requires exactly one valid <action> block."},
            )

        seg = action_segments[0]
        shape_guard = self._handle_action_shape_guard(seg, 1)
        if shape_guard is not None:
            return AtomicBundleActionValidationResult(
                False,
                str(getattr(shape_guard, "reason", "") or "invalid_action_shape"),
                {
                    "message": str(getattr(shape_guard, "next_query", "") or ""),
                    "blocked_action": str(seg.content.get("type") or seg.content.get("action") or "").strip(),
                },
            )

        file_body_check = self._bundle_file_body_validation(seg.content)
        if not file_body_check.ok:
            return file_body_check

        preview_state = _AtomicBundlePreviewState(self.state, active_intent=proposed_active_intent)
        command = dict(seg.content or {})
        action_type = str(command.get("type") or command.get("action") or "").strip().lower()
        if action_type in {"create_file", "write_file"} and "content" not in command and isinstance(command.get("file_content"), str):
            command["content"] = command["file_content"]

        required, reason = self.intent_guard.action_requires_intent(
            command,
            preview_state,
            batch_size=1,
            current_user_input=getattr(ctx, "user_input", ""),
        )
        if required:
            return AtomicBundleActionValidationResult(
                False,
                reason,
                {
                    "blocked_action": action_type,
                    "allowed_actions": list(getattr(proposed_active_intent, "allowed_actions", []) or []),
                },
            )

        config = getattr(self.state, "_config", None) or getattr(self.agent, "config", None)
        preview_runtime = IntentRuntime(config, state=preview_state) if config is not None else None
        if preview_runtime is not None:
            preview_runtime.active_intent = proposed_active_intent
            stop_info = preview_runtime.pre_action_check(command)
            if isinstance(stop_info, dict):
                return AtomicBundleActionValidationResult(
                    False,
                    str(stop_info.get("reason") or "intent_action_not_allowed"),
                    {
                        **stop_info,
                        "blocked_action": action_type,
                        "allowed_actions": list(getattr(proposed_active_intent, "allowed_actions", []) or []),
                    },
                )

        return AtomicBundleActionValidationResult(True)

    async def decide(self, ctx, segments, *, intent_payload: dict | None) -> ActionPolicyDecision:
        action_segments = [
            seg for seg in segments if getattr(seg, "type", "") == "action" and isinstance(getattr(seg, "content", None), dict)
        ]
        parsed_action_count = len(action_segments)

        if not action_segments:
            self.state_view.set_reuse_only_intent_required(False)
            self.state_view.set_transition_only_intent_required(False)
            self.state_view.clear_disallowed_action_repeat()
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

        build_fix_requirement = self._handle_build_fix_intent_requirement(parsed_action_count)
        if build_fix_requirement is not None:
            return build_fix_requirement

        multi_write_requirement = self._handle_multi_write_intent_requirement(ctx, action_segments, parsed_action_count)
        if multi_write_requirement is not None:
            return multi_write_requirement

        hard_exhausted_requirement = self._handle_hard_exhausted_intent(parsed_action_count)
        if hard_exhausted_requirement is not None:
            return hard_exhausted_requirement

        for seg in action_segments:
            shape_guard = self._handle_action_shape_guard(seg, parsed_action_count)
            if shape_guard is not None:
                return shape_guard

            intent_requirement = self._handle_intent_guard_requirement(
                seg,
                ctx,
                parsed_action_count=parsed_action_count,
            )
            if intent_requirement is not None:
                return intent_requirement

        self.stage_logger.log(
            "action_policy",
            "pass",
            action_count=parsed_action_count,
            reason="actions_allowed_to_proceed",
        )
        self.state_view.set_reuse_only_intent_required(False)
        self.state_view.set_transition_only_intent_required(False)
        self.state_view.clear_disallowed_action_repeat()
        return ActionPolicyDecision.pass_through(
            reason="actions_allowed_to_proceed",
            source="action_policy",
            parsed_action_count=parsed_action_count,
        )
