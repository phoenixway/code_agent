"""Canonical extraction and sanitization of user-visible text from model responses."""

from __future__ import annotations

import re

THINK_TAG_RE = re.compile(r"<think(?:\s+[^>]*)?>.*?</think>", re.IGNORECASE | re.DOTALL)
INTENT_TAG_RE = re.compile(r"<intent(?:\s+[^>]*)?>.*?</intent>", re.IGNORECASE | re.DOTALL)
ACTION_TAG_RE = re.compile(r"<action(?:\s+[^>]*)?>.*?</action>", re.IGNORECASE | re.DOTALL)
MEMORY_BLOCK_TAG_RE = re.compile(
    r"<(fact|finding|decision|preference|progress)\b[^>]*>.*?</\1>",
    re.IGNORECASE | re.DOTALL,
)
MEMORY_INLINE_TAG_RE = re.compile(r"</?(fact|finding|decision|preference|progress)\b[^>]*>", re.IGNORECASE)
PREVIOUSLY_PERFORMED_ACTION_RE = re.compile(r"<previously_performed_action[^>]*/>", re.IGNORECASE)
SYSTEM_AUDIT_LINE_RE = re.compile(r"(?im)^\s*system_tool_audit:.*?$")
TOOL_HISTORY_LINE_RE = re.compile(r"(?im)^\s*tool_history\s+\{.*?$")
HISTORY_TOOL_ACTION_RE = re.compile(r'(?is)<action[^>]*\btype\s*=\s*"history_tool"[^>]*>.*?</action>')
HISTORY_TOOL_TAG_RE = re.compile(r"(?is)<history_tool\b[^>]*>.*?</history_tool>")
GENERIC_TAG_RE = re.compile(r"<[^>]+>")
CONTROL_MARKUP_RE = re.compile(
    r"<\s*(think|intent|action|fact|finding|decision|preference|progress|history_tool|previously_performed_action)\b",
    re.IGNORECASE,
)


def extract_visible_text_for_user(response: str) -> str:
    if not isinstance(response, str):
        return ""
    text = response
    if not text.strip():
        return ""

    text = THINK_TAG_RE.sub(" ", text)
    text = INTENT_TAG_RE.sub(" ", text)
    text = ACTION_TAG_RE.sub(" ", text)
    text = MEMORY_BLOCK_TAG_RE.sub(" ", text)
    text = MEMORY_INLINE_TAG_RE.sub(" ", text)
    text = PREVIOUSLY_PERFORMED_ACTION_RE.sub(" ", text)
    text = SYSTEM_AUDIT_LINE_RE.sub(" ", text)
    text = TOOL_HISTORY_LINE_RE.sub(" ", text)
    text = HISTORY_TOOL_ACTION_RE.sub(" ", text)
    text = HISTORY_TOOL_TAG_RE.sub(" ", text)
    text = GENERIC_TAG_RE.sub(" ", text)
    text = re.sub(r"\s+", " ", text).strip()
    return text


def contains_control_markup(response: str) -> bool:
    if not isinstance(response, str) or not response:
        return False
    return bool(CONTROL_MARKUP_RE.search(response))
