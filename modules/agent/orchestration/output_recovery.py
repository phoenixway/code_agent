"""Recovery decisions for invalid or incomplete model outputs before dispatch."""

from __future__ import annotations

import re

from .decision_models import ParsedModelOutput
from .output_recovery_routing import OutputRecoveryRoutingMixin
from .output_recovery_terminal import OutputRecoveryTerminalMixin
from .response_semantics import ResponseSemantics
from .stage_logging import OrchestrationStageLogger


class ModelOutputRecoveryHandler(OutputRecoveryTerminalMixin, OutputRecoveryRoutingMixin):
    MODIFY_COMPLETION_CLAIM_RE = re.compile(
        r"(?is)\b("
        r"готово|"
        r"зміни\s+внесен(?:о|і)|"
        r"код\s+змінен(?:о|ий)|"
        r"виправлен(?:о|ий|а)|"
        r"я\s+(?:додав|додала|змінив|змінила|оновив|оновила|виправив|виправила|реалізував|реалізувала)|"
        r"тепер\s+працює|"
        r"done|"
        r"changes?\s+applied|"
        r"code\s+(?:changed|updated|fixed)|"
        r"i\s+(?:added|changed|updated|fixed|implemented)"
        r")"
    )


    NEGATED_MODIFY_COMPLETION_RE = re.compile(
        r"(?is)(?:\b(?:no|not|nothing)\b[^\n\r]{0,40}\b(?:changes?\s+applied|code\s+(?:changed|updated|fixed)|i\s+(?:added|changed|updated|fixed|implemented))\b|"
        r"\b(?:не|ще\s+не|нічого\s+не)\b[^\n\r]{0,60}\b(?:зміни\s+внесен(?:о|і)|код\s+змінен(?:о|ий)|виправлен(?:о|ий|а)|я\s+(?:додав|додала|змінив|змінила|оновив|оновила|виправив|виправила|реалізував|реалізувала))\b)"
    )

    NON_COMPLETION_PROGRESS_RE = re.compile(
        r"(?is)\b("
        r"no\s+changes?\s+applied\s+yet|"
        r"nothing\s+has\s+been\s+applied\s+yet|"
        r"still\s+need\s+to|"
        r"need\s+(?:refreshed\s+)?budget|"
        r"request\s+(?:a\s+formal\s+)?intent\s+reuse|"
        r"not\s+applied\s+yet|"
        r"no\s+changes?\s+have\s+been\s+applied|"
        r"змін\s+ще\s+не\s+внесено|"
        r"нічого\s+ще\s+не\s+застосовано|"
        r"ще\s+не\s+застосовано|"
        r"потрібно\s+оновити\s+бюджет|"
        r"потрібен\s+оновлений\s+бюджет|"
        r"потрібно\s+запросити\s+reuse|"
        r"no\s+changes\s+applied\s+yet"
        r")\b"
    )

    INTERNAL_SUMMARY_HEADING_RE = re.compile(
        r"(?im)^\s*("
        r"active goal|"
        r"established facts|"
        r"current best answer|"
        r"active plan\s*/\s*strategy|"
        r"execution state|"
        r"pending checks|"
        r"avoid regression|"
        r"important errors\s*/\s*policy events|"
        r"next best step|"
        r"execution snapshot"
        r")\s*:"
    )

    def __init__(self, agent, prompt_builder):
        self.agent = agent
        self.state = agent.state
        self.config = agent.config
        self.prompt_builder = prompt_builder
        self.stage_logger = OrchestrationStageLogger(getattr(agent, "log", None), self.state)
        self.semantics = ResponseSemantics()

    def _intent_universe_label(self) -> str:
        if getattr(self.state, "active_intent", None) is not None:
            return "active_contract"
        return "no_active_contract"

    def _missing_action_or_answer_retries(self) -> int:
        getter = getattr(self.state, "get_stop_reason_count", None)
        if callable(getter):
            try:
                return int(getter("missing_action_or_answer") or 0)
            except Exception:
                return 0
        return 0

    def _accepted_memory_checkpoint_only(self) -> bool:
        return bool(getattr(self.state, "last_memory_checkpoint_only", False))

    def _set_reflection_repair_pending(self, value: bool, kind: str = "") -> None:
        try:
            setattr(self.state, "think_reflection_repair_pending", bool(value))
            setattr(self.state, "think_reflection_repair_kind", str(kind or "").strip() if value else "")
        except Exception:
            pass

    def _current_active_intent_id(self) -> str:
        active_intent = getattr(self.state, "active_intent", None)
        return str(getattr(active_intent, "intent_id", "") or "").strip()

    def _note_missing_think_reflection_warning(self) -> int:
        intent_id = self._current_active_intent_id()
        current_intent_id = str(getattr(self.state, "missing_think_reflection_warning_intent_id", "") or "").strip()
        current_count = int(getattr(self.state, "missing_think_reflection_warning_count", 0) or 0)
        if not intent_id or intent_id != current_intent_id:
            current_count = 0
        current_count += 1
        try:
            setattr(self.state, "missing_think_reflection_warning_count", current_count)
            setattr(self.state, "missing_think_reflection_warning_intent_id", intent_id)
        except Exception:
            pass
        return current_count

    def _clear_missing_think_reflection_warning(self) -> None:
        try:
            setattr(self.state, "missing_think_reflection_warning_count", 0)
            setattr(self.state, "missing_think_reflection_warning_intent_id", "")
        except Exception:
            pass

    def _has_followup_output(self, parsed_output: ParsedModelOutput) -> bool:
        if bool(getattr(parsed_output, "has_action_segment", False)):
            return True
        if bool(getattr(parsed_output, "has_intent_segment", False)):
            return True
        return bool(str(getattr(parsed_output, "visible_text", "") or "").strip())

    def _is_missing_durable_state_checkpoint(self, parsed_output: ParsedModelOutput) -> bool:
        return False

    def _is_missing_memory_update_done(self, parsed_output: ParsedModelOutput) -> bool:
        text = str(getattr(parsed_output, "response", "") or "").strip()
        if not text:
            return False
        if bool(getattr(parsed_output, "operational_checkpoint_satisfied", False)):
            return False
        if self.semantics.has_memory_update_done(text):
            return False
        if self._is_missing_durable_state_checkpoint(parsed_output):
            return False
        return self.semantics.has_checkpoint_tags(text)

    def _is_modify_context(self) -> bool:
        active_intent = getattr(self.state, "active_intent", None)
        if active_intent is not None:
            active_type = str(getattr(active_intent, "intent_type", "") or "").strip().upper()
            return active_type == "MODIFY"

        last_completed_intent_type = str(getattr(self.state, "last_completed_intent_type", "") or "").strip().upper()
        if last_completed_intent_type == "MODIFY":
            return True

        # FIXME:
        # task_kind is a bootstrap heuristic only. It must not override an active
        # accepted intent contract. Use it only as a last-resort fallback when no
        # active intent exists and no recent completed intent gives a better signal.
        state_machine = getattr(self.state, "state_machine", None)
        task_kind = getattr(state_machine, "task_kind", None)
        task_kind_value = str(getattr(task_kind, "value", task_kind or "")).strip().upper()
        return task_kind_value == "MODIFICATION"

    def _has_current_turn_state_change_proof(self) -> bool:
        return int(getattr(self.state, "current_turn_state_change_count", 0) or 0) > 0

    def _is_negated_or_non_completion_modify_text(self, text: str) -> bool:
        normalized = str(text or "").strip()
        if not normalized:
            return False
        if self.NON_COMPLETION_PROGRESS_RE.search(normalized):
            return True
        return bool(self.NEGATED_MODIFY_COMPLETION_RE.search(normalized))

    def _is_read_only_shell(self, command_text: str) -> bool:
        lowered = str(command_text or "").strip().lower()
        if not lowered:
            return False
        if any(tok in lowered for tok in (">", "| tee", ">>", "sed -i", "perl -i", "mkdir ", "rm ", "mv ", "cp ", "touch ")):
            return False
        bins = ("find ", "rg ", "grep ", "ls ", "cat ", "head ", "tail ", "wc ", "stat ", "file ", "pwd", "pwd ", "awk ", "sed -n")
        return lowered.startswith(bins)

    def _is_state_changing_action(self, content: dict) -> bool:
        if not isinstance(content, dict):
            return False
        cmd_type = str(content.get("type") or content.get("action") or "").strip().lower()
        if cmd_type in {"edit_file", "create_file", "write_file", "write_file_block", "append_file_block", "delete_file", "replace", "git_add", "git_commit", "git_checkout"}:
            return True
        if cmd_type != "run_shell":
            return False
        return not self._is_read_only_shell(str(content.get("command") or ""))

    def _has_state_changing_action(self, parsed_output: ParsedModelOutput) -> bool:
        for seg in list(getattr(parsed_output, "segments", []) or []):
            if getattr(seg, "type", "") != "action":
                continue
            if self._is_state_changing_action(getattr(seg, "content", None)):
                return True
        return False

    def _state_changing_action_missing_operational_review(self, parsed_output: ParsedModelOutput) -> bool:
        return False

    def _state_changing_modify_checkpoint_reason(self, parsed_output: ParsedModelOutput) -> str:
        return ""

    def _note_architecture_defect_repeat(self, defect_kind: str) -> int:
        normalized = str(defect_kind or "").strip()
        if not normalized:
            return 0
        current_kind = str(getattr(self.state, "architecture_defect_repeat_kind", "") or "").strip()
        current_count = int(getattr(self.state, "architecture_defect_repeat_count", 0) or 0)
        if current_kind != normalized:
            current_count = 0
        current_count += 1
        try:
            setattr(self.state, "architecture_defect_repeat_kind", normalized)
            setattr(self.state, "architecture_defect_repeat_count", current_count)
        except Exception:
            pass
        return current_count

    def _clear_architecture_defect_repeat(self) -> None:
        try:
            setattr(self.state, "architecture_defect_repeat_kind", "")
            setattr(self.state, "architecture_defect_repeat_count", 0)
        except Exception:
            pass

    def _note_malformed_think_count(self, defect_kind: str) -> int:
        normalized = str(defect_kind or "").strip()
        if not normalized:
            return 0
        intent_id = self._current_active_intent_id()
        current_intent_id = str(getattr(self.state, "malformed_think_intent_id", "") or "").strip()
        current_count = int(getattr(self.state, "malformed_think_count", 0) or 0)
        if not intent_id or current_intent_id != intent_id:
            current_count = 0
        current_count += 1
        try:
            setattr(self.state, "malformed_think_intent_id", intent_id)
            setattr(self.state, "malformed_think_count", current_count)
        except Exception:
            pass
        return current_count

    def _decay_malformed_think_count(self) -> int:
        intent_id = self._current_active_intent_id()
        current_intent_id = str(getattr(self.state, "malformed_think_intent_id", "") or "").strip()
        current_count = int(getattr(self.state, "malformed_think_count", 0) or 0)
        if not intent_id or current_intent_id != intent_id or current_count <= 0:
            return 0
        current_count = max(0, current_count - 1)
        try:
            setattr(self.state, "malformed_think_count", current_count)
        except Exception:
            pass
        return current_count

    def _clear_malformed_think_count(self) -> None:
        try:
            setattr(self.state, "malformed_think_intent_id", "")
            setattr(self.state, "malformed_think_count", 0)
        except Exception:
            pass

    def _note_recovery_loop_handoff_repeat(self, defect_kind: str) -> int:
        intent_id = self._current_active_intent_id()
        current_intent_id = str(getattr(self.state, "recovery_loop_handoff_intent_id", "") or "").strip()
        current_count = int(getattr(self.state, "recovery_loop_handoff_count", 0) or 0)
        if not intent_id or current_intent_id != intent_id:
            current_count = 0
        current_count += 1
        try:
            setattr(self.state, "recovery_loop_handoff_intent_id", intent_id)
            setattr(self.state, "recovery_loop_handoff_count", current_count)
            setattr(self.state, "recovery_loop_handoff_defect_kind", str(defect_kind or "").strip())
        except Exception:
            pass
        return current_count

    def _clear_recovery_loop_handoff_repeat(self) -> None:
        try:
            setattr(self.state, "recovery_loop_handoff_intent_id", "")
            setattr(self.state, "recovery_loop_handoff_count", 0)
            setattr(self.state, "recovery_loop_handoff_defect_kind", "")
        except Exception:
            pass

    def _note_large_malformed_response(self, defect_kind: str) -> int:
        intent_id = self._current_active_intent_id()
        current_intent_id = str(getattr(self.state, "large_malformed_response_intent_id", "") or "").strip()
        current_count = int(getattr(self.state, "large_malformed_response_count", 0) or 0)
        if not intent_id or current_intent_id != intent_id:
            current_count = 0
        current_count += 1
        try:
            setattr(self.state, "large_malformed_response_intent_id", intent_id)
            setattr(self.state, "large_malformed_response_count", current_count)
            setattr(self.state, "large_malformed_response_kind", str(defect_kind or "").strip())
        except Exception:
            pass
        return current_count

    def _clear_large_malformed_response(self) -> None:
        try:
            setattr(self.state, "large_malformed_response_intent_id", "")
            setattr(self.state, "large_malformed_response_count", 0)
            setattr(self.state, "large_malformed_response_kind", "")
        except Exception:
            pass

    def _is_checkpoint_defect_kind(self, invalid_kind: str) -> bool:
        return str(invalid_kind or "").strip() in {
            "missing_think",
            "missing_memory_update_done",
            "no_accepted_checkpoint_tags",
            "malformed_plain_think_requires_tagged_think",
            "malformed_checkpoint",
            "state_changing_action_requires_think_reflection",
        }

    def _is_malformed_think_defect_kind(self, invalid_kind: str) -> bool:
        return str(invalid_kind or "").strip() in {
            "malformed_incomplete_think",
            "nested_think",
            "action_inside_think",
            "file_content_inside_think",
            "intent_inside_think",
        }

    def _is_unproven_modify_completion_claim(self, parsed_output: ParsedModelOutput) -> bool:
        if parsed_output.has_action_segment:
            return False
        if not self._is_modify_context():
            return False
        if self._has_current_turn_state_change_proof():
            return False
        text = str(getattr(parsed_output, "visible_text", "") or "").strip()
        if not text:
            return False
        if self._is_negated_or_non_completion_modify_text(text):
            return False
        return bool(self.MODIFY_COMPLETION_CLAIM_RE.search(text))

    def _is_internal_summary_instead_of_final_answer(self, parsed_output: ParsedModelOutput) -> bool:
        if parsed_output.has_action_segment:
            return False
        text = str(getattr(parsed_output, "visible_text", "") or "").strip()
        if not text:
            return False

        heading_hits = self.INTERNAL_SUMMARY_HEADING_RE.findall(text)
        if len(heading_hits) >= 2:
            return True

        lowered = text.lower()
        if (
            "the user asked to summarize conversation history" in lowered
            or "compress heavily" in lowered
            or "continue the current task normally" in lowered
        ) and len(heading_hits) >= 1:
            return True

        return False

    def _build_fix_final_answer_missing_build_status(self, parsed_output: ParsedModelOutput) -> bool:
        if parsed_output.has_action_segment:
            return False
        if not bool(getattr(self.state, "is_build_fix_intent_active", lambda: False)()):
            return False
        text = str(getattr(parsed_output, "visible_text", "") or "").strip()
        if not text:
            return False
        checker = getattr(self.state, "build_fix_final_answer_has_build_status", None)
        if not callable(checker):
            return False
        try:
            return not bool(checker(text))
        except Exception:
            return False

    @property
    def ui(self):
        return self.agent.ui
