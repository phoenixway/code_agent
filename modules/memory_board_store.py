from __future__ import annotations

import hashlib
import json
import time
from dataclasses import asdict, dataclass, field
from typing import Iterable
from pathlib import Path

ALLOWED_KINDS = ("fact", "finding", "decision", "preference", "progress")
ALLOWED_SCOPES = ("intent", "session", "project")
ACTIVE_STATUSES = ("active", "superseded", "rejected")


@dataclass(slots=True)
class MemoryEntry:
    id: str
    kind: str
    text: str
    scope: str
    intent_id: str | None
    source: str
    status: str
    created_at: float
    updated_at: float
    fingerprint: str
    supersedes: str | None = None
    metadata: dict = field(default_factory=dict)

    def to_dict(self) -> dict:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict) -> "MemoryEntry":
        payload = dict(data or {})
        payload.setdefault("metadata", {})
        return cls(**payload)


class MemoryBoardStore:
    """
    Committed durable memory for the agent.

    Design goals:
    - one source of truth for durable memory entries
    - append-oriented API with controlled superseding
    - scope-aware rendering for system prompt projection
    - deterministic, non-LLM-based prompt view
    """

    def __init__(
        self,
        storage_path: str | None = None,
        *,
        max_entries_total: int = 1200,
        max_entries_per_scope: int = 400,
        max_prompt_entries_per_scope: int = 12,
        max_prompt_progress_entries: int = 8,
        max_entry_text_chars: int = 500,
    ) -> None:
        self.storage_path = storage_path
        self.max_entries_total = max(100, int(max_entries_total))
        self.max_entries_per_scope = max(50, int(max_entries_per_scope))
        self.max_prompt_entries_per_scope = max(3, int(max_prompt_entries_per_scope))
        self.max_prompt_progress_entries = max(3, int(max_prompt_progress_entries))
        self.max_entry_text_chars = max(80, int(max_entry_text_chars))

        self._entries: list[MemoryEntry] = []
        self._index_by_id: dict[str, MemoryEntry] = {}
        self._index_by_fingerprint: dict[str, str] = {}

        if self.storage_path:
            self.load()

    # ----------------------------
    # Persistence
    # ----------------------------

    def load(self) -> None:
        if not self.storage_path:
            return
        path = Path(self.storage_path)
        if not path.exists():
            return
        raw = json.loads(path.read_text(encoding="utf-8"))
        items = raw.get("entries", [])
        self._entries = []
        self._index_by_id = {}
        self._index_by_fingerprint = {}
        for item in items:
            entry = MemoryEntry.from_dict(item)
            self._entries.append(entry)
            self._index_by_id[entry.id] = entry
            if entry.status == "active":
                self._index_by_fingerprint[entry.fingerprint] = entry.id

    def save(self) -> None:
        if not self.storage_path:
            return
        path = Path(self.storage_path)
        path.parent.mkdir(parents=True, exist_ok=True)
        payload = {
            "version": 1,
            "saved_at": time.time(),
            "entries": [entry.to_dict() for entry in self._entries],
        }
        path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")

    # ----------------------------
    # Helpers
    # ----------------------------

    def _normalize_kind(self, value: str) -> str:
        return str(value or "").strip().lower()

    def _normalize_scope(self, value: str) -> str:
        return str(value or "").strip().lower()

    def _normalize_text(self, value: str) -> str:
        text = str(value or "").strip()
        text = " ".join(text.split())
        if len(text) > self.max_entry_text_chars:
            text = text[: self.max_entry_text_chars].rstrip() + "…"
        return text

    def _normalize_intent_id(self, value: str | None) -> str | None:
        if value is None:
            return None
        text = str(value).strip()
        return text or None

    def _make_fingerprint(self, *, kind: str, scope: str, text: str, intent_id: str | None) -> str:
        core = f"{kind}|{scope}|{intent_id or '-'}|{text.lower()}"
        return hashlib.sha256(core.encode("utf-8")).hexdigest()[:24]

    def _new_entry_id(self, fingerprint: str) -> str:
        stamp = f"{time.time_ns()}|{fingerprint}"
        return "mb_" + hashlib.sha256(stamp.encode("utf-8")).hexdigest()[:16]

    def _check_invariants(self, *, kind: str, scope: str, text: str) -> None:
        if kind not in ALLOWED_KINDS:
            raise ValueError(f"Unsupported memory kind: {kind}")
        if scope not in ALLOWED_SCOPES:
            raise ValueError(f"Unsupported memory scope: {scope}")
        if not text:
            raise ValueError("Memory entry text must not be empty")

    def _trim_if_needed(self) -> None:
        if len(self._entries) <= self.max_entries_total:
            return

        protected_ids = {
            entry.id
            for entry in self._entries
            if entry.status == "active" and entry.scope in {"project", "session"}
        }
        protected_ids.update(
            entry.id
            for entry in self._entries[-self.max_prompt_progress_entries :]
            if entry.kind == "progress" and entry.status == "active"
        )

        survivors: list[MemoryEntry] = []
        for entry in reversed(self._entries):
            if len(survivors) >= self.max_entries_total:
                break
            if entry.id in protected_ids or entry.status != "active":
                survivors.append(entry)
                continue
            survivors.append(entry)

        survivors.reverse()
        self._entries = survivors
        self._rebuild_indexes()

    def _enforce_per_scope_limits(self) -> None:
        active_by_scope: dict[str, list[MemoryEntry]] = {scope: [] for scope in ALLOWED_SCOPES}
        for entry in self._entries:
            if entry.status == "active":
                active_by_scope[entry.scope].append(entry)

        to_supersede: list[MemoryEntry] = []
        for scope, items in active_by_scope.items():
            overflow = len(items) - self.max_entries_per_scope
            if overflow > 0:
                to_supersede.extend(items[:overflow])

        if not to_supersede:
            return

        now = time.time()
        for entry in to_supersede:
            entry.status = "superseded"
            entry.updated_at = now

        self._rebuild_indexes()

    def _rebuild_indexes(self) -> None:
        self._index_by_id = {}
        self._index_by_fingerprint = {}
        for entry in self._entries:
            self._index_by_id[entry.id] = entry
            if entry.status == "active":
                self._index_by_fingerprint[entry.fingerprint] = entry.id

    # ----------------------------
    # Public API
    # ----------------------------

    def add_entry(
        self,
        *,
        kind: str,
        text: str,
        scope: str,
        intent_id: str | None = None,
        source: str = "runtime",
        metadata: dict | None = None,
    ) -> tuple[bool, MemoryEntry, str]:
        """
        Returns:
            (created_new, entry, reason)
            reason in {"created", "duplicate"}
        """
        kind_n = self._normalize_kind(kind)
        scope_n = self._normalize_scope(scope)
        text_n = self._normalize_text(text)
        intent_n = self._normalize_intent_id(intent_id)
        self._check_invariants(kind=kind_n, scope=scope_n, text=text_n)

        fingerprint = self._make_fingerprint(
            kind=kind_n,
            scope=scope_n,
            text=text_n,
            intent_id=intent_n if scope_n == "intent" else None,
        )

        existing_id = self._index_by_fingerprint.get(fingerprint)
        if existing_id:
            existing = self._index_by_id[existing_id]
            return False, existing, "duplicate"

        now = time.time()
        entry = MemoryEntry(
            id=self._new_entry_id(fingerprint),
            kind=kind_n,
            text=text_n,
            scope=scope_n,
            intent_id=intent_n if scope_n == "intent" else None,
            source=str(source or "runtime").strip() or "runtime",
            status="active",
            created_at=now,
            updated_at=now,
            fingerprint=fingerprint,
            metadata=dict(metadata or {}),
        )
        self._entries.append(entry)
        self._index_by_id[entry.id] = entry
        self._index_by_fingerprint[fingerprint] = entry.id

        self._enforce_per_scope_limits()
        self._trim_if_needed()
        self.save()
        return True, entry, "created"

    def supersede_entry(
        self,
        entry_id: str,
        *,
        replacement_text: str | None = None,
        source: str = "runtime",
        metadata: dict | None = None,
    ) -> tuple[bool, MemoryEntry | None, MemoryEntry | None]:
        """
        Supersedes an active entry. Optionally creates a replacement entry
        of the same kind/scope/intent.
        Returns: (changed, old_entry, new_entry)
        """
        entry = self._index_by_id.get(str(entry_id or "").strip())
        if entry is None or entry.status != "active":
            return False, None, None

        now = time.time()
        entry.status = "superseded"
        entry.updated_at = now
        self._rebuild_indexes()

        replacement = None
        if replacement_text:
            _, replacement, _ = self.add_entry(
                kind=entry.kind,
                text=replacement_text,
                scope=entry.scope,
                intent_id=entry.intent_id,
                source=source,
                metadata={
                    **dict(entry.metadata or {}),
                    **dict(metadata or {}),
                    "supersedes": entry.id,
                },
            )
            if replacement is not None:
                replacement.supersedes = entry.id

        self.save()
        return True, entry, replacement

    def entries(
        self,
        *,
        status: str | None = "active",
        scope: str | None = None,
        kind: str | None = None,
        intent_id: str | None = None,
        newest_first: bool = False,
    ) -> list[MemoryEntry]:
        items = self._entries[:]
        if status is not None:
            items = [e for e in items if e.status == status]
        if scope is not None:
            scope_n = self._normalize_scope(scope)
            items = [e for e in items if e.scope == scope_n]
        if kind is not None:
            kind_n = self._normalize_kind(kind)
            items = [e for e in items if e.kind == kind_n]
        if intent_id is not None:
            wanted = self._normalize_intent_id(intent_id)
            items = [e for e in items if e.intent_id == wanted]
        if newest_first:
            items.reverse()
        return items

    def entries_for_intent_lineage(
        self,
        intent_ids: list[str] | tuple[str, ...] | set[str] | None,
        *,
        status: str | None = "active",
        kind: str | None = None,
        newest_first: bool = False,
    ) -> list[MemoryEntry]:
        wanted = []
        for value in list(intent_ids or []):
            normalized = self._normalize_intent_id(value)
            if normalized and normalized not in wanted:
                wanted.append(normalized)
        if not wanted:
            return []

        items = self.entries(status=status, scope="intent", kind=kind, newest_first=False)
        ranked: list[tuple[int, int, MemoryEntry]] = []
        order = {intent_id: idx for idx, intent_id in enumerate(wanted)}
        for pos, entry in enumerate(items):
            if entry.intent_id not in order:
                continue
            ranked.append((order[entry.intent_id], pos, entry))

        ranked.sort(key=lambda item: (item[0], item[1]), reverse=False)
        out = [entry for _, _, entry in ranked]
        if newest_first:
            out.reverse()
        return out

    def inherit_intent_scope(
        self,
        *,
        from_intent_id: str | None,
        to_intent_id: str | None,
        lineage_id: str | None = None,
        source: str = "runtime",
    ) -> int:
        from_id = self._normalize_intent_id(from_intent_id)
        to_id = self._normalize_intent_id(to_intent_id)
        if not from_id or not to_id or from_id == to_id:
            return 0

        inherited = 0
        for entry in self.entries(status="active", scope="intent", intent_id=from_id, newest_first=False):
            metadata = dict(entry.metadata or {})
            metadata.setdefault("inherited_from_intent_id", from_id)
            if lineage_id:
                metadata.setdefault("lineage_id", str(lineage_id).strip())
            metadata["inherited_to_intent_id"] = to_id
            created, _, reason = self.add_entry(
                kind=entry.kind,
                text=entry.text,
                scope="intent",
                intent_id=to_id,
                source=source,
                metadata=metadata,
            )
            if created or reason == "created":
                inherited += 1
        if inherited:
            self.save()
        return inherited

    def get_entry(self, entry_id: str) -> MemoryEntry | None:
        return self._index_by_id.get(str(entry_id or "").strip())

    def clear_intent_scope(self, intent_id: str) -> int:
        wanted = self._normalize_intent_id(intent_id)
        if not wanted:
            return 0
        changed = 0
        now = time.time()
        for entry in self._entries:
            if entry.status == "active" and entry.scope == "intent" and entry.intent_id == wanted:
                entry.status = "superseded"
                entry.updated_at = now
                changed += 1
        if changed:
            self._rebuild_indexes()
            self.save()
        return changed

    def clear_scopes(self, *scopes: str) -> int:
        wanted_scopes = {
            self._normalize_scope(scope)
            for scope in scopes
            if self._normalize_scope(scope) in ALLOWED_SCOPES
        }
        if not wanted_scopes:
            return 0

        changed = 0
        now = time.time()
        for entry in self._entries:
            if entry.status == "active" and entry.scope in wanted_scopes:
                entry.status = "superseded"
                entry.updated_at = now
                changed += 1

        if changed:
            self._rebuild_indexes()
            self.save()
        return changed

    def reset_for_new_session(self) -> int:
        """
        Preserve durable project memory across launches, but clear session and
        intent scopes so a new agent session starts with no carried-over
        session-local or intent-local memory.
        """
        return self.clear_scopes("session", "intent")

    def export_dict(self) -> dict:
        return {
            "version": 1,
            "entries": [entry.to_dict() for entry in self._entries],
        }

    # ----------------------------
    # Prompt projection
    # ----------------------------

    def _render_scope_block(
        self,
        title: str,
        entries: Iterable[MemoryEntry],
        *,
        max_items: int,
    ) -> list[str]:
        lines = [f"[{title}]"]
        count = 0
        for entry in entries:
            if count >= max_items:
                break
            suffix = ""
            if entry.scope == "intent" and entry.intent_id:
                suffix = f" (intent={entry.intent_id})"
            lines.append(f"- {entry.kind}{suffix}: {entry.text}")
            count += 1
        if count == 0:
            lines.append("- none")
        return lines

    def to_system_prompt(
        self,
        active_intent_id: str | None = None,
        *,
        lineage_intent_ids: list[str] | tuple[str, ...] | set[str] | None = None,
    ) -> str:
        """
        Deterministic committed-memory projection for model context.
        Prefer exact active intent entries first, but allow same-lineage fallback
        so that legitimate replace transitions do not appear memory-empty after
        summarization.
        """
        normalized_active_intent_id = self._normalize_intent_id(active_intent_id)
        ordered_lineage_ids: list[str] = []
        for value in list(lineage_intent_ids or []):
            normalized = self._normalize_intent_id(value)
            if normalized and normalized not in ordered_lineage_ids:
                ordered_lineage_ids.append(normalized)
        if normalized_active_intent_id and normalized_active_intent_id not in ordered_lineage_ids:
            ordered_lineage_ids.insert(0, normalized_active_intent_id)

        if ordered_lineage_ids:
            intent_entries = self.entries_for_intent_lineage(
                ordered_lineage_ids,
                status="active",
                newest_first=False,
            )
        else:
            intent_entries = []
        session_entries = self.entries(status="active", scope="session")
        project_entries = self.entries(status="active", scope="project")

        intent_progress = [e for e in intent_entries if e.kind == "progress"]
        intent_core = [e for e in intent_entries if e.kind != "progress"]

        lines = [
            "## MEMORY BOARD",
            "Committed durable memory extracted from prior execution.",
            "Treat these entries as higher priority than compressed narrative history.",
            "Do not silently contradict them; explicitly correct them only with new evidence.",
            "",
        ]

        lines.extend(
            self._render_scope_block(
                "PROJECT MEMORY",
                project_entries[-self.max_prompt_entries_per_scope :],
                max_items=self.max_prompt_entries_per_scope,
            )
        )
        lines.append("")
        lines.extend(
            self._render_scope_block(
                "SESSION MEMORY",
                session_entries[-self.max_prompt_entries_per_scope :],
                max_items=self.max_prompt_entries_per_scope,
            )
        )
        lines.append("")
        lines.extend(
            self._render_scope_block(
                "CURRENT INTENT MEMORY",
                intent_core[-self.max_prompt_entries_per_scope :],
                max_items=self.max_prompt_entries_per_scope,
            )
        )
        lines.append("")
        lines.extend(
            self._render_scope_block(
                "CURRENT INTENT PROGRESS LOG",
                intent_progress[-self.max_prompt_progress_entries :],
                max_items=self.max_prompt_progress_entries,
            )
        )

        return "\n".join(lines)
