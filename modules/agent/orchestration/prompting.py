"""Prompt construction for orchestrator runtime and recovery flows."""

from __future__ import annotations

from textwrap import dedent

from modules.defaults import DEFAULT_SYSTEM_PROMPT

from ..intent_message_resolver import resolve_intent_message_key
from ..intent_messages import render_intent_message


class OrchestratorPromptBuilder:
    def __init__(self, agent):
        self.agent = agent
        self.state = agent.state
        self.config = agent.config
        self.memory_board_store = getattr(agent, "memory_board_store", None)

    def _current_active_intent(self):
        return getattr(self.state, "active_intent", None)

    def _current_active_intent_id(self) -> str | None:
        active_intent = self._current_active_intent()
        if active_intent is None:
            return None
        value = getattr(active_intent, "intent_id", None)
        return str(value).strip() if value else None

    def _current_intent_allowed_actions(self) -> list[str]:
        active_intent = self._current_active_intent()
        return list(getattr(active_intent, "allowed_actions", []) or []) if active_intent is not None else []

    def _current_intent_goal(self) -> str:
        active_intent = self._current_active_intent()
        return str(getattr(active_intent, "goal", "") or "") if active_intent is not None else ""

    def _current_intent_type(self) -> str:
        active_intent = self._current_active_intent()
        return str(getattr(active_intent, "intent_type", "") or "") if active_intent is not None else ""

    def _render_recovery_message(self, message_key: str, default: str, *, next_hint: str = "") -> str:
        rendered = render_intent_message(message_key, next_hint=next_hint, default="")
        return rendered or default

    def build_system_message(self, tools_prompt: str, ctx_prompt: str) -> str:
        prompt = DEFAULT_SYSTEM_PROMPT.replace("__TOOLS_DESCRIPTION__", tools_prompt)
        blocks = [prompt, ctx_prompt]

        memory_board = getattr(self.agent, "memory_board_store", None)
        active_intent_id = self._current_active_intent_id()
        if memory_board is not None and hasattr(memory_board, "to_system_prompt"):
            try:
                memory_prompt = memory_board.to_system_prompt(active_intent_id=active_intent_id)
                blocks.append(memory_prompt)
                if self.agent.log and isinstance(memory_prompt, str) and memory_prompt.strip():
                    self.agent.log.debug(
                        "PromptBuilder.memory_board_prompt active_intent_id=%s chars=%s\n%s",
                        active_intent_id or "",
                        len(memory_prompt),
                        memory_prompt,
                    )
            except Exception as exc:
                if self.agent.log:
                    self.agent.log.warning(f"Memory board prompt build failed: {exc}")

        blocks.append(self.build_memory_board_protocol_prompt())
        system_message = "\n\n".join(block for block in blocks if isinstance(block, str) and block.strip())
        if self.agent.log:
            self.agent.log.debug(
                "PromptBuilder.system_message built blocks=%s tools_chars=%s ctx_chars=%s total_chars=%s",
                len([block for block in blocks if isinstance(block, str) and block.strip()]),
                len(tools_prompt or ""),
                len(ctx_prompt or ""),
                len(system_message or ""),
            )
            self.agent.log.debug("PromptBuilder.system_message.full\n%s", system_message)
        return system_message

    def build_memory_board_protocol_prompt(self) -> str:
        return dedent(
            """
            ## MEMORY BOARD PROTOCOL
            You may emit inline durable-memory tags directly in your normal response text.
            Supported tags:
            - <fact scope="intent|session|project">...</fact>
            - <finding scope="intent|session|project">...</finding>
            - <decision scope="intent|session|project">...</decision>
            - <preference scope="intent|session|project">...</preference>
            - <progress scope="intent">...</progress>

            Rules:
            - Use memory tags only for high-value information that must survive history compression.
            - Do not log routine actions, tool calls, or noisy low-level observations.
            - Use scope="intent" for knowledge needed to continue the current intent contract.
            - Use scope="session" for preferences or guidance that should persist for the current session.
            - Use scope="project" only for durable project-wide facts or decisions.
            - Use <progress scope="intent"> only for milestone-level updates that would be critical if the rest of the history were lost.
            - Do not silently contradict previously committed memory; if new evidence changes something important, emit a new explicit correcting tag.
            - Memory tags are optional and can appear alongside normal prose, <intent>, and <action>.
            """
        ).strip()

    def build_intent_required_prompt(self, reason: str, allowed_actions: list[str] | None = None) -> str:
        next_hint = ""
        if allowed_actions:
            next_hint = f"\nAllowed actions for the next intent contract: {', '.join(allowed_actions)}."
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

    def build_reuse_current_intent_prompt(
        self,
        reason: str,
        allowed_actions: list[str] | None = None,
        *,
        goal: str | None = None,
    ) -> str:
        next_hint = ""
        if allowed_actions:
            next_hint = f"\nAllowed actions under the CURRENT intent contract: {', '.join(allowed_actions)}."
        goal_hint = ""
        if isinstance(goal, str) and goal.strip():
            goal_hint = f"\nCurrent contract goal remains the same: {goal.strip()}."
        return (
            "SYSTEM: Continue under the current intent contract.\n"
            f"Reason: {reason}.{next_hint}{goal_hint}\n"
            "The current intent contract remains valid and its goal remains the same.\n"
            "Intent here means the formal runtime contract for the current user-facing goal and allowed actions, not a new local intention, substep label, or next micro-step.\n"
            "Continue toward that goal using the updated allowed tools and constraints.\n"
            "Do not repeat the action pattern that was just blocked or low-value.\n"
            "Do not relabel, refresh, replace, or reactivate the intent contract unless there is a valid reason from the system prompt or runtime.\n"
            "Do not restart the task from the beginning. Continue from already gathered evidence, files, and conclusions under the same contract.\n"
            "Change the next action when needed. Do not change the contract without a valid reason.\n"
            "Return the next step that most increases progress toward the goal, or provide a plain-text answer if the goal can already be answered."
        )

    def build_keep_current_intent_recovery_prompt(self, stop_info: dict | None) -> str:
        stop_info = stop_info or {}
        reason = str(stop_info.get("reason") or "").strip()
        allowed_actions = self._current_intent_allowed_actions()
        goal = self._current_intent_goal()
        next_hint = f"\nAllowed actions under the CURRENT intent contract: {', '.join(allowed_actions)}." if allowed_actions else ""

        message_defaults = {
            "intent_step_limit_soft_exceeded": "Continue under the current intent contract.",
            "user_approved_more_steps_after_hard_limit": "Continue under the current intent contract.",
            "intent_blocked_action_signature": "A specific action is blocked, but the current intent contract is still valid.",
            "action_not_allowed_in_phase": "The current intent contract remains valid, but the previous phase-specific recovery conflicted with it.",
            "retry_or_continuation_after_failure": "The previous step failed, but the current intent contract still remains valid.",
            "suspect_intent_relabel_repeat": "The current intent contract is still valid.",
        }
        message_keys = {
            "intent_step_limit_soft_exceeded": "keep_current_intent_soft_limit",
            "user_approved_more_steps_after_hard_limit": "keep_current_intent_after_user_more_steps",
            "intent_blocked_action_signature": stop_info.get("message_key") or "blocked_action_keep_current_intent",
            "action_not_allowed_in_phase": "keep_current_intent_conflicting_phase_actions",
            "retry_or_continuation_after_failure": stop_info.get("message_key") or "blocked_action_keep_current_intent",
            "suspect_intent_relabel_repeat": stop_info.get("message_key") or "suspect_intent_relabel_repeat",
        }
        header = self._render_recovery_message(
            message_keys.get(reason, "blocked_action_keep_current_intent"),
            message_defaults.get(reason, "Continue under the current intent contract."),
            next_hint=next_hint,
        )

        base_lines = [
            f"SYSTEM: {header}" if not header.startswith("SYSTEM:") else header,
            f"Reason: {reason}.",
        ]
        if allowed_actions:
            base_lines.append(f"Allowed actions under the CURRENT intent contract: {', '.join(allowed_actions)}.")
        if goal:
            base_lines.append(f"Current contract goal remains the same: {goal}.")
        base_lines.extend(
            [
                "The current intent contract remains valid and its goal remains the same.",
                "Intent here means the formal runtime contract for the current user-facing goal and allowed actions, not a new local intention or next micro-step.",
                "Continue toward that goal using the updated allowed tools and constraints.",
                "Do not restart the task from the beginning. Continue from already gathered evidence under the same contract if there is no valid reason to change it.",
                "Do not repeat the action pattern that was just blocked or low-value.",
            ]
        )

        if reason == "user_approved_more_steps_after_hard_limit":
            base_lines.extend(
                [
                    "User approved a small additional step budget for the CURRENT intent contract.",
                    "Return the next valid <action> now.",
                ]
            )
        elif reason == "intent_step_limit_soft_exceeded":
            base_lines.extend(
                [
                    "Choose the next action that most increases progress toward the goal.",
                    "Prefer one final allowed <action>, or return a final plain-text answer if the evidence is already enough.",
                ]
            )
        elif reason == "intent_blocked_action_signature":
            blocked_reason = str((stop_info.get("policy_metadata") or {}).get("blocked_reason") or "")
            if blocked_reason:
                base_lines.append(f"The blocked action pattern failed because of: {blocked_reason}.")
            base_lines.extend(
                [
                    "Do NOT retry the same action with cosmetic changes.",
                    "Choose the next action that most increases progress toward the goal.",
                    "Return one materially different next <action>, or provide a plain-text answer if the goal can already be answered.",
                ]
            )
        elif reason == "retry_or_continuation_after_failure":
            details = stop_info.get("error_details") or {}
            mismatch_type = str(details.get("mismatch_type") or "")
            if mismatch_type:
                base_lines.append(f"Last recoverable failure detail: {mismatch_type}.")
            base_lines.extend(
                [
                    "Prefer a deterministic recovery step inside the SAME current intent contract.",
                    "Do not open a new intent contract unless the work truly changed.",
                    "If the previous edit failed because the search block was not unique or whitespace did not match, first read the exact target block, then retry edit_file with exact text, or use write_file with full validated content.",
                    "Return the next valid <action>.",
                ]
            )
        elif reason == "action_not_allowed_in_phase":
            base_lines.extend(
                [
                    "Use the CURRENT intent contract action family instead of switching to a conflicting phase-specific action set.",
                    "Return the next valid <action> that directly serves the current goal.",
                ]
            )
        elif reason == "suspect_intent_relabel_repeat":
            base_lines.extend(
                [
                    "There is no valid reason to relabel or replace the contract now.",
                    "Do not treat the next local step as a new intent.",
                    "Do not restart the same investigation path from the beginning.",
                    "Continue from the strongest evidence already gathered under the current contract.",
                    "Return the next step that directly continues the current work.",
                ]
            )
        else:
            base_lines.extend(
                [
                    "Choose the next action that most increases progress toward the goal.",
                    "Return the next materially different <action>, or provide a plain-text answer if the goal can already be answered.",
                ]
            )

        return "\n".join(base_lines)

    def _should_prefer_current_intent_recovery(self, stop_info: dict | None) -> bool:
        stop_info = stop_info or {}
        reason = str(stop_info.get("reason") or "").strip()
        active_intent = self._current_active_intent()
        if active_intent is None:
            return False

        if reason in {
            "intent_step_limit_soft_exceeded",
            "user_approved_more_steps_after_hard_limit",
            "intent_blocked_action_signature",
            "retry_or_continuation_after_failure",
            "suspect_intent_relabel_repeat",
        }:
            return True

        if reason == "action_not_allowed_in_phase":
            active_allowed = set(self._current_intent_allowed_actions())
            next_actions = stop_info.get("next_actions") or []
            next_set = set(next_actions if isinstance(next_actions, list) else [])
            active_type = self._current_intent_type()
            if not active_allowed:
                return False
            if active_type == "MODIFY":
                return False
            if next_set and not next_set.issubset(active_allowed):
                return True

        return False

    def build_suspect_intent_change_message(self, stop_info: dict | None) -> str:
        stop_info = stop_info or {}
        suspicion = stop_info.get("suspicion") or {}
        old_goal = str(suspicion.get("old_goal") or "")
        new_goal = str(suspicion.get("new_goal") or "")
        reason = str(stop_info.get("reason") or "suspect_intent_relabel_repeat")
        parts = [
            "Модель підозріло змінила поточний intent contract у межах тієї самої лінії роботи.",
            f"Причина: {reason}.",
        ]
        if old_goal:
            parts.append(f"Стара ціль контракту: {old_goal}")
        if new_goal:
            parts.append(f"Нова ціль контракту: {new_goal}")
        parts.extend(
            [
                "Обери один із варіантів:",
                "- Keep original goal: змусити модель триматися попередньої цілі контракту.",
                "- Allow changed goal: дозволити нову ціль один раз.",
                "- Stop and answer from current evidence: зупинити tool use і відповісти з уже зібраного.",
            ]
        )
        return "\n".join(parts)

    def build_intent_overrun_message(self, stop_info: dict | None) -> str:
        stop_info = stop_info or {}
        reason = str(stop_info.get("reason") or "intent_step_limit_exceeded")
        return (
            "Поточний intent contract досяг жорсткого ліміту кроків. Далі агент не повинен продовжувати самовільно.\n"
            f"Причина: {reason}.\n"
            "Обери один із двох варіантів:\n"
            "- Approve more steps: дозволити ще невеликий бюджет кроків для ЦЬОГО самого intent contract.\n"
            "- Stop and answer from current evidence: зупинити tool use і отримати відповідь лише з уже зібраного."
        )

    def build_suspect_intent_change_confirmation_suffix(self) -> str:
        return "\nТак = Allow changed goal. Ні = Keep original goal."

    def build_intent_overrun_confirmation_suffix(self) -> str:
        return "\nТак = Approve more steps. Ні = Stop and answer from current evidence."

    def build_action_format_recovery_prompt(
        self,
        header: str,
        *,
        forbid_audit_markers: bool = False,
        state_changing_only: bool = False,
        single_readonly_action_only: bool = False,
    ) -> str:
        lines = [
            f"SYSTEM: {header}",
            "Return only valid <action> content for the next step.",
        ]
        if state_changing_only:
            lines.extend(
                [
                    "For this recovery step, return exactly one valid state-changing <action>.",
                    "Do not return read-only batching here.",
                ]
            )
        elif single_readonly_action_only:
            lines.extend(
                [
                    "For this recovery step, return EXACTLY ONE valid read-only <action>.",
                    "Do not return a batch.",
                    "Do not return multiple <action> blocks.",
                    "Make the next search/action narrower and more targeted than before.",
                ]
            )
        else:
            lines.extend(
                [
                    "For read-only investigation, multiple separate <action>...</action> blocks are allowed.",
                    "Compatible format: one <action>...</action> block may contain a JSON array of read-only action objects.",
                    "For any state-changing step, return only one valid <action>.",
                    "Do not use JSON arrays for state-changing actions.",
                ]
            )
        lines.extend(
            [
                "No prose outside <action>.",
                "If unsure, prefer separate <action> blocks.",
            ]
        )
        if forbid_audit_markers:
            lines.append("Do not output audit markers like SYSTEM_TOOL_AUDIT, TOOL_HISTORY, or <previously_performed_action>.")
        return "\n".join(lines)

    def build_missing_action_or_answer_prompt(self) -> str:
        return (
            "SYSTEM: You analyzed the next step but did not return a valid action or a final answer.\n"
            "Return the next valid <action> now, or provide a final plain-text answer if no tool is needed.\n"
            "Do not output TOOL_HISTORY, SYSTEM_TOOL_AUDIT, or <previously_performed_action>.\n"
            "Do not output <think> without an action or final answer."
        )

    def build_intent_only_deadend_prompt(self) -> str:
        return (
            "SYSTEM: You returned an <intent> block but did not provide the next valid step.\n"
            "If tool use is needed, return the next valid <action> now.\n"
            "If no tool is needed, return a final plain-text answer now.\n"
            "Do not repeat the same <intent> again unless you are explicitly retrying or replacing it.\n"
            "Do not output TOOL_HISTORY, SYSTEM_TOOL_AUDIT, or <previously_performed_action>."
        )

    def typed_recovery_header(self, stop_info: dict | None) -> str:
        stop_info = stop_info or {}
        reason = str(stop_info.get("reason") or "").strip()
        code = str(stop_info.get("error_code") or "").strip()
        message_key = resolve_intent_message_key(stop_info)
        next_actions = stop_info.get("next_actions") or []
        if not isinstance(next_actions, list):
            next_actions = []
        next_hint = f"\nAllowed next actions: {', '.join(next_actions)}." if next_actions else ""

        registry_rendered = render_intent_message(message_key, next_hint=next_hint, default="")
        if registry_rendered:
            return registry_rendered

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
            "repeating_no_progress": "You are repeating actions without measurable progress.",
            "repeating_failure": "You are repeating failing actions without changing strategy.",
            "too_broad_search": "Your last search was too broad or too noisy.",
            "low_value_broad_search_repeat": "You are repeating broad low-value searches.",
            "history_self_reference_hit": "Your search matched only self-referential artifact/history content, which is not real usage evidence.",
            "search_batch_aborted_after_first_action": "Your read-only search batch was aborted after the first action. Do not send another broad search batch.",
            "intent_force_plaintext_completion": "User requested final answer from already gathered evidence. Stop tool use now.",
            "full_read_confirmation_required": "Full read of a very large file requires explicit confirmation. Prefer skeleton or chunked read first.",
        }
        if reason in headers:
            return headers[reason] + next_hint
        if code == "FILE_ALREADY_AVAILABLE_USE_EXISTING_CONTEXT":
            return "This file is already available in history at the current version. Re-reading it without a specific reason is blocked." + next_hint
        if code == "LIST_DIRECTORY_MISSING_PATH":
            return "list_directory requires an explicit path. Root fallback is blocked in recovery." + next_hint
        if code == "TOO_BROAD_SEARCH":
            return (
                "Your search was too broad or too noisy. "
                "Return one narrower search only. Prefer a more specific pattern, a narrower path, or stricter excludes."
            ) + next_hint
        if code == "LOW_VALUE_BROAD_SEARCH_REPEAT":
            return (
                "You are repeating broad low-value searches. "
                "Do not batch more broad searches. Return one targeted search or conclude with current evidence."
            ) + next_hint
        if code == "HISTORY_SELF_REFERENCE_HIT":
            return (
                "Your search matched only self-referential artifact/history content. "
                "That is not real usage evidence. Return one narrower search that excludes artifact files."
            ) + next_hint
        if code == "SEARCH_BATCH_ABORTED_AFTER_FIRST_ACTION":
            return (
                "Your previous read-only search batch was aborted after the first action. "
                "Do not send another batch. Return exactly one narrower search_content action."
            ) + next_hint
        if code == "INTENT_FORCE_PLAINTEXT_COMPLETION":
            return (
                "User requested final answer from already gathered evidence. "
                "Do not use more tools under this intent contract now. Return plain text only."
            ) + next_hint
        if code == "FULL_READ_CONFIRMATION_REQUIRED":
            return (
                "Full read of a very large file requires explicit confirmation. "
                "Prefer read_file_skeleton first, or use read_chunk with line ranges. "
                "If full content is truly required, repeat read_file with confirm_large_read=true."
            ) + next_hint
        return "Previous action violated orchestration policy. Choose a different strategy and follow the required next actions." + next_hint

    def build_typed_stop_recovery_prompt(self, stop_info: dict | None) -> str:
        stop_info = stop_info or {}
        reason = str(stop_info.get("reason") or "").strip()
        state_changing_only = reason in {"repeating_failure", "repeating_no_progress", "observe_budget_exhausted"}
        single_readonly_action_only = reason in {
            "too_broad_search",
            "low_value_broad_search_repeat",
            "history_self_reference_hit",
            "search_batch_aborted_after_first_action",
            "planned_turn_working_material_too_large",
            "planned_full_read_too_large",
            "intent_blocked_action_signature",
        }
        prompt = self.build_action_format_recovery_prompt(
            self.typed_recovery_header(stop_info),
            forbid_audit_markers=True,
            state_changing_only=state_changing_only,
            single_readonly_action_only=single_readonly_action_only,
        )
        if reason in {"planned_turn_working_material_too_large", "planned_full_read_too_large", "intent_blocked_action_signature"}:
            active_intent = getattr(self.state, "active_intent", None)
            active_goal = getattr(active_intent, "goal", "") if active_intent is not None else ""
            prompt += (
                "\nDo NOT send another <intent> block now."
                f"\nCurrent contract goal remains the same: {active_goal}."
                "\nContinue under the current intent contract."
                "\nContinue toward the same goal using the updated allowed tools and constraints."
                "\nDo not repeat the blocked or low-value action pattern."
                "\nDo not restart the task from the beginning. Continue from already gathered evidence under the same contract."
                "\nReturn EXACTLY ONE materially different read-only action."
            )
        if single_readonly_action_only:
            prompt += (
                "\nFor search_content, prefer explicit import patterns, narrower directories, "
                "or stronger exclude_dirs. Avoid repeating the same broad batch."
            )
        return prompt

    def build_plain_text_completion_prompt(self, sm, stop_info: dict | None) -> str:
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

    def build_intent_transition_rejected_prompt(self, reason, allowed_actions=None, goal=""):
        stop_info = {
            "reason": reason,
            "recoverable": True,
            "next_actions": allowed_actions or [],
        }
        if goal:
            stop_info["goal"] = goal
        return self.build_orchestrated_recovery_prompt(stop_info)

    def build_intent_completed_prompt(self) -> str:
        return (
            "SYSTEM: The current intent contract is completed.\n"
            "Return a concise plain-text answer for the user using the evidence already gathered.\n"
            "Do not emit another <intent> block.\n"
            "Do not emit any <action> block."
        )

    def build_approved_changed_goal_prompt(self) -> str:
        return (
            "SYSTEM: User explicitly approved the changed intent contract goal for this one transition.\n"
            "The new intent contract is now active.\n"
            "Return the next valid <action> or a final plain-text answer if no tool is needed.\n"
            "Do not emit another cosmetic relabel."
        )

    def build_keep_original_goal_prompt(
        self,
        reason: str,
        allowed_actions: list[str] | None = None,
        *,
        goal: str | None = None,
    ) -> str:
        return (
            self.build_reuse_current_intent_prompt(
                reason,
                allowed_actions,
                goal=goal,
            )
            + "\nKeep the original goal. Do NOT rewrite or narrow the current contract goal."
            + "\nReturn the next valid <action> that directly serves the current goal."
        )

    def build_retry_recovery_query(self, recovery_actions: list[str] | None = None) -> str:
        recovery_actions = recovery_actions or []
        if recovery_actions:
            return (
                "SYSTEM: Retry with recovery strategy.\n"
                f"Preferred actions: {', '.join(recovery_actions)}.\n"
                "Do not repeat the previous action with the same arguments."
            )
        return (
            "SYSTEM: Retry with a different strategy and different arguments.\n"
            "Do not repeat the previous action call."
        )

    def build_open_search_recovery_query(self, error_details: str) -> str:
        return (
            "SYSTEM: Use a file discovery recovery step now.\n"
            "Call list_directory or search_files before any write operation.\n"
            f"Last error: {error_details}"
        )

    def build_malformed_read_file_payload_prompt(self) -> str:
        return (
            "SYSTEM: Your last read_file call used invalid payload.\n"
            "Return EXACTLY ONE valid read_file action now.\n"
            "Required format:\n"
            '<action type="read_file">{"path":"relative/or/absolute/path"}</action>\n'
            "Include a top-level `path` field.\n"
            "Do not nest JSON under `command`.\n"
            "Do not add any other action in this reply."
        )

    def build_malformed_read_file_skeleton_payload_prompt(self) -> str:
        return (
            "SYSTEM: Your last read_file_skeleton call used invalid payload.\n"
            "Return EXACTLY ONE valid read_file_skeleton action now.\n"
            "Required format:\n"
            '<action type="read_file_skeleton">{"path":"relative/or/absolute/path"}</action>\n'
            "Include a top-level `path` field.\n"
            "Do not nest JSON under `command`.\n"
            "Do not add any other action in this reply."
        )

    def build_malformed_read_chunk_payload_prompt(self) -> str:
        return (
            "SYSTEM: Your last read_chunk call used invalid payload.\n"
            "Return EXACTLY ONE valid read_chunk action now.\n"
            "Preferred format:\n"
            '<action type="read_chunk">{"path":"relative/or/absolute/path","start_line":1304,"end_line":1500}</action>\n'
            "Use top-level `path`, `start_line`, and `end_line` fields.\n"
            "Do not nest JSON under `command`.\n"
            "Do not add any other action in this reply.\n"
            "Do not switch back to guessed byte offsets unless they are explicitly required."
        )

    def build_orchestrated_recovery_prompt(self, stop_info: dict | None) -> str:
        stop_info = stop_info or {}
        reason = str(stop_info.get("reason") or "")

        if self._should_prefer_current_intent_recovery(stop_info):
            return self.build_keep_current_intent_recovery_prompt(stop_info)

        if reason in {
            "cross_target_read_without_reason",
            "recover_repeated_fingerprint",
            "policy_denied",
            "malformed_read_file_payload",
            "malformed_read_file_skeleton_payload",
            "malformed_read_chunk_payload",
            "too_broad_search",
            "low_value_broad_search_repeat",
            "history_self_reference_hit",
            "search_batch_aborted_after_first_action",
            "planned_turn_working_material_too_large",
            "planned_full_read_too_large",
            "turn_working_material_too_large",
            "suspect_intent_goal_drift",
        }:
            return self.build_typed_stop_recovery_prompt(stop_info)

        required = stop_info.get("next_actions") or []
        required_hint = f"Required next actions: {', '.join(required)}.\n" if required else ""
        return (
            "SYSTEM: Previous action violated orchestration policy.\n"
            f"{required_hint}"
            "Choose a different strategy and return the next valid <action>."
        )