"""Canonical extraction and sanitization of user-visible text from model responses."""

from __future__ import annotations

import re

THINK_TAG_RE = re.compile(r"<think(?:\s+[^>]*)?>.*?</think>", re.IGNORECASE | re.DOTALL)
INTENT_TAG_RE = re.compile(r"<intent(?:\s+[^>]*)?>.*?</intent>", re.IGNORECASE | re.DOTALL)
ACTION_TAG_RE = re.compile(r"<action(?:\s+[^>]*)?>.*?</action>", re.IGNORECASE | re.DOTALL)
FILE_CONTENT_TAG_RE = re.compile(r"<file_content(?:\s+[^>]*)?>.*?</file_content>", re.IGNORECASE | re.DOTALL)
MEMORY_BLOCK_TAG_RE = re.compile(
    r"<(fact|finding|decision|preference|progress|path)\b[^>]*>.*?</\1>",
    re.IGNORECASE | re.DOTALL,
)
MEMORY_INLINE_TAG_RE = re.compile(r"</?(fact|finding|decision|preference|progress|path)\b[^>]*>", re.IGNORECASE)
MEMORY_REVIEW_RE = re.compile(r"<memory_review\b[^>]*/>", re.IGNORECASE)
SUBGOAL_TAG_RE = re.compile(r"<subgoal\b[^>]*(?:>.*?</subgoal>|/>)", re.IGNORECASE | re.DOTALL)
MEMORY_UPDATE_DONE_RE = re.compile(r"<memory_update_done\s*/>", re.IGNORECASE)
PREVIOUSLY_PERFORMED_ACTION_RE = re.compile(r"<previously_performed_action[^>]*/>", re.IGNORECASE)
SYSTEM_AUDIT_LINE_RE = re.compile(r"(?im)^\s*system_tool_audit:.*?$")
TOOL_HISTORY_LINE_RE = re.compile(r"(?im)^\s*tool_history\s+\{.*?$")
HISTORY_TOOL_ACTION_RE = re.compile(r'(?is)<action[^>]*\btype\s*=\s*"history_tool"[^>]*>.*?</action>')
HISTORY_TOOL_TAG_RE = re.compile(r"(?is)<history_tool\b[^>]*>.*?</history_tool>")
GENERIC_TAG_RE = re.compile(r"<[^>]+>")
CONTROL_MARKUP_RE = re.compile(
    r"<\s*(think|intent|action|file_content|fact|finding|decision|preference|progress|path|subgoal|memory_review|memory_update_done|history_tool|previously_performed_action)\b",
    re.IGNORECASE,
)
PLAIN_THINK_PREFIX_RE = re.compile(r"^\s*(think|thinking)\s*:?\s*(?:\n+|$)", re.IGNORECASE)
UNPAIRED_OPERATIONAL_OPEN_RE = re.compile(
    r"<(fact|finding|decision|preference|progress|path|subgoal)\b",
    re.IGNORECASE,
)
THINK_VERBOSE_CHAR_LIMIT = 800


def _mask_complete_control_blocks(response: str) -> str:
    text = str(response or "")

    def _mask(match: re.Match) -> str:
        return " " * (match.end() - match.start())

    for regex in (
        THINK_TAG_RE,
        INTENT_TAG_RE,
        ACTION_TAG_RE,
        FILE_CONTENT_TAG_RE,
        MEMORY_BLOCK_TAG_RE,
        MEMORY_REVIEW_RE,
        SUBGOAL_TAG_RE,
        MEMORY_UPDATE_DONE_RE,
        PREVIOUSLY_PERFORMED_ACTION_RE,
        HISTORY_TOOL_ACTION_RE,
        HISTORY_TOOL_TAG_RE,
    ):
        text = regex.sub(_mask, text)
    return text


def strip_plain_think_prefix_artifacts(response: str) -> tuple[str, bool]:
    if not isinstance(response, str):
        return "", False

    text = response
    match = PLAIN_THINK_PREFIX_RE.match(text)
    if not match:
        return text, False

    remainder = text[match.end():]
    control_positions = [
        pos
        for pos in [
            remainder.lower().find("<intent"),
            remainder.lower().find("<action"),
            remainder.lower().find("<think"),
        ]
        if pos >= 0
    ]
    if control_positions:
        return remainder[min(control_positions):].lstrip(), True

    block_split = re.split(r"\n\s*\n", remainder, maxsplit=1)
    if len(block_split) == 2:
        return block_split[1].lstrip(), True

    return "", True


def detect_invalid_think_markup(response: str) -> str:
    if not isinstance(response, str) or not response.strip():
        return ""
    lowered = response.lower()
    if "<think" not in lowered:
        return ""

    for match in THINK_TAG_RE.finditer(response):
        body = str(match.group(0) or "")
        inner_match = re.match(r"<think(?:\s+[^>]*)?>(.*)</think>", body, re.IGNORECASE | re.DOTALL)
        think_body = (inner_match.group(1) if inner_match else "").strip()
        think_body_lower = think_body.lower()
        if "<think" in think_body_lower:
            return "malformed_verbose_or_nested_think"
        if "<action" in think_body_lower:
            return "malformed_verbose_or_nested_think"
        if "```" in think_body:
            return "malformed_verbose_or_nested_think"
        if len(think_body) > THINK_VERBOSE_CHAR_LIMIT:
            return "malformed_verbose_or_nested_think"
    return ""


def extract_visible_text_for_user(response: str) -> str:
    if not isinstance(response, str):
        return ""
    text = response
    if not text.strip():
        return ""
    if detect_invalid_think_markup(text):
        return ""

    text, _ = strip_plain_think_prefix_artifacts(text)
    text = text.replace("\r\n", "\n").replace("\r", "\n")
    text = THINK_TAG_RE.sub("\n", text)
    text = INTENT_TAG_RE.sub("\n", text)
    text = ACTION_TAG_RE.sub("\n", text)
    text = FILE_CONTENT_TAG_RE.sub("\n", text)
    text = MEMORY_BLOCK_TAG_RE.sub("\n", text)
    text = MEMORY_INLINE_TAG_RE.sub("\n", text)
    text = MEMORY_REVIEW_RE.sub("\n", text)
    text = SUBGOAL_TAG_RE.sub("\n", text)
    text = MEMORY_UPDATE_DONE_RE.sub("\n", text)
    text = PREVIOUSLY_PERFORMED_ACTION_RE.sub("\n", text)
    text = SYSTEM_AUDIT_LINE_RE.sub("\n", text)
    text = TOOL_HISTORY_LINE_RE.sub("\n", text)
    text = HISTORY_TOOL_ACTION_RE.sub("\n", text)
    text = HISTORY_TOOL_TAG_RE.sub("\n", text)
    text = GENERIC_TAG_RE.sub(" ", text)
    text = re.sub(r"[^\S\n]+", " ", text)
    text = re.sub(r" *\n *", "\n", text)
    text = re.sub(r"\n{3,}", "\n\n", text).strip()
    return text


def contains_control_markup(response: str) -> bool:
    if not isinstance(response, str) or not response:
        return False
    return bool(CONTROL_MARKUP_RE.search(response) or MEMORY_REVIEW_RE.search(response) or FILE_CONTENT_TAG_RE.search(response))


def detect_incomplete_control_markup(response: str) -> str:
    if not isinstance(response, str) or not response.strip():
        return ""

    masked = _mask_complete_control_blocks(response)
    lowered = masked.lower()

    if lowered.rfind("<think") > lowered.rfind("</think>"):
        return "malformed_incomplete_think"
    if lowered.rfind("<action") > lowered.rfind("</action>"):
        return "malformed_incomplete_action"
    if lowered.rfind("<intent") > lowered.rfind("</intent>"):
        return "malformed_incomplete_intent"
    if lowered.rfind("<file_content") > lowered.rfind("</file_content>"):
        return "malformed_incomplete_file_content"
    if UNPAIRED_OPERATIONAL_OPEN_RE.search(masked):
        return "truncated_internal_response"
    return ""
