"""Semantic helpers for orchestrator response classification."""

from __future__ import annotations

import re


class ResponseSemantics:
    THINK_BLOCK_RE = re.compile(
        r"<think(?:\s+[^>]*)?>(.*?)</think>",
        re.IGNORECASE | re.DOTALL,
    )
    REFLECTION_TAG_RE = re.compile(
        r"<(fact|finding|decision|preference|progress)\b",
        re.IGNORECASE,
    )
    MEMORY_TAG_BLOCK_RE = re.compile(
        r"<(fact|finding|decision|preference|progress)\b[^>]*>.*?</\1>",
        re.IGNORECASE | re.DOTALL,
    )

    def reflection_tag_count(self, raw_response: str) -> int:
        text = str(raw_response or "")
        if not text:
            return 0
        return len(list(self.REFLECTION_TAG_RE.finditer(text)))

    def has_substantial_think(self, raw_response: str) -> bool:
        text = str(raw_response or "")
        if not text:
            return False

        matches = list(self.THINK_BLOCK_RE.finditer(text))
        if not matches:
            return False

        for match in matches:
            think_text = re.sub(r"<[^>]+>", " ", match.group(1) or "")
            if len(re.findall(r"\S+", think_text)) >= 5:
                return True

        return False

    def substantial_think_without_reflection(self, raw_response: str) -> bool:
        text = str(raw_response or "")
        if not text:
            return False

        matches = list(self.THINK_BLOCK_RE.finditer(text))
        if not matches:
            return False

        lowered = text.lower()
        for match in matches:
            think_text = re.sub(r"<[^>]+>", " ", match.group(1) or "")
            word_count = len(re.findall(r"\S+", think_text))
            if word_count < 5:
                continue

            tail = text[match.end():]
            tail_lower = lowered[match.end():]
            next_boundary_positions = [
                pos
                for pos in [
                    tail_lower.find("<action"),
                    tail_lower.find("<intent"),
                ]
                if pos >= 0
            ]
            boundary = min(next_boundary_positions) if next_boundary_positions else len(tail)
            reflection_slice = tail[:boundary]

            if self.REFLECTION_TAG_RE.search(reflection_slice):
                continue

            return True

        return False

    def _strip_non_plaintext_control_blocks(self, text: str) -> str:
        """
        Remove internal/control structures that should not count as user-facing
        plain text:
        - whole <think>...</think> blocks
        - whole memory/reflection tag blocks, including their content
        - any leftover raw tags

        Important: memory tag content is useful for memory, but it is not a
        final user-facing plain-text answer by itself.
        """
        cleaned = str(text or "")
        cleaned = self.THINK_BLOCK_RE.sub(" ", cleaned)
        cleaned = self.MEMORY_TAG_BLOCK_RE.sub(" ", cleaned)
        cleaned = re.sub(r"<[^>]+>", " ", cleaned)
        cleaned = re.sub(r"\s+", " ", cleaned).strip()
        return cleaned

    def is_reflection_only_repair_turn(self, raw_response: str, parsed_output, parsed_action_count: int) -> bool:
        text = str(raw_response or "").strip()
        if not text:
            return False

        if parsed_action_count > 0 or bool(getattr(parsed_output, "has_action_segment", False)):
            return False

        invalid_kind = str(getattr(parsed_output, "invalid_kind", "") or "").strip()
        if invalid_kind and invalid_kind != "missing_action_or_answer":
            return False

        if self.reflection_tag_count(text) <= 0:
            return False

        stripped = self._strip_non_plaintext_control_blocks(text)
        return not stripped

    def is_plaintext_answer_path(self, raw_response: str, parsed_output, parsed_action_count: int) -> bool:
        text = str(raw_response or "").strip()
        if not text:
            return False

        if parsed_action_count > 0 or bool(getattr(parsed_output, "has_action_segment", False)):
            return False

        invalid_kind = str(getattr(parsed_output, "invalid_kind", "") or "").strip()
        if invalid_kind and invalid_kind != "missing_action_or_answer":
            return False

        visible_text = str(getattr(parsed_output, "visible_text", "") or "").strip()
        if visible_text:
            return True

        stripped = self._strip_non_plaintext_control_blocks(text)
        return bool(stripped)