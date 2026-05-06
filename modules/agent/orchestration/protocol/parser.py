"""Strict parser for the protocol compiler pipeline."""

from __future__ import annotations

import json
import re
from typing import Any

from .lexer import ProtocolLexer
from .models import (
    ActionNode,
    CompilerAnalysis,
    EndTagToken,
    ErrorValue,
    FileContentNode,
    FencedCodeToken,
    InlineCodeToken,
    IntentNode,
    LiteralProtocolTagNode,
    MarkerNode,
    MemoryNode,
    Node,
    ResponseAst,
    ResponseShape,
    SelfClosingTagToken,
    Span,
    StartTagToken,
    SubgoalNode,
    TextToken,
    ThinkNode,
    VisibleTextNode,
)
from .spec import PROTOCOL_SPEC


class ProtocolParser:
    MEMORY_TAGS = {"fact", "finding", "decision", "path", "progress", "memory_review"}
    ACTION_XML_FIELD_RE = re.compile(
        r"</?\s*(type|action|path|command|args|payload|content)\b",
        re.IGNORECASE,
    )
    ACTION_TOOL_CODE_RE = re.compile(
        r"^\s*[A-Za-z_][A-Za-z0-9_]*(?:\.[A-Za-z_][A-Za-z0-9_]*)?\s*\([^{}]*\)\s*$",
        re.DOTALL,
    )
    PROTOCOL_TAG_IN_STRING_RE = re.compile(
        r"</?\s*(action|intent|think|file_content|memory_update_done|memory_review|fact|finding|decision|path|progress|subgoal)\b",
        re.IGNORECASE,
    )
    THINK_FORBIDDEN_TAG_MAP = {
        "action": "E_ACTION_INSIDE_THINK",
        "intent": "E_INTENT_INSIDE_THINK",
        "file_content": "E_FILE_CONTENT_INSIDE_THINK",
        "fact": "E_MEMORY_TAG_INSIDE_THINK",
        "finding": "E_MEMORY_TAG_INSIDE_THINK",
        "decision": "E_MEMORY_TAG_INSIDE_THINK",
        "path": "E_MEMORY_TAG_INSIDE_THINK",
        "progress": "E_MEMORY_TAG_INSIDE_THINK",
        "memory_review": "E_MEMORY_TAG_INSIDE_THINK",
        "memory_update_done": "E_MEMORY_TAG_INSIDE_THINK",
        "subgoal": "E_MEMORY_TAG_INSIDE_THINK",
    }

    def __init__(self, spec=PROTOCOL_SPEC):
        self.spec = spec
        self.lexer = ProtocolLexer(spec)

    def parse(self, raw: str) -> tuple[ResponseAst | None, ErrorValue | None, tuple[Any, ...]]:
        text = str(raw or "")
        tokens = self.lexer.lex(text)
        nodes: list[Node] = []
        i = 0

        while i < len(tokens):
            token = tokens[i]
            if isinstance(token, TextToken):
                if token.text:
                    nodes.append(VisibleTextNode(text=token.text, span=token.span))
                i += 1
                continue
            if isinstance(token, InlineCodeToken):
                nodes.append(LiteralProtocolTagNode(text=token.text, context="inline_code", span=token.span))
                i += 1
                continue
            if isinstance(token, FencedCodeToken):
                nodes.append(LiteralProtocolTagNode(text=token.text, context="fenced_code", span=token.span))
                i += 1
                continue
            if isinstance(token, SelfClosingTagToken):
                if token.name == "memory_update_done":
                    nodes.append(MarkerNode(span=token.span))
                elif token.name == "memory_review":
                    nodes.append(MemoryNode(tag=token.name, attrs=token.attrs, content=None, span=token.span))
                else:
                    nodes.append(LiteralProtocolTagNode(text=token.span.excerpt, context="self_closing", span=token.span))
                i += 1
                continue
            if isinstance(token, EndTagToken):
                return None, self._error("E_AMBIGUOUS_PROTOCOL_SYNTAX", token.span, actual=token.name), tokens
            if not isinstance(token, StartTagToken):
                i += 1
                continue
            result = self._parse_block(tokens, i)
            if isinstance(result, ErrorValue):
                return None, result, tokens
            node, next_index = result
            nodes.append(node)
            i = next_index

        return ResponseAst(raw=text, nodes=tuple(nodes)), None, tokens

    def _parse_block(self, tokens: tuple[Any, ...], start_index: int) -> tuple[Node, int] | ErrorValue:
        token = tokens[start_index]
        assert isinstance(token, StartTagToken)
        name = token.name

        if name == "think":
            # Scan for forbidden tags or the end tag
            for i in range(start_index + 1, len(tokens)):
                inner_token = tokens[i]
                if isinstance(inner_token, (StartTagToken, SelfClosingTagToken)):
                    code = self.THINK_FORBIDDEN_TAG_MAP.get(inner_token.name)
                    if code:
                        return self._error(code, inner_token.span, actual=inner_token.name)
                elif isinstance(inner_token, EndTagToken) and inner_token.name == "think":
                    # Found the closing tag. The block is valid.
                    closing_index = i
                    body_tokens = tokens[start_index + 1 : closing_index]
                    body_span = self._merge_spans(token.span, tokens[closing_index].span)
                    body_text = self._concat_text(body_tokens)
                    return ThinkNode(content=body_text, span=body_span), closing_index + 1
            # If loop finishes, tag was not closed
            return self._error("E_UNCLOSED_THINK", token.span, actual=name)

        closing_index = self._find_matching_end(tokens, start_index + 1, name)
        if closing_index is None:
            if name == "file_content":
                return self._error("E_FILE_CONTENT_UNCLOSED", token.span, actual=name)
            return self._error("E_AMBIGUOUS_PROTOCOL_SYNTAX", token.span, actual=name)
        body_tokens = tokens[start_index + 1 : closing_index]
        body_span = self._merge_spans(token.span, tokens[closing_index].span)
        body_text = self._concat_text(body_tokens)

        if name == "intent":
            payload, error = self._parse_json_object(body_text, "E_INTENT_JSON_INVALID", body_span)
            if error is not None:
                return error
            return IntentNode(
                attrs=token.attrs,
                raw_payload=body_text,
                json_payload=payload,
                json_error=None,
                span=body_span,
            ), closing_index + 1
        if name == "action":
            payload, error = self._parse_json_any(body_text, "E_ACTION_JSON_INVALID", body_span)
            if error is not None:
                return error
            return ActionNode(
                attrs=token.attrs,
                raw_payload=body_text,
                json_payload=payload,
                json_error=None,
                span=body_span,
            ), closing_index + 1
        if name == "file_content":
            return FileContentNode(content=body_text, span=body_span), closing_index + 1
        if name == "subgoal":
            return SubgoalNode(attrs=token.attrs, content=body_text or None, span=body_span), closing_index + 1
        if name in self.MEMORY_TAGS:
            return MemoryNode(tag=name, attrs=token.attrs, content=body_text or None, span=body_span), closing_index + 1
        return LiteralProtocolTagNode(text=body_text, context="unknown_block", span=body_span), closing_index + 1

    def _find_matching_end(self, tokens: tuple[Any, ...], start_index: int, name: str) -> int | None:
        depth = 0
        for index in range(start_index, len(tokens)):
            token = tokens[index]
            if isinstance(token, StartTagToken) and token.name == name:
                depth += 1
                continue
            if isinstance(token, EndTagToken) and token.name == name:
                if depth == 0:
                    return index
                depth -= 1
        return None

    def _concat_text(self, tokens: tuple[Any, ...]) -> str:
        parts: list[str] = []
        for token in tokens:
            if isinstance(token, TextToken):
                parts.append(token.text)
            elif isinstance(token, InlineCodeToken):
                parts.append(token.text)
            elif isinstance(token, FencedCodeToken):
                parts.append(token.text)
            else:
                parts.append(token.span.excerpt)
        return "".join(parts)

    def _parse_json_object(self, text: str, code: str, span: Span) -> tuple[dict[str, Any] | None, ErrorValue | None]:
        try:
            payload = json.loads(text)
        except json.JSONDecodeError as exc:
            return None, self._error(code, span, actual=exc.msg)
        if not isinstance(payload, dict):
            return None, self._error(code, span, actual=type(payload).__name__)
        found_tag = self._find_protocol_tag_in_json_strings(payload)
        if found_tag:
            return None, self._error("E_PROTOCOL_TAG_IN_JSON_STRING", span, actual=found_tag)
        return payload, None

    def _parse_json_any(self, text: str, code: str, span: Span) -> tuple[Any | None, ErrorValue | None]:
        try:
            payload = json.loads(text)
            if isinstance(payload, list):
                return None, self._error("E_ACTION_PAYLOAD_ARRAY", span, actual="json_array")
            if not isinstance(payload, dict):
                return None, self._error("E_ACTION_PAYLOAD_NOT_OBJECT", span, actual=type(payload).__name__)
            found_tag = self._find_protocol_tag_in_json_strings(payload)
            if found_tag:
                return None, self._error("E_PROTOCOL_TAG_IN_JSON_STRING", span, actual=found_tag)
            return payload, None
        except json.JSONDecodeError as exc:
            stripped_text = text.strip()
            if self.ACTION_XML_FIELD_RE.search(stripped_text):
                return None, self._error("E_ACTION_PAYLOAD_XML_FIELDS", span, actual="xml_like_tags")
            if self.ACTION_TOOL_CODE_RE.match(stripped_text):
                return None, self._error("E_ACTION_PAYLOAD_TOOL_CODE", span, actual="tool_code_like")
            return None, self._error(code, span, actual=exc.msg)

    def _find_protocol_tag_in_json_strings(self, payload: Any) -> str | None:
        if isinstance(payload, str):
            match = self.PROTOCOL_TAG_IN_STRING_RE.search(payload)
            if match:
                return match.group(0)
        elif isinstance(payload, dict):
            for value in payload.values():
                found = self._find_protocol_tag_in_json_strings(value)
                if found:
                    return found
        elif isinstance(payload, list):
            for item in payload:
                found = self._find_protocol_tag_in_json_strings(item)
                if found:
                    return found
        return None

    def _error(self, code: str, span: Span | None, *, actual: str | None = None) -> ErrorValue:
        spec = self.spec.errors[code]
        return ErrorValue(
            code=code,
            phase=spec.phase,
            severity="recoverable",
            message=spec.default_message,
            span=span,
            actual=actual,
            transaction_applied=False,
            action_dispatched=False,
            recovery_id=spec.recovery_id,
        )

    def _merge_spans(self, start: Span, end: Span) -> Span:
        excerpt = start.excerpt
        if start.start != end.end:
            excerpt = excerpt + " ... " + end.excerpt
        if len(excerpt) > 160:
            excerpt = excerpt[:157] + "..."
        return Span(start=start.start, end=end.end, excerpt=excerpt)
