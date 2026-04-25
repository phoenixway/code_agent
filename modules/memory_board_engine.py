from __future__ import annotations

import logging
import re
from dataclasses import dataclass, field

from .memory_board_store import ALLOWED_KINDS, ALLOWED_SCOPES, MemoryBoardStore, MemoryEntry


TAG_NAMES = "|".join(ALLOWED_KINDS)
TAG_RE = re.compile(
    rf"<(?P<kind>{TAG_NAMES})\b(?P<attrs>[^>]*?)(?:>(?P<body>.*?)</(?P=kind)>|/>)",
    re.IGNORECASE | re.DOTALL,
)
ATTR_RE = re.compile(r"""([a-zA-Z_][\w\-]*)\s*=\s*(?:"([^"]*)"|'([^']*)')""")


@dataclass(slots=True)
class ParsedMemoryTag:
    kind: str
    text: str
    scope: str
    attrs: dict
    raw: str


@dataclass(slots=True)
class MemoryBoardCommit:
    accepted: bool
    reason: str
    tag: ParsedMemoryTag
    entry: MemoryEntry | None = None
    normalized_scope: str | None = None


@dataclass(slots=True)
class MemoryBoardApplyResult:
    clean_text: str
    parsed_count: int = 0
    accepted_count: int = 0
    rejected_count: int = 0
    commits: list[MemoryBoardCommit] = field(default_factory=list)

    @property
    def accepted_entries(self) -> list[MemoryEntry]:
        return [item.entry for item in self.commits if item.accepted and item.entry is not None]


class MemoryBoardEngine:
    """
    Parses inline durable-memory tags from model text and commits validated
    entries into MemoryBoardStore.

    Philosophy:
    - model proposes through inline tags
    - runtime validates and commits
    - store remains the single source of truth
    """

    def __init__(
        self,
        store: MemoryBoardStore,
        *,
        logger=None,
        max_tag_text_chars: int = 500,
        max_tags_per_message: int = 12,
    ) -> None:
        self.store = store
        self.log = logger or logging.getLogger("debug")
        self.max_tag_text_chars = max(80, int(max_tag_text_chars))
        self.max_tags_per_message = max(1, int(max_tags_per_message))

    # ----------------------------
    # Public API
    # ----------------------------

    def parse_tags(self, response_text: str) -> tuple[str, list[ParsedMemoryTag]]:
        if not isinstance(response_text, str) or not response_text:
            return response_text, []

        matches = list(TAG_RE.finditer(response_text))
        if not matches:
            return response_text, []

        tags: list[ParsedMemoryTag] = []
        for match in matches[: self.max_tags_per_message]:
            kind = str(match.group("kind") or "").strip().lower()
            attrs = self._parse_attrs(match.group("attrs") or "")
            body_raw = match.group("body")
            body = self._normalize_text(body_raw or "")
            if not body:
                body = self._normalize_text(attrs.get("text") or "")
                if body and self.log:
                    self.log.debug(
                        "memory_tag_parser_fallback=xml_attributes kind=%s scope=%s",
                        kind,
                        str(attrs.get("scope") or "").strip().lower(),
                    )
            scope = str(attrs.get("scope") or "").strip().lower()
            tags.append(
                ParsedMemoryTag(
                    kind=kind,
                    text=body,
                    scope=scope,
                    attrs=attrs,
                    raw=match.group(0),
                )
            )

        clean_text = TAG_RE.sub("", response_text)
        clean_text = re.sub(r"\n{3,}", "\n\n", clean_text).strip()
        return clean_text, tags

    def apply_response_text(
        self,
        response_text: str,
        *,
        active_intent_id: str | None = None,
        current_user_input: str = "",
        source: str = "model",
    ) -> MemoryBoardApplyResult:
        clean_text, tags = self.parse_tags(response_text)
        result = MemoryBoardApplyResult(clean_text=clean_text, parsed_count=len(tags))

        if self.log:
            self.log.debug(
                "MemoryBoard.apply_response_text source=%s active_intent_id=%s parsed_tags=%s response_chars=%s clean_chars=%s",
                source,
                active_intent_id or "",
                len(tags),
                len(response_text or ""),
                len(clean_text or ""),
            )
            if tags:
                for idx, tag in enumerate(tags, start=1):
                    self.log.debug(
                        "MemoryBoard.tag[%s] kind=%s scope=%s attrs=%s text=%s raw=%s",
                        idx,
                        tag.kind,
                        tag.scope,
                        tag.attrs,
                        tag.text,
                        tag.raw,
                    )

        for tag in tags:
            commit = self._commit_tag(
                tag,
                active_intent_id=active_intent_id,
                current_user_input=current_user_input,
                source=source,
            )
            result.commits.append(commit)
            if commit.accepted:
                result.accepted_count += 1
            else:
                result.rejected_count += 1
            if self.log:
                self.log.debug(
                    "MemoryBoard.commit kind=%s accepted=%s reason=%s normalized_scope=%s entry=%s",
                    tag.kind,
                    commit.accepted,
                    commit.reason,
                    commit.normalized_scope,
                    getattr(commit.entry, "text", None),
                )

        if self.log and tags:
            self.log.debug("MemoryBoard.clean_text\n%s", clean_text)

        return result

    # ----------------------------
    # Commit rules
    # ----------------------------

    def _commit_tag(
        self,
        tag: ParsedMemoryTag,
        *,
        active_intent_id: str | None,
        current_user_input: str,
        source: str,
    ) -> MemoryBoardCommit:
        normalized_scope = self._normalize_scope(tag.scope)

        if tag.kind not in ALLOWED_KINDS:
            return MemoryBoardCommit(False, "unsupported_kind", tag, normalized_scope=normalized_scope or None)

        if not normalized_scope:
            return MemoryBoardCommit(False, "missing_scope", tag)

        if normalized_scope not in ALLOWED_SCOPES:
            return MemoryBoardCommit(False, "unsupported_scope", tag, normalized_scope=normalized_scope)

        if not tag.text:
            return MemoryBoardCommit(False, "empty_text", tag, normalized_scope=normalized_scope)

        if len(tag.text) > self.max_tag_text_chars:
            return MemoryBoardCommit(False, "text_too_long", tag, normalized_scope=normalized_scope)

        if self._looks_low_value(tag):
            return MemoryBoardCommit(False, "low_value_entry", tag, normalized_scope=normalized_scope)

        if tag.kind == "progress":
            if normalized_scope != "intent":
                return MemoryBoardCommit(False, "progress_must_use_intent_scope", tag, normalized_scope=normalized_scope)
            if not active_intent_id:
                return MemoryBoardCommit(False, "no_active_intent_for_progress", tag, normalized_scope=normalized_scope)

        if normalized_scope == "intent" and not active_intent_id:
            return MemoryBoardCommit(False, "intent_scope_without_active_intent", tag, normalized_scope=normalized_scope)

        effective_scope = self._downgrade_scope_if_needed(
            tag,
            normalized_scope=normalized_scope,
            current_user_input=current_user_input,
        )

        try:
            created, entry, reason = self.store.add_entry(
                kind=tag.kind,
                text=tag.text,
                scope=effective_scope,
                intent_id=active_intent_id if effective_scope == "intent" else None,
                source=source,
                metadata={"attrs": tag.attrs},
            )
        except Exception as exc:
            if self.log:
                self.log.warning("MemoryBoardEngine commit failed: %s", exc)
            return MemoryBoardCommit(False, "store_error", tag, normalized_scope=effective_scope)

        accepted_reason = "created" if created else reason
        return MemoryBoardCommit(True, accepted_reason, tag, entry=entry, normalized_scope=effective_scope)

    # ----------------------------
    # Validation helpers
    # ----------------------------

    def _parse_attrs(self, attrs_raw: str) -> dict:
        attrs = {}
        if not isinstance(attrs_raw, str) or not attrs_raw.strip():
            return attrs
        cleaned = attrs_raw.strip()
        if cleaned.endswith("/"):
            cleaned = cleaned[:-1].rstrip()
        for key, v1, v2 in ATTR_RE.findall(cleaned):
            attrs[str(key).strip().lower()] = str(v1 or v2 or "").strip()
        return attrs

    def _normalize_scope(self, value: str) -> str:
        return str(value or "").strip().lower()

    def _normalize_text(self, value: str) -> str:
        text = str(value or "").strip()
        text = " ".join(text.split())
        return text

    def _has_concrete_anchor(self, text: str) -> bool:
        if re.search(r"\bline\s+\d+\b", text):
            return True
        if re.search(r"\b(lines?|ряд(ок|ки|ків))\s+\d+", text):
            return True
        if ".kt" in text or ".py" in text or ".java" in text:
            return True
        if "`" in text:
            return True
        concrete_words = (
            "located", "found", "identified", "implementation", "function", "method",
            "class", "composable", "symbol", "path", "chunk", "skeleton",
            "line ", "ряд", "знайден", "виявлен", "локаліз", "реалізаці", "метод", "функц", "кнопк",
        )
        return any(word in text for word in concrete_words)

    def _looks_like_path_content(self, text: str) -> bool:
        value = str(text or "").strip()
        if not value:
            return False
        if "/" in value or "\\" in value:
            return True
        if re.search(r"\.[a-zA-Z0-9]{1,8}(?::\d+)?\b", value):
            return True
        return False

    def _looks_like_plan_content(self, text: str) -> bool:
        lowered = str(text or "").lower().strip()
        if not lowered:
            return False

        plan_prefixes = (
            "plan to ",
            "next i will ",
            "next step ",
            "next steps ",
            "remaining steps ",
            "todo: ",
            "to do: ",
            "subgoal ",
            "subgoals ",
            "create subgoal ",
            "mark subgoal ",
            "need to ",
            "should now ",
            "i should now ",
        )
        if any(lowered.startswith(prefix) for prefix in plan_prefixes):
            return True

        plan_fragments = (
            "<subgoal",
            "action=\"create\"",
            "action=\"modify\"",
            "action=\"mark_done\"",
            "action=\"mark_blocked\"",
            "action=\"remove\"",
            "action=\"reorder\"",
            "todo list",
            "remaining tasks",
            "plan board",
            "subgoal board",
            "next action",
            "next actions",
            "next step is",
            "steps left",
        )
        return any(fragment in lowered for fragment in plan_fragments)

    def _looks_low_value(self, tag: ParsedMemoryTag) -> bool:
        text = tag.text.lower().strip()

        if len(text) < 12:
            return True

        if tag.kind == "path":
            return not self._looks_like_path_content(tag.text)

        if self._looks_like_plan_content(text):
            return True

        routine_prefixes = (
            "read file ",
            "read chunk ",
            "opened file ",
            "ran grep ",
            "ran rg ",
            "searched ",
            "listed directory ",
            "continued investigation",
            "continued work",
            "made progress",
            "did analysis",
        )

        if tag.kind != "progress":
            if any(text.startswith(prefix) for prefix in routine_prefixes):
                return True
            return False

        if self._has_concrete_anchor(text):
            return False

        generic_progress_starts = (
            "continuing investigation",
            "continuing work",
            "proceeding to",
            "starting investigation",
            "executing ",
            "reading ",
            "searching ",
            "examining ",
            "looking for ",
            "checking ",
            "working on ",
            "moving to ",
        )
        if any(text.startswith(prefix) for prefix in generic_progress_starts):
            return True

        bad_fragments = (
            "read file",
            "read chunk",
            "ran command",
            "used search",
            "listed files",
            "continued investigating",
            "continued working",
        )
        if any(fragment in text for fragment in bad_fragments) and not self._has_concrete_anchor(text):
            return True

        return False

    def _downgrade_scope_if_needed(
        self,
        tag: ParsedMemoryTag,
        *,
        normalized_scope: str,
        current_user_input: str,
    ) -> str:
        text = tag.text.lower()

        if normalized_scope == "project":
            if tag.kind in {"preference", "progress"}:
                return "session"
            local_markers = (
                "this conversation",
                "for this session",
                "у цій сесії",
                "у цій розмові",
                "for now",
                "temporarily",
                "тимчасово",
            )
            if any(marker in text for marker in local_markers):
                return "session"

        if normalized_scope == "session" and tag.kind == "progress":
            return "intent"

        if normalized_scope == "intent" and tag.kind in {"preference"}:
            if "user" in text or "користувач" in text:
                return "session"

        return normalized_scope
