"""Prompt construction for orchestrator runtime and recovery flows."""

from __future__ import annotations

import json
from textwrap import dedent

from modules.defaults import DEFAULT_SYSTEM_PROMPT

from ..intent_message_resolver import resolve_intent_message_key
from ..intent_messages import render_intent_message
from .decision_models import RecoveryContext
from .intent_universe import IntentUniverseResolver
from .recovery_policy import RecoveryPolicyResolver


class OrchestratorPromptBuilder:
    def __init__(self, agent):
        self.agent = agent
        self.state = agent.state
        self.config = agent.config
        self.memory_board_store = getattr(agent, "memory_board_store", None)
        self.recovery_policy_resolver = getattr(agent, "recovery_policy_resolver", None) or RecoveryPolicyResolver(
            getattr(agent, "allowed_actions_resolver", None)
        )
        self.intent_universe_resolver = IntentUniverseResolver()

    def _recovery_context(self, stop_info: dict | RecoveryContext | None) -> RecoveryContext:
        return self.recovery_policy_resolver.normalize_context(
            stop_info,
            active_intent=self._current_active_intent(),
        )

    def _current_active_intent(self):
        return getattr(self.state, "active_intent", None)

    def _intent_universe(self):
        return self.intent_universe_resolver.resolve(self.state, self.config)

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

    def _action_hints_from_stop_info(self, stop_info: dict | None) -> tuple[list[str], list[str], str]:
        ctx = self._recovery_context(stop_info)
        resolved = ctx.resolved_action_policy()
        if resolved is None:
            return ctx.intent_allowed_actions, ctx.recommended_next_actions, ctx.next_actions_source
        return resolved.intent_actions, resolved.recommended_actions, resolved.authoritative_source

    def _effective_intent_step_limit(self, active_intent) -> int:
        if active_intent is None:
            return 0
        safe_steps_limit = int(getattr(active_intent, "safe_steps_limit", 0) or 0)
        user_step_extension = int(getattr(active_intent, "user_step_extension", 0) or 0)
        return max(0, safe_steps_limit + max(0, user_step_extension))

    def _intent_steps_remaining(self, active_intent) -> int:
        if active_intent is None:
            return 0
        return max(
            0,
            self._effective_intent_step_limit(active_intent) - int(getattr(active_intent, "step_count", 0) or 0),
        )

    def _summarize_last_action(self) -> str:
        state = getattr(self, "state", None)
        if state is None:
            return "none"

        fingerprint = str(getattr(state, "last_action_fingerprint", "") or "").strip()
        status = str(getattr(state, "last_action_status", "") or "").strip().lower()
        if fingerprint:
            cmd_type, _, payload = fingerprint.partition(":")
            rendered = cmd_type or "action"
            if payload:
                try:
                    data = json.loads(payload)
                    path = data.get("path")
                    command = data.get("command")
                    pattern = data.get("pattern") or data.get("query") or data.get("name")
                    if isinstance(path, str) and path.strip():
                        rendered += f'("{path}")'
                    elif isinstance(command, str) and command.strip():
                        rendered += f'("{command[:80]}")'
                    elif pattern not in (None, ""):
                        rendered += f'("{str(pattern)[:80]}")'
                except Exception:
                    pass
            if status:
                return f"{rendered} -> {status}"
            return rendered

        recent_problem_actions = getattr(state, "recent_problem_actions", None) or []
        if recent_problem_actions:
            latest = recent_problem_actions[-1]
            cmd = latest.get("command") if isinstance(latest, dict) else None
            if isinstance(cmd, dict):
                cmd_type = str(cmd.get("type") or cmd.get("action") or "action")
                path = cmd.get("path")
                rendered = cmd_type
                if isinstance(path, str) and path.strip():
                    rendered += f'("{path}")'
                latest_status = str(latest.get("status") or "").strip().lower()
                if latest_status:
                    return f"{rendered} -> {latest_status}"
                return rendered

        return "none"

    def _derive_current_best_answer(self, active_intent) -> str:
        memory_board = getattr(self.agent, "memory_board_store", None)
        if memory_board is None or not hasattr(memory_board, "entries") or active_intent is None:
            return "none yet"

        intent_id = getattr(active_intent, "intent_id", None)
        if not intent_id:
            return "none yet"

        try:
            entries = memory_board.entries(
                status="active",
                scope="intent",
                intent_id=intent_id,
                newest_first=True,
            )
        except Exception:
            return "none yet"

        ranked = []
        for entry in entries:
            kind = str(getattr(entry, "kind", "") or "")
            text = str(getattr(entry, "text", "") or "").strip()
            if not text:
                continue
            if kind == "progress":
                score = 3
            elif kind == "finding":
                score = 2
            elif kind == "fact":
                score = 1
            else:
                score = 0
            ranked.append((score, text))

        if not ranked:
            return "none yet"

        ranked.sort(key=lambda item: item[0], reverse=True)
        top = [text for _, text in ranked[:2]]
        joined = " | ".join(top)
        return joined[:280].rstrip() + ("…" if len(joined) > 280 else "")

    def build_active_intent_contract_prompt(self) -> str:
        universe = self._intent_universe()
        active_intent = self._current_active_intent()
        if active_intent is None or not universe.has_active_contract:
            return ""

        intent_id = str(getattr(active_intent, "intent_id", "") or "").strip() or "<none>"
        intent_type = str(getattr(active_intent, "intent_type", "") or "").strip() or "<none>"
        goal = str(getattr(active_intent, "goal", "") or "").strip() or "<none>"
        allowed_actions = list(getattr(active_intent, "allowed_actions", []) or [])
        safe_steps_limit = int(getattr(active_intent, "safe_steps_limit", 0) or 0)
        steps_used = int(getattr(active_intent, "step_count", 0) or 0)
        steps_remaining = self._intent_steps_remaining(active_intent)
        retry_limit = int(getattr(active_intent, "retry_limit", 0) or 0)
        retry_count = int(getattr(active_intent, "retry_count", 0) or 0)
        last_action = self._summarize_last_action()
        current_best_answer = self._derive_current_best_answer(active_intent)
        accepted = "yes"
        mode = "active"

        lines = [
            "## ACTIVE INTENT CONTRACT",
            "Status: ACTIVE",
            f"Accepted by runtime: {accepted}",
            "This contract remains active until runtime explicitly completes, replaces, rejects, or closes it.",
            "Do not emit another <intent mode=\"activate\"> for the same ongoing work.",
            "Continue under this contract unless runtime explicitly requires a legitimate transition.",
            "",
            "VALID REASONS TO CHANGE THE ACTIVE INTENT CONTRACT:",
            "- user_requested_new_task",
            "- current_intent_completed",
            "- current_intent_exhausted",
            "- work_type_changed",
            "- current_intent_no_longer_fits",
            "If none of these reasons applies, do NOT emit <intent mode=\"activate\"> or <intent mode=\"replace\"> again for this same ongoing work.",
            "",
            f"intent_id: {intent_id}",
            f"intent_type: {intent_type}",
            f"goal: {goal}",
            f"allowed_actions: {', '.join(allowed_actions) if allowed_actions else 'none'}",
            f"safe_steps_limit: {safe_steps_limit}",
            f"steps_used: {steps_used}",
            f"steps_remaining: {steps_remaining}",
            f"retry_limit: {retry_limit}",
            f"retry_count: {retry_count}",
            f"mode: {mode}",
            "",
            f"last_action: {last_action}",
            f"current_best_answer: {current_best_answer}",
            "",
            "Next valid behaviors:",
            "- return exactly one allowed action to advance the current work",
            "- or return a plain-text answer if current evidence is already sufficient",
            "- or emit <intent mode=\"complete\"> followed by a plain-text answer if the goal is achieved",
            "",
            "Do NOT:",
            "- emit a new <intent mode=\"activate\"> or <intent mode=\"replace\"> for the same goal",
            "- restart reconnaissance from the beginning",
            "- ignore already established current_best_answer and intent-scoped memory without new evidence",
        ]
        return "\n".join(lines)

    def build_no_active_intent_contract_prompt(self) -> str:
        universe = self._intent_universe()
        active_intent = self._current_active_intent()
        if active_intent is not None or universe.has_active_contract:
            return ""

        steps_used = universe.intentless_steps_used
        steps_limit = universe.intentless_steps_limit
        intent_required = universe.intent_required_now
        intent_required_reason = str(universe.intent_requirement_reason or "").strip() or "none"
        last_action = self._summarize_last_action()

        lines = [
            "## INTENT MODE STATUS",
            "Status: NO ACTIVE INTENT CONTRACT",
            "Runtime mode: INTENTLESS_SHORT_MODE",
            "Accepted by runtime: no active contract",
            "There is currently NO active accepted formal intent contract for this work.",
            "This mode is only for short unguided continuation before a formal contract is required.",
            "Do not claim that a current intent contract remains active, because none exists.",
            "",
            f"intentless_steps_used: {steps_used}",
            f"intentless_steps_limit: {steps_limit}",
            f"formal_intent_required_now: {'yes' if intent_required else 'no'}",
            f"intent_requirement_reason: {intent_required_reason}",
            f"last_action: {last_action}",
            "",
            "Rules in this mode:",
            "- continue from already gathered evidence; do not restart from zero",
            "- if the next step needs governed multi-step execution, emit a formal <intent> now",
            "- until activation succeeds, do not assume contract-scoped permissions or allowed_actions",
            "- if a formal intent is already required, do not return another bare <action> first",
            "- if current evidence is already sufficient, answer directly in plain text",
        ]
        return "\n".join(lines)

    def build_system_message(self, tools_prompt: str, ctx_prompt: str) -> str:
        prompt = DEFAULT_SYSTEM_PROMPT.replace("__TOOLS_DESCRIPTION__", tools_prompt)
        blocks = [prompt, ctx_prompt]

        memory_board = getattr(self.agent, "memory_board_store", None)
        active_intent_id = self._current_active_intent_id()

        active_intent_prompt = self.build_active_intent_contract_prompt()
        if active_intent_prompt:
            blocks.append(active_intent_prompt)
            if self.agent.log:
                self.agent.log.debug(
                    "PromptBuilder.active_intent_contract_prompt active_intent_id=%s chars=%s\n%s",
                    active_intent_id or "",
                    len(active_intent_prompt),
                    active_intent_prompt,
                )
        else:
            no_active_prompt = self.build_no_active_intent_contract_prompt()
            if no_active_prompt:
                blocks.append(no_active_prompt)
                if self.agent.log:
                    self.agent.log.debug(
                        "PromptBuilder.no_active_intent_contract_prompt chars=%s\n%s",
                        len(no_active_prompt),
                        no_active_prompt,
                    )

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
        universe = self._intent_universe()
        active_intent = self._current_active_intent()
        if not universe.has_active_contract or active_intent is None:
            return (
                "SYSTEM: A formal intent contract is required before further tool use.\n"
                f"Reason: {reason}.{next_hint}\n"
                "There is currently NO active accepted intent contract for this work.\n"
                "Continue from already gathered evidence. Do not restart the task from zero.\n"
                "Return EXACTLY ONE <intent> JSON block first.\n"
                "Until activation succeeds, do not assume contract-scoped permissions or allowed_actions.\n"
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
        return (
            "SYSTEM: A formal intent transition/update is required before further tool use.\n"
            f"Reason: {reason}.{next_hint}\n"
            "A formal runtime intent contract is already relevant for this work.\n"
            "Return the required <intent> block first, then the next valid step if needed."
        )

    def build_invalid_intent_contract_prompt(self, reason: str, allowed_actions: list[str] | None = None) -> str:
        next_hint = ""
        if allowed_actions:
            next_hint = f"\nAllowed actions for the next intent contract: {', '.join(allowed_actions)}."
        return (
            "SYSTEM: Your last <intent> block was syntactically invalid and was not accepted by runtime.\n"
            f"Reason: {reason}.{next_hint}\n"
            "There is still NO active accepted intent contract unless runtime explicitly says otherwise.\n"
            "Continue from already gathered evidence. Do not restart from zero.\n"
            "Return EXACTLY ONE corrected <intent> JSON block now.\n"
            "Do not return a bare <action> before the corrected <intent> is accepted."
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
            "unnecessary_intent_reactivation_or_replace": "The active intent contract is already present and remains active.",
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
                "Continue toward that goal using the updated allowed tools and constraints.",
                "Do not restart the task from the beginning. Continue from already gathered evidence under the same contract if there is no valid reason to change it.",
                "Do not repeat the action pattern that was just blocked or low-value.",
            ]
        )

        if reason == "user_approved_more_steps_after_hard_limit":
            base_lines.extend(
                [
                    "User approved additional budget for this same intent contract.",
                    "Continue from current evidence under the same contract.",
                    "Return the next valid output.",
                ]
            )
        elif reason == "intent_step_limit_soft_exceeded":
            base_lines.extend(
                [
                    "First decide whether the current evidence is already sufficient for a useful answer.",
                    "If it is sufficient, return a final plain-text answer now.",
                    "If it is not sufficient, return exactly one next <action> that most increases progress toward the goal.",
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
                    "Use the CURRENT intent contract action family instead of switching to a conflicting legacy recovery action set.",
                    "Return the next valid <action> that directly serves the current goal.",
                ]
            )
        elif reason == "unnecessary_intent_reactivation_or_replace":
            base_lines.extend(
                [
                    "The active intent contract is already shown in the system prompt and remains active by default.",
                    "It will remain active until runtime explicitly completes, replaces, rejects, or closes it for a valid listed reason.",
                    "There is no valid reason to reactivate or replace this same active intent contract now.",
                    "Do not emit another <intent mode=\"activate\"> or <intent mode=\"replace\"> for this same contract.",
                    "Return the next valid <action> under the current contract, or provide a plain-text answer if the evidence is already sufficient.",
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

    def build_suspect_intent_change_message(self, stop_info: dict | None) -> str:
        ctx = self._recovery_context(stop_info)
        suspicion = ctx.suspicion or {}
        old_goal = str(suspicion.get("old_goal") or "")
        new_goal = str(suspicion.get("new_goal") or "")
        reason = ctx.reason or "suspect_intent_relabel_repeat"
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
        ctx = self._recovery_context(stop_info)
        reason = ctx.reason or "intent_step_limit_exceeded"
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
            lines.append("Do not output audit/history markers such as SYSTEM_TOOL_AUDIT or <previously_performed_action>.")
        return "\n".join(lines)

    def build_malformed_action_strict_recovery_prompt(self) -> str:
        return (
            "SYSTEM: Your last response contained malformed <action> content.\n"
            "Return EXACTLY ONE valid <action>...</action> block now.\n"
            "Inside it:\n"
            "- include exactly ONE JSON object for exactly ONE next action.\n"
            "- Do not return multiple <action> blocks.\n"
            "- Do not return a JSON array.\n"
            "- Do not include prose outside <action>.\n"
            "If no tool is needed, return a plain-text answer instead of any <action>."
        )

    def build_audit_marker_echo_strict_recovery_prompt(self) -> str:
        return (
            "SYSTEM: Your last response echoed an internal audit marker instead of a valid next step.\n"
            "Do not output audit/history markers such as SYSTEM_TOOL_AUDIT or <previously_performed_action>.\n"
            "Return the next valid output now.\n"
            "If a tool is needed, return EXACTLY ONE valid <action>...</action> block.\n"
            "If no tool is needed, return a plain-text answer.\n"
            "Do not output <think> without an action or final answer."
        )

    def build_missing_action_or_answer_prompt(self) -> str:
        return (
            "SYSTEM: Your last response did not include a valid next step or a final answer.\n"
            "Return the next valid output now.\n"
            "If a tool is needed, return EXACTLY ONE valid <action>...</action> block.\n"
            "If no tool is needed, return a plain-text answer.\n"
            "Do not output historical tool markers, SYSTEM_TOOL_AUDIT, or <previously_performed_action>.\n"
            "Do not output <think> without an action or final answer."
        )

    def build_tool_history_echo_without_action_prompt(self) -> str:
        return (
            "SYSTEM: Your last response echoed a historical tool marker instead of a valid next step.\n"
            "Do not output TOOL_HISTORY, history_tool, or other historical markers again.\n"
            "Return the next valid output now.\n"
            "If a tool is needed, return EXACTLY ONE valid <action>...</action> block.\n"
            "If no tool is needed, return a plain-text answer.\n"
            "Do not output <think> without an action or final answer."
        )

    def build_intent_only_deadend_prompt(self) -> str:
        return (
            "SYSTEM: Your last response included an <intent> block but did not include a valid next step or a final answer.\n"
            "Return the next valid output now.\n"
            "If a tool is needed, return EXACTLY ONE valid <action>...</action> block.\n"
            "If no tool is needed, return a plain-text answer.\n"
            "Do not repeat the same <intent> again unless you are explicitly retrying or replacing it.\n"
            "Do not output historical tool markers, SYSTEM_TOOL_AUDIT, or <previously_performed_action>."
        )

    def typed_recovery_header(self, stop_info: dict | None) -> str:
        ctx = self._recovery_context(stop_info)
        stop_info = ctx.to_stop_info()
        reason = ctx.reason.strip()
        code = ctx.error_code.strip()
        message_key = resolve_intent_message_key(stop_info)
        intent_actions, recommended_actions, source = self._action_hints_from_stop_info(stop_info)
        next_hint = ""
        if intent_actions:
            next_hint = self._format_next_actions_hint(intent_actions, "intent")
        elif recommended_actions:
            next_hint = self._format_next_actions_hint(recommended_actions, "recommended")
        elif source:
            next_hint = self._format_next_actions_hint(stop_info.get("next_actions") or [], source)

        registry_rendered = render_intent_message(message_key, next_hint=next_hint, default="")
        if registry_rendered:
            return registry_rendered

        headers = {
            "reread_after_summary": "You just summarized context and then tried to re-read a file already in history without a specific reason. Use existing context instead.",
            "reread_already_in_history": "You tried to re-read a file that is already available in history without a specific reason.",
            "observe_budget_exhausted": "Read-only exploration budget is exhausted. Move to a more concrete next step now.",
            "action_not_allowed_in_phase": "A legacy recovery suggestion conflicted with the current execution contract.",
            "root_listing_budget_exhausted": "Root-level directory listing budget is exhausted for this turn.",
            "list_directory_budget_exhausted": "list_directory budget is exhausted for this turn.",
            "directory_descent_budget_exhausted": "Directory descent budget is exhausted. Stop walking folders one level at a time.",
            "broad_recon_budget_exhausted": "Broad reconnaissance budget is exhausted. Narrow the search or move to editing.",
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
        return (
            "Previous action violated orchestration policy. "
            "Choose a different valid next step consistent with the current contract and current evidence."
        ) + next_hint

    def _format_next_actions_hint(self, next_actions: list[str] | None, source: str = "") -> str:
        actions = next_actions or []
        if not actions:
            return ""
        source_value = str(source or "").strip().lower()
        if source_value == "intent":
            label = "Allowed actions under the CURRENT intent contract"
        elif source_value == "recommended":
            label = "Runtime-suggested next actions"
        else:
            label = "Allowed next actions"
        return f"\n{label}: {', '.join(actions)}."

    def build_typed_stop_recovery_prompt(self, stop_info: dict | None) -> str:
        ctx = self._recovery_context(stop_info)
        stop_info = ctx.to_stop_info()
        reason = ctx.reason.strip()
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
        ctx = self._recovery_context(stop_info)
        task_kind = getattr(sm, "task_kind", None)
        kind = getattr(task_kind, "value", str(task_kind or "UNKNOWN"))
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
        if route_hint:
            parts.append(route_hint)
        return "\n".join(parts)

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
            "Return EXACTLY ONE materially different next step.\n"
            "Prefer search_content, read_file_skeleton, search_files, list_directory, or a narrow read-only run_shell if allowed.\n"
            "If current evidence is already sufficient, return a plain-text answer instead.\n"
            "Do not re-send another malformed recovery attempt."
        )

    def build_orchestrated_recovery_prompt(self, stop_info: dict | None) -> str:
        ctx = self._recovery_context(stop_info)
        stop_info = ctx.to_stop_info()
        reason = ctx.reason
        universe = self._intent_universe()

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
        return (
            "SYSTEM: Previous action violated orchestration policy.\n"
            f"{required_hint}"
            "Use these only as recovery hints, not as a replacement for the current contract.\n"
            "Return the next valid output."
        )
