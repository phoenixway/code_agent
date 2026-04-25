import re
import json
import logging
from dataclasses import dataclass
from typing import List, Any, Optional


@dataclass
class Segment:
    type: str  # 'thought', 'text', 'action', 'file_content'
    content: Any


class ResponseParser:
    ACTION_KEYS = ("type", "command", "action")
    FILE_BLOCK_ACTION_TYPES = {"write_file_block", "append_file_block"}
    ACTION_TAG_RE = re.compile(
        r"<action[^>]*>.*?</action>",
        re.DOTALL | re.IGNORECASE,
    )
    NESTED_TOOL_TAG_RE = re.compile(
        r'^\s*<([a-zA-Z_][\w\-]*)>(.*?)</\1>\s*$',
        re.DOTALL | re.IGNORECASE,
    )
    ACTION_INTERNAL_THINK_RE = re.compile(
        r'<(?:think|thinking)>(.*?)</(?:think|thinking)>',
        re.DOTALL | re.IGNORECASE,
    )
    FILE_CONTENT_TAG_RE = re.compile(
        r"<file_content(?:\s+[^>]*)?>(.*?)</file_content>",
        re.DOTALL | re.IGNORECASE,
    )

    def __init__(self):
        self.log = logging.getLogger("debug")

    def parse(self, text: str) -> List[Segment]:
        """
        Parses the LLM response into a sequence of Segments (Thought, Text, Action).
        Implements fallback logic for malformed think tags and strictly ignores JSON within thoughts.
        """
        if not text:
            return []

        segments = []

        # 1. Fallback Logic for Malformed Tags
        # Check if there are more closing tags than opening tags,
        # or if the structure implies we should just grab everything up to the last </think>
        open_tags = len(re.findall(r'<think>', text, re.IGNORECASE))
        close_tags = len(re.findall(r'</think>', text, re.IGNORECASE))

        # Heuristic: If we have dangling closing tags, use greedy fallback
        if close_tags > open_tags:
            last_close_match = None
            for match in re.finditer(r'</think>', text, re.IGNORECASE):
                last_close_match = match

            if last_close_match:
                end_pos = last_close_match.end()
                thought_content = text[:last_close_match.start()].strip()
                # Remove <think> tags from the content to make it clean
                thought_content = re.sub(r'<think>', '', thought_content, flags=re.IGNORECASE).strip()

                segments.append(Segment('thought', thought_content))

                # The rest is potential Actions/Text
                remaining_text = text[end_pos:]
                segments.extend(self._parse_mixed_content(remaining_text))
                return self._attach_file_content_blocks(segments)

        # 2. Standard Logic: Split by <think> blocks
        parts = re.split(r'(<think>.*?</think>)', text, flags=re.DOTALL | re.IGNORECASE)

        for part in parts:
            if not part.strip():
                continue

            think_match = re.match(r'<think>(.*?)</think>', part, flags=re.DOTALL | re.IGNORECASE)
            if think_match:
                content = think_match.group(1).strip()
                if content:
                    segments.append(Segment('thought', content))
            else:
                segments.extend(self._parse_mixed_content(part))

        return self._attach_file_content_blocks(segments)

    def _parse_mixed_content(self, text: str) -> List[Segment]:
        """
        Scans a string for protocol tags while treating <file_content> as an opaque raw block.
        Anything not in an action or file_content tag is Text.
        """
        segments = []
        parts = re.split(
            r'(<file_content(?:\s+[^>]*)?>.*?</file_content>)',
            text,
            flags=re.DOTALL | re.IGNORECASE,
        )

        for part in parts:
            if not part.strip():
                continue

            file_content_match = re.match(
                r'<file_content(?:\s+[^>]*)?>(.*?)</file_content>',
                part,
                flags=re.DOTALL | re.IGNORECASE,
            )

            if file_content_match:
                segments.append(Segment("file_content", file_content_match.group(1) or ""))
            else:
                action_parts = re.split(self.ACTION_TAG_RE, part)
                action_matches = list(self.ACTION_TAG_RE.finditer(part))
                for index, text_part in enumerate(action_parts):
                    stripped_part = text_part.strip()
                    if stripped_part:
                        segments.append(Segment('text', stripped_part))
                    if index >= len(action_matches):
                        continue

                    action_match = action_matches[index]
                    part_text = action_match.group(0)
                    inner_match = re.match(r'<action([^>]*)>(.*?)</action>', part_text, flags=re.DOTALL | re.IGNORECASE)
                    if not inner_match:
                        segments.append(Segment('text', part_text))
                        continue

                    action_attrs_raw = inner_match.group(1) or ""
                    raw_action_content = inner_match.group(2).strip()
                    action_attrs = self._parse_action_attributes(action_attrs_raw)

                    json_content = self._strip_internal_action_thoughts(raw_action_content)

                    json_payload = self._extract_nested_tool_payload(json_content)
                    if json_payload is None:
                        json_payload = self._extract_json(json_content)

                    if json_payload is not None:
                        normalized_actions = self._normalize_action_payload(action_attrs, json_payload)
                        if normalized_actions:
                            segments.extend(Segment('action', action_obj) for action_obj in normalized_actions)
                        else:
                            if self.log:
                                preview = part_text.strip().replace("\n", " ")[:240]
                                self.log.warning(
                                    f"Parser warning: action block missing required keys. Preview: {preview}"
                                )
                            segments.append(Segment('text', part_text))
                    else:
                        if self.log:
                            preview = part_text.strip().replace("\n", " ")[:240]
                            cleaned_preview = json_content.strip().replace("\n", " ")[:240]
                            self.log.warning(
                                "Parser warning: failed to parse action JSON. Preview: %s | cleaned_action_content: %s",
                                preview,
                                cleaned_preview,
                            )
                        segments.append(Segment('text', part_text))

        return segments

    def _attach_file_content_blocks(self, segments: List[Segment]) -> List[Segment]:
        if not segments:
            return segments

        merged: List[Segment] = []
        i = 0
        while i < len(segments):
            segment = segments[i]
            if (
                segment.type == "action"
                and isinstance(segment.content, dict)
                and i + 1 < len(segments)
            ):
                next_segment = segments[i + 1]
                action_type = str(segment.content.get("type") or segment.content.get("action") or "").strip().lower()
                if action_type in self.FILE_BLOCK_ACTION_TYPES and getattr(next_segment, "type", "") == "file_content":
                    action_payload = dict(segment.content)
                    body = str(getattr(next_segment, "content", "") or "")
                    if body.startswith("\r\n"):
                        body = body[2:]
                    elif body.startswith("\n"):
                        body = body[1:]
                    action_payload["file_content"] = body
                    merged.append(Segment("action", action_payload))
                    i += 2
                    continue

            merged.append(segment)
            i += 1

        return merged

    def _strip_internal_action_thoughts(self, text: str) -> str:
        """
        Removes ignorable internal reasoning tags accidentally placed inside <action>...</action>,
        such as <thinking>...</thinking> or <think>...</think>, before attempting payload parse.
        """
        if not isinstance(text, str) or not text.strip():
            return text

        matches = list(self.ACTION_INTERNAL_THINK_RE.finditer(text))
        if not matches:
            return text

        cleaned = self.ACTION_INTERNAL_THINK_RE.sub("", text).strip()

        if self.log:
            previews = []
            for match in matches[:3]:
                snippet = (match.group(1) or "").strip().replace("\n", " ")
                previews.append(snippet[:120])
            self.log.debug(
                "Parser debug: stripped %s internal think/thinking block(s) from inside <action>. previews=%s",
                len(matches),
                previews,
            )

        return cleaned

    def _parse_action_attributes(self, attrs_raw: str) -> dict:
        """Parses attributes from <action ...> into a dict, e.g. type/path."""
        attrs = {}
        if not isinstance(attrs_raw, str) or not attrs_raw.strip():
            return attrs
        for key, value in re.findall(r'([a-zA-Z_][\w\-]*)\s*=\s*"([^"]*)"', attrs_raw):
            attrs[key.strip()] = value.strip()
        return attrs

    def _parse_key_value_tags(self, text: str) -> Optional[dict]:
        """Parses XML-like key/value tags into a dictionary."""
        data = {}

        # Format A: <value name="path">file.txt</value>
        named_value_pattern = re.compile(
            r'<value\s+name="([^"]+)">(.*?)</value>',
            re.DOTALL | re.IGNORECASE,
        )
        for key, value in named_value_pattern.findall(text):
            data[key.strip()] = value.strip()

        # Format B: <path>file.txt</path>
        simple_tag_pattern = re.compile(r'<([a-zA-Z_][\w\-]*)>(.*?)</\1>', re.DOTALL | re.IGNORECASE)
        for key, value in simple_tag_pattern.findall(text):
            key_clean = key.strip()
            if key_clean.lower() == "value":
                continue
            data[key_clean] = value.strip()

        if not data:
            return None
        return data

    def _normalize_action_payload(self, action_attrs: dict, json_obj_or_list: Any) -> List[dict]:
        """
        Normalizes a parsed <action> payload into a list of valid action dicts.
        A single object yields zero or one actions; an array may expand into many.
        """
        if isinstance(json_obj_or_list, dict):
            normalized = self._merge_action_item(action_attrs, json_obj_or_list)
            return [normalized] if normalized else []

        if isinstance(json_obj_or_list, list):
            if self.log:
                self.log.debug("Parser debug: action array payload detected.")
            normalized_actions = []
            invalid_items = 0
            for item in json_obj_or_list:
                normalized = self._merge_action_item(action_attrs, item)
                if normalized:
                    normalized_actions.append(normalized)
                else:
                    invalid_items += 1

            if normalized_actions:
                if self.log:
                    self.log.debug(
                        "Parser debug: action array payload expanded into %s actions.",
                        len(normalized_actions),
                    )
                    if invalid_items:
                        self.log.warning(
                            "Parser warning: action array payload ignored %s invalid item(s).",
                            invalid_items,
                        )
                return normalized_actions

            if self.log:
                self.log.warning("Parser warning: action array payload rejected because no valid action items.")
            return []

        return []

    def _merge_action_item(self, action_attrs: dict, payload: Any) -> Optional[dict]:
        """Merges <action> attributes with one payload item and validates action shape."""
        if not isinstance(payload, dict):
            return None

        merged_obj = dict(action_attrs)
        merged_obj.update(payload)

        action_type = action_attrs.get("type")
        if action_type and "type" not in merged_obj:
            merged_obj["type"] = action_type.strip()

        if any(key in merged_obj for key in self.ACTION_KEYS):
            return merged_obj
        return None

    def _extract_nested_tool_payload(self, text: str):
        """
        Supports malformed-but-common wrapper formats like:
        <action><run_shell>{...}</run_shell></action>
        """
        if not isinstance(text, str) or not text.strip():
            return None

        match = self.NESTED_TOOL_TAG_RE.match(text)
        if not match:
            return None

        tool_name = match.group(1).strip()
        inner = (match.group(2) or "").strip()
        if not tool_name:
            return None

        payload = self._extract_json(inner)
        if isinstance(payload, dict):
            if "type" not in payload and "action" not in payload:
                payload["type"] = tool_name
            return payload

        kv_payload = self._parse_key_value_tags(inner)
        if isinstance(kv_payload, dict):
            kv_payload.setdefault("type", tool_name)
            return kv_payload

        if inner:
            return {"type": tool_name, "command": inner}

        return {"type": tool_name}

    def reconstruct(self, segments: List[Segment]) -> str:
        """
        Reconstructs the raw text response from a list of Segments.
        """
        response_parts = []
        for segment in segments:
            if segment.type == 'thought':
                response_parts.append(f"<think>\n{segment.content}\n</think>")
            elif segment.type == 'action':
                action_content = segment.content.copy()
                action_type = action_content.pop('type', None)
                file_content = action_content.pop("file_content", None)
                action_str = json.dumps(action_content, indent=4)

                if action_type:
                    response_parts.append(f'<action type="{action_type}">\n{action_str}\n</action>')
                else:
                    response_parts.append(f"<action>\n{action_str}\n</action>")
                if action_type in self.FILE_BLOCK_ACTION_TYPES and isinstance(file_content, str):
                    response_parts.append(f"<file_content>{file_content}</file_content>")
            elif segment.type == 'file_content':
                response_parts.append(f"<file_content>{segment.content}</file_content>")

            elif segment.type == 'text':
                response_parts.append(segment.content)
        return "\n".join(response_parts)

    def _extract_json(self, text: str):
        """
        Attempts to parse JSON from a string.
        Handles CDATA blocks for cases like shell commands.
        Returns json_obj or None.
        """
        cdata_match = re.match(r'^\s*<!\[CDATA\[(.*?)\]\]>\s*$', text, re.DOTALL)
        if cdata_match:
            cdata_body = cdata_match.group(1).strip()
            try:
                parsed = json.loads(cdata_body)
                if isinstance(parsed, dict):
                    return parsed
            except Exception:
                pass
            return {"command": cdata_body}

        try:
            return json.loads(text)
        except json.JSONDecodeError:
            try:
                start_brace = text.find('{')
                end_brace = text.rfind('}')
                if start_brace != -1 and end_brace != -1 and start_brace < end_brace:
                    json_str = text[start_brace:end_brace + 1]
                    return json.loads(json_str)
            except json.JSONDecodeError:
                pass

        parsed_data = self._parse_key_value_tags(text)
        if parsed_data:
            return parsed_data

        return None
