"""Intent payload application and transition handling."""

from __future__ import annotations

import re

from .dependencies import TransitionLayerCollaborators
from .intent_transition_apply import IntentTransitionApplyMixin
from .intent_transition_routing import IntentTransitionRoutingMixin
from ..responses.stage_logging import OrchestrationStageLogger


class IntentTransitionHandler(IntentTransitionApplyMixin, IntentTransitionRoutingMixin):
    REMAINING_OPEN_CONTROL_TAG_RE = re.compile(r"<\s*(intent|action)\b", re.IGNORECASE)
    REMAINING_ACTION_TAG_RE = re.compile(r"<\s*action\b", re.IGNORECASE)
    INTENT_TAG_RE = re.compile(
        r"<intent\b(?P<attrs>[^>]*?)(?:>(?P<body>.*?)</intent>|(?P<selfclose>/\s*>))",
        re.IGNORECASE | re.DOTALL,
    )
    THINK_TAG_RE = re.compile(r"<think(?:\s+[^>]*)?>.*?</think>", re.IGNORECASE | re.DOTALL)
    ACTION_BLOCK_RE = re.compile(r"<action(?:\s+[^>]*)?>.*?</action>", re.IGNORECASE | re.DOTALL)
    FILE_CONTENT_TAG_RE = re.compile(r"<file_content(?:\s+[^>]*)?>.*?</file_content>", re.IGNORECASE | re.DOTALL)
    MEMORY_BLOCK_RE = re.compile(r"<(fact|finding|decision|preference|progress|path)\b[^>]*>.*?</\1>", re.IGNORECASE | re.DOTALL)
    MEMORY_TAG_RE = re.compile(r"</?(fact|finding|decision|preference|progress|path)\b[^>]*>", re.IGNORECASE)
    MEMORY_REVIEW_RE = re.compile(r"<memory_review\b[^>]*/>", re.IGNORECASE)
    SUBGOAL_TAG_RE = re.compile(r"<subgoal\b[^>]*(?:>.*?</subgoal>|/>)", re.IGNORECASE | re.DOTALL)
    MEMORY_UPDATE_DONE_RE = re.compile(r"<memory_update_done\s*/>", re.IGNORECASE)
    ATTR_RE = re.compile(r"""([a-zA-Z_][\w\-]*)\s*=\s*(?:"([^"]*)"|'([^']*)')""")

    def __init__(self, agent, prompt_builder, recovery):
        self.agent = agent
        self.runtime = TransitionLayerCollaborators.from_agent(agent, needs_config=True)
        self.state = self.runtime.state
        self.config = self.runtime.config
        self.prompt_builder = prompt_builder
        self.recovery = recovery
        self.stage_logger = OrchestrationStageLogger(self.runtime.logger, self.state)

    def _intent_universe_label(self) -> str:
        if getattr(self.state, "active_intent", None) is not None:
            return "active_contract"
        return "no_active_contract"

    @property
    def ui(self):
        return getattr(self.agent, "ui", None)

    @property
    def logger(self):
        return self.runtime.logger

    def _resumable_intent_meta(self) -> tuple[str, str, str]:
        interruption = getattr(self.state, "last_technical_interruption", None)
        interruption_id = str(getattr(interruption, "resumable_intent_id", "") or "").strip()
        resumable_id = interruption_id or str(getattr(self.state, "last_resumable_intent_id", "") or "").strip()
        resumable_type = str(getattr(self.state, "last_resumable_intent_type", "") or "").strip()
        resumable_goal = str(getattr(self.state, "last_resumable_intent_goal", "") or "").strip()
        return resumable_id, resumable_type, resumable_goal

    def _parse_attrs(self, attrs_raw: str) -> dict[str, str]:
        attrs: dict[str, str] = {}
        if not isinstance(attrs_raw, str) or not attrs_raw.strip():
            return attrs
        for key, v1, v2 in self.ATTR_RE.findall(attrs_raw.strip()):
            attrs[str(key).strip().lower()] = str(v1 or v2 or "").strip()
        return attrs

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
        if re.search(r"<\s*intent\b", masked, re.IGNORECASE):
            return False
        action_count = len(self.REMAINING_ACTION_TAG_RE.findall(masked))
        if action_count != 1:
            return False
        masked = self.ACTION_BLOCK_RE.sub(" ", masked)
        masked = self.FILE_CONTENT_TAG_RE.sub(" ", masked)
        masked = self.MEMORY_BLOCK_RE.sub(" ", masked)
        masked = self.MEMORY_TAG_RE.sub(" ", masked)
        masked = self.MEMORY_REVIEW_RE.sub(" ", masked)
        masked = self.SUBGOAL_TAG_RE.sub(" ", masked)
        masked = self.MEMORY_UPDATE_DONE_RE.sub(" ", masked)
        return not bool(re.sub(r"<[^>]+>", " ", masked).strip())


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

    def _strip_matching_current_intent_block(self, response_text: str, intent_payload: dict | None) -> str:
        text = str(response_text or "")
        if not text or not isinstance(intent_payload, dict):
            return text
        matches = list(self.INTENT_TAG_RE.finditer(text))
        if not matches:
            return text
        payload_mode = str((intent_payload or {}).get("mode") or "").strip().lower()
        payload_id = str((intent_payload or {}).get("intent_id") or "").strip()
        payload_type = str((intent_payload or {}).get("intent_type") or "").strip().upper()
        payload_goal = str((intent_payload or {}).get("goal") or "").strip()
        for match in reversed(matches):
            attrs = self._parse_attrs(match.group("attrs") or "")
            body = str(match.group("body") or "").strip()
            block_payload = None
            if body:
                try:
                    import json
                    parsed = json.loads(body)
                    if isinstance(parsed, dict):
                        block_payload = parsed
                except Exception:
                    block_payload = None
            if block_payload is None:
                continue
            block_mode = str(block_payload.get("mode") or attrs.get("mode") or "").strip().lower()
            block_id = str(block_payload.get("intent_id") or "").strip()
            block_type = str(block_payload.get("intent_type") or "").strip().upper()
            block_goal = str(block_payload.get("goal") or "").strip()
            comparisons = 0
            if payload_mode:
                comparisons += 1
                if block_mode != payload_mode:
                    continue
            if payload_id:
                comparisons += 1
                if block_id != payload_id:
                    continue
            if payload_type:
                comparisons += 1
                if block_type != payload_type:
                    continue
            if payload_goal:
                comparisons += 1
                if block_goal != payload_goal:
                    continue
            if comparisons == 0:
                continue
            start, end = match.span(0)
            return (text[:start] + text[end:]).strip()
        return text

    def _has_no_followup_after_intent(self, response_text: str) -> bool:
        return not bool(self._response_without_think_and_intent(response_text))

    def _reuse_has_inline_single_action(self, intent_payload: dict | None, response_text: str) -> bool:
        payload_mode = str((intent_payload or {}).get("mode") or "").strip().lower()
        if payload_mode != "reuse":
            return False
        masked = self._response_without_think_and_intent(
            self._strip_matching_current_intent_block(response_text, intent_payload)
        )
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
        masked = self._response_without_think_and_intent(
            self._strip_matching_current_intent_block(response_text, intent_payload)
        )
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

    def _current_transition_has_inline_action_only(self, intent_payload: dict | None, response_text: str) -> bool:
        stripped = self._strip_matching_current_intent_block(response_text, intent_payload)
        return self._remaining_has_action_only(stripped)

    def _followup_conflict_reason_after_current_transition(self, intent_payload: dict | None, response_text: str) -> str:
        stripped = self._strip_matching_current_intent_block(response_text, intent_payload)
        return self._remaining_followup_conflict_reason(stripped)

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
