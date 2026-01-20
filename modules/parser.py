import re
import json
from dataclasses import dataclass
from typing import List, Any, Optional

@dataclass
class Segment:
    type: str  # 'thought', 'text', 'action'
    content: Any

class ResponseParser:
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
        parts = re.split(r'(<action>.*?</action>)', text, flags=re.DOTALL | re.IGNORECASE)

        for part in parts:
            if not part.strip():
                continue

            action_match = re.match(r'<action>(.*?)</action>', part, flags=re.DOTALL | re.IGNORECASE)
            if action_match:
                json_content = action_match.group(1).strip()
                json_obj = self._extract_json(json_content)
                if json_obj:
                    if isinstance(json_obj, dict) and any(k in json_obj for k in ["type", "command", "action"]):
                        segments.append(Segment('action', json_obj))
                    else:
                        segments.append(Segment('text', part)) # Not a valid command, treat as text
                else:
                    segments.append(Segment('text', part)) # Not valid JSON, treat as text
            else:
                stripped_part = part.strip()
                if stripped_part:
                    segments.append(Segment('text', stripped_part))

        return segments

    def _extract_json(self, text: str):
        """
        Attempts to parse JSON from a string.
        Returns json_obj or None.
        """
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
                pass # If it still fails, we'll return None

        return None
