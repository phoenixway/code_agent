"""Semantic helpers for orchestrator response classification."""

from __future__ import annotations

import re

from .visible_text import strip_plain_think_prefix_artifacts


class ResponseSemantics:
    CHECKPOINT_TAG_RE = re.compile(
        r"<(fact|finding|decision|preference|progress|path|subgoal|memory_review)\b",
        re.IGNORECASE,
    )
    THINK_BLOCK_RE = re.compile(
        r"<think(?:\s+[^>]*)?>(.*?)</think>",
        re.IGNORECASE | re.DOTALL,
    )
    REFLECTION_TAG_RE = re.compile(
        r"<(fact|finding|decision|preference|progress|path|subgoal|memory_review|memory_update_done)\b",
        re.IGNORECASE,
    )
    MEMORY_TAG_BLOCK_RE = re.compile(
        r"<(fact|finding|decision|preference|progress|path)\b[^>]*>.*?</\1>",
        re.IGNORECASE | re.DOTALL,
    )
    MEMORY_REVIEW_RE = re.compile(r"<memory_review\b[^>]*/>", re.IGNORECASE)
    SUBGOAL_BLOCK_RE = re.compile(r"<subgoal\b[^>]*(?:>.*?</subgoal>|/>)", re.IGNORECASE | re.DOTALL)
    MEMORY_UPDATE_DONE_RE = re.compile(r"<memory_update_done\s*/>", re.IGNORECASE)
    FILE_CONTENT_RE = re.compile(r"<file_content(?:\s+[^>]*)?>.*?</file_content>", re.IGNORECASE | re.DOTALL)
    ACTION_OPEN_RE = re.compile(r"<action(?:\s+[^>]*)?>", re.IGNORECASE)
    LEAKED_SYSTEM_RESULT_RE = re.compile(
        r"\bSYSTEM\s+RESULT\b(?:\s*\([^)]*\)|\s+for\b|\s*:)",
        re.IGNORECASE,
    )

    def has_plain_think_prefix(self, raw_response: str) -> bool:
        _cleaned, stripped = strip_plain_think_prefix_artifacts(str(raw_response or ""))
        return stripped

    def reflection_tag_count(self, raw_response: str) -> int:
        text = str(raw_response or "")
        if not text:
            return 0
        return len(list(self.REFLECTION_TAG_RE.finditer(text)))

    def checkpoint_tag_count(self, raw_response: str) -> int:
        text = str(raw_response or "")
        if not text:
            return 0
        return len(list(self.CHECKPOINT_TAG_RE.finditer(text)))

    def has_checkpoint_tags(self, raw_response: str) -> bool:
        return self.checkpoint_tag_count(raw_response) > 0

    def has_memory_update_done(self, raw_response: str) -> bool:
        return bool(self.MEMORY_UPDATE_DONE_RE.search(str(raw_response or "")))

    def has_complete_think_before_action(self, raw_response: str) -> bool:
        text = str(raw_response or "")
        if not text:
            return False

        action_match = self.ACTION_OPEN_RE.search(text)
        if not action_match:
            return False

        action_start = action_match.start()
        for match in self.THINK_BLOCK_RE.finditer(text):
            if match.end() <= action_start:
                return True
        return False

    def has_checkpoint_before_action(self, raw_response: str) -> bool:
        text = str(raw_response or "")
        if not text:
            return False

        action_match = self.ACTION_OPEN_RE.search(text)
        if not action_match:
            return False

        before_action = text[: action_match.start()]
        return self.has_checkpoint_tags(before_action)

    def has_memory_update_done_before_action(self, raw_response: str) -> bool:
        text = str(raw_response or "")
        if not text:
            return False

        action_match = self.ACTION_OPEN_RE.search(text)
        if not action_match:
            return False

        before_action = text[: action_match.start()]
        return self.has_memory_update_done(before_action)

    def has_valid_state_changing_review_before_action(self, raw_response: str) -> bool:
        text = str(raw_response or "")
        if not text:
            return False

        if not self.has_complete_think_before_action(text):
            return False
        if not self.has_checkpoint_before_action(text):
            return False
        if not self.has_memory_update_done_before_action(text):
            return False
        return True

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
        cleaned, _ = strip_plain_think_prefix_artifacts(cleaned)
        cleaned = self.THINK_BLOCK_RE.sub(" ", cleaned)
        cleaned = self.MEMORY_TAG_BLOCK_RE.sub(" ", cleaned)
        cleaned = self.MEMORY_REVIEW_RE.sub(" ", cleaned)
        cleaned = self.SUBGOAL_BLOCK_RE.sub(" ", cleaned)
        cleaned = self.MEMORY_UPDATE_DONE_RE.sub(" ", cleaned)
        cleaned = self.FILE_CONTENT_RE.sub(" ", cleaned)
        cleaned = re.sub(r"<[^>]+>", " ", cleaned)
        cleaned = re.sub(r"\s+", " ", cleaned).strip()
        return cleaned


    def looks_like_leaked_system_result(self, raw_response: str) -> bool:
        """Return True when assistant-visible text appears to replay tool transcript.

        SYSTEM RESULT blocks are internal tool/result transcript material. They may
        be present in system/history context, but the model must not copy them
        into a plain assistant answer. This detector intentionally looks for the
        canonical transcript prefixes used by the runtime, not ordinary prose
        such as "the system result was useful".
        """
        text = str(raw_response or "")
        if not text:
            return False
        return bool(self.LEAKED_SYSTEM_RESULT_RE.search(text))

    def is_reflection_only_repair_turn(self, raw_response: str, parsed_output, parsed_action_count: int) -> bool:
        return self.is_durable_state_repair_turn(
            raw_response,
            parsed_output,
            parsed_action_count,
            required_kind="missing_think_reflection",
        )

    def is_durable_state_repair_turn(
        self,
        raw_response: str,
        parsed_output,
        parsed_action_count: int,
        *,
        required_kind: str = "",
    ) -> bool:
        text = str(raw_response or "").strip()
        if not text:
            return False

        if parsed_action_count > 0 or bool(getattr(parsed_output, "has_action_segment", False)):
            return False

        invalid_kind = str(getattr(parsed_output, "invalid_kind", "") or "").strip()
        if invalid_kind and invalid_kind != "missing_action_or_answer":
            return False

        stripped = self._strip_non_plaintext_control_blocks(text)
        if stripped:
            return False

        kind = str(required_kind or "").strip()
        if kind == "missing_memory_update_done":
            return self.has_memory_update_done(text)

        return self.has_checkpoint_tags(text) and self.has_memory_update_done(text)

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
