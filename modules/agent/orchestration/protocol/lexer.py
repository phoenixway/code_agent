"""Markdown-aware lexer for Angelica protocol responses."""

from __future__ import annotations

import re

from .models import (
    EndTagToken,
    FencedCodeToken,
    InlineCodeToken,
    ProtocolToken,
    SelfClosingTagToken,
    Span,
    StartTagToken,
    TextToken,
)
from .spec import PROTOCOL_SPEC


ATTR_RE = re.compile(r"""([a-zA-Z_][\w\-]*)\s*=\s*(?:"([^"]*)"|'([^']*)')""")


class ProtocolLexer:
    def __init__(self, spec=PROTOCOL_SPEC):
        self.spec = spec

    def lex(self, raw: str) -> tuple[ProtocolToken, ...]:
        text = str(raw or "")
        tokens: list[ProtocolToken] = []
        i = 0
        buffer_start = 0
        length = len(text)

        while i < length:
            if text.startswith("```", i):
                if buffer_start < i:
                    tokens.append(self._text_token(text, buffer_start, i))
                end = self._find_fenced_end(text, i + 3)
                fence_text = text[i:end]
                first_line_end = fence_text.find("\n")
                lang = None
                if first_line_end != -1:
                    head = fence_text[3:first_line_end].strip()
                    lang = head or None
                tokens.append(FencedCodeToken(text=fence_text, lang=lang, span=self._span(text, i, end)))
                i = end
                buffer_start = i
                continue
            if text[i] == "`":
                end = text.find("`", i + 1)
                if end != -1:
                    if buffer_start < i:
                        tokens.append(self._text_token(text, buffer_start, i))
                    end += 1
                    tokens.append(InlineCodeToken(text=text[i:end], span=self._span(text, i, end)))
                    i = end
                    buffer_start = i
                    continue
            if text[i] == "<" and self._is_structural_boundary(text, i):
                tag = self._try_lex_tag(text, i)
                if tag is not None:
                    if buffer_start < i:
                        tokens.append(self._text_token(text, buffer_start, i))
                    if isinstance(tag, StartTagToken) and self.spec.blocks[tag.name].kind == "closed":
                        block_tokens, next_index = self._capture_closed_block(text, tag)
                        tokens.extend(block_tokens)
                        i = next_index
                    else:
                        tokens.append(tag)
                        i = tag.span.end
                    buffer_start = i
                    continue
            i += 1

        if buffer_start < length:
            tokens.append(self._text_token(text, buffer_start, length))
        return tuple(tokens)

    def _find_fenced_end(self, text: str, search_from: int) -> int:
        end = text.find("\n```", search_from)
        if end == -1:
            return len(text)
        return end + 4

    def _is_structural_boundary(self, text: str, index: int) -> bool:
        if index == 0:
            return True
        prev_newline = text.rfind("\n", 0, index)
        prefix = text[prev_newline + 1:index]
        return prefix.strip() == ""

    def _try_lex_tag(self, text: str, index: int) -> ProtocolToken | None:
        close = text.find(">", index + 1)
        if close == -1:
            return None
        raw_tag = text[index + 1:close].strip()
        if not raw_tag:
            return None
        is_end = raw_tag.startswith("/")
        is_self_closing = raw_tag.endswith("/")
        core = raw_tag[1:].strip() if is_end else raw_tag[:-1].strip() if is_self_closing else raw_tag
        if not core:
            return None
        parts = core.split(None, 1)
        name = parts[0].strip().lower()
        if name not in self.spec.blocks:
            return None
        attrs = self._parse_attrs(parts[1] if len(parts) > 1 else "")
        span = self._span(text, index, close + 1)
        if is_end:
            return EndTagToken(name=name, span=span)
        if is_self_closing:
            return SelfClosingTagToken(name=name, attrs=attrs, span=span)
        return StartTagToken(name=name, attrs=attrs, span=span)

    def _capture_closed_block(self, text: str, start_tag: StartTagToken) -> tuple[list[ProtocolToken], int]:
        body_start = start_tag.span.end
        close_text = f"</{start_tag.name}>"
        body_end = text.find(close_text, body_start)
        if body_end == -1:
            return [start_tag], body_start
        end_token = EndTagToken(name=start_tag.name, span=self._span(text, body_end, body_end + len(close_text)))
        return [
            start_tag,
            TextToken(text=text[body_start:body_end], span=self._span(text, body_start, body_end)),
            end_token,
        ], body_end + len(close_text)

    def _parse_attrs(self, raw: str) -> dict[str, str]:
        attrs: dict[str, str] = {}
        for key, v1, v2 in ATTR_RE.findall(raw or ""):
            attrs[str(key).strip().lower()] = str(v1 or v2 or "").strip()
        return attrs

    def _text_token(self, text: str, start: int, end: int) -> TextToken:
        return TextToken(text=text[start:end], span=self._span(text, start, end))

    def _span(self, text: str, start: int, end: int) -> Span:
        excerpt = text[start:end]
        if len(excerpt) > 160:
            excerpt = excerpt[:157] + "..."
        return Span(start=start, end=end, excerpt=excerpt)
