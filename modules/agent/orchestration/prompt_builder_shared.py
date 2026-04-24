"""Shared prompt-builder helpers for orchestration prompt modules."""

from __future__ import annotations

import json

from modules.defaults import DEFAULT_SYSTEM_PROMPT

from ..intent_message_resolver import resolve_intent_message_key
from ..intent_messages import render_intent_message
from .decision_models import RecoveryContext
from .intent_universe import IntentUniverseResolver
from .recovery_policy import RecoveryPolicyResolver


class PromptBuilderSharedMixin:
        def _init_prompt_builder_shared(self, agent):
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

        def _memory_tag_followup_lines(self) -> list[str]:
            # Step-based memory-tag follow-up is disabled.
            # Reflection is now tied to substantial think blocks rather than step debt.
            return []

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

        def _should_prefer_current_intent_recovery(self, stop_info: dict | None) -> bool:
            ctx = self._recovery_context(stop_info)
            return self.recovery_policy_resolver.should_prefer_current_intent_recovery(
                ctx,
                active_intent=self._current_active_intent(),
            )

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

        def _plain_text_completion_kind(self, sm) -> str:
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