"""Prompt construction for orchestrator runtime and recovery flows."""

from __future__ import annotations

import json
from textwrap import dedent
from pathlib import Path

from modules.defaults import DEFAULT_SYSTEM_PROMPT

from ..intent_message_resolver import resolve_intent_message_key
from ..intent_messages import render_intent_message
from .decision_models import RecoveryContext
from .intent_universe import IntentUniverseResolver
from .recovery_policy import RecoveryPolicyResolver


class OrchestratorPromptBuilder:
    SOURCE_FILE_SUFFIXES = {
        ".py", ".kt", ".kts", ".java", ".js", ".jsx", ".ts", ".tsx", ".go",
        ".rs", ".c", ".cc", ".cpp", ".cxx", ".h", ".hpp", ".cs", ".swift",
        ".rb", ".php", ".scala", ".sql", ".sh", ".bash", ".zsh", ".xml",
        ".json", ".yaml", ".yml", ".toml", ".gradle", ".md",
    }

    def __init__(self, agent):
        self.agent = agent
        self.state = agent.state
        self.config = agent.config
        self.planner = getattr(agent, "planner", None)
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


    def _recent_resumable_intent_lines(self) -> list[str]:
        intent_id = str(getattr(self.state, "last_resumable_intent_id", "") or "").strip()
        if not intent_id:
            return []
        intent_type = str(getattr(self.state, "last_resumable_intent_type", "") or "").strip()
        goal = str(getattr(self.state, "last_resumable_intent_goal", "") or "").strip()
        reason = str(
            getattr(self.state, "last_resumable_intent_completion_reason", "")
            or getattr(self.state, "last_resumable_completion_reason", "")
            or ""
        ).strip()
        allowed = list(getattr(self.state, "last_resumable_intent_allowed_actions", []) or [])
        lines = [
            "",
            "## RECENTLY COMPLETED RESUMABLE INTENT",
            f"recent_intent_id: {intent_id}",
            f"recent_intent_type: {intent_type or '<none>'}",
            f"recent_completion_reason: {reason or '<none>'}",
            f"recent_goal: {goal or '<none>'}",
            f"recent_allowed_actions: {', '.join(allowed) if allowed else 'none'}",
            "The previous active contract was closed after a forced plain-text completion / hard-limit handoff.",
            "Do NOT silently continue that exhausted contract.",
            "If the new user message continues the SAME user-facing goal and the SAME type/direction of work, emit EXACTLY ONE <intent> JSON block with mode=\"reuse\" for this same intent_id to refresh budget for the same lineage.",
            "If the new user message is actually a different task, activate a new intent normally.",
        ]
        return lines

    def _active_intent_lineage_ids(self) -> list[str]:
        active_intent = self._current_active_intent()
        if active_intent is None:
            return []
        runtime = getattr(self.state, "intent_runtime", None)
        getter = getattr(runtime, "get_active_intent_lineage_ids", None)
        if callable(getter):
            try:
                values = getter() or []
                cleaned = []
                for value in values:
                    text = str(value or "").strip()
                    if text and text not in cleaned:
                        cleaned.append(text)
                if cleaned:
                    return cleaned
            except Exception:
                pass
        active_intent_id = str(getattr(active_intent, "intent_id", "") or "").strip()
        return [active_intent_id] if active_intent_id else []

    def _memory_projection_intent_ids(self) -> list[str]:
        active_lineage_ids = self._active_intent_lineage_ids()
        if active_lineage_ids:
            return active_lineage_ids

        recent_ids: list[str] = []
        for value in (
            getattr(self.state, "last_resumable_intent_id", None),
            getattr(self.state, "last_resumable_intent_lineage_id", None),
        ):
            text = str(value or "").strip()
            if text and text not in recent_ids:
                recent_ids.append(text)
        return recent_ids

    def _memory_tag_followup_lines(self) -> list[str]:
        expected = bool(getattr(self.state, "memory_tag_expected_next_step", False))
        if not expected:
            return []
        reason = str(getattr(self.state, "memory_tag_reason", "") or "").strip()
        intent_id = str(getattr(self.state, "memory_tag_expected_intent_id", "") or "").strip()
        lines = [
            "",
            "Memory-board follow-up from the previous step:",
            "- Previous step produced meaningful evidence but no memory tag was emitted.",
            "- In the next response, if that information still matters for continuation, emit the missing concise memory tag before any action or final answer.",
        ]
        if reason:
            lines.append(f"- Reason: {reason}")
        if intent_id:
            lines.append(f"- Expected intent_id: {intent_id}")
        return lines

    def _render_recovery_message(self, message_key: str, default: str, *, next_hint: str = "") -> str:
        rendered = render_intent_message(message_key, next_hint=next_hint, default="")
        return rendered or default

    def _recovery_protocol_name(self) -> str:
        for value in (
            getattr(self.state, "recovery_protocol", None),
            getattr(self.state, "operational_recovery_protocol", None),
            getattr(self.config, "RECOVERY_PROTOCOL", None),
            getattr(self.config, "OPERATIONAL_RECOVERY_PROTOCOL", None),
        ):
            text = str(value or "").strip().lower()
            if text in {"op", "legacy_think"}:
                return text
        return "legacy_think"

    def _short_failed_tool(self, stop_info: dict | None) -> str:
        ctx = self._recovery_context(stop_info)
        if ctx.failed_tool:
            return ctx.failed_tool
        command = ctx.command or {}
        return str(command.get("type") or command.get("action") or "action").strip() or "action"

    def _short_failed_error(self, stop_info: dict | None) -> str:
        ctx = self._recovery_context(stop_info)
        if ctx.failed_error_message_short:
            return ctx.failed_error_message_short
        details = ctx.error_details or {}
        for key in ("short_message", "message_short", "error_message_short", "message"):
            value = str(details.get(key) or "").strip()
            if value:
                return value
        value = str(ctx.message or "").strip()
        if value:
            return value
        code = str(ctx.failed_error_code or ctx.error_code or "").strip()
        return code or "unknown error"

    def _stop_info_path(self, stop_info: dict | None) -> str:
        ctx = self._recovery_context(stop_info)
        command = ctx.command or {}
        details = ctx.error_details or {}
        return str(
            command.get("path")
            or details.get("path")
            or details.get("target_path")
            or ""
        ).strip()

    def _is_existing_source_file(self, path: str, stop_info: dict | None) -> bool:
        if not path:
            return False
        ctx = self._recovery_context(stop_info)
        details = ctx.error_details or {}
        if "target_exists" in details:
            target_exists = details.get("target_exists")
        else:
            target_exists = Path(path).exists()
        suffix = Path(path).suffix.lower()
        return bool(target_exists) and suffix in self.SOURCE_FILE_SUFFIXES

    def _active_intent_allows_full_rewrite(self) -> bool:
        allowed = {str(a).strip() for a in self._current_intent_allowed_actions() if str(a).strip()}
        return bool({"write_file", "write_file_block"} & allowed)

    def _full_rewrite_allowed(self, stop_info: dict | None) -> bool:
        ctx = self._recovery_context(stop_info)
        if ctx.full_rewrite_allowed is not None:
            return bool(ctx.full_rewrite_allowed)
        details = ctx.error_details or {}
        path = self._stop_info_path(stop_info)
        if not self._is_existing_source_file(path, stop_info):
            return True
        fresh_full_read = bool(
            details.get("fresh_full_read_after_last_modification")
            or details.get("fresh_full_read")
            or details.get("fresh_read_after_last_modification")
        )
        targeted_edit_impractical = bool(
            details.get("targeted_edit_impractical")
            or details.get("edit_file_failed_deterministically")
            or details.get("deterministic_edit_failure")
        )
        mismatch_type = str(details.get("mismatch_type") or "").strip()
        if mismatch_type in {
            "multiple_similar_blocks",
            "search_text_stale_or_block_modified",
            "whitespace_mismatch",
            "no_similar_block_found",
        }:
            targeted_edit_impractical = True
        return self._active_intent_allows_full_rewrite() and fresh_full_read and targeted_edit_impractical

    def _compose_failure_context(self, stop_info: dict | None, *, safe_recovery_action: str = "") -> RecoveryContext:
        ctx = self._recovery_context(stop_info)
        ctx.failed_tool = ctx.failed_tool or self._short_failed_tool(stop_info)
        ctx.failed_error_code = ctx.failed_error_code or str(ctx.error_code or "").strip()
        ctx.failed_error_message_short = ctx.failed_error_message_short or self._short_failed_error(stop_info)
        ctx.safe_recovery_action = safe_recovery_action or ctx.safe_recovery_action
        ctx.full_rewrite_allowed = self._full_rewrite_allowed(stop_info)
        ctx.recovery_protocol = ctx.recovery_protocol or self._recovery_protocol_name()
        return ctx

    def _render_failure_checkpoint(self, *, fact: str, gap: str, next_step: str) -> str:
        protocol = self._recovery_protocol_name()
        if protocol == "op":
            safe = {
                "fact": fact.replace('"', "'"),
                "gap": gap.replace('"', "'"),
                "next": next_step.replace('"', "'"),
            }
            return f'<op fact="{safe["fact"]}" gap="{safe["gap"]}" next="{safe["next"]}" />'
        return "\n".join([
            "<think>",
            f"! {fact}",
            f"? {gap}",
            f"→ {next_step}",
            "</think>",
        ])

    def _render_strict_failure_recovery(
        self,
        stop_info: dict | None,
        *,
        fact: str,
        gap: str,
        next_step: str,
        action_block: str,
        trailing_blocks: list[str] | None = None,
        safe_recovery_action: str = "",
    ) -> str:
        ctx = self._compose_failure_context(stop_info, safe_recovery_action=safe_recovery_action)
        checkpoint = self._render_failure_checkpoint(
            fact=fact,
            gap=gap,
            next_step=next_step,
        )
        blocks = [checkpoint, "<memory_update_done />", action_block]
        for block in list(trailing_blocks or []):
            if str(block or "").strip():
                blocks.append(block)
        ctx.raw.update(
            {
                "failed_tool": ctx.failed_tool,
                "failed_error_code": ctx.failed_error_code,
                "failed_error_message_short": ctx.failed_error_message_short,
                "safe_recovery_action": ctx.safe_recovery_action,
                "full_rewrite_allowed": ctx.full_rewrite_allowed,
                "recovery_protocol": ctx.recovery_protocol,
            }
        )
        return "\n".join(blocks)

    def _default_action_block(self, action_type: str) -> str:
        return f'<action>{{"type":"{action_type}"}}</action>'

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

    def _effective_intent_hard_limit(self, active_intent) -> int:
        if active_intent is None:
            return 0
        nominal = self._effective_intent_step_limit(active_intent)
        allowance = int(getattr(self.config, "INTENT_COMPLETION_ALLOWANCE", 1) or 0)
        return max(0, nominal + max(0, allowance))

    def _intent_hard_steps_remaining(self, active_intent) -> int:
        if active_intent is None:
            return 0
        return max(0, self._effective_intent_hard_limit(active_intent) - int(getattr(active_intent, "step_count", 0) or 0))

    def _active_intent_is_hard_exhausted(self, active_intent=None) -> bool:
        active_intent = active_intent or self._current_active_intent()
        if active_intent is None:
            return False
        checker = getattr(self.state, "has_hard_exhausted_active_intent", None)
        if callable(checker):
            try:
                return bool(checker())
            except Exception:
                pass
        return self._intent_hard_steps_remaining(active_intent) <= 0

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

        lineage_intent_ids = self._active_intent_lineage_ids()
        if not lineage_intent_ids:
            intent_id = getattr(active_intent, "intent_id", None)
            if intent_id:
                lineage_intent_ids = [str(intent_id).strip()]
        if not lineage_intent_ids:
            return "none yet"

        try:
            entries_for_lineage = getattr(memory_board, "entries_for_intent_lineage", None)
            if callable(entries_for_lineage):
                entries = entries_for_lineage(
                    lineage_intent_ids,
                    status="active",
                    newest_first=True,
                )
            else:
                entries = []
                for intent_id in lineage_intent_ids:
                    entries.extend(memory_board.entries(
                        status="active",
                        scope="intent",
                        intent_id=intent_id,
                        newest_first=False,
                    ))
                entries.reverse()
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
        hard_steps_remaining = self._intent_hard_steps_remaining(active_intent)
        effective_hard_limit = self._effective_intent_hard_limit(active_intent)
        retry_limit = int(getattr(active_intent, "retry_limit", 0) or 0)
        retry_count = int(getattr(active_intent, "retry_count", 0) or 0)
        last_action = self._summarize_last_action()
        current_best_answer = "see injected memory board context" if self.memory_board_store is not None else "none yet"
        accepted = "yes"
        mode = "active"

        if self._active_intent_is_hard_exhausted(active_intent):
            return "\n".join(
                [
                    "## ACTIVE INTENT CONTRACT",
                    "Status: ACTIVE BUT HARD-EXHAUSTED",
                    f"Accepted by runtime: {accepted}",
                    "The current intent contract still names the same work, but its hard step budget is exhausted.",
                    "Normal <action> output is forbidden under this exhausted contract.",
                    "Do NOT continue under the current contract with another normal tool step.",
                    "",
                    f"intent_id: {intent_id}",
                    f"intent_type: {intent_type}",
                    f"goal: {goal}",
                    f"allowed_actions: {', '.join(allowed_actions) if allowed_actions else 'none'}",
                    f"safe_steps_limit: {safe_steps_limit}",
                    f"effective_nominal_step_limit: {self._effective_intent_step_limit(active_intent)}",
                    f"effective_hard_step_limit: {effective_hard_limit}",
                    f"steps_used: {steps_used}",
                    f"nominal_steps_remaining: {steps_remaining}",
                    f"hard_steps_remaining: {hard_steps_remaining}",
                    "step_budget_status: hard limit reached",
                    f"retry_limit: {retry_limit}",
                    f"retry_count: {retry_count}",
                    f"mode: {mode}",
                    "",
                    f"last_action: {last_action}",
                    f"current_best_answer: {current_best_answer}",
                    "",
                    "Allowed next outputs now:",
                    "1. Emit EXACTLY ONE <intent> JSON block with mode=\"reuse\" for this SAME intent_id and switch_reason=\"current_intent_exhausted\" to request refreshed budget for the same lineage.",
                    "2. Emit <intent mode=\"complete\"> followed by a final plain-text answer if the goal is already achieved.",
                    "3. Return a plain-text handoff/answer from current evidence if more work is needed but no refreshed budget is yet available.",
                    "",
                    "Forbidden now:",
                    "- any normal <action> under this exhausted contract",
                    "- silent budget refresh",
                    "- reactivating or replacing the same intent instead of reuse",
                    "- restarting reconnaissance from zero",
                ]
            )

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
            f"effective_nominal_step_limit: {self._effective_intent_step_limit(active_intent)}",
            f"effective_hard_step_limit: {effective_hard_limit}",
            f"steps_used: {steps_used}",
            f"nominal_steps_remaining: {steps_remaining}",
            f"hard_steps_remaining: {hard_steps_remaining}",
            ("step_budget_status: nominal" if steps_remaining > 0 else ("step_budget_status: nominal limit reached but hard-limit completion allowance remains" if hard_steps_remaining > 0 else "step_budget_status: hard limit reached")),
            f"retry_limit: {retry_limit}",
            f"retry_count: {retry_count}",
            f"mode: {mode}",
            "",
            f"last_action: {last_action}",
            f"current_best_answer: {current_best_answer}",
            "",
            "Memory-board expectation for this contract:",
            "- After each meaningful evidence gain, emit exactly ONE concise memory tag if the new fact, finding, decision, or milestone would matter after history compression.",
            "- Prefer <finding scope=\"intent\"> for newly established conclusions and <progress scope=\"intent\"> for milestone-level continuation state.",
            "- Do not emit a memory tag for routine tool usage with no durable insight.",
        ]
        lines.extend(self._memory_tag_followup_lines())
        lines.extend([
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
        ])
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
        lines.extend(self._memory_tag_followup_lines())
        lines.extend(self._recent_resumable_intent_lines())
        return "\n".join(lines)

    def build_system_message(self, tools_prompt: str, ctx_prompt: str) -> str:
        prompt = DEFAULT_SYSTEM_PROMPT.replace("__TOOLS_DESCRIPTION__", tools_prompt)
        blocks = [prompt, ctx_prompt]
        blocks.append(
            "Navigation guidance: prefer `read_file_skeleton` to inspect structure cheaply and obtain symbol line ranges before using broader or larger reads. "
            "When you already know the symbol target, prefer `extract_symbol` over repeated search + chunk hunting, and use `read_chunk` only for exact line-ranged follow-up. "
            "Under MODIFY, investigation remains valid until edit-readiness is achieved."
        )

        blocks.append(self.build_plan_board_protocol_prompt())
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

    def build_intent_runtime_context_message(self) -> dict[str, str] | None:
        active_intent_id = self._current_active_intent_id()
        active_intent_prompt = self.build_active_intent_contract_prompt()
        if active_intent_prompt:
            if self.agent.log:
                self.agent.log.debug(
                    "PromptBuilder.intent_runtime_context active_intent_id=%s chars=%s\n%s",
                    active_intent_id or "",
                    len(active_intent_prompt),
                    active_intent_prompt,
                )
            return {
                "role": "user",
                "content": (
                    "Runtime context only. This intent contract/status block is authoritative for the current step.\n\n"
                    f"{active_intent_prompt}"
                ),
            }

        no_active_prompt = self.build_no_active_intent_contract_prompt()
        if not no_active_prompt:
            return None

        if self.agent.log:
            self.agent.log.debug(
                "PromptBuilder.intent_runtime_context chars=%s\n%s",
                len(no_active_prompt),
                no_active_prompt,
            )

        return {
            "role": "user",
            "content": (
                "Runtime context only. This intent contract/status block is authoritative for the current step.\n\n"
                f"{no_active_prompt}"
            ),
        }

    def build_memory_board_context_message(self) -> dict[str, str] | None:
        memory_board = getattr(self.agent, "memory_board_store", None)
        if memory_board is None or not hasattr(memory_board, "to_system_prompt"):
            return None

        active_intent_id = self._current_active_intent_id()
        active_intent_lineage_ids = self._memory_projection_intent_ids()
        try:
            memory_prompt = memory_board.to_system_prompt(
                active_intent_id=active_intent_id,
                lineage_intent_ids=active_intent_lineage_ids,
            )
        except Exception as exc:
            if self.agent.log:
                self.agent.log.warning(f"Memory board prompt build failed: {exc}")
            return None

        if not isinstance(memory_prompt, str) or not memory_prompt.strip():
            return None

        if self.agent.log:
            self.agent.log.debug(
                "PromptBuilder.memory_board_context active_intent_id=%s chars=%s\n%s",
                active_intent_id or "",
                len(memory_prompt),
                memory_prompt,
            )

        return {
            "role": "user",
            "content": (
                "Reference context only. This memory board is durable working context from prior execution.\n\n"
                f"{memory_prompt}"
            ),
        }

    def build_plan_board_context_message(self) -> dict[str, str] | None:
        planner = getattr(self.agent, "planner", None)
        if planner is None or not hasattr(planner, "render_runtime_snapshot"):
            return None
        board = getattr(self.state, "task_board", None)
        snapshot = planner.render_runtime_snapshot(board)
        if not isinstance(snapshot, str) or not snapshot.strip():
            return None
        if self.agent.log:
            self.agent.log.debug(
                "PromptBuilder.plan_board_context chars=%s\n%s",
                len(snapshot),
                snapshot,
            )
        return {
            "role": "user",
            "content": (
                "Runtime context only. This current plan board is canonical decomposition state for the current active intent.\n\n"
                f"{snapshot}"
            ),
        }

    def build_plan_board_protocol_prompt(self) -> str:
        planner = getattr(self.agent, "planner", None)
        if planner is not None and hasattr(planner, "build_protocol_instructions"):
            return planner.build_protocol_instructions()
        return ""

    def build_memory_board_protocol_prompt(self) -> str:
        return dedent(
            """
            ## MEMORY BOARD PROTOCOL
            Memory tags are part of working continuity, not decoration.
            Supported tags:
            - <fact scope="intent|session|project">...</fact>
            - <finding scope="intent|session|project">...</finding>
            - <decision scope="intent|session|project">...</decision>
            - <preference scope="intent|session|project">...</preference>
            - <progress scope="intent">...</progress>
            - <path scope="intent|session|project">...</path>
            - <memory_review status="no_change" scope="intent" />
            - <memory_update_done />

            DURABLE STATE CHECKPOINT RULE:
            - Durable-state checkpointing is mandatory.
            - Every step must run this cycle in order: Sufficiency Check -> State Review -> Memory/Subgoal Update -> Action or Answer.
            - You MUST emit memory tags and/or formal plan tags:
              after every <think>,
              after every meaningful reasoning result,
              after every tool result that materially changes what is known, what should be done next, or what is already completed,
              and after every user input that changes the active goal interpretation, plan structure, priorities, constraints, or durable memory relevance.
            - Put the tags immediately after </think> and before any <action> or plain-text continuation.
            - End the memory/subgoal review block for the step with <memory_update_done />.
            - If the review found no memory/subgoal mutation to emit, output <memory_update_done /> anyway after the review.
            - If the review found no durable mutation but you still need to acknowledge the review explicitly before a risky action, you may emit <memory_review status="no_change" scope="intent" /> immediately before <memory_update_done />.
            - When in doubt, checkpoint more rather than less.
            - Loss of durable operational state after history compression is a critical failure.

            Tag selection:
            - Use <fact> for information directly verified by tool output, code, or runtime state already visible in history.
            - Use <finding> for conclusions, interpretations, suspected behavior, or any statement that is not directly quoted or directly observable from tool output.
            - Use <decision> for durable chosen rules, strategy choices, or explicit working decisions that should survive compression.
            - Use <progress> for milestone-level continuation state.
            - Use <path> for file paths, directory paths, module paths, or exact edit/inspection surfaces that are likely to matter later in the same work.
            - Use <preference> only for durable preference-like guidance that actually matters later.
            - Do NOT write plans, subgoals, next-step lists, or pending task decompositions into the memory board.
            - Do NOT collapse formal subgoal mutations into <progress> or <decision>; use the dedicated <subgoal ...> XML tags for subgoal state changes.
            - If the content is a plan, step list, next action, or task decomposition, it belongs in <subgoal ...>, not in memory tags.
            - If a newly discovered path is likely to be revisited, checkpoint it explicitly with <path> instead of burying it inside <fact> or prose.
            - If the injected MEMORY BOARD is marked stale, review it first and correct misleading operational memory before relying on it.

            Scope rules:
            - Use scope="intent" for information useful for continuing the current line of work.
            - Use scope="session" for information useful later in the current session.
            - Use scope="project" only for durable project-wide facts, decisions, or preferences.
            - Prefer the narrowest correct scope.

            What to preserve:
            - all verified facts established during thinking
            - all real conclusions reached during thinking
            - all chosen decisions made during thinking
            - important paths that the agent is likely to revisit
            - milestone-level progress that would matter after compression
            - recovery consequences that change the continuation rules
            - current-best-answer updates when they materially changed

            What NOT to do:
            - Do not log routine actions, tool calls, or noisy low-level observations.
            - Do not emit one arbitrary tag when the thinking produced several durable outcomes.
            - Do not silently contradict previously committed memory; if new evidence changes something important, emit a new explicit correcting tag.
            - Do not store "plan to", "next I will", "remaining steps", "todo list", or similar planning content in memory tags.

            Good examples:
            <think>
            The handler reads planIdFlow and mutates links through getPlanById(planId), so the current Today links behavior is still bound to a specific day plan. The clean direction is to remove the day-plan dependency at the handler boundary.
            </think>
            <finding scope="intent">DayPlanScopeLinksHandler is day-specific because it reads planIdFlow and mutates links through getPlanById(planId).</finding>
            <decision scope="intent">Remove the day-plan dependency at the handler boundary instead of preserving planIdFlow semantics for Today links.</decision>
            <memory_update_done />

            <think>
            The sheet derives displayed links from DayPlanUiState.dayPlan linked IDs. That means the rendering layer is also day-specific, not only the mutation layer. We now know there are at least two binding points to replace.
            </think>
            <path scope="intent">modules/day_plan/day_scope_links_sheet.py</path>
            <fact scope="intent">DayScopeLinksSheet derives displayed links from DayPlanUiState.dayPlan linked IDs.</fact>
            <finding scope="intent">The current Today links flow is day-specific in both mutation logic and rendering logic.</finding>
            <progress scope="intent">Identified the main per-day binding points that must be replaced.</progress>
            <memory_update_done />

            <think>
            The last file read failed because the path was wrong, but runtime provided a reliable parent directory. I should not retry the same missing path. I should inspect the suggested directory and locate the correct file from there.
            </think>
            <finding scope="intent">The previous file-read failure was caused by a wrong path, not by proof that the repository logic is absent.</finding>
            <decision scope="intent">Do not retry the same missing-file read; inspect the suggested parent directory and locate the correct file from there.</decision>
            <memory_update_done />

            <think>
            Memory board reviewed. No durable correction is needed before continuing.
            </think>
            <memory_review status="no_change" scope="intent" />
            <memory_update_done />

            Format:
            - Prefer 1-4 sentences per tag.
            - Use compact wording.
            - Preserve the conclusion, rule, fact, decision, or milestone rather than the whole reasoning chain.
            """
        ).strip()

    def build_intent_required_prompt(self, reason: str, allowed_actions: list[str] | None = None) -> str:
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
        alternative = "edit_file" if "edit_file" in allowed else (allowed[0] if allowed else "<allowed action>")
        normalized_type = str(intent_type or "").strip().upper()
        normalized_blocked = str(blocked_action or "").strip().lower()
        if normalized_type == "INVESTIGATE" and normalized_blocked in {
            "edit_file",
            "write_file",
            "write_file_block",
            "append_file_block",
            "create_file",
            "delete_file",
            "replace",
        }:
            header = (
                "SYSTEM: You repeated the same disallowed modifying action under the current INVESTIGATE intent.\n"
                if repeated
                else "SYSTEM: The current intent is INVESTIGATE and cannot modify files.\n"
            )
            return (
                f"{header}"
                f"Blocked action type: {blocked_action or 'unknown'}.\n"
                f"Current active intent id: {intent_id or '<active_intent_id>'}.\n"
                f"Current allowed_actions: {allowed_line}.\n"
                "Emit EXACTLY ONE <intent mode=\"reuse\"> block to switch this same goal to MODIFY.\n"
                "Use switch_reason=\"work_type_changed\".\n"
                "Do not emit edit_file until reuse is accepted.\n"
                "If this disallowed edit repeats again, do not suggest more actions; return only the reuse block."
            )
        if normalized_blocked == "write_file_block":
            return (
                f"{'SYSTEM: You repeated the same disallowed action under the current intent contract.\\n' if repeated else 'SYSTEM: Tool `write_file_block` is not allowed by the current intent contract.\\n'}"
                f"Blocked action type: {blocked_action or 'unknown'}.\n"
                f"Current active intent id: {intent_id or '<active_intent_id>'}.\n"
                f"Current allowed_actions: {allowed_line}.\n"
                "Either:\n"
                "1. emit <intent mode=\"reuse\"> with allowed_actions including write_file_block;\n"
                "2. use edit_file;\n"
                "3. stop and ask the user.\n"
                "Do not repeat write_file_block until the intent is updated."
            )
        header = (
            "SYSTEM: You repeated the same disallowed action under the current intent contract.\n"
            if repeated
            else "SYSTEM: Your last action is not allowed under the current intent contract.\n"
        )
        return (
            f"{header}"
            f"Blocked action type: {blocked_action or 'unknown'}.\n"
            f"Current active intent id: {intent_id or '<active_intent_id>'}.\n"
            f"Current allowed_actions: {allowed_line}.\n"
            "Do not repeat the same disallowed action until the intent is updated.\n"
            "Choose EXACTLY ONE of these paths:\n"
            f"1. Use an allowed action now, for example `{alternative}` if it fits the current file state.\n"
            "2. Emit <intent mode=\"reuse\"> to expand allowed_actions before using the blocked tool.\n"
            "If you use reuse, do not emit the blocked action in the same reply unless the updated intent is accepted first."
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

    def build_invalid_intent_contract_prompt(self, reason: str, allowed_actions: list[str] | None = None) -> str:
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
                    "Do NOT retry the same action with cosmetic changes.",
                    "Choose the next step that most increases progress toward the goal.",
                    "Return the next valid output under the current contract.",
                    "Prefer one materially different next <action> only if tool use is still needed.",
                    "If the goal can already be answered, return a plain-text answer instead.",
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
                    "If the previous edit failed because the search block was not unique or whitespace did not match, first retrieve the exact target block from file content, then retry edit_file with verbatim exact text, or use write_file with full validated content.",
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
            "Пріоритет зараз: якнайшвидше чисто завершити роботу з уже наявного evidence.\n"
            "Продовження НЕ означає: знову відкривати exploration або повторювати вже зроблене дослідження.\n"
            "Продовження означає: або чисто завершити відповідь з уже досягнутого стану, або зробити рівно наступний валідний крок, якщо ще бракує конкретної деталі.\n"
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
            "Return the next valid output for the next step.",
        ]
        if state_changing_only:
            lines.extend(
                [
                    "For this recovery step, prefer exactly one valid state-changing <action> if tool use is still needed.",
                    "Do not return read-only batching here.",
                    "If no tool is needed, return a plain-text answer.",
                ]
            )
        elif single_readonly_action_only:
            lines.extend(
                [
                    "For this recovery step, prefer exactly one valid read-only <action> if tool use is still needed.",
                    "Do not return a batch.",
                    "Do not return multiple <action> blocks.",
                    "Make the next search/action narrower and more targeted than before.",
                    "If no tool is needed or current evidence is already sufficient, return a plain-text answer instead.",
                ]
            )
        else:
            lines.extend(
                [
                    "For read-only investigation, multiple separate <action>...</action> blocks are allowed.",
                    "Compatible format: one <action>...</action> block may contain a JSON array of read-only action objects.",
                    "For any state-changing step, return only one valid <action>.",
                    "Do not use JSON arrays for state-changing actions.",
                    "If no tool is needed, return a plain-text answer.",
                ]
            )
        lines.extend(
            [
                "No prose outside <action> when returning an <action> block.",
                "If you return plain text instead, do not include any <action> block.",
                "If unsure, prefer one simple valid next step.",
            ]
        )
        if forbid_audit_markers:
            lines.append("Do not output audit/history markers such as SYSTEM_TOOL_AUDIT or <previously_performed_action>.")
        return "\n".join(lines)

    def build_malformed_action_strict_recovery_prompt(self) -> str:
        return (
            "SYSTEM: Your last response contained malformed <action> content.\n"
            "Return the next valid output now.\n"
            "If a tool is needed, return EXACTLY ONE valid <action>...</action> block.\n"
            "Inside it:\n"
            "- include exactly ONE JSON object for exactly ONE next action.\n"
            "- Do not return multiple <action> blocks.\n"
            "- Do not return a JSON array.\n"
            "- If you need to write a large file, use write_file_block plus a following raw <file_content>...</file_content> block instead of huge escaped JSON content.\n"
            "- Do not include prose outside <action>.\n"
            "If no tool is needed, return a plain-text answer instead of any <action>."
        )

    def build_incomplete_think_recovery_prompt(self) -> str:
        return (
            "SYSTEM: Your last response was truncated inside <think>.\n"
            "That is internal control text and cannot be forwarded to the user.\n"
            "Return a complete valid response from the beginning.\n"
            "If you need a <think> block, keep it compact and exact:\n"
            "<think>\n"
            "! one verified state\n"
            "? one exact gap, if any\n"
            "→ one next operation\n"
            "</think>\n"
            "No plans, no prose paragraphs, no nested <think>, no code fences.\n"
            "Then emit any needed memory/subgoal tags and end the checkpoint with <memory_update_done />.\n"
            "Then return either exactly one <action>...</action> or a plain final answer.\n"
            "Do not continue the previous incomplete sentence."
        )

    def build_malformed_verbose_or_nested_think_prompt(self) -> str:
        return (
            "SYSTEM: Your <think> block was too long, nested, or malformed.\n"
            "Return EXACTLY ONE compact operational review only:\n"
            "<think>\n"
            "! one verified state\n"
            "? one exact gap, if any\n"
            "→ one next operation\n"
            "</think>\n"
            "Use at most 3 short lines inside <think>.\n"
            "Then emit memory/subgoal tags, <memory_update_done />, and exactly one action if needed.\n"
            "Do not include plans, numbered steps, prose paragraphs, code fences, or another <think> inside <think>."
        )

    def build_strict_compact_think_prompt(self) -> str:
        return (
            "SYSTEM: Your malformed <think> repeated.\n"
            "Return EXACTLY this compact shape and nothing more inside the think block:\n"
            "<think>\n"
            "! one verified state\n"
            "? one exact gap, if any\n"
            "→ one next operation\n"
            "</think>\n"
            "Then emit only needed durable tags, then <memory_update_done />, then at most one action.\n"
            "No plans, no paragraphs, no markdown, no nested tags inside <think>."
        )

    def build_exact_think_skeleton_prompt(self) -> str:
        return (
            "SYSTEM: Malformed <think> repeated again.\n"
            "Return EXACTLY this skeleton with no extra prose:\n"
            "<think>\n"
            "! ...\n"
            "? ...\n"
            "→ ...\n"
            "</think>\n"
            "<memory_update_done />\n"
            "<action>...</action>\n"
            "If durable tags are needed, place them between </think> and <memory_update_done />.\n"
            "Do not add any plans, explanations, numbered steps, or nested <think>."
        )

    def build_malformed_think_limit_prompt(self) -> str:
        return (
            "SYSTEM: Malformed <think> repeated too many times in the same intent.\n"
            "Do not produce another long planning block.\n"
            "Either return one safe, compact, fully valid step now, or return a plain-text diagnostic that the runtime needs a smaller deterministic move."
        )

    def build_incomplete_action_recovery_prompt(self) -> str:
        return (
            "SYSTEM: Your last response was truncated inside <action>.\n"
            "Return the complete action package again from the beginning.\n"
            "If a tool is needed, return EXACTLY ONE complete valid <action>...</action> block.\n"
            "Do not continue the previous incomplete JSON fragment."
        )

    def build_incomplete_intent_recovery_prompt(self) -> str:
        return (
            "SYSTEM: Your last response was truncated inside <intent>.\n"
            "Return the complete intent transition again from the beginning, or omit it if no transition is needed.\n"
            "Do not continue the previous incomplete JSON fragment."
        )

    def build_incomplete_file_content_recovery_prompt(self) -> str:
        return (
            "SYSTEM: Your last response was truncated inside <file_content>.\n"
            "Return the entire action package again, or split the file into smaller append_file_block chunks.\n"
            "A block file write must include a complete <action>...</action> plus a complete <file_content>...</file_content> block.\n"
            "Do not continue the previous incomplete file body."
        )

    def build_file_content_must_follow_action_prompt(self, stop_info: dict | None = None) -> str:
        path = self._stop_info_path(stop_info) or "..."
        action_block = (
            '<action>\n'
            '{\n'
            '  "type": "write_file_block",\n'
            f'  "path": "{path}",\n'
            '  "overwrite": true\n'
            '}\n'
            '</action>'
        )
        file_block = "<file_content>\nraw content\n</file_content>"
        gap = (
            "The <file_content> block must appear immediately after </action>; "
            "do not put <file_content> inside <action>, before <action>, or repeat the same malformed shape."
        )
        return self._render_strict_failure_recovery(
            stop_info,
            fact="write_file_block failed: file_content_must_follow_action",
            gap=gap,
            next_step="return action first, then the raw file_content block in the required order",
            action_block=action_block,
            trailing_blocks=[file_block],
            safe_recovery_action="write_file_block_with_immediate_file_content",
        )

    def build_truncated_internal_response_prompt(self) -> str:
        return (
            "SYSTEM: Your last response was truncated inside internal control markup.\n"
            "That internal text cannot be forwarded to the user.\n"
            "Return a complete valid response from the beginning.\n"
            "Use complete control tags only; do not continue the previous incomplete fragment."
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

    def build_missing_think_reflection_prompt(self) -> str:
        return (
            "SYSTEM: Your last <think> block continued execution without the required durable-state checkpoint.\n"
            "Return ONLY the missing checkpoint now using supported memory tags and/or formal <subgoal ...> tags.\n"
            "This is a repair-only turn: do not return an <action>, a final answer, or a new <intent> block in the same reply.\n"
            "Capture ALL valuable results of the thinking, not just one token tag.\n"
            "Use these tags as needed: <fact>, <finding>, <decision>, <preference>, <progress>, <path>, <subgoal ...>, or <memory_review status=\"no_change\" scope=\"intent\" /> when the review changed nothing durable.\n"
            "If the thinking produced multiple facts, findings, decisions, or milestones, emit multiple tags.\n"
            "Place the tags immediately after </think> and end with <memory_update_done />.\n"
            "After runtime accepts the reflection repair, it will ask for the next valid output separately."
        )

    def build_state_changing_action_requires_think_reflection_prompt(self) -> str:
        return (
            "SYSTEM: Your last response moved from meaningful reasoning into a state-changing MODIFY action without the required durable-state checkpoint.\n"
            "Return a complete operational review now before the action continues.\n"
            "Start with a complete <think>...</think> block.\n"
            "Then emit the needed memory/subgoal update tags.\n"
            "If nothing durable changed, emit <memory_review status=\"no_change\" scope=\"intent\" />.\n"
            "Close the checkpoint with <memory_update_done />.\n"
            "After that, if a change is still needed, return EXACTLY ONE allowed state-changing <action>...</action> block."
        )

    def build_missing_memory_update_done_prompt(self) -> str:
        return (
            "SYSTEM: Your last response updated durable state but did not close the checkpoint with <memory_update_done />.\n"
            "Return ONLY the missing checkpoint close now.\n"
            "If the previously emitted memory/subgoal tags are still correct, do not repeat long prose or an action.\n"
            "If a memory/subgoal mutation is still missing, emit it first and then end with <memory_update_done />.\n"
            "This is a repair-only turn: do not return an <action>, a final answer, or a new <intent> block in the same reply."
        )

    def build_missing_think_for_state_change_prompt(self) -> str:
        return (
            "SYSTEM: A state-changing MODIFY action requires a complete tagged <think>...</think> block before the checkpoint.\n"
            "Return a complete operational review now.\n"
            "Start with a complete <think>...</think> block.\n"
            "Then emit durable tags such as <subgoal ...>, <decision>, <finding>, <progress>, <path>, or <memory_review status=\"no_change\" scope=\"intent\" />.\n"
            "Close the checkpoint with <memory_update_done />.\n"
            "After that, if a change is still needed, return EXACTLY ONE allowed state-changing <action>...</action> block."
        )

    def build_no_accepted_checkpoint_tags_prompt(self) -> str:
        return (
            "SYSTEM: Your last state-changing MODIFY step had a <think> block but no accepted durable-state checkpoint tags before the action.\n"
            "Return a complete checkpoint now.\n"
            "Start with a complete <think>...</think> block.\n"
            "Then emit at least one accepted durable tag: <subgoal ...>, <fact>, <finding>, <decision>, <preference>, <progress>, <path>, or <memory_review status=\"no_change\" scope=\"intent\" />.\n"
            "Close the checkpoint with <memory_update_done />.\n"
            "After that, if a change is still needed, return EXACTLY ONE allowed state-changing <action>...</action> block."
        )

    def build_malformed_plain_think_requires_tagged_think_prompt(self) -> str:
        return (
            "SYSTEM: For a state-changing MODIFY step, plain `think` text is invalid here.\n"
            "Use a proper tagged block: <think>...</think>.\n"
            "Return the full operational review again from the beginning.\n"
            "Start with complete <think>...</think>, then durable tags, then <memory_update_done />, then at most one state-changing <action>."
        )

    def build_malformed_checkpoint_prompt(self) -> str:
        return (
            "SYSTEM: Your last state-changing MODIFY step had an invalid durable-state checkpoint shape.\n"
            "Use exactly this order:\n"
            "1. complete <think>...</think>\n"
            "2. one or more durable tags or <memory_review status=\"no_change\" scope=\"intent\" />\n"
            "3. <memory_update_done />\n"
            "4. exactly one state-changing <action>...</action>\n"
            "Return the corrected step from the beginning."
        )

    def build_recovery_loop_detected_prompt(self, defect_kind: str) -> str:
        return (
            "SYSTEM: The same checkpoint recovery defect repeated multiple times without dispatch.\n"
            f"Detected defect: {str(defect_kind or '').strip() or 'checkpoint_contradiction'}.\n"
            "Do not repeat the same checkpoint ritual again.\n"
            "Either return one materially corrected full step with complete <think>, durable tags, <memory_update_done />, and one action, or return a plain-text diagnostic explaining that runtime verification is internally contradictory."
        )

    def build_terminal_recovery_loop_handoff_text(
        self,
        *,
        defect_kind: str,
        blocked_action: str = "",
        path_or_action: str = "",
    ) -> str:
        normalized = str(defect_kind or "").strip() or "recovery_loop_detected"
        active = self._current_active_intent()
        intent_id = str(getattr(active, "intent_id", "") or "<active_intent>").strip() or "<active_intent>"
        goal = str(getattr(active, "goal", "") or "").strip() or "unknown goal"
        blocked = str(blocked_action or "").strip() or "unknown action"
        path_hint = str(path_or_action or "").strip() or blocked
        return (
            "Я застряг у recovery loop.\n\n"
            "Що сталося:\n"
            f"- кілька разів намагався виконати дію `{blocked}`;\n"
            f"- runtime відхиляв її з причиною `{normalized}`;\n"
            "- після recovery я знову повертався до схожого кроку;\n"
            "- без втручання користувача є ризик далі витрачати токени без прогресу.\n\n"
            "Поточний стан:\n"
            f"- active intent: `{intent_id}`;\n"
            f"- остання ціль: `{goal}`;\n"
            f"- остання проблемна дія/файл: `{path_hint}`.\n\n"
            "Рекомендація:\n"
            "1. або дозволь потрібний tool через intent reuse;\n"
            "2. або попроси мене перейти на інший інструмент;\n"
            "3. або дай команду на безпечний verify/rollback, наприклад `git diff`, `read exact block`, `git restore`."
        )

    def build_terminal_repeated_disallowed_action_handoff_text(
        self,
        *,
        blocked_action: str,
        intent_id: str,
        intent_type: str = "",
        allowed_actions: list[str] | None = None,
    ) -> str:
        allowed = [str(action).strip() for action in (allowed_actions or []) if str(action).strip()]
        allowed_line = ", ".join(allowed) if allowed else "none"
        normalized_type = str(intent_type or "").strip().upper()
        type_suffix = f" ({normalized_type})" if normalized_type else ""
        return (
            "Я зупиняюся: кілька разів була спроба використати "
            f"`{str(blocked_action or 'unknown').strip() or 'unknown'}`, але цей tool не дозволений поточним intent contract.\n\n"
            f"Поточний intent: `{str(intent_id or '<active_intent>').strip() or '<active_intent>'}`{type_suffix}\n"
            f"Дозволені tools: {allowed_line}\n"
            f"Заблокований tool: {str(blocked_action or 'unknown').strip() or 'unknown'}\n\n"
            "Щоб продовжити:\n"
            "1. дозволь цей tool через intent reuse;\n"
            "2. або скажи використовувати тільки дозволений tool, наприклад `edit_file`, якщо він підходить;\n"
            "3. або попроси показати `git diff` і поточний стан файлів."
        )

    def build_terminal_large_malformed_response_handoff_text(
        self,
        *,
        invalid_kind: str,
        raw_chars: int,
        blocked_action: str = "",
        path_or_action: str = "",
    ) -> str:
        active = self._current_active_intent()
        intent_id = str(getattr(active, "intent_id", "") or "<active_intent>").strip() or "<active_intent>"
        goal = str(getattr(active, "goal", "") or "").strip() or "unknown goal"
        action_hint = str(blocked_action or "").strip() or str(path_or_action or "").strip() or "unknown action"
        return (
            "Зупинився: модель кілька разів повернула занадто велику й невалідну internal response.\n\n"
            f"- invalid kind: `{str(invalid_kind or '').strip() or 'malformed_response'}`\n"
            f"- raw size: {int(raw_chars or 0)} chars\n"
            f"- active intent: `{intent_id}`\n"
            f"- goal: `{goal}`\n"
            f"- problem action/file: `{action_hint}`\n\n"
            "Runtime відхилив відповідь до dispatch. Продовження таким самим шляхом, ймовірно, лише спалить токени.\n"
            "Оберіть наступне:\n"
            "1. targeted edit;\n"
            "2. дозволений full rewrite через `write_file_block`;\n"
            "3. manual verify/read exact block."
        )

    def build_checkpoint_defect_prompt(self, invalid_kind: str) -> str:
        normalized = str(invalid_kind or "").strip()
        if normalized == "missing_think":
            return self.build_missing_think_for_state_change_prompt()
        if normalized == "missing_memory_update_done":
            return self.build_missing_memory_update_done_prompt()
        if normalized == "no_accepted_checkpoint_tags":
            return self.build_no_accepted_checkpoint_tags_prompt()
        if normalized == "malformed_plain_think_requires_tagged_think":
            return self.build_malformed_plain_think_requires_tagged_think_prompt()
        if normalized == "malformed_checkpoint":
            return self.build_malformed_checkpoint_prompt()
        return self.build_state_changing_action_requires_think_reflection_prompt()

    def build_durable_state_repair_prompt(self, repair_kind: str = "") -> str:
        if str(repair_kind or "").strip() == "missing_memory_update_done":
            return self.build_missing_memory_update_done_prompt()
        return self.build_missing_think_reflection_prompt()

    def build_reflection_repair_accepted_prompt(self) -> str:
        return (
            "SYSTEM: Durable-state checkpoint repair accepted.\n"
            "Continue directly from the already chosen next step.\n"
            "Do not repeat the reflection tags.\n"
            "Do not restate the same decision in prose.\n"
            "If tool use is needed, return EXACTLY ONE valid <action>...</action> block.\n"
            "If no tool is needed, return a plain-text answer."
        )

    def build_leaked_system_result_recovery_prompt(self) -> str:
        return (
            "SYSTEM: Your last response copied internal SYSTEM RESULT text into the assistant-visible answer.\n"
            "SYSTEM RESULT blocks are internal tool-result transcript material, not assistant-visible output.\n"
            "Do not quote, replay, summarize as a transcript, or emit SYSTEM RESULT blocks.\n"
            "Return exactly one valid next output now:\n"
            "- one valid <action> if tool use is still needed\n"
            "- or one normal final plain-text answer without internal tool-result markers\n"
            "- or one valid <intent> transition only if runtime truly requires it\n"
            "Continue from the evidence already present in context. Do not repeat the leaked transcript text."
        )

    def build_missing_action_or_answer_prompt(self) -> str:
        return (
            "SYSTEM: Your last response did not include a valid next step or a final answer.\n"
            "Return the next valid output now.\n"
            "If a tool is needed, return EXACTLY ONE valid <action>...</action> block.\n"
            "If no tool is needed, return a plain-text answer.\n"
            "If you use <think> or emit memory/subgoal tags, end that checkpoint with <memory_update_done /> before the action or answer.\n"
            "Do not output historical tool markers, SYSTEM_TOOL_AUDIT, or <previously_performed_action>.\n"
            "Do not output <think> without an action or final answer."
        )


    def build_internal_summary_instead_of_final_answer_prompt(self) -> str:
        sm = getattr(self.state, "state_machine", None)
        stop_info = {
            "reason": "internal_summary_instead_of_final_answer",
            "recoverable": True,
            "error_code": "INTERNAL_SUMMARY_INSTEAD_OF_FINAL_ANSWER",
            "next_actions": [],
            "intent_allowed_actions": [],
            "next_actions_source": "intent",
        }
        base = self.build_plain_text_completion_prompt(sm, stop_info)
        return (
            "SYSTEM: Your last response was an internal execution summary, not a user-facing final answer.\n"
            "Do not summarize internal execution state, memory, plan, or snapshot fields.\n"
            + base
        )

    def build_modify_completion_claim_without_proof_prompt(self) -> str:
        return (
            "SYSTEM: Your last response claimed that code changes were already applied, but this turn has no successful state-changing tool result proving that.\n"
            "Do not claim completion or applied changes without proof.\n"
            "Return the next valid output now.\n"
            "If a change still needs to be applied, return EXACTLY ONE valid state-changing <action>...</action> block.\n"
            "If no change was actually applied, return a plain-text explanation that no changes were applied yet.\n"
            "Do not say \"done\", \"added\", \"fixed\", \"updated\", or equivalent unless a successful state-changing result in this turn proves it."
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

    def build_intent_only_without_next_step_prompt(self) -> str:
        return (
            "SYSTEM: Your last response changed or referenced intent state but did not provide a valid next step or a final answer.\n"
            "Return the next valid output now.\n"
            "If a tool is needed, return EXACTLY ONE valid <action>...</action> block.\n"
            "If no tool is needed, return a plain-text answer.\n"
            "Do not repeat the same <intent> again unless runtime explicitly requires a legitimate transition.\n"
            "Do not output historical tool markers, SYSTEM_TOOL_AUDIT, or <previously_performed_action>."
        )

    def build_intent_accepted_without_followup_prompt(self, active_goal: str = "") -> str:
        goal_hint = f"\nCurrent contract goal remains the same: {active_goal}." if active_goal else ""
        return (
            "SYSTEM: Intent accepted. The current contract is now active.\n"
            "This phase boundary is normal: the contract change was accepted, and runtime is now waiting for the next valid output under that contract.\n"
            "Return the next valid output now.\n"
            "If tool use is needed, return EXACTLY ONE valid <action>...</action> block.\n"
            "If no tool is needed, return a plain-text answer.\n"
            "If the goal is already achieved, you may complete the intent and answer in plain text.\n"
            "Do not emit another <intent> block for this same ongoing work.\n"
            "Do not treat the accepted transition itself as an error. Continue under the active contract."
            f"{goal_hint}"
        )


    def build_transition_bundle_too_dense_prompt(self) -> str:
        return (
            "SYSTEM: Your last response contained conflicting or ambiguous control items.\n"
            "Transactional bundles are allowed only when they stay coherent: at most one intent transition and at most one action.\n"
            "Return only the corrected next valid output now under the current runtime state.\n"
            "Do not emit multiple intent transitions.\n"
            "Do not emit multiple <action> blocks or an action array.\n"
            "If a contract is already active, do not emit another <intent> block unless a real transition is required.\n"
            "If tool use is needed, return EXACTLY ONE valid <action>...</action> block.\n"
            "If no tool is needed, return a plain-text answer."
        )

    def build_multiple_actions_prompt(self) -> str:
        return (
            "SYSTEM: Your last response contained multiple top-level <action> blocks.\n"
            "Return EXACTLY ONE valid <action>...</action> block now.\n"
            "Only top-level protocol <action> blocks count here; raw text inside <file_content> does not.\n"
            "Do not use an action array.\n"
            "Do not batch state-changing actions."
        )

    def build_conflicting_intent_transitions_prompt(self) -> str:
        return (
            "SYSTEM: Your last response contained conflicting intent transitions.\n"
            "Return at most one <intent> transition in the reply.\n"
            "If a contract is already active and no real transition is needed, do not emit another <intent> block.\n"
            "After that, return either one valid <action> or a plain-text answer."
        )

    def build_followup_conflict_prompt(self, reason: str) -> str:
        normalized = str(reason or "").strip()
        if normalized == "multiple_actions":
            return self.build_multiple_actions_prompt()
        if normalized == "conflicting_intent_transitions":
            return self.build_conflicting_intent_transitions_prompt()
        if normalized == "intent_complete_with_action_not_allowed":
            return self.build_completion_with_action_not_allowed_prompt()
        return self.build_transition_bundle_too_dense_prompt()

    def build_completion_with_action_not_allowed_prompt(self) -> str:
        return (
            "SYSTEM: A completed intent may not include a follow-up <action> in the same reply.\n"
            "If the goal is complete, return the final plain-text answer only.\n"
            "If more tool work is still needed, do not complete the intent yet.\n"
            "Return the corrected output now."
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
        if reason in {
            "reread_after_summary",
            "reread_already_in_history",
            "reread_already_in_history_use_existing_content",
        } and ctx.message:
            return str(ctx.message).strip() + next_hint

        headers = {
            "reread_after_summary": "You just summarized context and then tried to re-read a file already in history without a specific reason. Use existing context instead.",
            "reread_already_in_history": "You tried to re-read a file that is already available in history without a specific reason.",
            "reread_already_in_history_use_existing_content": "File content is already available in history. Use that content now. Do not call read_file again.",
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
                "Do not send another batch. Return one narrower search_content action, or answer from current evidence if enough is already known."
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
                "\nReturn the next valid output under the current contract."
                "\nReturn EXACTLY ONE materially different read-only action."
                "\nUse it only if tool use is still needed."
                "\nIf current evidence is already sufficient, return a plain-text answer instead."
            )
        if single_readonly_action_only:
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
        return (
            "SYSTEM: Previous action violated orchestration policy.\n"
            f"{required_hint}"
            "Use these only as recovery hints, not as a replacement for the current contract.\n"
            "Return the next valid output."
        )
