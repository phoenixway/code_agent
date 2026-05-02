"""Helpers for parsing intent-aware model responses."""

from __future__ import annotations

import json
import re

from ..decision_models import NormalizedModelResponse, ParsedModelOutput
from .parsing_actions import ParsingActionsMixin
from .parsing_intent import ParsingIntentMixin
from .parsing_normalization import ParsingNormalizationMixin
from .think_repair import ThinkAutoRepairResult, ThinkBoundaryRepairer


class IntentResponseParser(ParsingNormalizationMixin, ParsingIntentMixin, ParsingActionsMixin):
    INTENT_TAG_RE = re.compile(
        r"<intent\b(?P<attrs>[^>]*?)(?:>(?P<body>.*?)</intent>|(?P<selfclose>/\s*>))",
        re.IGNORECASE | re.DOTALL,
    )
    THINK_TAG_RE = re.compile(r"<think(?:\s+[^>]*)?>.*?</think>", re.IGNORECASE | re.DOTALL)
    ACTION_TAG_RE = re.compile(r"<action(?:\s+[^>]*)?>.*?</action>", re.IGNORECASE | re.DOTALL)
    ACTION_BLOCK_RE = re.compile(
        r"<action(?:\s+[^>]*)?>(?P<body>.*?)</action>",
        re.IGNORECASE | re.DOTALL,
    )
    ACTION_XML_PAYLOAD_TAG_RE = re.compile(
        r"<\s*(type|path|command|tool_code|intent|think|file_content)\b",
        re.IGNORECASE,
    )
    TOP_LEVEL_CONTROL_BLOCK_RE = re.compile(
        r"(?im)(^|\n)[ \t]*<(?P<tag>"
        r"think|intent|action|file_content|fact|finding|decision|preference|progress|path|subgoal|memory_review|memory_update_done"
        r")\b"
    )
    TOOL_HISTORY_RE = re.compile(r"(?im)^\s*tool_history\s+\{.*?$")
    HISTORY_TOOL_ACTION_RE = re.compile(r'(?is)<action[^>]*\btype\s*=\s*"history_tool"[^>]*>.*?</action>')
    HISTORY_TOOL_TAG_RE = re.compile(r"(?is)<history_tool\b[^>]*>.*?</history_tool>")
    ATTR_RE = re.compile(r"""([a-zA-Z_][\w\-]*)\s*=\s*(?:"([^"]*)"|'([^']*)')""")
    INT_FIELDS = {
        "safe_steps_limit",
        "retry_limit",
        "requested_steps",
    }
    LIST_FIELDS = {
        "allowed_actions",
    }

    READ_ONLY_ACTION_TYPES = {
        "read_file",
        "read_chunk",
        "read_file_skeleton",
        "extract_kotlin_function",
        "extract_symbol",
        "search_content",
        "search_files",
        "list_directory",
        "find_files",
        "git_diff",
    }

    def __init__(self, logger=None):
        self.logger = logger
        self.think_repairer = ThinkBoundaryRepairer(logger)

    def _build_parsed_output(
        self,
        *,
        safe_response: str,
        safe_segments,
        has_action_tag: bool,
        has_action_segment: bool,
        has_intent_segment: bool,
        visible_text: str,
        invalid_kind: str,
        normalized: NormalizedModelResponse,
    ) -> ParsedModelOutput:
        return ParsedModelOutput(
            response=safe_response,
            segments=safe_segments,
            has_action_tag=has_action_tag,
            has_action_segment=has_action_segment,
            has_intent_segment=has_intent_segment,
            visible_text=visible_text,
            invalid_kind=invalid_kind,
            model_stop_reason="",
            auto_closed_think=bool(normalized.think_repair_applied),
            auto_closed_think_reason=str(normalized.think_repair_reason or ""),
            auto_closed_think_tag=str(normalized.think_repair_tag or ""),
        )
