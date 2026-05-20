"""Recovery and retry prompt builders."""

from __future__ import annotations

from ..runtime.filesystem_path_failure import INVALID_PATH_ERROR_CODE, restore_filesystem_path_failure


class RecoveryPromptBuilderMixin:
    def build_repeated_thinking_without_valid_output_prompt(self, stop_info: dict | None = None) -> str:
        reason = str((stop_info or {}).get("reason") or "repeated_thinking_without_valid_output").strip()
        return (
            "SYSTEM: Enough internal planning/thinking for now.\n"
            f"Reason: {reason}.\n"
            "Your recent replies contained substantial <think> content, but did not produce a valid executable or final output.\n"
            "The NEXT reply must be immediately valid.\n"
            "Valid outputs now are:\n"
            "- one valid <action>\n"
            "- one valid read-only batch of tool calls if batching is allowed\n"
            "- one plain-text final answer\n"
            "- one valid <intent> request/transition if runtime truly requires it\n"
            "- or a valid combination of thinking plus memory/subgoal tags plus one of the allowed outputs above\n"
            "If you use <think> or emit memory/subgoal tags, close the durable-state checkpoint with <memory_update_done /> before the action or final answer.\n"
            "Do NOT return another planning/thinking-only reply.\n"
            "Do NOT restate the next step without performing it.\n"
            "Return a valid output now."
        )

    def build_keep_current_intent_recovery_prompt(self, stop_info: dict | None) -> str:
        ctx = self._recovery_context(stop_info)
        stop_info = ctx.to_stop_info()
        reason = ctx.reason.strip()
        allowed_actions = self._current_intent_allowed_actions()
        goal = self._current_intent_goal()
        next_hint = f"\nAllowed actions under the CURRENT intent contract: {', '.join(allowed_actions)}." if allowed_actions else ""

        message_defaults = {
            "intent_step_limit_soft_exceeded": "Continue under the current intent contract.",
            "user_approved_more_steps_after_hard_limit": "Continue under the current intent contract.",
            "intent_blocked_action_signature": "A specific action is blocked, but the current intent contract is still valid.",
            "action_not_allowed_in_phase": "The current intent contract remains valid, but a legacy recovery suggestion conflicted with it.",
            "retry_or_continuation_after_failure": "The previous step failed, but the current intent contract still remains valid.",
            "unnecessary_intent_reactivation_or_replace": "The active intent contract is already present and remains active by default until valid conditions from system prompt met.",
            "suspect_intent_relabel_repeat": "The current intent contract is still valid.",
        }
        message_keys = {
            "intent_step_limit_soft_exceeded": "keep_current_intent_soft_limit",
            "user_approved_more_steps_after_hard_limit": "keep_current_intent_after_user_more_steps",
            "intent_blocked_action_signature": stop_info.get("message_key") or "blocked_action_keep_current_intent",
            "action_not_allowed_in_phase": "keep_current_intent_conflicting_phase_actions",
            "retry_or_continuation_after_failure": stop_info.get("message_key") or "blocked_action_keep_current_intent",
            "unnecessary_intent_reactivation_or_replace": stop_info.get("message_key") or "unnecessary_intent_reactivation_or_replace",
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
                "Priority now is to finish quickly from the strongest evidence already gathered.",
                "Continue from the strongest valid state already reached under the same contract.",
                "Do not restart the task from the beginning unless a concrete missing detail is identified or runtime explicitly changes the contract.",
                "Do not repeat already completed investigation.",
                "Do not reopen exploration just because continuation is allowed.",
                "Do not keep the intent open if the goal is already answerable.",
                "Do not repeat the action pattern that was just blocked or low-value.",
            ]
        )

        if reason == "user_approved_more_steps_after_hard_limit":
            base_lines.extend(
                [
                    "User approved additional budget for this same intent contract.",
                    "Continue from current evidence under the same contract.",
                    "This approval does NOT mean search again by default.",
                    "It means continue this same work from where you validly left off and finish as quickly as the evidence allows.",
                    "If the goal is already ready to answer, use the approval to finish cleanly: complete the intent and answer now.",
                    "Otherwise perform only the already-prepared next valid step under the same intent, with completion preferred over renewed exploration.",
                    "Return the next valid output.",
                ]
            )
        elif reason == "intent_step_limit_soft_exceeded":
            base_lines.extend(
                [
                    "First decide whether current evidence is already sufficient.",
                    "If yes, complete the intent and return a final plain-text answer now.",
                    "If not, continue only from the last valid point already reached under this same intent and prefer the shortest path to completion.",
                    "Do not interpret this soft-limit continuation as default permission to keep searching.",
                    "Prefer exactly one next <action> only if a concrete missing detail still requires tool use, and use it to finish rather than to reopen exploration.",
                    "If the user explicitly asks to continue this SAME line of work after a near-final answer and this contract budget is exhausted or about to be exhausted, do not silently keep stepping under the same budget.",
                    "In that case, emit a formal <intent mode=\"reuse\"> request for the SAME active intent_id with requested_steps to refresh the budget for this same intent lineage.",
                ]
            )
        elif reason == "intent_blocked_action_signature":
            blocked_reason = str((stop_info.get("policy_metadata") or {}).get("blocked_reason") or "")
            if blocked_reason:
                base_lines.append(f"The blocked action pattern failed because of: {blocked_reason}.")
            base_lines.extend(
                [
                    "[RECOVERY_SCOPE]",
                    "This instruction applies only to the next corrective step after a blocked action pattern under the current intent.",
                    "[NEXT_STEP_RULE]",
                    "Avoid repeating the blocked action shape.",
                    "Choose one allowed action that materially changes the evidence path, or answer directly if current evidence is sufficient.",
                    "Return the next valid output under the current contract.",
                    "[EXIT_CONDITION]",
                    "After one successful progress-making step or a final answer, resume normal intent execution.",
                ]
            )
        elif reason == "retry_or_continuation_after_failure":
            details = stop_info.get("error_details") or {}
            mismatch_type = str(details.get("mismatch_type") or "")
            failed_action = str((stop_info.get("command") or {}).get("type") or details.get("failed_action_type") or "").strip()
            structural_recovery_available = "extract_symbol" in allowed_actions and "replace_symbol" in allowed_actions
            if mismatch_type:
                base_lines.append(f"Last recoverable failure detail: {mismatch_type}.")
            if failed_action:
                base_lines.append(f"Last failed tool: {failed_action}.")
            base_lines.extend(
                [
                    "Prefer a deterministic recovery step inside the SAME current intent contract.",
                    "Do not open a new intent contract unless the work truly changed.",
                ]
            )
            if structural_recovery_available:
                base_lines.extend(
                    [
                        "If the previous edit_file failed because the search block was not unique, stale, missing, or whitespace did not match, prefer structural recovery for supported symbol-sized changes: use extract_symbol to retrieve the exact current symbol, then use replace_symbol with replacement content that preserves the same symbol name/kind.",
                        "Do not treat an edit_file mismatch as a replace_symbol failure. If the failed tool was edit_file, replace_symbol remains a valid recovery candidate when the active contract allows it.",
                        "Use read_chunk/search_content before edit_file only when the change is not symbol-sized, the symbol is unsupported or ambiguous, or replace_symbol is not appropriate.",
                    ]
                )
            else:
                base_lines.append(
                    "If the previous edit failed because the search block was not unique or whitespace did not match, first retrieve the exact target block from file content, then retry edit_file with verbatim exact text, or use write_file with full validated content."
                )
            base_lines.extend(
                [
                    "For edit_file, copy search_text verbatim from the most recent exact file-content tool result.",
                    "If the same file was already modified earlier in this flow, treat pre-edit blocks from that file as stale and reread the current target block before another edit_file call.",
                    "Do not reconstruct indentation or whitespace from memory.",
                    "Return the next valid output.",
                    "If tool use is needed, return exactly one valid <action>.",
                ]
            )
        elif reason == "action_not_allowed_in_phase":
            base_lines.extend(
                [
                    "Use the CURRENT intent contract action family instead of switching to a conflicting legacy recovery action set.",
                    "Return the next valid output that directly serves the current goal.",
                    "If tool use is needed, return the next valid <action>.",
                ]
            )
        elif reason == "unnecessary_intent_reactivation_or_replace":
            base_lines.extend(
                [
                    "The active intent contract is already shown in the system prompt and remains active by default.",
                    "It will remain active until runtime explicitly completes, replaces, rejects, or closes it for a valid listed reason.",
                    "There is no valid reason to reactivate or replace this same active intent contract now.",
                    "Do not emit another <intent mode=\"activate\"> or <intent mode=\"replace\"> for this same contract.",
                    "Return the next valid output under the current contract.",
                    "If tool use is needed, return the next valid <action>.",
                    "If the evidence is already sufficient, return a plain-text answer.",
                ]
            )
        elif reason == "suspect_intent_relabel_repeat":
            base_lines.extend(
                [
                    "There is no valid reason to relabel or replace the contract now.",
                    "Do not treat the next local step as a new intent.",
                    "Do not restart the same investigation path from the beginning.",
                    "Continue from the strongest evidence already gathered under the current contract.",
                    "Return the next valid output that directly continues the current work.",
                ]
            )
        else:
            base_lines.extend(
                [
                    "Choose the next step that most increases progress toward the goal.",
                    "Return the next valid output under the current contract.",
                    "If tool use is needed, return the next materially different <action>.",
                    "If the goal can already be answered, return a plain-text answer instead.",
                ]
            )

        return "\n".join(base_lines)

    def build_no_active_intent_recovery_prompt(self, stop_info: dict | None) -> str:
        ctx = self._recovery_context(stop_info)
        stop_info = ctx.to_stop_info()
        reason = ctx.reason.strip()
        required = stop_info.get("next_actions") or []
        source = str(ctx.next_actions_source or "").strip().lower()
        if source == "recommended" and required:
            required_hint = (
                f"Runtime-suggested next actions: {', '.join(required)}.\n"
                "These are recovery hints, not proof that contract-scoped tool use is already allowed."
            )
        else:
            required_hint = f"Allowed next actions: {', '.join(required)}." if required else "Allowed next actions: none."
        return (
            "SYSTEM: No active intent contract is currently in force.\n"
            f"Reason: {reason}.\n"
            f"{required_hint}\n"
            "Continue from already gathered evidence and conclusions. Do not restart the task from zero.\n"
            "If the next step needs governed multi-step execution, activate a formal <intent> now.\n"
            "Until activation succeeds, do not assume contract-scoped permissions or allowed_actions.\n"
            "If current evidence is already sufficient, return a plain-text answer instead of more tool use.\n"
            "Return the next valid step accordingly."
        )

    def _should_prefer_current_intent_recovery(self, stop_info: dict | None) -> bool:
        ctx = self._recovery_context(stop_info)
        return self.recovery_policy_resolver.should_prefer_current_intent_recovery(
            ctx,
            active_intent=self._current_active_intent(),
        )

    def build_typed_stop_recovery_prompt(self, stop_info: dict | None) -> str:
        ctx = self._recovery_context(stop_info)
        stop_info = ctx.to_stop_info()
        reason = str(ctx.reason or "").strip()
        if reason == "missing_executable":
            return self.build_missing_executable_prompt(stop_info)
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
            str(self.typed_recovery_header(stop_info) or ""),
            forbid_audit_markers=True,
            state_changing_only=state_changing_only,
            single_readonly_action_only=single_readonly_action_only,
        ) or ""
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
                "\nReturn the next valid output under the current contract."
                "\n[RECOVERY_SCOPE] This instruction applies only to the next corrective step for this blocked or oversized read-only action pattern under the current intent."
                "\n[NEXT_STEP_RULE] Use a materially different read-only action only if tool use is still needed. Follow the current contract and updated runtime constraints."
                "\n[EXIT_CONDITION] After a successful corrective step, resume normal intent execution. If current evidence is already sufficient, return a plain-text answer instead."
            )
        if reason in {"too_broad_search", "low_value_broad_search_repeat"}:
            prompt += (
                "\nYour last search was too broad or a low-value repeat. Unbounded searches are expensive and often noisy."
                "\nA single bounded reconnaissance search is allowed when exact files are unknown. A bounded search must use at least two of: a specific path, a specific pattern, `include_extensions`, or `exclude_dirs`."
                "\nIf the previous search already returned candidate paths, the next step must be a targeted read (`read_file`, `read_chunk`, `read_file_skeleton`) on those paths, not another broad search."
                "\nDo not repeat the same root-level or weakly bounded `search_content` query."
                "\nIf you still need search, make the next `search_content` materially narrower than the failed search."
                "\nTo narrow your next search and make it a valid bounded reconnaissance step:"
                "\n- Use a more specific path instead of the root."
                "\n- Use a more specific pattern (e.g., an exact symbol, class name, or function name)."
                "\n- Use `include_extensions` to limit the search to relevant file types (e.g., `.py`, `.kt`)."
                "\n- Exclude noisy directories like `docs`, `build`, `.git`, or log files unless they are the explicit target."
                "\nCode is primary evidence. Documentation (`docs/`) can be used to discover terms, but should be treated as secondary evidence unless the user explicitly asked for it."
                "\nSpend the next action on the shortest path to concrete evidence."
            )
        elif single_readonly_action_only:
            if reason == "planned_full_read_too_large":
                prompt += (
                    "\nFor supported source files (.kt/.py) and symbol-sized work, prefer read_file_skeleton or extract_symbol over large read_chunk ranges."
                    "\nIf the target symbol name is known or inferable from the task, return exactly one extract_symbol action as the next read-only step."
                    "\nUse read_chunk only when the needed target is not a supported symbol, is ambiguous, or requires a precise non-symbol block."
                )
            prompt += (
                "\nFor search_content, prefer explicit import patterns, narrower directories, "
                "or stronger exclude_dirs. Avoid repeating the same broad batch."
            )
        return prompt

    def _plain_text_completion_kind(self, sm) -> str:
        task_kind = getattr(sm, "task_kind", None)
        task_kind_value = str(getattr(task_kind, "value", str(task_kind or "")) or "").strip().upper()

        # HYBRID is a stronger display signal than an INVESTIGATE active intent:
        # it means the stop came from a mixed inspect/modify state machine.
        if task_kind_value == "HYBRID" or task_kind_value.endswith(".HYBRID") or "HYBRID" in task_kind_value:
            return "HYBRID"

        active_intent = self._current_active_intent()
        if active_intent is not None:
            active_type = str(getattr(active_intent, "intent_type", "") or "").strip().upper()
            if active_type:
                return active_type

        last_completed_intent_type = str(getattr(self.state, "last_completed_intent_type", "") or "").strip().upper()
        if last_completed_intent_type:
            return last_completed_intent_type

        # FIXME:
        # task_kind is only a fallback display heuristic here. Plain-text
        # completion should prefer the current accepted contract type whenever it
        # exists, because task_kind can be noisier than the runtime contract.
        task_kind = getattr(sm, "task_kind", None)
        return getattr(task_kind, "value", str(task_kind or "UNKNOWN"))

    def build_plain_text_completion_prompt(self, sm, stop_info: dict | None) -> str:
        ctx = self._recovery_context(stop_info)
        kind = self._plain_text_completion_kind(sm)
        reason = ctx.reason
        target = getattr(sm, "target_file", None) or "<unknown>"
        route_hint = ""
        if hasattr(sm, "_inspection_route_hint"):
            try:
                route_hint = sm._inspection_route_hint() or ""
            except Exception:
                route_hint = ""
        parts = [
            "SYSTEM: Stop tool use now.",
            f"Task kind: {kind}.",
            f"Recovery reason: {reason}.",
            f"Current target: {target}.",
            "Return a concise plain-text answer in the user's language using only the evidence already gathered.",
            "Do not output any <action> block.",
            "Do not ask to inspect more files.",
            "Answer the user's question directly and, if relevant, give one concrete next step.",
        ]
        if str(kind or "").strip().upper() == "MODIFY":
            parts.extend(
                [
                    "Because this is MODIFY work, the final answer must include:",
                    "- exact file paths changed in this run",
                    "- a short statement of what changed",
                    "- whether git diff was checked",
                    "- whether build/tests were run",
                    "- any unverified assumption or residual risk",
                    "If git diff was not checked, say so explicitly.",
                    "If build/tests were not run, say so explicitly.",
                    "Do not imply full verification without tool evidence.",
                ]
            )
        missing_exec = str(ctx.error_details.get("missing_executable") or "").strip()
        if missing_exec in {"gradle", "gradlew"}:
            parts.append(
                "If build verification was blocked by missing Gradle/gradlew, say explicitly that build/tests were not run because Gradle is unavailable in this environment."
            )
        resumable_intent_id = str(getattr(self.state, "last_resumable_intent_id", "") or "").strip()
        if resumable_intent_id:
            parts.append(
                f"The current active contract will be closed after this final plain-text answer. If the user later asks to continue the SAME work, request <intent mode=\"reuse\"> for intent_id {resumable_intent_id} instead of silently continuing the exhausted contract."
            )
        if route_hint:
            parts.append(route_hint)
        return "\n".join(parts)

    def build_current_intent_retry_recovery_query(
        self,
        recovery_actions: list[str] | None = None,
        *,
        error_code: str = "",
        error_details: dict | None = None,
        command: dict | None = None,
    ) -> str:
        recovery_actions = [str(a) for a in (recovery_actions or []) if str(a or "").strip()]
        stop_info = {
            "reason": "retry_or_continuation_after_failure",
            "recoverable": True,
            "error_code": error_code,
            "error_details": dict(error_details or {}),
            "command": dict(command or {}),
            "next_actions": list(recovery_actions),
            "intent_allowed_actions": list(recovery_actions),
            "next_actions_source": "intent",
        }
        code = str(error_code or "").strip().upper()
        details = error_details or {}
        mismatch_type = str(details.get("mismatch_type") or "")
        path = str((command or {}).get("path") or details.get("path") or "..." or "").strip() or "..."
        path_failure = restore_filesystem_path_failure(command, details)
        if path_failure is not None or code == INVALID_PATH_ERROR_CODE:
            path_failure = path_failure or restore_filesystem_path_failure(
                command,
                {
                    **dict(details),
                    "recovery_kind": details.get("recovery_kind") or "INVALID_ACTION_PATH_RECOVERY",
                    "invalid_path": details.get("invalid_path") or path,
                    "failed_action_type": details.get("failed_action_type") or str((command or {}).get("type") or ""),
                    "known_valid_roots": list(details.get("known_valid_roots") or ["."]),
                    "recommended_next_actions": list(details.get("recommended_next_actions") or []),
                    "message": details.get("message") or self._short_failed_error(stop_info),
                },
            )
            known_root = "."
            if path_failure is not None and path_failure.known_valid_roots:
                known_root = str(path_failure.known_valid_roots[0] or ".").strip() or "."
            failed_path = path_failure.invalid_path if path_failure is not None else path
            failed_action = path_failure.failed_action_type if path_failure is not None else str((command or {}).get("type") or "action")
            return self._render_strict_failure_recovery(
                stop_info,
                fact=f"{failed_action} failed: {self._short_failed_error(stop_info)}",
                gap=(
                    f"The previous filesystem path is invalid: {failed_path}. "
                    "Do not reuse the failed path. "
                    "Do not derive sibling, child, or package paths from the failed path. "
                    "Do not guess Android/Kotlin package roots. "
                    "Do not substitute another guessed replacement path. "
                    "First prove a valid root with an allowed read-only action."
                ),
                next_step=(
                    f"first establish a valid root with list_directory on {known_root}, "
                    "or search_files/search_content from '.' before any further bounded search or read"
                ),
                action_block=f'<action>{{"type":"list_directory","path":"{known_root}"}}</action>',
                safe_recovery_action="list_directory",
            )
        if code in {"MISSING_FILE_CONTENT_BLOCK", "FILE_CONTENT_MUST_FOLLOW_ACTION"}:
            full_rewrite_allowed = self._full_rewrite_allowed(stop_info)
            if not full_rewrite_allowed and self._is_existing_source_file(path, stop_info):
                return self._render_strict_failure_recovery(
                    stop_info,
                    fact=f"write_file_block failed: {self._short_failed_error(stop_info)}",
                    gap=(
                        "Do not retry full-file rewrite yet. Use git_diff/fresh exact read and targeted edit_file unless full rewrite policy is satisfied. "
                        "Required order if a block rewrite later becomes valid: <action>...</action> immediately followed by <file_content>...</file_content>."
                    ),
                    next_step="use git_diff or fresh exact read of the current file, then targeted edit_file",
                    action_block='<action>{"type":"git_diff","path":"' + path + '"}</action>',
                    safe_recovery_action="git_diff_then_targeted_edit_file",
                )
            action_block = (
                '<action>\n'
                '{\n'
                '  "type": "write_file_block",\n'
                f'  "path": "{path}",\n'
                '  "overwrite": true\n'
                '}\n'
                '</action>'
            )
            return self._render_strict_failure_recovery(
                stop_info,
                fact=f"write_file_block failed: {self._short_failed_error(stop_info)}",
                gap=(
                    "The <file_content> block must appear immediately after </action>; do not put <file_content> inside <action>, "
                    "before <action>, or repeat the same malformed shape."
                ),
                next_step="repeat write_file_block with action first and raw file_content immediately after",
                action_block=action_block,
                trailing_blocks=["<file_content>\nraw content\n</file_content>"],
                safe_recovery_action="write_file_block_with_immediate_file_content",
            )
        if code == "MALFORMED_READ_CHUNK_PAYLOAD":
            return self._render_strict_failure_recovery(
                stop_info,
                fact=f"read_chunk failed: {self._short_failed_error(stop_info)}",
                gap=(
                    "Use top-level path plus start_line/end_line integers or start_byte/end_byte integers; "
                    "do not nest payload under command or repeat the same malformed shape."
                ),
                next_step="send one corrected read_chunk payload",
                action_block=(
                    '<action>{"type":"read_chunk","path":"'
                    + path
                    + '","start_line":1304,"end_line":1500}</action>'
                ),
                safe_recovery_action="corrected_read_chunk",
            )
        if code == "CONTENT_TOO_LARGE_FOR_JSON_FILE_ACTION":
            action_block = (
                '<action>{"type":"write_file_block","path":"'
                + path
                + '","overwrite":true}</action>'
            )
            return self._render_strict_failure_recovery(
                stop_info,
                fact=f"{self._short_failed_tool(stop_info)} failed: {self._short_failed_error(stop_info)}",
                gap="Use write_file_block metadata in action JSON and place raw file content immediately after </action>.",
                next_step="switch to write_file_block and, if needed, append_file_block chunks",
                action_block=action_block,
                trailing_blocks=["<file_content>\nraw content\n</file_content>"],
                safe_recovery_action="write_file_block_with_followup_file_content",
            )
        if code == "CONTENT_TOO_LARGE_FOR_JSON_FILE_ACTION":
            pass
        if code == "VALIDATION_ERROR":
            gap = (
                "Retrieve the exact current target block from file content, copy search_text verbatim, and do not reconstruct whitespace from memory."
            )
            next_step = "read exact current block, then targeted edit_file"
            if mismatch_type == "noop_edit":
                gap = "The previous edit would not change the file; do not repeat a no-op replacement."
                next_step = "answer if no change is needed, or send an edit_file replacement that actually differs"
            elif mismatch_type in {"no_similar_block_found", "search_text_stale_or_block_modified", "whitespace_mismatch"}:
                gap = "Your search_text does not match current file; do not retry edit_file from memory."
                next_step = "use read_chunk or read_file to fetch the exact current target block, then targeted edit_file"
            elif mismatch_type == "edit_file_full_rewrite_disallowed":
                gap = "Do not simulate a full rewrite via edit_file on an existing source file."
                next_step = "read the exact smaller target block and perform one surgical edit"
            elif mismatch_type == "edit_file_crosses_import_boundary":
                gap = "Do not inject imports by replacing a class or function anchor."
                next_step = "read the current package/import header and edit that exact header block separately"
            return self._render_strict_failure_recovery(
                stop_info,
                fact=f"{self._short_failed_tool(stop_info)} failed: {self._short_failed_error(stop_info)}",
                gap=gap,
                next_step=next_step,
                action_block=f'<action>{{"type":"read_chunk","path":"{path}","start_line":1,"end_line":80}}</action>',
                safe_recovery_action="fresh_exact_read_then_targeted_edit_file",
            )
        if code == "MISSING_EXECUTABLE":
            missing_exec = str(details.get("missing_executable") or "")
            gap = "Do not retry the same shell command; use an available alternative or report verification blocked."
            next_step = "choose a different available tool or plain-text handoff"
            if missing_exec in {"gradle", "gradlew"}:
                gap = "Gradle verification is unavailable here; do not keep retrying build commands."
                next_step = "report build/tests blocked or use another installed verification tool"
            return self._render_strict_failure_recovery(
                stop_info,
                fact=f"run_shell failed: {self._short_failed_error(stop_info)}",
                gap=gap,
                next_step=next_step,
                action_block=self._default_action_block(recovery_actions[0] if recovery_actions else "run_shell"),
                safe_recovery_action=recovery_actions[0] if recovery_actions else "run_shell",
            )

        preferred = recovery_actions[0] if recovery_actions else "action"
        return self._render_strict_failure_recovery(
            stop_info,
            fact=f"{self._short_failed_tool(stop_info)} failed: {self._short_failed_error(stop_info)}",
            gap="do not repeat the same invalid shape or identical failing arguments",
            next_step=f"use one materially different safe next operation: {preferred}",
            action_block=self._default_action_block(preferred),
            safe_recovery_action=preferred,
        )

    def build_missing_plan_review_after_state_change_prompt(
        self,
        *,
        action_type: str = "",
        target: str = "",
        reason: str = "",
        action_effects: list[str] | None = None,
    ) -> str:
        action_type = str(action_type or "").strip()
        target = str(target or "").strip()
        reason = str(reason or "state_changing_action_committed").strip()
        effects = [str(effect or "").strip() for effect in (action_effects or []) if str(effect or "").strip()]
        previous = action_type or "state-changing action"
        if target:
            previous = f"{previous} on {target}"
        effect_line = f"Previous action effects: {', '.join(effects)}.\n" if effects else ""
        return (
            "SYSTEM: Action was not executed. A previous state-changing action succeeded, so the active plan/subgoal board must be reviewed before another tool action.\n"
            f"Reason: {reason}.\n"
            f"Previous completed action: {previous}.\n"
            f"{effect_line}"
            "[RECOVERY_SCOPE]\n"
            "This applies only to the next response after a state-changing action.\n"
            "[NEXT_STEP_RULE]\n"
            "Do not emit any <action>.\n"
            "Review current plan and sub-goals. Emit only necessary clarification of them or their status if needed, and always end with a valid plan review checkpoint:\n"
            "<plan_review_done />\n"
            "If the previous action satisfied a subgoal, update it using the existing <subgoal ... /> protocol, preferably action=\"mark_done\" with concrete evidence before <plan_review_done />.\n"
            "[EXIT_CONDITION]\n"
            "After this checkpoint, normal action output may resume.\n"
            "Do not repeat the same edit just because the old subgoal text still says to make it.\n"
            "Do not automatically complete the whole intent unless the goal is actually complete.\n"
            "Do not suppress legitimate verification or a distinct follow-up edit."
        )

    def build_current_intent_hard_exhausted_action_prompt(self) -> str:
        return (
            "SYSTEM: Action was not executed. The current intent hard step budget is exhausted, so normal tool actions are forbidden until the intent is continued or closed.\n"
            "Reason: current_intent_hard_exhausted.\n"
            "[RECOVERY_SCOPE]\n"
            "This applies only to the next response while the current intent is hard-exhausted.\n"
            "[NEXT_STEP_RULE]\n"
            "Do not emit any normal <action>.\n"
            "Choose one allowed continuation:\n"
            "1. request intent reuse with switch_reason=\"current_intent_exhausted\";\n"
            "2. complete the current intent if the goal is done;\n"
            "3. provide a concise plain-text handoff/status if user input is needed.\n"
            "[EXIT_CONDITION]\n"
            "After the intent is reused, completed, or handed off, normal execution rules resume according to the new state."
        )

    def build_missing_executable_prompt(self, stop_info: dict | None) -> str:
        ctx = self._recovery_context(stop_info)
        return self.build_current_intent_retry_recovery_query(
            self._current_intent_allowed_actions() or ["run_shell"],
            error_code="MISSING_EXECUTABLE",
            error_details=ctx.error_details,
            command=ctx.command,
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
        return self.build_current_intent_retry_recovery_query(
            ["read_chunk"],
            error_code="MALFORMED_READ_CHUNK_PAYLOAD",
            error_details={"path": "relative/or/absolute/path"},
            command={"type": "read_chunk", "path": "relative/or/absolute/path"},
        )

    def build_repeated_malformed_read_chunk_payload_prompt(self, allowed_actions=None, goal: str = "") -> str:
        filtered = []
        for action in list(allowed_actions or []):
            action_value = str(action or "").strip()
            if action_value and action_value != "read_chunk" and action_value not in filtered:
                filtered.append(action_value)
        allowed_text = ", ".join(filtered) if filtered else "plain-text answer"
        goal_text = str(goal or "").strip()
        goal_line = f"Current intent goal remains the same: {goal_text}.\n" if goal_text else ""
        return (
            "SYSTEM: Your read_chunk payload was already invalid once in this turn, and the corrective retry did not recover.\n"
            "Do NOT output read_chunk again in the next reply.\n"
            f"{goal_line}"
            f"Next valid options now: {allowed_text}.\n"
            "[RECOVERY_SCOPE]\n"
            "This applies only to the next corrective step after repeated malformed read_chunk payloads.\n"
            "[NEXT_STEP_RULE]\n"
            "Choose one valid alternative from the listed options, or answer directly if current evidence is sufficient.\n"
            "Prefer search_content, read_file_skeleton, search_files, list_directory, or a narrow read-only run_shell if allowed.\n"
            "Do not re-send another malformed recovery attempt.\n"
            "[EXIT_CONDITION]\n"
            "After one valid alternative step or a final answer, resume normal execution."
        )

    def build_orchestrated_recovery_prompt(self, stop_info: dict | None) -> str:
        ctx = self._recovery_context(stop_info)
        stop_info = ctx.to_stop_info()
        reason = ctx.reason
        universe = self._intent_universe()

        if (
            reason == "retry_or_continuation_after_failure"
            and bool(stop_info.get("recoverable"))
            and str(stop_info.get("error_code") or "").strip()
        ):
            return self.build_current_intent_retry_recovery_query(
                self._current_intent_allowed_actions() or stop_info.get("next_actions") or [],
                error_code=str(stop_info.get("error_code") or ""),
                error_details=stop_info.get("error_details") or {},
                command=stop_info.get("command") or {},
            )

        if self._should_prefer_current_intent_recovery(stop_info):
            return self.build_keep_current_intent_recovery_prompt(stop_info)

        if not universe.has_active_contract and reason in {
            "retry_or_continuation_after_failure",
            "multi_step_without_intent_contract",
            "invalid_intent_json",
            "empty_intent_block",
            "intent_required_parse_error",
        }:
            return self.build_no_active_intent_recovery_prompt(stop_info)

        if reason in {
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

        intent_actions, recommended_actions, source = self._action_hints_from_stop_info(stop_info)
        if intent_actions:
            required_hint = f"Allowed actions under the CURRENT intent contract: {', '.join(intent_actions)}.\n"
        elif recommended_actions:
            required_hint = f"Runtime-suggested next actions: {', '.join(recommended_actions)}.\n"
        else:
            required = stop_info.get("next_actions") or []
            if required and source == "intent":
                required_hint = f"Allowed actions under the CURRENT intent contract: {', '.join(required)}.\n"
            elif required and source == "recommended":
                required_hint = f"Runtime-suggested next actions: {', '.join(required)}.\n"
            else:
                required_hint = f"Runtime-provided next-action hints: {', '.join(required)}.\n" if required else ""
        last_action = ""
        summarized_last_action = self._summarize_last_action()
        if summarized_last_action and summarized_last_action != "none":
            last_action = f"Last committed action: {summarized_last_action}.\n"
        return (
            "SYSTEM: Previous action violated orchestration policy.\n"
            f"{last_action}"
            f"{required_hint}"
            "Use these only as recovery hints, not as a replacement for the current contract.\n"
            "Return the next valid output."
        )
