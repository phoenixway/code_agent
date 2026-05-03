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
RAW_CONTROL_TAG_FRAGMENT_RE = re.compile(
    r"</?\s*(think|intent|action|file_content|fact|finding|decision|preference|progress|path|subgoal)\b"
    r"|<\s*(memory_review|memory_update_done)\b",
    re.IGNORECASE,
)
PLAIN_THINK_PREFIX_RE = re.compile(r"^\s*(think|thinking)\s*:?\s*(?:\n+|$)", re.IGNORECASE)
UNPAIRED_OPERATIONAL_OPEN_RE = re.compile(
    r"<(fact|finding|decision|preference|progress|path|subgoal)\b",
    re.IGNORECASE,
)
FENCED_CODE_RE = re.compile(r"```.*?```", re.DOTALL)
INLINE_CODE_RE = re.compile(r"`[^`\n]+`")
XML_COMMENT_RE = re.compile(r"<!--.*?-->", re.DOTALL)
QUOTED_TAG_RE = re.compile(
    r"""(["'])[^"'\\\n]*(?:\\.[^"'\\\n]*)*<(?:think|intent|action|file_content|fact|finding|decision|preference|progress|path|subgoal|memory_review|memory_update_done)\b[^"'\\\n>]*>[^"'\\\n]*\1""",
    re.IGNORECASE,
)
ESCAPED_TAG_RE = re.compile(
    r"(?:&lt;|\\<)\s*(?:think|intent|action|file_content|fact|finding|decision|preference|progress|path|subgoal|memory_review|memory_update_done)\b",
    re.IGNORECASE,
)


def _mask_with_spaces(text: str, regex: re.Pattern[str]) -> str:
    def _mask(match: re.Match) -> str:
        return " " * (match.end() - match.start())

    return regex.sub(_mask, text)


def _mask_textual_control_contexts(response: str) -> str:
    text = str(response or "")
    for regex in (
        XML_COMMENT_RE,
        FENCED_CODE_RE,
        INLINE_CODE_RE,
        QUOTED_TAG_RE,
        ESCAPED_TAG_RE,
    ):
        text = _mask_with_spaces(text, regex)
    return text


def _mask_complete_control_blocks(response: str) -> str:
    text = _mask_textual_control_contexts(response)

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
    masked_response = _mask_textual_control_contexts(response)
    lowered = masked_response.lower()
    if "<think" not in lowered:
        return ""

    for match in THINK_TAG_RE.finditer(masked_response):
        body = str(match.group(0) or "")
        inner_match = re.match(r"<think(?:\s+[^>]*)?>(.*)</think>", body, re.IGNORECASE | re.DOTALL)
        think_body = (inner_match.group(1) if inner_match else "").strip()
        think_body_lower = think_body.lower()
        if "<think" in think_body_lower:
            return "nested_think"
        if "<action" in think_body_lower:
            return "action_inside_think"
        if "<file_content" in think_body_lower:
            return "file_content_inside_think"
        if "<intent" in think_body_lower:
            return "intent_inside_think"
    return ""


def sanitize_visible_text_for_user(response: str) -> tuple[str, bool]:
    if not isinstance(response, str):
        return "", False
    text = response
    if not text.strip():
        return "", False

    masked_for_detection = _mask_textual_control_contexts(text)
    text, _ = strip_plain_think_prefix_artifacts(text)
    masked_for_detection, _ = strip_plain_think_prefix_artifacts(masked_for_detection)
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
    masked_for_detection = masked_for_detection.replace("\r\n", "\n").replace("\r", "\n")
    masked_for_detection = THINK_TAG_RE.sub("\n", masked_for_detection)
    masked_for_detection = INTENT_TAG_RE.sub("\n", masked_for_detection)
    masked_for_detection = ACTION_TAG_RE.sub("\n", masked_for_detection)
    masked_for_detection = FILE_CONTENT_TAG_RE.sub("\n", masked_for_detection)
    masked_for_detection = MEMORY_BLOCK_TAG_RE.sub("\n", masked_for_detection)
    masked_for_detection = MEMORY_INLINE_TAG_RE.sub("\n", masked_for_detection)
    masked_for_detection = MEMORY_REVIEW_RE.sub("\n", masked_for_detection)
    masked_for_detection = SUBGOAL_TAG_RE.sub("\n", masked_for_detection)
    masked_for_detection = MEMORY_UPDATE_DONE_RE.sub("\n", masked_for_detection)
    masked_for_detection = PREVIOUSLY_PERFORMED_ACTION_RE.sub("\n", masked_for_detection)
    masked_for_detection = SYSTEM_AUDIT_LINE_RE.sub("\n", masked_for_detection)
    masked_for_detection = TOOL_HISTORY_LINE_RE.sub("\n", masked_for_detection)
    masked_for_detection = HISTORY_TOOL_ACTION_RE.sub("\n", masked_for_detection)
    masked_for_detection = HISTORY_TOOL_TAG_RE.sub("\n", masked_for_detection)
    leak_detected = bool(RAW_CONTROL_TAG_FRAGMENT_RE.search(masked_for_detection))
    text = GENERIC_TAG_RE.sub(" ", text)
    text = re.sub(r"[^\S\n]+", " ", text)
    text = re.sub(r" *\n *", "\n", text)
    text = re.sub(r"\n{3,}", "\n\n", text).strip()
    return text, leak_detected


def extract_visible_text_for_user(response: str) -> str:
    text, _ = sanitize_visible_text_for_user(response)
    return text


def visible_text_has_control_tag_leak(response: str) -> bool:
    _text, leak_detected = sanitize_visible_text_for_user(response)
    return leak_detected


def contains_control_markup(response: str) -> bool:
    if not isinstance(response, str) or not response:
        return False
    masked = _mask_textual_control_contexts(response)
    return bool(CONTROL_MARKUP_RE.search(masked) or MEMORY_REVIEW_RE.search(masked) or FILE_CONTENT_TAG_RE.search(masked))


def detect_incomplete_control_markup(response: str) -> str:
    if not isinstance(response, str) or not response.strip():
        return ""

    masked = _mask_complete_control_blocks(response)
    lowered = masked.lower()

    if lowered.rfind("<think") > lowered.rfind("</think>"):
        think_start = lowered.rfind("<think")
        trailing = lowered[think_start:] if think_start >= 0 else lowered
        if "<action" in trailing:
            return "action_inside_think"
        if "<file_content" in trailing:
            return "file_content_inside_think"
        if "<intent" in trailing:
            return "intent_inside_think"
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


_TERMINAL_DANGLING_WORDS = {
    "i", "i'm", "im", "i’ll", "ill", "the", "a", "an", "and", "or", "but",
    "to", "for", "with", "that", "this", "it", "is", "are", "was", "were",
    "я", "мені", "ми", "він", "вона", "це", "цей", "ця", "що", "як", "і", "та",
    "але", "для", "у", "в", "на", "з", "із", "до", "про",
}

_TERMINAL_END_PUNCT_RE = re.compile(r"[.!?…։。！？»”\"')\]`]+$")


def terminal_plaintext_completion_status(response: str) -> tuple[bool, str, str]:
    """Validate user-visible text for an intent-completion final answer.

    Returns (is_valid, reason, visible_text).

    This is deliberately lightweight. It is not a quality evaluator. It only
    blocks obvious transport/model truncation cases such as:
        <intent mode="complete">...</intent>
        Готово. Я

    The guard should prevent half-committing an intent completion when the
    accompanying final user-facing answer is missing or visibly cut off.
    """
    visible, leak_detected = sanitize_visible_text_for_user(response)
    text = str(visible or "").strip()
    if leak_detected:
        return False, "control_tag_leak_in_visible_text", text
    if not text:
        return False, "terminal_plaintext_missing", text

    compact = re.sub(r"\s+", " ", text).strip()
    if len(compact) < 20:
        return False, "terminal_plaintext_too_short", text

    words = re.findall(r"[A-Za-zА-Яа-яІіЇїЄєҐґ0-9_`./-]+", compact)
    if len(words) < 3:
        return False, "terminal_plaintext_too_few_words", text

    last_word = words[-1].strip("`'\"“”‘’()[]{}.,!?…:;").lower() if words else ""
    if last_word in _TERMINAL_DANGLING_WORDS:
        return False, "terminal_plaintext_dangling_word", text

    # A very short answer without terminal punctuation is suspicious. Longer
    # final answers can be valid without punctuation because they may end with a
    # path, command, or markdown fragment.
    if len(compact) < 80 and not _TERMINAL_END_PUNCT_RE.search(compact):
        return False, "terminal_plaintext_no_terminal_punctuation", text

    return True, "", text
