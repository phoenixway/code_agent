"""Helpers for parsing intent-aware model responses."""

from __future__ import annotations

import json
import re

from .decision_models import ParsedModelOutput
from .visible_text import (
    detect_incomplete_control_markup,
    detect_invalid_think_markup,
    extract_visible_text_for_user,
    strip_plain_think_prefix_artifacts,
)


class IntentResponseParser:
    INTENT_TAG_RE = re.compile(
        r"<intent\b(?P<attrs>[^>]*?)(?:>(?P<body>.*?)</intent>|(?P<selfclose>/\s*>))",
        re.IGNORECASE | re.DOTALL,
    )
    THINK_TAG_RE = re.compile(r"<think(?:\s+[^>]*)?>.*?</think>", re.IGNORECASE | re.DOTALL)
    ACTION_TAG_RE = re.compile(r"<action(?:\s+[^>]*)?>.*?</action>", re.IGNORECASE | re.DOTALL)
    ACTION_BLOCK_RE = re.compile(
        r"<action(?:\s+[^>]*)?>(?P<body>.*?)</action>",
        re.IGNORECASE | re.DOTALL,
    )
    ACTION_XML_PAYLOAD_TAG_RE = re.compile(
        r"<\s*(type|path|command|tool_code|intent|think|file_content)\b",
        re.IGNORECASE,
    )
    TOOL_HISTORY_RE = re.compile(r"(?im)^\s*tool_history\s+\{.*?$")
    HISTORY_TOOL_ACTION_RE = re.compile(r'(?is)<action[^>]*\btype\s*=\s*"history_tool"[^>]*>.*?</action>')
    HISTORY_TOOL_TAG_RE = re.compile(r"(?is)<history_tool\b[^>]*>.*?</history_tool>")
    ATTR_RE = re.compile(r"""([a-zA-Z_][\w\-]*)\s*=\s*(?:"([^"]*)"|'([^']*)')""")
    INT_FIELDS = {
        "safe_steps_limit",
        "retry_limit",
        "requested_steps",
    }
    LIST_FIELDS = {
        "allowed_actions",
    }

    def __init__(self, logger=None):
        self.logger = logger

    def _debug(self, message: str, *args) -> None:
        if self.logger is not None:
            self.logger.debug(message, *args)

    def _mask_think_blocks(self, response_text: str) -> str:
        def _mask(match: re.Match) -> str:
            return " " * (match.end() - match.start())

        return self.THINK_TAG_RE.sub(_mask, response_text)

    def _spans_for_action_blocks(self, response_text: str) -> list[tuple[int, int]]:
        if not isinstance(response_text, str) or not response_text:
            return []
        return [match.span(0) for match in self.ACTION_TAG_RE.finditer(response_text)]

    def _span_inside_any(self, start: int, end: int, spans: list[tuple[int, int]]) -> bool:
        for span_start, span_end in spans:
            if start >= span_start and end <= span_end:
                return True
        return False

    def _parse_attrs(self, attrs_raw: str) -> dict[str, str]:
        attrs: dict[str, str] = {}
        if not isinstance(attrs_raw, str) or not attrs_raw.strip():
            return attrs
        cleaned = attrs_raw.strip()
        if cleaned.endswith("/"):
            cleaned = cleaned[:-1].rstrip()
        for key, v1, v2 in self.ATTR_RE.findall(cleaned):
            attrs[str(key).strip().lower()] = str(v1 or v2 or "").strip()
        return attrs

    def _parse_allowed_actions(self, raw_value) -> list[str] | None:
        if raw_value is None:
            return None
        if isinstance(raw_value, list):
            raw_items = raw_value
        else:
            text = str(raw_value or "").strip()
            if not text:
                return []
            try:
                parsed = json.loads(text)
            except Exception:
                parsed = None
            if isinstance(parsed, list):
                raw_items = parsed
            else:
                text = text.strip()
                if text.startswith("[") and text.endswith("]"):
                    text = text[1:-1].strip()
                raw_items = [item.strip() for item in text.split(",")]
        actions: list[str] = []
        for item in raw_items:
            action = str(item or "").strip().strip('"').strip("'")
            if action and action not in actions:
                actions.append(action)
        return actions

    def _normalize_attr_payload(self, attrs: dict[str, str]) -> tuple[dict | None, str | None]:
        if not attrs:
            return None, None
        payload: dict = {}
        for key, value in attrs.items():
            if key in {"mode", "intent_id", "intent_type", "goal", "switch_reason", "switch_explanation", "completion_reason", "completion_explanation"}:
                if value:
                    payload[key] = value
                continue
            if key in self.INT_FIELDS:
                if value == "":
                    continue
                try:
                    payload[key] = int(value)
                except Exception:
                    return None, f"invalid_intent_numeric_field_{key}"
                continue
            if key in self.LIST_FIELDS:
                parsed = self._parse_allowed_actions(value)
                if parsed is None:
                    continue
                payload[key] = parsed
                continue

        mode = str(payload.get("mode") or attrs.get("mode") or "").strip().lower()
        if not mode:
            return None, "intent_mode_required"
        payload["mode"] = mode
        return payload, None

    def _intent_fallback_from_attributes(self, attrs_raw: str, *, self_closing: bool) -> tuple[dict | None, str | None]:
        attrs = self._parse_attrs(attrs_raw)
        payload, error = self._normalize_attr_payload(attrs)
        if payload is not None:
            self._debug(
                "IntentParser.extract intent_parser_fallback=%s keys=%s",
                "self_closing_xml_attributes" if self_closing else "xml_attributes",
                sorted(payload.keys()),
            )
        return payload, error

    def _merge_mode_from_intent_attrs(self, payload: dict, attrs_raw: str) -> tuple[dict, str | None]:
        attrs = self._parse_attrs(attrs_raw)
        tag_mode = str(attrs.get("mode") or "").strip().lower()
        if not tag_mode:
            return payload, None

        body_mode = str(payload.get("mode") or "").strip().lower()
        if not body_mode:
            payload["mode"] = tag_mode
            return payload, None

        if body_mode != tag_mode:
            return payload, "conflicting_intent_mode"

        payload["mode"] = body_mode
        return payload, None

    def extract_intent_update_and_strip(self, response_text: str) -> tuple[str, dict | None, str | None]:
        if not isinstance(response_text, str) or not response_text:
            self._debug("IntentParser.extract skipped: empty_or_non_string response=%r", response_text)
            return response_text, None, None

        masked_response = self._mask_think_blocks(response_text)
        action_spans = self._spans_for_action_blocks(masked_response)
        all_matches = list(self.INTENT_TAG_RE.finditer(masked_response))
        matches = [
            match
            for match in all_matches
            if not self._span_inside_any(match.start(0), match.end(0), action_spans)
        ]
        if not matches:
            self._debug(
                "IntentParser.extract no_top_level_intent_match response_chars=%s intent_matches=%s action_blocks=%s preview=%r",
                len(response_text),
                len(all_matches),
                len(action_spans),
                response_text[:400],
            )
            return response_text, None, None

        last_match = matches[-1]
        full_span = last_match.span(0)
        raw_block = last_match.group("body") or ""
        attrs_raw = last_match.group("attrs") or ""
        self_closing = bool(last_match.group("selfclose"))
        last_block = raw_block.strip()
        clean_text = (response_text[: full_span[0]] + response_text[full_span[1] :]).strip()

        self._debug(
            "IntentParser.extract matched_intent blocks=%s full_response_chars=%s raw_block_chars=%s stripped_block_chars=%s",
            len(matches),
            len(response_text),
            len(raw_block or ""),
            len(last_block or ""),
        )
        self._debug("IntentParser.extract matched_block_raw=%r", raw_block)
        self._debug("IntentParser.extract matched_block_stripped=%r", last_block)
        self._debug("IntentParser.extract clean_text_preview=%r", clean_text[:400])

        if not last_block:
            payload, fallback_error = self._intent_fallback_from_attributes(attrs_raw, self_closing=self_closing)
            if payload is not None:
                return clean_text, payload, None
            self._debug("IntentParser.extract empty_intent_block after_strip=True")
            return clean_text, None, fallback_error or "empty_intent_block"

        try:
            payload = json.loads(last_block)
        except json.JSONDecodeError as exc:
            if self.ACTION_TAG_RE.search(last_block):
                self._debug(
                    "IntentParser.extract intent_body_contains_action raw_block_chars=%s",
                    len(last_block or ""),
                )
                return clean_text, None, "intent_body_contains_action"

            self._debug(
                "IntentParser.extract invalid_intent_json msg=%s line=%s col=%s pos=%s",
                exc.msg,
                exc.lineno,
                exc.colno,
                exc.pos,
            )
            start = max(0, exc.pos - 80)
            end = min(len(last_block), exc.pos + 80)
            self._debug(
                "IntentParser.extract invalid_intent_json_context start=%s end=%s context=%r",
                start,
                end,
                last_block[start:end],
            )
            payload, fallback_error = self._intent_fallback_from_attributes(attrs_raw, self_closing=self_closing)
            if payload is not None:
                return clean_text, payload, None
            return clean_text, None, fallback_error or "invalid_intent_json"

        self._debug(
            "IntentParser.extract parsed_intent_payload type=%s keys=%s",
            type(payload).__name__,
            sorted(payload.keys()) if isinstance(payload, dict) else "<non-dict>",
        )
        if isinstance(payload, dict):
            payload, merge_error = self._merge_mode_from_intent_attrs(payload, attrs_raw)
            if merge_error:
                return clean_text, None, merge_error
        return clean_text, payload, None

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
        has_intent_segment = any(seg.type == "intent" for seg in segments)
        has_action_segment = any(seg.type == "action" for seg in segments)
        if not has_intent_segment or has_action_segment:
            return False
        visible_text = self.extract_visible_non_action_text(response)
        return not bool(visible_text)

    def has_conflicting_intent_transitions(self, segments) -> bool:
        intent_count = sum(1 for seg in segments if getattr(seg, "type", "") == "intent")
        return intent_count >= 2

    def has_multiple_actions(self, segments) -> bool:
        action_count = sum(1 for seg in segments if getattr(seg, "type", "") == "action")
        return action_count >= 2

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
        """Return a protocol error kind for malformed top-level <intent> bodies.

        Contract:
        - <intent> must contain JSON intent payload data, or be a valid
          attribute-only fallback handled by extract_intent_update_and_strip.
        - Raw <action>...</action> inside <intent> is never a valid intent body.
        - A JSON string value may mention "<action>" as data; that is valid when
          the whole intent body parses as JSON.
        """
        text = str(response or "")
        if not text:
            return ""

        masked_response = self._mask_think_blocks(text)
        action_spans = self._spans_for_action_blocks(masked_response)

        for match in self.INTENT_TAG_RE.finditer(masked_response):
            if self._span_inside_any(match.start(0), match.end(0), action_spans):
                # This is an intent nested inside an action, which is handled by
                # the malformed action guard. Do not mislabel it here.
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
        """Return a protocol error kind for malformed <action> payloads.

        Contract:
        - <action> must contain exactly one JSON object.
        - XML-style tool fields such as <type> or <path> inside <action> are invalid.
        - Control tags such as <intent>, <think>, <file_content>, or <tool_code>
          inside <action> are invalid when they are raw markup, not JSON string
          content.

        Important: validate JSON first. A valid JSON action may legitimately
        contain strings with XML-like text, code snippets, examples, or quoted
        protocol fragments. Those strings are data, not control markup. The
        production bug this guard targets is raw XML-style tool payload inside
        <action>, especially lower-level parser recovery turning it into a
        partial command.
        """
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

                # A successfully parsed JSON object is the canonical action
                # payload. Do not reject it just because a string value contains
                # text such as "<intent>" or "<type>"; those are data.
                continue

            # JSON did not parse. Now raw XML/control tags inside <action> are
            # definitely protocol markup, not string data.
            if self.ACTION_XML_PAYLOAD_TAG_RE.search(body):
                return "malformed_action"

            # Non-JSON action body without recognizable XML tags is still not a
            # dispatchable action payload.
            return "malformed_action"

        return ""

    def classify(self, response: str, segments) -> ParsedModelOutput:
        safe_response = response if isinstance(response, str) else ""
        safe_segments = list(segments or [])
        has_action_tag = "<action" in safe_response.lower()
        has_action_segment = any(seg.type == "action" for seg in safe_segments)
        has_intent_segment = any(seg.type == "intent" for seg in safe_segments)
        visible_text = self.extract_visible_non_action_text(safe_response)
        invalid_kind = ""
        has_plain_think_prefix = self.has_plain_think_prefix(safe_response)
        incomplete_control_kind = detect_incomplete_control_markup(safe_response)
        invalid_think_kind = detect_invalid_think_markup(safe_response)
        malformed_intent_kind = self.malformed_intent_payload_kind(safe_response)
        malformed_action_kind = self.malformed_action_payload_kind(safe_response)

        if has_plain_think_prefix and self.logger is not None and (has_action_segment or has_intent_segment or bool(visible_text)):
            self.logger.warning("response_parser_fallback=plain_think_prefix_ignored")

        if incomplete_control_kind:
            invalid_kind = incomplete_control_kind
        elif invalid_think_kind:
            invalid_kind = invalid_think_kind
        elif malformed_intent_kind:
            invalid_kind = malformed_intent_kind
        elif malformed_action_kind:
            invalid_kind = malformed_action_kind
        elif self.has_file_content_before_action(safe_segments):
            invalid_kind = "file_content_must_follow_action"
        elif has_action_tag and not has_action_segment:
            invalid_kind = "malformed_action"
        elif self.has_conflicting_intent_transitions(safe_segments):
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
            elif self.is_intent_only_response(safe_response, safe_segments):
                invalid_kind = "intent_only_without_next_step"
            elif self.needs_action_or_answer_recovery(safe_response, safe_segments):
                invalid_kind = "missing_action_or_answer"

        return ParsedModelOutput(
            response=safe_response,
            segments=safe_segments,
            has_action_tag=has_action_tag,
            has_action_segment=has_action_segment,
            has_intent_segment=has_intent_segment,
            visible_text=visible_text,
            invalid_kind=invalid_kind,
            model_stop_reason="",
        )