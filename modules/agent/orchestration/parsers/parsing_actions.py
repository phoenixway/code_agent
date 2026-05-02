"""Action and structure guards for intent-aware response parsing."""

from __future__ import annotations

import json

from .visible_text import (
    detect_incomplete_control_markup,
    detect_invalid_think_markup,
    extract_visible_text_for_user,
    strip_plain_think_prefix_artifacts,
    visible_text_has_control_tag_leak,
)


class ParsingActionsMixin:
    def extract_visible_non_action_text(self, response: str) -> str:
        return extract_visible_text_for_user(response)

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
            or self.has_plain_think_prefix(response)
        )

    def has_plain_think_prefix(self, response: str) -> bool:
        _cleaned, stripped = strip_plain_think_prefix_artifacts(str(response or ""))
        return stripped

    def is_intent_only_response(self, response: str, segments) -> bool:
        if not isinstance(response, str):
            return False
        has_action_segment = any(seg.type == "action" for seg in segments)
        visible_text = self.extract_visible_non_action_text(response)
        if has_action_segment or bool(visible_text):
            return False

        text = str(response or "")
        if "<intent" not in text.lower():
            return False
        _clean_text, payload, error = self.extract_intent_update_and_strip(text)
        if payload is None or error:
            return False
        return str(payload.get("mode") or "").strip().lower() != "reuse"

    def is_valid_reuse_only_intent_response(self, response: str, segments) -> bool:
        if not isinstance(response, str):
            return False
        has_action_segment = any(seg.type == "action" for seg in segments)
        visible_text = self.extract_visible_non_action_text(response)
        if has_action_segment or bool(visible_text):
            return False
        text = str(response or "")
        if "<intent" not in text.lower():
            return False
        _clean_text, payload, error = self.extract_intent_update_and_strip(text)
        if payload is None or error:
            return False
        return str(payload.get("mode") or "").strip().lower() == "reuse"

    def has_conflicting_intent_transitions(self, response: str, segments) -> bool:
        intent_count = sum(1 for seg in segments if getattr(seg, "type", "") == "intent")
        if intent_count < 2:
            masked_response = self._mask_think_blocks(str(response or ""))
            action_spans = self._spans_for_action_blocks(masked_response)
            top_level_matches = [
                match
                for match in self.INTENT_TAG_RE.finditer(masked_response)
                if not self._span_inside_any(match.start(0), match.end(0), action_spans)
            ]
            intent_count = len(top_level_matches)
        return intent_count >= 2

    def action_segment_is_read_only(self, segment) -> bool:
        if getattr(segment, "type", "") != "action":
            return False
        content = getattr(segment, "content", None)
        if not isinstance(content, dict):
            return False
        action_type = str(content.get("type") or content.get("action") or "").strip().lower()
        return action_type in self.READ_ONLY_ACTION_TYPES

    def multiple_actions_are_pure_read_only(self, segments) -> bool:
        action_segments = [
            seg for seg in list(segments or [])
            if getattr(seg, "type", "") == "action"
        ]
        if len(action_segments) < 2:
            return False
        return all(self.action_segment_is_read_only(seg) for seg in action_segments)

    def has_multiple_actions(self, segments) -> bool:
        action_count = sum(1 for seg in segments if getattr(seg, "type", "") == "action")
        if action_count < 2:
            return False
        return not self.multiple_actions_are_pure_read_only(segments)

    def has_file_content_before_action(self, segments) -> bool:
        saw_file_content = False
        for seg in list(segments or []):
            seg_type = getattr(seg, "type", "")
            if seg_type == "file_content":
                saw_file_content = True
                continue
            if seg_type == "text":
                if str(getattr(seg, "content", "") or "").strip():
                    continue
            if seg_type == "action" and saw_file_content:
                return True
        return False

    def malformed_intent_payload_kind(self, response: str) -> str:
        text = str(response or "")
        if not text:
            return ""

        masked_response = self._mask_think_blocks(text)
        action_spans = self._spans_for_action_blocks(masked_response)

        for match in self.INTENT_TAG_RE.finditer(masked_response):
            if self._span_inside_any(match.start(0), match.end(0), action_spans):
                continue

            body = str(match.group("body") or "").strip()
            if not body:
                continue

            try:
                json.loads(body)
                continue
            except json.JSONDecodeError:
                pass

            if self.ACTION_TAG_RE.search(body):
                return "intent_body_contains_action"

        return ""

    def malformed_action_payload_kind(self, response: str) -> str:
        text = str(response or "")
        if not text:
            return ""

        for match in self.ACTION_BLOCK_RE.finditer(text):
            body = str(match.group("body") or "").strip()
            if not body:
                return "malformed_action"

            try:
                payload = json.loads(body)
            except json.JSONDecodeError:
                payload = None

            if payload is not None:
                if isinstance(payload, list):
                    return "action_payload_array"
                if not isinstance(payload, dict):
                    return "malformed_action"
                action_type = str(payload.get("type") or payload.get("action") or payload.get("command") or "").strip()
                if not action_type:
                    return "malformed_action"
                continue

            if self.ACTION_XML_PAYLOAD_TAG_RE.search(body):
                return "malformed_action"
            return "malformed_action"

        return ""

    def visible_text_before_control_protocol_kind(self, response: str) -> str:
        text = str(response or "")
        if not text.strip():
            return ""
        masked = self.think_repairer._mask_textual_protocol_contexts(text)
        match = self.TOP_LEVEL_CONTROL_BLOCK_RE.search(masked)
        if match is None:
            return ""
        prefix = text[:match.start()]
        if not str(prefix or "").strip():
            return ""
        visible_prefix = self.extract_visible_non_action_text(prefix)
        if not str(visible_prefix or "").strip():
            return ""
        return "mixed_visible_text_and_control_protocol"

    def classify(self, response: str, segments, *, allow_think_autorepair: bool = True):
        safe_response = response if isinstance(response, str) else ""
        normalized = self.normalize_model_response(
            safe_response,
            allow_think_autorepair=allow_think_autorepair,
        )
        safe_response = normalized.normalized_response
        safe_segments = list(segments or [])
        has_action_tag = "<action" in safe_response.lower()
        has_action_segment = any(seg.type == "action" for seg in safe_segments)
        has_intent_segment = any(seg.type == "intent" for seg in safe_segments)
        visible_text = self.extract_visible_non_action_text(safe_response)
        invalid_kind = ""
        has_plain_think_prefix = self.has_plain_think_prefix(safe_response)
        incomplete_control_kind = detect_incomplete_control_markup(safe_response)
        invalid_think_kind = detect_invalid_think_markup(safe_response)
        mixed_visible_control_kind = self.visible_text_before_control_protocol_kind(safe_response)
        malformed_intent_kind = self.malformed_intent_payload_kind(safe_response)
        malformed_action_kind = self.malformed_action_payload_kind(safe_response)
        control_tag_leak = visible_text_has_control_tag_leak(safe_response)

        if has_plain_think_prefix and self.logger is not None and (has_action_segment or has_intent_segment or bool(visible_text)):
            self.logger.warning("response_parser_fallback=plain_think_prefix_ignored")

        if incomplete_control_kind:
            invalid_kind = incomplete_control_kind
        elif invalid_think_kind:
            invalid_kind = invalid_think_kind
        elif mixed_visible_control_kind:
            invalid_kind = mixed_visible_control_kind
        elif control_tag_leak:
            invalid_kind = "control_tag_leak_in_visible_text"
        elif malformed_intent_kind:
            invalid_kind = malformed_intent_kind
        elif malformed_action_kind:
            invalid_kind = malformed_action_kind
        elif self.has_file_content_before_action(safe_segments):
            invalid_kind = "file_content_must_follow_action"
        elif has_action_tag and not has_action_segment:
            invalid_kind = "malformed_action"
        elif self.has_conflicting_intent_transitions(safe_response, safe_segments):
            invalid_kind = "conflicting_intent_transitions"
        elif self.has_multiple_actions(safe_segments):
            invalid_kind = "multiple_actions"
        elif self.is_tool_history_echo_without_action(safe_response, safe_segments):
            invalid_kind = "tool_history_echo"
        elif has_plain_think_prefix and not has_action_segment and not has_intent_segment and not visible_text:
            invalid_kind = "plain_think_without_valid_output"
        else:
            response_lower = safe_response.lower()
            contains_audit_marker = (
                "system_tool_audit:" in response_lower
                or response_lower.strip().startswith("tool_history ")
                or "<previously_performed_action" in response_lower
            )
            if contains_audit_marker and not has_action_segment:
                invalid_kind = "audit_marker_echo"
            elif self.is_valid_reuse_only_intent_response(safe_response, safe_segments):
                invalid_kind = ""
            elif self.is_intent_only_response(safe_response, safe_segments):
                invalid_kind = "intent_only_without_next_step"
            elif self.needs_action_or_answer_recovery(safe_response, safe_segments):
                invalid_kind = "missing_action_or_answer"

        return self._build_parsed_output(
            safe_response=safe_response,
            safe_segments=safe_segments,
            has_action_tag=has_action_tag,
            has_action_segment=has_action_segment,
            has_intent_segment=has_intent_segment,
            visible_text=visible_text,
            invalid_kind=invalid_kind,
            normalized=normalized,
        )
