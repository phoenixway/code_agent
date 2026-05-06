"""Shared prompt-builder helpers for orchestration prompt modules."""

from __future__ import annotations

import json
import re
from pathlib import Path

from modules.defaults import DEFAULT_SYSTEM_PROMPT

from ...intent_message_resolver import resolve_intent_message_key
from ...intent_messages import render_intent_message
from ..shared.decision_models import RecoveryContext
from ..shared.recovery_policy import RecoveryPolicyResolver
from ..transitions.intent_universe import IntentUniverseResolver


class PromptBuilderSharedMixin:
    SOURCE_FILE_SUFFIXES = {
        ".py", ".kt", ".kts", ".java", ".js", ".jsx", ".ts", ".tsx", ".go",
        ".rs", ".c", ".cc", ".cpp", ".cxx", ".h", ".hpp", ".cs", ".swift",
        ".rb", ".php", ".scala", ".sql", ".sh", ".bash", ".zsh", ".xml",
        ".json", ".yaml", ".yml", ".toml", ".gradle", ".md",
    }
    LOGGY_LINE_RE = re.compile(
        r"^(?:[$>#]|❯|at\s+|Caused by:|Traceback\b|> Task\b|BUILD (?:FAILED|SUCCESSFUL)\b|e:\s|\w+Exception\b)",
        re.IGNORECASE,
    )

    def _init_prompt_builder_shared(self, agent):
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
        return [
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
        active = self._active_intent_lineage_ids()
        if active:
            return active
        recent = str(getattr(self.state, "last_resumable_intent_id", "") or "").strip()
        return [recent] if recent else []

    def _memory_tag_followup_lines(self) -> list[str]:
        if not bool(getattr(self.state, "memory_tag_expected_next_step", False)):
            return []

        expected_intent_id = str(getattr(self.state, "memory_tag_expected_intent_id", "") or "").strip()
        active_intent_id = str(self._current_active_intent_id() or "").strip()
        if expected_intent_id and active_intent_id and expected_intent_id != active_intent_id:
            return []

        reason = str(getattr(self.state, "memory_tag_reason", "") or "").strip()
        reason_map = {
            "meaningful_evidence_gain": "Previous step produced meaningful evidence but no memory tag was emitted.",
            "meaningful_progress": "Previous step made meaningful progress but no memory tag was emitted.",
            "durable_decision": "Previous step established a durable decision but no memory tag was emitted.",
        }
        message = reason_map.get(reason) or "Previous step should have emitted one concise memory tag before continuing."
        return [
            "",
            "Memory-board follow-up from the previous step:",
            f"- {message}",
            "- If this step continues the same intent, emit exactly one concise memory tag before the next action or final answer.",
        ]

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

    def _latest_operational_journal_entry(self) -> dict | None:
        state = getattr(self, "state", None)
        if state is None:
            return None
        snapshotter = getattr(state, "operational_journal_snapshot", None)
        if callable(snapshotter):
            try:
                snapshot = snapshotter() or []
                if snapshot:
                    latest = snapshot[-1]
                    return latest if isinstance(latest, dict) else None
            except Exception:
                pass
        journal = list(getattr(state, "operational_journal", []) or [])
        if not journal:
            return None
        latest = journal[-1]
        if isinstance(latest, dict):
            return latest
        if hasattr(latest, "__dict__"):
            try:
                return dict(vars(latest))
            except Exception:
                return None
        return None

    def _summarize_last_committed_action(self) -> str:
        entry = self._latest_operational_journal_entry()
        if not isinstance(entry, dict):
            return "none"
        if str(entry.get("kind") or "").strip() != "tool_execution_commit":
            return "none"

        action_type = str(entry.get("action_type") or "").strip()
        target = str(entry.get("target") or "").strip()
        if not action_type:
            effects = list(entry.get("action_effects") or [])
            if effects:
                primary = str(effects[0] or "").strip()
                if ":" in primary:
                    action_type, target = primary.split(":", 1)
                elif primary:
                    action_type = primary
        if not action_type:
            return "none"

        rendered = action_type
        if target:
            rendered += f'("{target[:120]}")'
        if bool(entry.get("action_dispatched", False)):
            return f"{rendered} -> success"
        return rendered

    def _summarize_last_failed_action(self) -> str:
        state = getattr(self, "state", None)
        if state is None:
            return "none"
        command = getattr(state, "last_failed_action_command", None)
        result = getattr(state, "last_failed_action_result", None)
        if not isinstance(command, dict):
            return "none"

        cmd_type = str(command.get("type") or command.get("action") or "action").strip() or "action"
        rendered = cmd_type
        path = command.get("path")
        shell_command = command.get("command")
        pattern = command.get("pattern") or command.get("query") or command.get("name")
        if isinstance(path, str) and path.strip():
            rendered += f'("{path[:120]}")'
        elif isinstance(shell_command, str) and shell_command.strip():
            rendered += f'("{shell_command[:80]}")'
        elif pattern not in (None, ""):
            rendered += f'("{str(pattern)[:80]}")'

        status = ""
        if isinstance(result, dict):
            status = str(result.get("status") or "").strip().lower()
        if status:
            return f"{rendered} -> {status}"
        return rendered

    def _summarize_last_action(self) -> str:
        committed = self._summarize_last_committed_action()
        if committed != "none":
            return committed

        failed = self._summarize_last_failed_action()
        if failed != "none":
            return failed

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
