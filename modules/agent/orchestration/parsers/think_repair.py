"""Conservative boundary repair for unclosed <think> blocks."""

from __future__ import annotations

import re
from dataclasses import dataclass

from ..shared.decision_models import NormalizedModelResponse

@dataclass
class ThinkAutoRepairResult:
    response_text: str
    applied: bool = False
    reason: str = ""
    tag_name: str = ""
    insert_at: int = -1
    confidence: str = ""
    blocked_by_atomicity: bool = False


class ThinkBoundaryRepairer:
    """Repair only one defect: an open <think> leaking into clear protocol tags.

    This layer is intentionally conservative. If the signal is ambiguous, it
    does nothing and leaves the response for normal structural recovery.
    """

    UNCLOSED_THINK_OPEN_RE = re.compile(r"<think(?:\s+[^>]*)?>", re.IGNORECASE)
    UNCLOSED_THINK_CLOSE_RE = re.compile(r"</think>", re.IGNORECASE)
    PROTOCOL_TAG_LINE_RE = re.compile(
        r"(?m)^(?P<indent>[ \t]*)"
        r"(?P<tag><(?P<name>action|intent|subgoal|memory_update_done|memory_review|finding|fact|decision|preference|progress|path|file_content)\b[^>]*>)"
    )
    FENCED_CODE_RE = re.compile(r"```.*?```", re.DOTALL)
    INLINE_CODE_RE = re.compile(r"`[^`\n]+`")
    XML_COMMENT_RE = re.compile(r"<!--.*?-->", re.DOTALL)
    QUOTED_PROTOCOL_RE = re.compile(
        r"""(["'])[^"'\\\n]*(?:\\.[^"'\\\n]*)*<(?:action|intent|subgoal|memory_update_done|memory_review|finding|fact|decision|preference|progress|path|file_content)\b[^"'\\\n>]*>[^"'\\\n]*\1""",
        re.IGNORECASE,
    )
    ESCAPED_PROTOCOL_RE = re.compile(
        r"(?:&lt;|\\<)\s*(?:action|intent|subgoal|memory_update_done|memory_review|finding|fact|decision|preference|progress|path|file_content)\b",
        re.IGNORECASE,
    )
    CANONICAL_PROTOCOL_SEQUENCE_RE = re.compile(
        r"(?is)"
        r"(?:"
        r"<(?:finding|fact|decision|preference|progress|path)\b[^>]*>.*?</(?:finding|fact|decision|preference|progress|path)>"
        r"|<subgoal\b[^>]*(?:>.*?</subgoal>|/>)"
        r"|<memory_review\b[^>]*/>"
        r")"
        r".{0,400}?<memory_update_done\s*/>"
        r".{0,400}?<action\b"
    )

    def __init__(self, logger=None):
        self.logger = logger

    def _debug(self, message: str, *args) -> None:
        if self.logger is not None:
            self.logger.debug(message, *args)

    def _mask_with_spaces(self, text: str, regex: re.Pattern[str]) -> str:
        def _mask(match: re.Match) -> str:
            return " " * (match.end() - match.start())

        return regex.sub(_mask, text)

    def _mask_textual_protocol_contexts(self, response_text: str) -> str:
        text = str(response_text or "")
        for regex in (
            self.XML_COMMENT_RE,
            self.FENCED_CODE_RE,
            self.INLINE_CODE_RE,
            self.QUOTED_PROTOCOL_RE,
            self.ESCAPED_PROTOCOL_RE,
        ):
            text = self._mask_with_spaces(text, regex)
        return text

    def repair(self, response_text: str, *, allow_autorepair: bool = True) -> ThinkAutoRepairResult:
        text = str(response_text or "")
        if not allow_autorepair:
            return ThinkAutoRepairResult(
                response_text=text,
                blocked_by_atomicity=True,
            )
        if not text.strip():
            return ThinkAutoRepairResult(response_text=text)

        masked = self._mask_textual_protocol_contexts(text)
        open_matches = list(self.UNCLOSED_THINK_OPEN_RE.finditer(masked))
        if not open_matches:
            return ThinkAutoRepairResult(response_text=text)
        close_matches = list(self.UNCLOSED_THINK_CLOSE_RE.finditer(masked))
        last_open = open_matches[-1]
        last_close_end = close_matches[-1].end() if close_matches else -1
        if last_close_end > last_open.start():
            return ThinkAutoRepairResult(response_text=text)

        trailing_masked = masked[last_open.end():]
        candidate_match = self.PROTOCOL_TAG_LINE_RE.search(trailing_masked)
        if candidate_match is None:
            return ThinkAutoRepairResult(response_text=text)

        candidate_name = str(candidate_match.group("name") or "").strip().lower()
        candidate_absolute_start = last_open.end() + candidate_match.start("tag")
        trailing_original = text[candidate_absolute_start:]
        trailing_masked_from_candidate = masked[candidate_absolute_start:]

        has_multiple_protocol_tags = len(list(self.PROTOCOL_TAG_LINE_RE.finditer(trailing_masked_from_candidate))) >= 2
        has_canonical_sequence = bool(self.CANONICAL_PROTOCOL_SEQUENCE_RE.search(trailing_original))
        has_followup_action = bool(re.search(r"(?is)<action(?:\s+[^>]*)?>\s*\{.*?</action>", trailing_original))

        high_confidence = False
        reason = ""
        if candidate_name == "memory_update_done":
            if has_followup_action:
                high_confidence = True
                reason = "memory_update_done_before_action_after_unclosed_think"
        elif candidate_name == "action":
            if re.match(r"(?is)<action(?:\s+[^>]*)?>\s*\{", trailing_original) and "</action>" in trailing_original:
                high_confidence = True
                reason = "action_json_after_unclosed_think"
        elif candidate_name in {"finding", "fact", "decision", "preference", "progress", "path", "subgoal", "memory_review"}:
            if has_canonical_sequence and has_multiple_protocol_tags:
                high_confidence = True
                reason = "canonical_protocol_sequence_after_unclosed_think"

        if not high_confidence:
            return ThinkAutoRepairResult(response_text=text)

        repaired = text[:candidate_absolute_start] + "</think>\n" + text[candidate_absolute_start:]
        self._debug(
            "ThinkBoundaryRepairer applied=%s tag=%s reason=%s insert_at=%s",
            True,
            candidate_name,
            reason,
            candidate_absolute_start,
        )
        return ThinkAutoRepairResult(
            response_text=repaired,
            applied=True,
            reason=reason,
            tag_name=candidate_name,
            insert_at=candidate_absolute_start,
            confidence="high",
            blocked_by_atomicity=False,
        )

    def normalize(self, response_text: str, *, allow_autorepair: bool = True) -> NormalizedModelResponse:
        raw_text = str(response_text or "")
        repair = self.repair(raw_text, allow_autorepair=allow_autorepair)
        repairs_applied: tuple[str, ...] = ("auto_close_think",) if repair.applied else ()
        repair_blocked_reason = "intent_atomicity_guard" if repair.blocked_by_atomicity else ""
        diagnostics = {
            "think_repair_candidate_tag": str(repair.tag_name or ""),
            "think_repair_insert_at": int(repair.insert_at),
        }
        return NormalizedModelResponse(
            raw_response=raw_text,
            normalized_response=str(repair.response_text or ""),
            repairs_applied=repairs_applied,
            repair_blocked_reason=repair_blocked_reason,
            think_repair_applied=bool(repair.applied),
            think_repair_reason=str(repair.reason or ""),
            think_repair_confidence=str(repair.confidence or ""),
            think_repair_tag=str(repair.tag_name or ""),
            think_repair_insert_at=int(repair.insert_at),
            think_repair_blocked_by_atomicity=bool(repair.blocked_by_atomicity),
            diagnostics=diagnostics,
        )
