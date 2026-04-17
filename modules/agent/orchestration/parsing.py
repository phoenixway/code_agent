"""Helpers for parsing intent-aware model responses."""

from __future__ import annotations

import json
import re


class IntentResponseParser:
    INTENT_TAG_RE = re.compile(r"<intent>(.*?)</intent>", re.IGNORECASE | re.DOTALL)

    def extract_intent_update_and_strip(self, response_text: str) -> tuple[str, dict | None, str | None]:
        if not isinstance(response_text, str) or not response_text:
            return response_text, None, None
        matches = list(self.INTENT_TAG_RE.finditer(response_text))
        if not matches:
            return response_text, None, None
        last_block = matches[-1].group(1).strip()
        clean_text = self.INTENT_TAG_RE.sub("", response_text).strip()
        if not last_block:
            return clean_text, None, "empty_intent_block"
        try:
            payload = json.loads(last_block)
        except json.JSONDecodeError:
            return clean_text, None, "invalid_intent_json"
        return clean_text, payload, None

    def extract_visible_non_action_text(self, response: str) -> str:
        if not isinstance(response, str):
            return ""
        text = response
        text = re.sub(r"<think>.*?</think>", " ", text, flags=re.DOTALL | re.IGNORECASE)
        text = re.sub(r"<intent>.*?</intent>", " ", text, flags=re.DOTALL | re.IGNORECASE)
        text = re.sub(r"<action(?:\s+type=\"[^\"]+\")?>.*?</action>", " ", text, flags=re.DOTALL | re.IGNORECASE)
        text = re.sub(r"(?im)^\s*tool_history\s+\{.*?$", " ", text)
        text = re.sub(r"(?im)^\s*system_tool_audit:.*?$", " ", text)
        text = re.sub(r"<previously_performed_action[^>]*/>", " ", text, flags=re.IGNORECASE)
        text = re.sub(r"\s+", " ", text).strip()
        return text

    def needs_action_or_answer_recovery(self, response: str, segments) -> bool:
        has_action_segment = any(seg.type == "action" for seg in segments)
        if has_action_segment:
            return False
        visible_text = self.extract_visible_non_action_text(response)
        if visible_text:
            return False
        return "<think" in response.lower() or "<intent" in response.lower() or "tool_history" in response.lower()

    def is_intent_only_response(self, response: str, segments) -> bool:
        if not isinstance(response, str):
            return False
        has_intent_segment = any(seg.type == "intent" for seg in segments)
        has_action_segment = any(seg.type == "action" for seg in segments)
        if not has_intent_segment or has_action_segment:
            return False
        visible_text = self.extract_visible_non_action_text(response)
        return not bool(visible_text)
