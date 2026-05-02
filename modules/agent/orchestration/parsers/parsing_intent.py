"""Intent extraction helpers for intent-aware response parsing."""

from __future__ import annotations

import json


class ParsingIntentMixin:
    def _mask_think_blocks(self, response_text: str) -> str:
        def _mask(match):
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
        repair = self.normalize_model_response(response_text, allow_think_autorepair=True)
        response_text = repair.normalized_response

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
