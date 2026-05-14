"""Intent lifecycle and build-fix prompt builders."""

from __future__ import annotations

import json


class IntentPromptBuilderMixin:
    def _suggest_example_intent_id(self, goal: str, *, fallback: str = "continue_requested_modification") -> str:
        text = str(goal or "").strip().lower()
        if not text:
            return fallback
        if any(token in text for token in ("save", "saved", "document", "docs", "markdown", "md file", "write to docs")):
            return "save_requested_document"
        if any(token in text for token in ("refactor", "rewrite", "cleanup", "clean up")):
            return "continue_requested_refactor"
        return fallback

    def _build_activate_or_atomic_bundle_prompt(
        self,
        *,
        header: str,
        reason: str,
        goal: str,
        allowed_actions: list[str] | None = None,
        intent_id: str = "",
    ) -> str:
        normalized_goal = self.sanitize_intent_goal(
            goal,
            fallback="Continue multi-step code modification.",
        )
        normalized_allowed = [str(action).strip() for action in (allowed_actions or []) if str(action).strip()]
        if not normalized_allowed:
            normalized_allowed = ["read_file", "read_chunk", "read_file_skeleton", "extract_symbol", "replace_symbol", "edit_file", "write_file_block", "create_file", "run_shell"]
        example_payload = {
            "intent_id": intent_id or self._suggest_example_intent_id(normalized_goal),
            "intent_type": "MODIFY",
            "goal": normalized_goal,
            "allowed_actions": normalized_allowed,
            "safe_steps_limit": 10,
            "retry_limit": 2,
            "mode": "activate",
        }
        return (
            f"SYSTEM: {header}\n"
            f"Reason: {reason}.\n"
            "Return a valid formal intent before the action.\n"
            "\n"
            "You may either:\n"
            "1. Return only one <intent mode=\"activate\">...</intent>, then wait for acceptance.\n"
            "2. Or return an atomic bundle: one <intent mode=\"activate\">...</intent> followed by exactly one valid <action>...</action> and required <file_content> if the action needs it.\n"
            "\n"
            "If you return a bundle, the whole bundle is all-or-nothing:\n"
            "- if the intent is invalid, no intent is activated and no action is dispatched;\n"
            "- if the action is not allowed by the proposed intent, no intent is activated and no action is dispatched;\n"
            "- if <file_content> is missing or malformed for a write action, no intent is activated and no action is dispatched.\n"
            "\n"
            "Do not include visible final answer text in the same response as an action.\n"
            "Return the corrected response from the beginning.\n"
            "Example intent:\n"
            "<intent mode=\"activate\">\n"
            f"{json.dumps(example_payload, ensure_ascii=False, indent=2)}\n"
            "</intent>"
        )

    def build_intent_required_prompt(self, reason: str, allowed_actions: list[str] | None = None) -> str:
        if str(reason or "").strip() == "build_failure_requires_formal_intent":
            return self.build_build_fix_intent_required_prompt(goal=self._current_intent_goal())
        next_hint = ""
        if allowed_actions:
            next_hint = f"\nAllowed actions for the next intent contract: {', '.join(allowed_actions)}."
        if reason == "invalid_intent_resumable_available":
            resumable_intent_id = str(getattr(self.state, "last_resumable_intent_id", "") or "").strip()
            if resumable_intent_id:
                return self.build_invalid_intent_resumable_available_prompt(
                    reason,
                    resumable_intent_id=resumable_intent_id,
                    resumable_intent_type=str(getattr(self.state, "last_resumable_intent_type", "") or "").strip(),
                    resumable_goal=str(getattr(self.state, "last_resumable_intent_goal", "") or "").strip(),
                )
        universe = self._intent_universe()
        active_intent = self._current_active_intent()
        if not universe.has_active_contract or active_intent is None:
            return (
                self._build_activate_or_atomic_bundle_prompt(
                    header="A formal intent contract is required before this tool use.",
                    reason=f"{reason}{next_hint}".strip(),
                    goal=self._current_intent_goal(),
                    allowed_actions=allowed_actions,
                )
                + "\nThere is currently NO active accepted intent contract for this work.\n"
                "Continue from already gathered evidence. Do not restart the task from zero.\n"
                "Until activation succeeds, do not assume contract-scoped permissions or allowed_actions."
            )
        if reason == "exhausted_intent_requires_reuse_or_completion":
            return self.build_limit_aware_reuse_prompt(
                reason,
                self._current_intent_allowed_actions(),
                goal=self._current_intent_goal(),
            )
        return (
            "SYSTEM: A formal intent transition/update is required before further tool use.\n"
            f"Reason: {reason}.{next_hint}\n"
            "A formal runtime intent contract is already relevant for this work.\n"
            "Return the required <intent> block first, then the next valid step if needed."
        )

    def build_repeated_disallowed_action_reuse_only_prompt(
        self,
        *,
        blocked_action: str,
        intent_id: str,
        intent_type: str = "",
        goal: str = "",
        allowed_actions: list[str] | None = None,
    ) -> str:
        blocked = str(blocked_action or "action").strip() or "action"
        active_intent = self._current_active_intent()
        resolved_intent_id = str(intent_id or getattr(active_intent, "intent_id", "") or "<active_intent_id>").strip()
        resolved_intent_type = str(intent_type or getattr(active_intent, "intent_type", "") or "").strip() or "<intent_type>"
        resolved_goal = str(goal or getattr(active_intent, "goal", "") or "").strip() or "<same goal>"
        allowed = [str(action).strip() for action in (allowed_actions or []) if str(action).strip()]
        expanded_allowed = list(allowed)
        if blocked not in expanded_allowed:
            expanded_allowed.append(blocked)
        allowed_json = json.dumps(expanded_allowed or [blocked], ensure_ascii=False)
        return (
            "SYSTEM: You repeated the same disallowed action under the current intent contract.\n"
            f"Blocked action type: {blocked}.\n"
            f"Current active intent id: {resolved_intent_id}.\n"
            f"Current allowed_actions: {', '.join(allowed) if allowed else 'none'}.\n"
            "Return only a top-level <intent mode=\"reuse\">...</intent>.\n"
            "Do not include <think> or <action>.\n"
            "Do not include <action> until intent reuse is accepted.\n"
            f"Do not repeat {blocked} until reuse is accepted.\n"
            "Use this shape:\n"
            "<intent mode=\"reuse\">\n"
            "{\n"
            f"  \"intent_id\": \"{resolved_intent_id}\",\n"
            f"  \"intent_type\": \"{resolved_intent_type}\",\n"
            f"  \"goal\": {json.dumps(resolved_goal, ensure_ascii=False)},\n"
            f"  \"allowed_actions\": {allowed_json},\n"
            "  \"mode\": \"reuse\",\n"
            "  \"requested_steps\": 5,\n"
            "  \"switch_reason\": \"work_type_changed\",\n"
            f"  \"switch_explanation\": \"The current goal requires `{blocked}`, but the current accepted intent contract does not allow that tool.\"\n"
            "}\n"
            "</intent>"
        )

    def build_reuse_only_transition_cannot_bundle_action_prompt(self, *, blocked_action: str = "") -> str:
        blocked = str(blocked_action or "the blocked tool").strip() or "the blocked tool"
        return (
            "SYSTEM: Your intent reuse transition is accepted, but the same response cannot also dispatch the blocked action.\n"
            f"Blocked action type: {blocked}.\n"
            "The reuse transition must complete first.\n"
            "Return only the next valid output under the updated contract now.\n"
            "If tool use is needed, return EXACTLY ONE <action>...</action> block.\n"
            "Do not repeat the <intent> block again unless runtime asks for another transition."
        )

    def build_repeated_disallowed_action_stop_diagnostic(
        self,
        *,
        blocked_action: str,
        intent_id: str,
        intent_type: str = "",
        allowed_actions: list[str] | None = None,
    ) -> str:
        blocked = str(blocked_action or "action").strip() or "action"
        allowed = [str(action).strip() for action in (allowed_actions or []) if str(action).strip()]
        return (
            "Execution stopped: repeated disallowed action loop.\n"
            f"The model repeatedly attempted `{blocked}` outside the active intent contract instead of reusing the intent or choosing an allowed action.\n"
            f"Current active intent id: {intent_id or '<active_intent_id>'}.\n"
            f"Current active intent type: {intent_type or '<intent_type>'}.\n"
            f"Current allowed_actions: {', '.join(allowed) if allowed else 'none'}.\n"
            "Required next decision: expand allowed_actions via a valid top-level <intent mode=\"reuse\"> block, choose an allowed action, or stop the task."
        )

    def build_intent_action_not_allowed_prompt(
        self,
        *,
        blocked_action: str,
        intent_id: str,
        intent_type: str = "",
        allowed_actions: list[str] | None = None,
        repeated: bool = False,
    ) -> str:
        allowed = [str(action).strip() for action in (allowed_actions or []) if str(action).strip()]
        allowed_line = ", ".join(allowed) if allowed else "none"
        normalized_type = str(intent_type or "").strip().upper()
        normalized_blocked = str(blocked_action or "").strip().lower()
        display_blocked = normalized_blocked or str(blocked_action or "unknown").strip() or "unknown"
        read_only_actions = {
            "read_file",
            "read_chunk",
            "read_file_skeleton",
            "extract_symbol",
            "extract_kotlin_function",
            "search_content",
            "search_files",
            "list_directory",
            "find_files",
            "git_diff",
            "run_shell",
        }
        investigate_to_modify = normalized_type == "INVESTIGATE" and display_blocked not in read_only_actions
        same_goal_upgrade_type = "MODIFY" if investigate_to_modify else (normalized_type or "<intent_type>")
        same_goal_switch_reason = "work_type_changed" if investigate_to_modify else "current_intent_no_longer_fits"

        if repeated:
            return self.build_repeated_disallowed_action_reuse_only_prompt(
                blocked_action=display_blocked,
                intent_id=intent_id,
                intent_type=intent_type,
                allowed_actions=allowed,
            )

        return (
            "SYSTEM: This action is outside the current intent contract.\n"
            "To continue with a different work type or expanded tools, return only a minimal intent transition.\n"
            f"Blocked action type: {display_blocked}.\n"
            f"Current active intent id: {intent_id or '<active_intent_id>'}.\n"
            f"Current allowed_actions: {allowed_line}.\n"
            "Do not include <think>, <memory_update_done />, <action>, <file_content>, or final answer until the transition is accepted.\n"
            "For a same-goal contract upgrade, use:\n"
            "<intent mode=\"reuse\">\n"
            "{\n"
            f'  "intent_id": "{intent_id or "<current_intent_id>"}",\n'
            f'  "intent_type": "{same_goal_upgrade_type}",\n'
            f'  "allowed_actions": [{", ".join(json.dumps(action, ensure_ascii=False) for action in (allowed + ([display_blocked] if display_blocked not in allowed else [])))}],\n'
            '  "mode": "reuse",\n'
            f'  "switch_reason": "{same_goal_switch_reason}"\n'
            "}\n"
            "</intent>\n"
            "For a new save/output artifact goal, use:\n"
            "<intent mode=\"replace\">\n"
            "{\n"
            '  "intent_id": "save_analysis_doc",\n'
            '  "intent_type": "MODIFY",\n'
            '  "goal": "Save the analysis as a markdown file.",\n'
            f'  "allowed_actions": [{json.dumps(display_blocked, ensure_ascii=False)}],\n'
            '  "mode": "replace",\n'
            '  "switch_reason": "save_requested"\n'
            "}\n"
            "</intent>"
        )

    def build_transition_only_intent_cannot_bundle_action_prompt(self, *, blocked_action: str = "") -> str:
        blocked = str(blocked_action or "the blocked tool").strip() or "the blocked tool"
        return (
            "SYSTEM: The intent transition was accepted, but this recovery step was transition-only.\n"
            f"Blocked action type: {blocked}.\n"
            "Do not include <think>, <memory_update_done />, <intent>, <action>, <file_content>, or final answer together in this recovery turn.\n"
            "Return only the next valid output under the updated contract now.\n"
            "If tool use is needed, return EXACTLY ONE <action>...</action> block in the next step."
        )

    def build_intent_payload_inside_action_prompt(self) -> str:
        return (
            "SYSTEM: Intent is not a tool.\n"
            "Return <intent mode=\"...\">...</intent> as a top-level block, not inside <action>.\n"
            "Do not wrap an intent payload inside action JSON with type=\"intent\"."
        )

    def build_noop_edit_prompt(self) -> str:
        return (
            "SYSTEM: This edit would not change the file.\n"
            "If no change is needed, answer.\n"
            "Otherwise return a replacement that differs from search_text."
        )

    def build_edit_retry_requires_fresh_read_prompt(self, *, path: str, allowed_actions: list[str] | None = None) -> str:
        allowed = [str(action).strip() for action in (allowed_actions or []) if str(action).strip()]
        allowed_line = ", ".join(allowed) if allowed else "read_chunk, read_file, search_content"
        return (
            "SYSTEM: Your search_text does not match current file. Read exact current block first.\n"
            f"Target path: {path or '<path>'}.\n"
            f"Allowed actions now: {allowed_line}.\n"
            "Do not retry edit_file from memory.\n"
            "Use read_chunk, read_file, or search_content to retrieve the exact current target block, then retry one targeted edit.\n"
            "Use write_file only if the full current file was freshly read and the active intent explicitly allows it."
        )

    def build_intent_body_contains_action_prompt(self) -> str:
        return (
            "SYSTEM: Your last <intent> block contained an <action> wrapper inside the intent body.\n"
            "That intent transition was not accepted by runtime.\n"
            "The body of <intent> must be exactly one JSON object for the intent transition.\n"
            "Do not put <action> inside <intent>.\n"
            "Correct format:\n"
            "<intent mode=\"complete\">\n"
            "{\n"
            "  \"intent_id\": \"...\",\n"
            "  \"mode\": \"complete\",\n"
            "  \"completion_reason\": \"goal_completed\",\n"
            "  \"completion_explanation\": \"...\"\n"
            "}\n"
            "</intent>\n"
            "If a tool action is also needed, put it after the accepted top-level <intent> block, not inside it.\n"
            "Return the corrected output now."
        )


    def build_invalid_intent_contract_prompt(self, reason: str, allowed_actions: list[str] | None = None) -> str:
        if str(reason or "").strip() == "intent_reuse_without_active_intent":
            return self.build_reuse_without_active_intent_activate_only_prompt()
        if str(reason or "").strip() == "intent_body_contains_action":
            return self.build_intent_body_contains_action_prompt()

        next_hint = ""
        if allowed_actions:
            next_hint = f"\nAllowed actions for the next intent contract: {', '.join(allowed_actions)}."
        return (
            "SYSTEM: Your last <intent> block was syntactically invalid and was not accepted by runtime.\n"
            f"Reason: {reason}.{next_hint}\n"
            "There is still NO active accepted intent contract unless runtime explicitly says otherwise.\n"
            "Continue from already gathered evidence. Do not restart from zero.\n"
            "Canonical format is a JSON object inside the intent tag.\n"
            "Do not rely on XML attributes for intent fields other than the outer mode attribute.\n"
            "Do not use a self-closing intent tag.\n"
            "Return EXACTLY ONE corrected <intent> JSON block now.\n"
            "Do not return a bare <action> before the corrected <intent> is accepted."
        )

    def build_invalid_intent_resumable_available_prompt(
        self,
        reason: str,
        *,
        resumable_intent_id: str,
        resumable_intent_type: str = "",
        resumable_goal: str = "",
    ) -> str:
        requested_steps = int(getattr(self.config, "INTENT_REUSE_EXTENSION_STEPS", 4) or 4)
        return (
            "SYSTEM: The intent block was not accepted, but resumable work is still available.\n"
            f"Reason: {reason}.\n"
            "Do not restart from zero.\n"
            f"Resumable intent_id: {resumable_intent_id}.\n"
            f"Resumable intent_type: {resumable_intent_type or '<same as resumable work>'}.\n"
            f"Resumable goal: {resumable_goal or '<same resumable goal>'}.\n"
            "Return EXACTLY ONE corrected <intent mode=\"reuse\"> block now.\n"
            "Canonical format is a JSON object inside the intent tag.\n"
            "Do not rely on XML attributes for intent fields other than the outer mode attribute.\n"
            "Do not use a self-closing intent tag.\n"
            "Do not emit an <action> before reuse is accepted.\n"
            "Return exactly:\n"
            "<intent mode=\"reuse\">\n"
            "{\n"
            f'  "intent_id": "{resumable_intent_id}",\n'
            f'  "intent_type": "{resumable_intent_type or "<intent_type>"}",\n'
            f'  "goal": "{resumable_goal or "<same resumable goal>"}",\n'
            f'  "requested_steps": {max(1, requested_steps)},\n'
            '  "switch_reason": "current_intent_exhausted"\n'
            "}\n"
            "</intent>"
        )

    def build_reuse_without_active_intent_activate_only_prompt(self, *, strict: bool = False) -> str:
        payload = {
            "intent_id": "save_analysis_to_docs",
            "intent_type": "MODIFY",
            "goal": "Save analysis to docs.",
            "allowed_actions": ["write_file_block"],
            "mode": "activate",
        }
        if strict:
            return (
                "SYSTEM: There is no active intent to reuse.\n"
                "Return only one top-level <intent mode=\"activate\">...</intent>.\n"
                "Do not use mode=\"reuse\".\n"
                "Do not include <think>, <memory_update_done />, <action>, <file_content>, or final answer."
            )
        return (
            "SYSTEM: There is no active intent to reuse.\n"
            "Return only one top-level <intent mode=\"activate\">...</intent>.\n"
            "Do not use mode=\"reuse\".\n"
            "Do not include <think>, <memory_update_done />, <action>, <file_content>, or final answer.\n"
            "Use a compact activate block, for example:\n"
            "<intent mode=\"activate\">\n"
            f"{json.dumps(payload, ensure_ascii=False, indent=2)}\n"
            "</intent>"
        )

    def build_plain_think_without_valid_output_prompt(self) -> str:
        return (
            "SYSTEM: Your last response used plain \"think\" instead of <think>...</think> and did not include a valid action or final answer.\n"
            "Do not use plain think markers.\n"
            "Return a valid response using the required tags.\n"
            "If you use <think>, emit any required memory/subgoal tags and end that checkpoint with <memory_update_done /> before the action or final answer.\n"
            "Return exactly one valid <action>...</action>, one valid <intent>...</intent> if runtime requires it, or one normal final plain-text answer."
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
            "The current runtime contract remains active for this same user-facing goal.\n"
            "Do not reactivate, replace, relabel, or restart this work without a valid runtime reason.\n"
            "Do not repeat the blocked or low-value action pattern.\n"
            "Priority now is to finish this work quickly from the strongest current evidence.\n"
            "Continue from the strongest valid state already reached under the same contract.\n"
            "Do not reopen exploration just because continuation is allowed.\n"
            "Return the next valid output, or complete the intent and answer now if current evidence is already sufficient."
        )

    def build_limit_aware_reuse_prompt(
        self,
        reason: str,
        allowed_actions: list[str] | None = None,
        *,
        goal: str | None = None,
        requested_steps: int | None = None,
    ) -> str:
        active_intent = self._current_active_intent()
        intent_id = str(getattr(active_intent, "intent_id", "") or "").strip() if active_intent is not None else ""
        intent_type = str(getattr(active_intent, "intent_type", "") or "").strip().upper() if active_intent is not None else ""
        if requested_steps is None:
            requested_steps = int(getattr(self.config, "INTENT_REUSE_EXTENSION_STEPS", 4) or 4)
        next_hint = f"\nAllowed actions under the CURRENT intent contract: {', '.join(allowed_actions)}." if allowed_actions else ""
        goal_hint = f"\nCurrent contract goal remains the same: {goal.strip()}." if isinstance(goal, str) and goal.strip() else ""
        return (
            "SYSTEM: Current intent step budget is exhausted.\n"
            f"Reason: {reason}.{next_hint}{goal_hint}\n"
            "Normal actions are forbidden until the intent is completed or reused with refreshed budget.\n"
            "Do NOT silently continue under the exhausted budget.\n"
            "Do NOT activate a fresh unrelated intent for the same goal.\n"
            "Allowed next outputs are ONLY:\n"
            "- EXACTLY ONE <intent> JSON block with mode=\"reuse\" for the SAME active intent_id to request refreshed steps for this same intent lineage\n"
            "- or <intent mode=\"complete\"> plus final answer if current evidence is already sufficient\n"
            "- or a plain handoff/answer from current evidence if more work remains but no continuation approval exists\n"
            f"Use requested_steps={max(1, int(requested_steps))}.\n"
            f"Keep intent_id={intent_id or '<active_intent_id>'} and intent_type={intent_type or '<active_intent_type>'}.\n"
            "Use switch_reason=\"current_intent_exhausted\" unless runtime explicitly indicates a different legitimate continuation reason.\n"
            "Do not emit an <action> in the same reply.\n"
            "Do not change the goal text. Reuse is for same goal + same lineage + refreshed budget."
        )

    def build_build_fix_intent_required_prompt(self, *, goal: str = "") -> str:
        normalized_goal = self.sanitize_intent_goal(
            goal or getattr(self.state, "build_fix_error_summary", ""),
            fallback="Fix current Android compile errors.",
        )
        payload = {
            "intent_id": "fix_build_errors",
            "intent_type": "MODIFY",
            "goal": normalized_goal,
            "allowed_actions": [
                "read_file",
                "edit_file",
                "write_file_block",
                "create_file",
                "run_shell",
            ],
            "safe_steps_limit": 10,
            "retry_limit": 2,
            "mode": "activate",
        }
        return (
            "SYSTEM: Build failure detected. Enter focused build-fix mode before further edits.\n"
            "Return only one top-level <intent mode=\"activate\">...</intent>.\n"
            "Do not include <think>, <memory_update_done />, <action>, <file_content>, or final answer.\n"
            "Use a goal under 100 characters, e.g. \"Fix current Android compile errors.\"\n"
            "\n"
            "<intent mode=\"activate\">\n"
            f"{json.dumps(payload, ensure_ascii=False, indent=2)}\n"
            "</intent>"
        )

    def build_formal_intent_required_for_multi_step_state_change_prompt(self, *, goal: str = "") -> str:
        normalized_goal = self.sanitize_intent_goal(
            goal,
            fallback="Continue multi-step code modification.",
        )
        return self._build_activate_or_atomic_bundle_prompt(
            header="Formal intent contract is required before this tool use.",
            reason="formal_intent_required_for_multi_step_state_change",
            goal=normalized_goal,
            allowed_actions=["read_file", "edit_file", "write_file_block", "create_file", "run_shell"],
            intent_id=self._suggest_example_intent_id(normalized_goal),
        )

    def build_atomic_bundle_rejected_prompt(
        self,
        *,
        invalid_part: str,
        reason: str,
        blocked_action: str = "",
        proposed_allowed_actions: list[str] | None = None,
        goal: str = "",
    ) -> str:
        part = str(invalid_part or "").strip() or "bundle"
        normalized_reason = str(reason or "").strip() or "invalid_bundle"
        lines = [
            "SYSTEM: Your response used an atomic intent/action bundle, but part of the bundle is invalid.",
            f"Invalid part: {part}.",
        ]
        if part == "action" and blocked_action:
            allowed = [str(action).strip() for action in (proposed_allowed_actions or []) if str(action).strip()]
            allowed_line = ", ".join(allowed) if allowed else "none"
            lines.append(
                f'Reason: the action type "{blocked_action}" is not allowed by the proposed intent contract.'
                if normalized_reason == "intent_action_not_allowed"
                else f"Reason: {normalized_reason}."
            )
            lines.append(f"Proposed allowed_actions: {allowed_line}.")
        elif part == "file_content":
            lines.append(f"Reason: {normalized_reason}.")
            lines.append("The write-like action is missing required file body content or the file-content pairing is malformed.")
        else:
            lines.append(f"Reason: {normalized_reason}.")
        lines.extend(
            [
                "The entire bundle was rejected:",
                "- no intent was activated;",
                "- no action was dispatched.",
                "Return a corrected valid response from the beginning:",
                "- either a valid <intent mode=\"activate\">...</intent>;",
                "- or a valid atomic bundle with that intent followed by exactly one allowed <action>.",
                "Do not include visible final answer text in the same response as an action.",
            ]
        )
        if goal:
            lines.append(f"Goal context: {goal}.")
        return "\n".join(lines)

    def build_build_fix_mode_blocks_feature_expansion_prompt(self, *, allowed_files: list[str] | None = None) -> str:
        file_hint = ""
        filtered = [str(path).strip() for path in (allowed_files or []) if str(path).strip()]
        if filtered:
            file_hint = f"\nCompiler-mentioned files to prioritize: {', '.join(filtered)}."
        return (
            "SYSTEM: Current task is in build-fix mode. Do not continue feature work.\n"
            "Use compiler-mentioned files and fix the current compile errors first.\n"
            "Read the compiler-mentioned files, fix the current error group, then rerun ./gradlew :app:assembleDebug.\n"
            f"{file_hint}"
        )

    def build_mixed_intent_transition_and_visible_answer_prompt(self) -> str:
        return (
            "SYSTEM: Your response mixed an intent transition with user-visible answer text in the same step.\n"
            "Choose exactly one valid shape:\n"
            "1. Return only one valid <intent mode=\"activate\">...</intent> or other required top-level intent transition.\n"
            "2. Or return only the final plain-text answer, with no <intent>, <action>, or other control tags.\n"
            "3. Or return a valid atomic bundle: one allowed <intent> transition followed by exactly one valid <action> and required <file_content> if needed.\n"
            "Do not put user-visible analysis or final-answer prose after an intent transition.\n"
            "Return the corrected response from the beginning."
        )

    def build_build_fix_final_answer_missing_build_status_prompt(self) -> str:
        return (
            "SYSTEM: Build-fix mode final answer is missing explicit build status.\n"
            "State exactly whether the build was run and whether it passed.\n"
            "If you ran ./gradlew :app:assembleDebug, say whether it passed or failed.\n"
            "If you did not run the build, say that explicitly.\n"
            "Return only the corrected user-visible final answer."
        )


    def build_intent_transition_rejected_prompt(self, reason, allowed_actions=None, goal=""):
        stop_info = {
            "reason": reason,
            "recoverable": True,
            "next_actions": allowed_actions or [],
            "intent_allowed_actions": allowed_actions or [],
            "next_actions_source": "intent",
        }
        if goal:
            stop_info["goal"] = goal
        return self.build_orchestrated_recovery_prompt(stop_info)

    def build_intent_completed_prompt(self) -> str:
        parts = [
            "SYSTEM: The current intent contract is completed.",
            "Return a concise plain-text answer for the user using the evidence already gathered.",
            "Do not emit another <intent> block.",
            "Do not emit any <action> block.",
        ]
        last_completed_intent_type = str(getattr(self.state, "last_completed_intent_type", "") or "").strip().upper()
        if last_completed_intent_type == "MODIFY":
            parts.extend(
                [
                    "Because this completed intent was MODIFY, the final answer must include changed files, what changed, whether git diff was checked, whether build/tests were run, and any unverified risks.",
                    "If git diff or build/tests were not run, say that explicitly.",
                ]
            )
        return "\n".join(parts)

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
            + "\nReturn the next valid output that directly serves the current goal."
        )

    def build_retry_recovery_query(self, recovery_actions: list[str] | None = None) -> str:
        recovery_actions = recovery_actions or []
        preferred = str((recovery_actions or ["action"])[0] or "action").strip()
        return self._render_strict_failure_recovery(
            {
                "error_code": "",
                "failed_tool": "action",
                "failed_error_message_short": "recoverable failure",
            },
            fact="action failed: recoverable failure",
            gap="do not repeat the same invalid shape or identical arguments",
            next_step=f"use one materially different safe next operation: {preferred}",
            action_block=self._default_action_block(preferred),
            safe_recovery_action=preferred,
        )
