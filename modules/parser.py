import re
import json
import logging
from dataclasses import dataclass
from typing import List, Any, Optional

@dataclass
class Segment:
    type: str  # 'thought', 'text', 'action'
    content: Any

class ResponseParser:
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
                # Clean up any partial opening tags inside if needed, or just take it raw
                # Remove <think> tags from the content to make it clean
                thought_content = re.sub(r'<think>', '', thought_content, flags=re.IGNORECASE).strip()
                
                segments.append(Segment('thought', thought_content))
                
                # The rest is potential Actions/Text
                remaining_text = text[end_pos:]
                segments.extend(self._parse_mixed_content(remaining_text))
                return segments

        # 2. Standard Logic: Split by <think> blocks
        # We use a regex to find all properly balanced (or as best as regex can) blocks
        # But since we want to handle "Action | Text | Thought | Action", 
        # we iterate through the string.
        
        # Strategy: Use split to separate Thoughts from Content
        # This regex splits the string by the think blocks, keeping the delimiters
        # Note: This is a non-greedy match for the content inside
        parts = re.split(r'(<think>.*?</think>)', text, flags=re.DOTALL | re.IGNORECASE)
        
        for part in parts:
            if not part.strip():
                continue
                
            # Check if this part is a think block
            think_match = re.match(r'<think>(.*?)</think>', part, flags=re.DOTALL | re.IGNORECASE)
            if think_match:
                content = think_match.group(1).strip()
                if content:
                    segments.append(Segment('thought', content))
            else:
                # This is "Active Content" (Text or JSON)
                # We need to scan this for JSONs
                segments.extend(self._parse_mixed_content(part))

        return segments

    def _parse_mixed_content(self, text: str) -> List[Segment]:
        """
        Scans a string for <action> tags. Anything not in an action tag is Text.
        """
        segments = []
        # Split by action tag, keeping the tag itself. This regex is broad on purpose.
        parts = re.split(r'(<action[^>]*>.*?</action>)', text, flags=re.DOTALL | re.IGNORECASE)

        for part in parts:
            if not part.strip():
                continue

            # More specific regex to extract data from the potential action block
            action_match = re.match(r'<action([^>]*)>(.*?)</action>', part, flags=re.DOTALL | re.IGNORECASE)
            
            if action_match:
                action_attrs_raw = action_match.group(1) or ""
                json_content = action_match.group(2).strip()
                action_attrs = self._parse_action_attributes(action_attrs_raw)
                action_type = action_attrs.get("type")
                
                json_obj = self._extract_json(json_content)
                
                if json_obj and isinstance(json_obj, dict):
                    # Merge attributes from <action ...> first (e.g., path="..."),
                    # then let payload fields override if present.
                    merged_obj = dict(action_attrs)
                    merged_obj.update(json_obj)
                    if action_type and "type" not in merged_obj:
                        merged_obj["type"] = action_type.strip()
                    
                    # Now, check if the object is a valid action by looking for a 'type' or 'command' key.
                    if any(k in merged_obj for k in ["type", "command", "action"]):
                        segments.append(Segment('action', merged_obj))
                    else:
                        if self.log:
                            preview = part.strip().replace("\n", " ")[:240]
                            self.log.warning(f"Parser warning: action block missing required keys. Preview: {preview}")
                        segments.append(Segment('text', part)) # Not a valid command, treat as text
                else:
                    if self.log:
                        preview = part.strip().replace("\n", " ")[:240]
                        self.log.warning(f"Parser warning: failed to parse action JSON. Preview: {preview}")
                    segments.append(Segment('text', part)) # Not valid JSON, treat as text
            else:
                # This is a text part
                stripped_part = part.strip()
                if stripped_part:
                    segments.append(Segment('text', stripped_part))

        return segments

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
                # Already handled above to avoid collisions.
                continue
            data[key_clean] = value.strip()

        if not data:
            return None
        return data

    def reconstruct(self, segments: List[Segment]) -> str:
        """
        Reconstructs the raw text response from a list of Segments.
        """
        response_parts = []
        for segment in segments:
            if segment.type == 'thought':
                response_parts.append(f"<think>\n{segment.content}\n</think>")
            elif segment.type == 'action':
                # Make a copy to avoid modifying the original segment content
                action_content = segment.content.copy()
                
                # Extract 'type' for the tag attribute, then remove it from the JSON payload
                action_type = action_content.pop('type', None)
                
                # The remaining content is the JSON payload
                action_str = json.dumps(action_content, indent=4)
                
                # Construct the tag with the type attribute if it exists
                if action_type:
                    response_parts.append(f'<action type="{action_type}">\n{action_str}\n</action>')
                else:
                    response_parts.append(f"<action>\n{action_str}\n</action>")

            elif segment.type == 'text':
                response_parts.append(segment.content)
        return "\n".join(response_parts)

    def _extract_json(self, text: str):
        """
        Attempts to parse JSON from a string.
        Handles CDATA blocks for cases like shell commands.
        Returns json_obj or None.
        """
        # First, check for CDATA block
        cdata_match = re.match(r'^\s*<!\[CDATA\[(.*?)\]\]>\s*$', text, re.DOTALL)
        if cdata_match:
            cdata_body = cdata_match.group(1).strip()
            # Prefer structured JSON payload if CDATA contains JSON.
            # Fallback to raw command string for shell-like payloads.
            try:
                parsed = json.loads(cdata_body)
                if isinstance(parsed, dict):
                    return parsed
            except Exception:
                pass
            return {"command": cdata_body}

        try:
            # First, try to load directly
            return json.loads(text)
        except json.JSONDecodeError:
            # If that fails, it might be because of escaped characters.
            # Let's try to find the JSON object within the string.
            # This is a common issue when the model returns a string with a JSON object inside.
            # For example: "`json\n{...}\n`"
            try:
                # Find the first '{' and the last '}'
                start_brace = text.find('{')
                end_brace = text.rfind('}')
                if start_brace != -1 and end_brace != -1 and start_brace < end_brace:
                    json_str = text[start_brace:end_brace+1]
                    return json.loads(json_str)
            except json.JSONDecodeError:
                pass # If it still fails, we'll try the next method

        # Fallback to XML-like key-value pair parsing
        parsed_data = self._parse_key_value_tags(text)
        if parsed_data:
            return parsed_data

        return None
