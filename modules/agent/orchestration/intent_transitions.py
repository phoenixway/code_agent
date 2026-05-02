"""Intent payload application and transition handling."""

from __future__ import annotations

import re

from .intent_transition_apply import IntentTransitionApplyMixin
from .intent_transition_routing import IntentTransitionRoutingMixin
from .stage_logging import OrchestrationStageLogger


class IntentTransitionHandler(IntentTransitionApplyMixin, IntentTransitionRoutingMixin):
    REMAINING_OPEN_CONTROL_TAG_RE = re.compile(r"<\s*(intent|action)\b", re.IGNORECASE)
    REMAINING_ACTION_TAG_RE = re.compile(r"<\s*action\b", re.IGNORECASE)
    INTENT_TAG_RE = re.compile(r"<intent(?:\s+[^>]*)?>.*?</intent>", re.IGNORECASE | re.DOTALL)
    THINK_TAG_RE = re.compile(r"<think(?:\s+[^>]*)?>.*?</think>", re.IGNORECASE | re.DOTALL)
    FILE_CONTENT_TAG_RE = re.compile(r"<file_content(?:\s+[^>]*)?>.*?</file_content>", re.IGNORECASE | re.DOTALL)
    MEMORY_BLOCK_RE = re.compile(r"<(fact|finding|decision|preference|progress|path)\b[^>]*>.*?</\1>", re.IGNORECASE | re.DOTALL)
    MEMORY_TAG_RE = re.compile(r"</?(fact|finding|decision|preference|progress|path)\b[^>]*>", re.IGNORECASE)
    MEMORY_REVIEW_RE = re.compile(r"<memory_review\b[^>]*/>", re.IGNORECASE)
    SUBGOAL_TAG_RE = re.compile(r"<subgoal\b[^>]*(?:>.*?</subgoal>|/>)", re.IGNORECASE | re.DOTALL)
    MEMORY_UPDATE_DONE_RE = re.compile(r"<memory_update_done\s*/>", re.IGNORECASE)

    def __init__(self, agent, prompt_builder, recovery):
        self.agent = agent
        self.state = agent.state
        self.config = agent.config
        self.prompt_builder = prompt_builder
        self.recovery = recovery
        self.stage_logger = OrchestrationStageLogger(getattr(agent, "log", None), self.state)

    def _intent_universe_label(self) -> str:
        if getattr(self.state, "active_intent", None) is not None:
            return "active_contract"
        return "no_active_contract"

    def _resumable_intent_meta(self) -> tuple[str, str, str]:
        interruption = getattr(self.state, "last_technical_interruption", None)
        interruption_id = str(getattr(interruption, "resumable_intent_id", "") or "").strip()
        resumable_id = interruption_id or str(getattr(self.state, "last_resumable_intent_id", "") or "").strip()
        resumable_type = str(getattr(self.state, "last_resumable_intent_type", "") or "").strip()
        resumable_goal = str(getattr(self.state, "last_resumable_intent_goal", "") or "").strip()
        return resumable_id, resumable_type, resumable_goal

    def _mask_file_content_blocks(self, text: str) -> str:
        def _mask(match: re.Match) -> str:
            return " " * (match.end() - match.start())

        return self.FILE_CONTENT_TAG_RE.sub(_mask, text)

    def _mask_for_followup_analysis(self, response_text: str, *, strip_intent: bool = False) -> str:
        text = str(response_text or "").strip()
        if not text:
            return ""
        masked = self.THINK_TAG_RE.sub(" ", text)
        masked = self._mask_file_content_blocks(masked)
        if strip_intent:
            masked = self.INTENT_TAG_RE.sub(" ", masked)
        return masked

    def _remaining_transition_bundle_too_dense(self, response_text: str) -> bool:
        masked = self._mask_for_followup_analysis(response_text)
        if not masked:
            return False
        intent_count = len(self.INTENT_TAG_RE.findall(masked))
        action_count = len(self.REMAINING_ACTION_TAG_RE.findall(masked))
        if intent_count >= 1:
            return True
        return action_count >= 2

    def _remaining_has_action_only(self, response_text: str) -> bool:
        masked = self._mask_for_followup_analysis(response_text)
        if not masked:
            return False
        if "<intent" in masked.lower():
            return False
        return bool(self.REMAINING_ACTION_TAG_RE.search(masked))


    def _remaining_has_plaintext_answer_only(self, response_text: str) -> bool:
        masked = self._mask_for_followup_analysis(response_text)
        if not masked:
            return False
        if re.search(r"<\s*(intent|action)\b", masked, re.IGNORECASE):
            return False
        masked = self.MEMORY_BLOCK_RE.sub(" ", masked)
        masked = self.MEMORY_TAG_RE.sub(" ", masked)
        masked = self.MEMORY_REVIEW_RE.sub(" ", masked)
        masked = self.SUBGOAL_TAG_RE.sub(" ", masked)
        masked = self.MEMORY_UPDATE_DONE_RE.sub(" ", masked)
        return bool(re.sub(r"<[^>]+>", " ", masked).strip())

    def _response_without_think_and_intent(self, response_text: str) -> str:
        return self._mask_for_followup_analysis(response_text, strip_intent=True).strip()

    def _has_no_followup_after_intent(self, response_text: str) -> bool:
        return not bool(self._response_without_think_and_intent(response_text))

    def _reuse_has_inline_single_action(self, intent_payload: dict | None, response_text: str) -> bool:
        payload_mode = str((intent_payload or {}).get("mode") or "").strip().lower()
        if payload_mode != "reuse":
            return False
        masked = self._response_without_think_and_intent(response_text)
        if not masked:
            return False
        if re.search(r"<\s*intent\b", masked, re.IGNORECASE):
            return False
        action_count = len(self.REMAINING_ACTION_TAG_RE.findall(masked))
        return action_count == 1

    def _reuse_has_inline_plaintext_answer(self, intent_payload: dict | None, response_text: str) -> bool:
        payload_mode = str((intent_payload or {}).get("mode") or "").strip().lower()
        if payload_mode != "reuse":
            return False
        masked = self._response_without_think_and_intent(response_text)
        if not masked:
            return False
        if re.search(r"<\s*(intent|action)\b", masked, re.IGNORECASE):
            return False
        masked = self.MEMORY_BLOCK_RE.sub(" ", masked)
        masked = self.MEMORY_TAG_RE.sub(" ", masked)
        masked = self.MEMORY_REVIEW_RE.sub(" ", masked)
        masked = self.SUBGOAL_TAG_RE.sub(" ", masked)
        masked = self.MEMORY_UPDATE_DONE_RE.sub(" ", masked)
        return bool(re.sub(r"<[^>]+>", " ", masked).strip())

    def _remaining_has_any_action(self, response_text: str) -> bool:
        masked = self._mask_for_followup_analysis(response_text)
        if not masked:
            return False
        return bool(self.REMAINING_ACTION_TAG_RE.search(masked))

    def _reuse_only_intent_required(self) -> bool:
        return bool(getattr(self.state, "reuse_only_intent_required", False))

    def _clear_reuse_only_intent_required(self) -> None:
        try:
            setattr(self.state, "reuse_only_intent_required", False)
            setattr(self.state, "reuse_only_blocked_action", "")
        except Exception:
            pass

    def _transition_only_intent_required(self) -> bool:
        return bool(getattr(self.state, "transition_only_intent_required", False))

    def _clear_transition_only_intent_required(self) -> None:
        try:
            setattr(self.state, "transition_only_intent_required", False)
            setattr(self.state, "transition_only_blocked_action", "")
        except Exception:
            pass

    def _note_transition_defect(self, reason: str) -> int:
        normalized_reason = str(reason or "").strip()
        universe = self._intent_universe_label()
        current_reason = str(getattr(self.state, "intent_transition_defect_reason", "") or "").strip()
        current_universe = str(getattr(self.state, "intent_transition_defect_universe", "") or "").strip()
        count = int(getattr(self.state, "intent_transition_defect_count", 0) or 0)
        if normalized_reason != current_reason or universe != current_universe:
            count = 0
        count += 1
        try:
            setattr(self.state, "intent_transition_defect_reason", normalized_reason)
            setattr(self.state, "intent_transition_defect_universe", universe)
            setattr(self.state, "intent_transition_defect_count", count)
        except Exception:
            pass
        return count

    def _clear_transition_defect(self) -> None:
        try:
            setattr(self.state, "intent_transition_defect_reason", "")
            setattr(self.state, "intent_transition_defect_universe", "")
            setattr(self.state, "intent_transition_defect_count", 0)
        except Exception:
            pass

    def _remaining_followup_conflict_reason(self, response_text: str) -> str:
        masked = self._mask_for_followup_analysis(response_text)
        if not masked:
            return ""
        if len(self.INTENT_TAG_RE.findall(masked)) >= 1:
            return "conflicting_intent_transitions"
        if len(self.REMAINING_ACTION_TAG_RE.findall(masked)) >= 2:
            return "multiple_actions"
        return ""

