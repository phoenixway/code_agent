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
        # Split by action tag, keeping the tag itself. This regex is broad on purpose.
        parts = re.split(r'(<action[^>]*>.*?</action>)', text, flags=re.DOTALL | re.IGNORECASE)

        for part in parts:
            if not part.strip():
                continue

            # More specific regex to extract data from the potential action block
            action_match = re.match(r'<action(?:\s+type="([^"]+)")?>(.*?)</action>', part, flags=re.DOTALL | re.IGNORECASE)
            
            if action_match:
                action_type = action_match.group(1) # This might be None
                json_content = action_match.group(2).strip()
                
                json_obj = self._extract_json(json_content)
                
                if json_obj and isinstance(json_obj, dict):
                    # If type was captured from attribute, add it to the object.
                    # This is the key fix: ensuring the type from the tag is in the dictionary.
                    if action_type:
                        json_obj['type'] = action_type.strip()
                    
                    # Now, check if the object is a valid action by looking for a 'type' or 'command' key.
                    if any(k in json_obj for k in ["type", "command", "action"]):
                        segments.append(Segment('action', json_obj))
                    else:
                        segments.append(Segment('text', part)) # Not a valid command, treat as text
                else:
                    segments.append(Segment('text', part)) # Not valid JSON, treat as text
            else:
                # This is a text part
                stripped_part = part.strip()
                if stripped_part:
                    segments.append(Segment('text', stripped_part))

        return segments

    def _parse_key_value_tags(self, text: str) -> Optional[dict]:
        """Parses a string of <key>value</key> tags into a dictionary."""
        data = {}
        # Regex to find <tag>value</tag>
        pattern = re.compile(r'<([^>]+)>(.*?)</\1>', re.DOTALL | re.IGNORECASE)
        matches = pattern.findall(text)
        if not matches:
            return None
        for key, value in matches:
            data[key.strip()] = value.strip()
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
            # If it's CDATA, assume it's a raw command string
            # and wrap it in a JSON object with a 'command' key.
            # This is specific to run_shell tools with CDATA.
            return {"command": cdata_match.group(1).strip()}

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
