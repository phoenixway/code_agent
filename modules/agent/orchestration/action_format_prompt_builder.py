"""Action-format and structural-recovery prompt builders."""

from __future__ import annotations

import re

from ..intent_message_resolver import resolve_intent_message_key
from ..intent_messages import render_intent_message


class ActionFormatPromptBuilderMixin:
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
            "SYSTEM: Your last response opened <think> but placed protocol tags before closing it.\n"
            "<think> may contain draft reasoning, but it must be closed with </think> before any memory tag, subgoal tag, <memory_update_done />, <intent>, <action>, <file_content>, or visible answer text.\n"
            "Do not put protocol tags or actions inside <think>.\n"
            "Return the corrected response from the beginning.\n"
            "Example:\n"
            "<think>\n"
            "I need to inspect the pipeline implementation before making a stronger recommendation.\n"
            "</think>\n"
            "<finding scope=\"intent\">The orchestration entry point is under modules/agent/orchestration/core.py.</finding>\n"
            "<memory_update_done />\n"
            "<action>{\"type\":\"read_file\",\"path\":\"modules/agent/orchestration/pipeline.py\"}</action>\n"
            "Do not continue the previous incomplete sentence."
        )

    def build_malformed_verbose_or_nested_think_prompt(self) -> str:
        return (
            "SYSTEM: Your last response opened <think> but used an invalid control boundary.\n"
            "<think> may contain draft reasoning, but it must be closed with </think> before any memory tag, subgoal tag, <memory_update_done />, <intent>, <action>, <file_content>, or visible answer text.\n"
            "Do not put protocol tags or actions inside <think>.\n"
            "Return the corrected response from the beginning.\n"
            "Example:\n"
            "<think>\n"
            "The current gap is the exact implementation of run_iteration.\n"
            "</think>\n"
            "<memory_update_done />\n"
            "<action>{\"type\":\"read_chunk\",\"path\":\"modules/agent/orchestration/pipeline.py\",\"start_line\":180,\"end_line\":299}</action>\n"
            "Do not continue the previous incomplete fragment."
        )

    def build_strict_compact_think_prompt(self) -> str:
        return (
            "SYSTEM: Your last response opened <think> but placed protocol tags before closing it again.\n"
            "<think> may contain draft reasoning, but it must be closed with </think> before any memory tag, subgoal tag, <memory_update_done />, <intent>, <action>, <file_content>, or visible answer text.\n"
            "Do not put protocol tags or actions inside <think>.\n"
            "Return the corrected response from the beginning.\n"
            "Example:\n"
            "<think>\n"
            "I need the exact current implementation before making the next edit.\n"
            "</think>\n"
            "<memory_update_done />\n"
            "<action>{\"type\":\"read_chunk\",\"path\":\"modules/agent/orchestration/pipeline.py\",\"start_line\":180,\"end_line\":299}</action>\n"
            "Do not continue the previous incomplete fragment."
        )

    def build_exact_think_skeleton_prompt(self) -> str:
        return (
            "SYSTEM: Your last response opened <think> but placed protocol tags before closing it again.\n"
            "<think> may contain draft reasoning, but it must be closed with </think> before any memory tag, subgoal tag, <memory_update_done />, <intent>, <action>, <file_content>, or visible answer text.\n"
            "Do not put protocol tags or actions inside <think>.\n"
            "Return the corrected response from the beginning.\n"
            "Example:\n"
            "<think>\n"
            "The current gap is the exact implementation of run_iteration.\n"
            "</think>\n"
            "<memory_update_done />\n"
            "<action>{\"type\":\"read_chunk\",\"path\":\"modules/agent/orchestration/pipeline.py\",\"start_line\":180,\"end_line\":299}</action>\n"
            "If durable tags are needed, place them between </think> and <memory_update_done />.\n"
            "Do not continue the previous incomplete fragment."
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
            "Do not return only <think> unless runtime explicitly asked for a strict repair-only response."
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

    def build_terminal_malformed_think_handoff_text(
        self,
        *,
        defect_kind: str = "",
    ) -> str:
        normalized = str(defect_kind or "").strip() or "malformed_think"
        active = self._current_active_intent()
        intent_id = str(getattr(active, "intent_id", "") or "<active_intent>").strip() or "<active_intent>"
        goal = str(getattr(active, "goal", "") or "").strip() or "unknown goal"
        return (
            "Я зупиняю виконання: модель кілька разів поспіль повернула некоректний внутрішній control-блок `<think>`.\n\n"
            "Що сталося:\n"
            f"- runtime відхилив відповідь з причиною `{normalized}`;\n"
            "- модель повторно залишала `<think>` незакритим, вкладала protocol/action tags всередину `<think>`, або писала довгий prose-plan замість компактного control-блоку;\n"
            "- жодні tool calls із malformed-відповідей не виконувались;\n"
            "- подальші retry без зміни інструкції ризикують спалювати токени без прогресу.\n\n"
            "Поточний стан:\n"
            f"- active intent: `{intent_id}`;\n"
            f"- goal: `{goal}`.\n\n"
            "Що робити далі:\n"
            "1. дай менший, детермінований наступний крок;\n"
            "2. або попроси продовжити без `<think>`/з exact skeleton;\n"
            "3. або попроси зробити fresh read/git diff перед новими edits."
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
            "Do not return only <think> unless runtime explicitly asked for a strict repair-only response."
        )

    def build_control_tag_leak_recovery_prompt(self) -> str:
        return (
            "SYSTEM: Your final answer still contains internal control tags.\n"
            "Return only the user-visible final answer.\n"
            "Do not include <think>, memory tags, subgoal tags, intent tags, action tags, or file_content."
        )

    def build_mixed_visible_text_and_control_protocol_prompt(self) -> str:
        return (
            "SYSTEM: Your response mixed a user-visible answer with internal protocol/tool use.\n"
            "Choose exactly one:\n"
            "1. Return only the final plain-text answer, with no <think>, <intent>, <action>, or other control tags.\n"
            "2. Or return internal protocol only: optional <think>, then memory/subgoal tags if needed, <memory_update_done />, and exactly one <action>.\n"
            "Do not put visible prose before internal protocol."
        )

    def sanitize_intent_goal(self, raw: str, fallback: str = "Continue multi-step code modification.") -> str:
        text = str(raw or "").replace("```", " ").strip()
        if not text:
            return fallback

        parts: list[str] = []
        for raw_line in text.splitlines():
            line = " ".join(raw_line.strip().split())
            if not line:
                continue
            if self.LOGGY_LINE_RE.match(line):
                continue
            parts.append(line)

        candidate = " ".join(parts)
        candidate = re.sub(r"\s+", " ", candidate).strip(" `")
        if not candidate:
            return fallback
        if not re.search(r"[A-Za-zА-Яа-яІіЇїЄє0-9]", candidate):
            return fallback

        noisy_markers = ("stacktrace", "traceback", "exception", "> task", "at ", "./gradlew", "adb ", "kspdebugkotlin")
        lowered = candidate.lower()
        if sum(marker in lowered for marker in noisy_markers) >= 2:
            return fallback

        if len(candidate) > 100:
            candidate = candidate[:100].rstrip()
            if " " in candidate:
                candidate = candidate.rsplit(" ", 1)[0].rstrip()
            candidate = candidate.rstrip(" ,;:-")

        candidate = candidate.replace("\n", " ").strip()
        if not candidate:
            return fallback
        return candidate[:100]

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
            "Do not return only <think> unless runtime explicitly asked for a strict repair-only response."
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

    def build_action_payload_array_prompt(self) -> str:
        return (
            "SYSTEM: Your last <action> block contained a JSON array, not a single action object.\n"
            "Return EXACTLY ONE valid <action>...</action> block now.\n"
            "Inside <action>, include exactly ONE JSON object for exactly ONE next action.\n"
            "Do not wrap actions in [...].\n"
            "If you need a narrowed read-only batch, use 2-4 separate top-level <action> blocks, one JSON object per block.\n"
            "That separate top-level batch is allowed only when every action is read-only and already narrowed.\n"
            "State-changing actions must remain single."
        )

    def build_multiple_actions_prompt(self) -> str:
        return (
            "SYSTEM: Your last response contained multiple top-level <action> blocks that cannot be batched.\n"
            "Multiple top-level <action> blocks are allowed only when every action is read-only.\n"
            "State-changing or mixed read/write batches are not atomic and are rejected.\n"
            "Return EXACTLY ONE valid <action>...</action> block now for the single next state-changing step, "
            "or return a pure read-only batch only if every action is read-only.\n"
            "Only top-level protocol <action> blocks count here; raw text inside <file_content> does not.\n"
            "Do not use an action array."
        )

    def build_conflicting_intent_transitions_prompt(self) -> str:
        return (
            "SYSTEM: Your last response contained conflicting intent transitions.\n"
            "Return only one top-level <intent> transition if a real transition is needed.\n"
            "Do not include <think>, <memory_update_done />, <action>, <file_content>, or final answer.\n"
            "If a contract is already active and no real transition is needed, do not emit another <intent> block."
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
