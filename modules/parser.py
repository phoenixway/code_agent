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
        Scans a string for JSON commands. Anything not JSON is Text.
        """
        segments = []
        cursor = 0
        length = len(text)

        while cursor < length:
            # Find next potential start of JSON
            start_brace = text.find('{', cursor)
            
            if start_brace == -1:
                # No more JSONs, the rest is text
                remaining = text[cursor:].strip()
                if remaining:
                    segments.append(Segment('text', remaining))
                break

            # If there is text before the brace, add it
            pre_text = text[cursor:start_brace].strip()
            if pre_text:
                segments.append(Segment('text', pre_text))

            # Attempt to extract valid JSON starting at start_brace
            json_obj, end_index = self._extract_json_with_index(text, start_brace)
            
            if json_obj:
                # Validate if it looks like a command
                if isinstance(json_obj, dict) and any(k in json_obj for k in ["type", "command", "action"]):
                    segments.append(Segment('action', json_obj))
                    cursor = end_index
                else:
                    # Valid JSON but not a command? Treat as text (or ignore). 
                    # For now, treat as text to be safe, or just skip past it?
                    # Let's treat it as text because the user might be explaining a JSON structure.
                    # Re-adding the brace to text and moving on is tricky because we just consumed it.
                    # Better strategy: If it's valid JSON but not a command, treat it as text.
                    raw_json = text[start_brace:end_index]
                    segments.append(Segment('text', raw_json))
                    cursor = end_index
            else:
                # Failed to parse JSON at this brace. 
                # Treat the brace as text and move cursor forward by 1 to search again
                segments.append(Segment('text', "{"))
                cursor = start_brace + 1

        return segments

    def _extract_json_with_index(self, text: str, start_index: int):
        """
        Attempts to parse JSON starting at start_index.
        Returns (json_obj, end_index) or (None, -1).
        end_index is the index immediately after the closing brace.
        """
        next_close = start_index
        while True:
            next_close = text.find('}', next_close + 1)
            if next_close == -1:
                break
            
            candidate = text[start_index : next_close + 1]
            try:
                data = json.loads(candidate)
                return data, next_close + 1
            except json.JSONDecodeError:
                continue
        
        return None, -1
