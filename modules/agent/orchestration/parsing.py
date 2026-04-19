"""Helpers for parsing intent-aware model responses."""

from __future__ import annotations

import json
import re

from .decision_models import ParsedModelOutput


class IntentResponseParser:
    INTENT_TAG_RE = re.compile(r"<intent(?:\s+[^>]*)?>(.*?)</intent>", re.IGNORECASE | re.DOTALL)
    TOOL_HISTORY_RE = re.compile(r"(?im)^\s*tool_history\s+\{.*?$")
    HISTORY_TOOL_ACTION_RE = re.compile(r"(?is)<action[^>]*\btype\s*=\s*\"history_tool\"[^>]*>.*?</action>")
    HISTORY_TOOL_TAG_RE = re.compile(r"(?is)<history_tool\b[^>]*>.*?</history_tool>")

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
        text = re.sub(r"<intent(?:\s+[^>]*)?>.*?</intent>", " ", text, flags=re.DOTALL | re.IGNORECASE)
        text = re.sub(r"<action(?:\s+type=\"[^\"]+\")?>.*?</action>", " ", text, flags=re.DOTALL | re.IGNORECASE)
        text = re.sub(self.TOOL_HISTORY_RE, " ", text)
        text = re.sub(self.HISTORY_TOOL_ACTION_RE, " ", text)
        text = re.sub(self.HISTORY_TOOL_TAG_RE, " ", text)
        text = re.sub(r"(?im)^\s*system_tool_audit:.*?$", " ", text)
        text = re.sub(r"<previously_performed_action[^>]*/>", " ", text, flags=re.IGNORECASE)
        text = re.sub(r"\s+", " ", text).strip()
        return text

    def is_tool_history_echo_without_action(self, response: str, segments) -> bool:
        if not isinstance(response, str):
            return False
        for seg in segments:
            if seg.type != "action" or not isinstance(seg.content, dict):
                continue
            action_type = str(seg.content.get("type") or seg.content.get("action") or "").strip().lower()
            if action_type == "history_tool":
                return True
        has_action_segment = any(seg.type == "action" for seg in segments)
        if has_action_segment:
            return False
        return bool(
            self.TOOL_HISTORY_RE.search(response)
            or self.HISTORY_TOOL_TAG_RE.search(response)
        )

    def needs_action_or_answer_recovery(self, response: str, segments) -> bool:
        has_action_segment = any(seg.type == "action" for seg in segments)
        if has_action_segment:
            for seg in segments:
                if seg.type != "action" or not isinstance(seg.content, dict):
                    continue
                action_type = str(seg.content.get("type") or seg.content.get("action") or "").strip().lower()
                if action_type == "history_tool":
                    return True
            return False
        visible_text = self.extract_visible_non_action_text(response)
        if visible_text:
            return False
        response_lower = response.lower()
        return (
            "<think" in response_lower
            or "<intent" in response_lower
            or "tool_history" in response_lower
            or "history_tool" in response_lower
        )

    def is_intent_only_response(self, response: str, segments) -> bool:
        if not isinstance(response, str):
            return False
        has_intent_segment = any(seg.type == "intent" for seg in segments)
        has_action_segment = any(seg.type == "action" for seg in segments)
        if not has_intent_segment or has_action_segment:
            return False
        visible_text = self.extract_visible_non_action_text(response)
        return not bool(visible_text)

    def classify(self, response: str, segments) -> ParsedModelOutput:
        safe_response = response if isinstance(response, str) else ""
        safe_segments = list(segments or [])
        has_action_tag = "<action" in safe_response.lower()
        has_action_segment = any(seg.type == "action" for seg in safe_segments)
        visible_text = self.extract_visible_non_action_text(safe_response)
        invalid_kind = ""

        if has_action_tag and not has_action_segment:
            invalid_kind = "malformed_action"
        elif self.is_tool_history_echo_without_action(safe_response, safe_segments):
            invalid_kind = "tool_history_echo"
        else:
            response_lower = safe_response.lower()
            contains_audit_marker = (
                "system_tool_audit:" in response_lower
                or response_lower.strip().startswith("tool_history ")
                or "<previously_performed_action" in response_lower
            )
            if contains_audit_marker and not has_action_segment:
                invalid_kind = "audit_marker_echo"
            elif self.is_intent_only_response(safe_response, safe_segments):
                invalid_kind = "intent_only_deadend"
            elif self.needs_action_or_answer_recovery(safe_response, safe_segments):
                invalid_kind = "missing_action_or_answer"

        return ParsedModelOutput(
            response=safe_response,
            segments=safe_segments,
            has_action_tag=has_action_tag,
            has_action_segment=has_action_segment,
            visible_text=visible_text,
            invalid_kind=invalid_kind,
        )
