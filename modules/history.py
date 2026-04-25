
"""
modules/history.py

History manager with pressure-aware working material protection and unified
artifact degradation for both protected working material and ordinary tool-heavy
history.

Key rules:
- tool returns may be stored as generic working material
- protection is short-lived but pressure-aware, not hop-driven
- heavy artifacts degrade in stages using unified material degradation helpers
- the same degradation primitives are used for working material and ordinary
  structured history under context pressure
- simple plain-text messages are not pressure-compacted
- get_history_for_api avoids duplicating the same read_file payload through both
  CURRENT FILE STATE and protected working material
"""

import hashlib
import json
import time
from pathlib import Path

from modules.code_parser import CodeParser
from modules.history_materials import HistoryMaterialTools


class HistoryManager:
    def __init__(
        self,
        chat_provider,
        logger=None,
        max_tokens=4000,
        storage_dir=".angelica",
        window_size=50,
        autosummarize_requires_confirmation=False,
    ):
        self.chat = chat_provider
        self.logger = logger
        self.max_tokens = max_tokens
        self.window_size = window_size
        self.autosummarize_requires_confirmation = autosummarize_requires_confirmation

        self.storage_root = Path(storage_dir)
        self.blobs_dir = self.storage_root / "blobs"
        self.blobs_dir.mkdir(parents=True, exist_ok=True)

        self.messages = []
        self.files = {}
        self.active_files = set()
        self.code_parser = CodeParser()

        self.SKELETON_THRESHOLD = 2000
        self.MAX_ACTIVE_FILES = 5

        self.SUMMARY_PROMPT_RATIO = 0.82
        self.SUMMARY_PROMPT_COOLDOWN_MIN = 200
        self.EMERGENCY_SUMMARY_RATIO = 0.95
        self.EMERGENCY_SUMMARY_COOLDOWN_MIN = 500
        self.SUMMARY_TARGET_RATIO = 0.5
        self.SUMMARY_MIN_INTERVAL_SEC = 45
        self.SUMMARY_MIN_TOKEN_GROWTH = max(256, self.max_tokens // 16)
        self.disable_summary_prompts = False

        self._next_summary_prompt_tokens = int(self.max_tokens * self.SUMMARY_PROMPT_RATIO)
        self._next_emergency_summary_tokens = int(self.max_tokens * self.EMERGENCY_SUMMARY_RATIO)
        self._last_summary_at = 0.0
        self._last_summary_tokens = 0
        self._observe_summary_deferrals_remaining = 0
        self._last_summary_execution_snapshot = ""

        self.MAX_STRUCTURED_TEXT_CHARS = 2500
        self.MAX_STRUCTURED_STDOUT_CHARS = 1200
        self.MAX_STRUCTURED_STDERR_CHARS = 800
        self.MAX_STRUCTURED_OUTPUT_LINES = 40
        self.LARGE_RESULT_COUNT_HINT = 80

        self.current_turn_id = 0
        self.TURN_WORKING_MATERIAL_SAFE_RATIO = 0.72

        # Pressure-aware working material policy.
        self.WM_DEFAULT_HOPS = 1
        self.WM_SHELL_HOPS = 2
        self.WM_MAX_PROTECTED_ITEMS = 6
        self.WM_MAX_FULL_FILE_ITEMS = 1
        self.WM_PROTECTED_RESERVE_RATIO = 0.12
        self.WM_MIN_PROTECTED_TOKENS = 160
        self.WM_MAX_PROTECTED_SHARE_RATIO = 0.34
        self._wm_seq = 0

        # Ordinary structured history pressure policy.
        self.ORDINARY_PRESSURE_TRIGGER_RATIO = 0.74
        self.ORDINARY_PRESSURE_TARGET_RATIO = 0.64
        self.ORDINARY_MAX_DEGRADED_PER_PASS = 6

        # Canonical durable memory is kept outside history.messages and
        # injected only into summarization as a separate reference block.
        self.memory_board_store = None

        self.material_tools = HistoryMaterialTools(
            code_parser=self.code_parser,
            max_structured_text_chars=self.MAX_STRUCTURED_TEXT_CHARS,
            max_structured_stdout_chars=self.MAX_STRUCTURED_STDOUT_CHARS,
            max_structured_stderr_chars=self.MAX_STRUCTURED_STDERR_CHARS,
            max_structured_output_lines=self.MAX_STRUCTURED_OUTPUT_LINES,
            large_result_count_hint=self.LARGE_RESULT_COUNT_HINT,
        )

    def _next_wm_seq(self) -> int:
        self._wm_seq += 1
        return self._wm_seq

    def _save_blob(self, content: str) -> str | None:
        if not content:
            return None
        content_bytes = content.encode("utf-8")
        blob_hash = hashlib.sha256(content_bytes).hexdigest()
        blob_path = self.blobs_dir / blob_hash
        self.blobs_dir.mkdir(parents=True, exist_ok=True)
        if not blob_path.exists():
            blob_path.write_bytes(content_bytes)
        return blob_hash

    def _load_blob(self, blob_hash: str) -> str:
        if not blob_hash:
            return ""
        blob_path = self.blobs_dir / blob_hash
        if not blob_path.exists():
            return ""
        try:
            return blob_path.read_bytes().decode("utf-8")
        except Exception as e:
            if self.logger:
                self.logger.error(f"Blob load error {blob_hash}: {e}")
            return ""

    def set_memory_board_store(self, store) -> None:
        self.memory_board_store = store

    def _build_active_intent_summary_block(self, state=None) -> str:
        active_intent = getattr(state, "active_intent", None) if state is not None else None
        if active_intent is None:
            return ""
        lines = [
            "## ACTIVE INTENT BOARD",
            "Canonical runtime state. Do not summarize, rewrite, or absorb this board into narrative history.",
            f"intent_id: {str(getattr(active_intent, 'intent_id', '') or '').strip() or '<none>'}",
            f"intent_type: {str(getattr(active_intent, 'intent_type', '') or '').strip() or '<none>'}",
            f"goal: {str(getattr(active_intent, 'goal', '') or '').strip() or '<none>'}",
            f"safe_steps_limit: {int(getattr(active_intent, 'safe_steps_limit', 0) or 0)}",
            f"steps_used: {int(getattr(active_intent, 'step_count', 0) or 0)}",
            f"retry_limit: {int(getattr(active_intent, 'retry_limit', 0) or 0)}",
            f"retry_count: {int(getattr(active_intent, 'retry_count', 0) or 0)}",
        ]
        return "\n".join(lines)

    def _build_plan_board_summary_block(self, state=None) -> str:
        board = getattr(state, "task_board", None) if state is not None else None
        if not isinstance(board, dict) or not board.get("steps"):
            return ""
        lines = [
            "## CURRENT PLAN BOARD (CANONICAL)",
            "Canonical runtime state. Do not summarize, rewrite, or absorb this board into narrative history.",
            f"goal: {str(board.get('goal', '') or '').strip() or '<none>'}",
            f"active_step_id: {str(board.get('active_step_id', '') or '').strip() or '-'}",
        ]
        for step in (board.get("steps") or []):
            if not isinstance(step, dict):
                continue
            sid = str(step.get("id", "") or "").strip() or "?"
            status = str(step.get("status", "") or "todo").strip() or "todo"
            title = str(step.get("title", "") or "").strip()
            lines.append(f"- {sid} [{status}] {title[:160]}")
        return "\n".join(lines)

    def _build_memory_board_summary_block(self, state=None) -> str:
        board = self.memory_board_store
        if board is None or not hasattr(board, "to_system_prompt"):
            return ""
        active_intent = getattr(state, "active_intent", None) if state is not None else None
        active_intent_id = getattr(active_intent, "intent_id", None) if active_intent is not None else None
        lineage_intent_ids: list[str] = []
        runtime = getattr(state, "intent_runtime", None) if state is not None else None
        getter = getattr(runtime, "get_active_intent_lineage_ids", None)
        if callable(getter):
            try:
                for value in getter() or []:
                    text = str(value or "").strip()
                    if text and text not in lineage_intent_ids:
                        lineage_intent_ids.append(text)
            except Exception:
                pass
        if not lineage_intent_ids:
            for value in (
                active_intent_id,
                getattr(state, "last_resumable_intent_id", None) if state is not None else None,
                getattr(state, "last_resumable_intent_lineage_id", None) if state is not None else None,
            ):
                text = str(value or "").strip()
                if text and text not in lineage_intent_ids:
                    lineage_intent_ids.append(text)
        try:
            text = board.to_system_prompt(
                active_intent_id=active_intent_id,
                lineage_intent_ids=lineage_intent_ids,
            )
            return text.strip() if isinstance(text, str) else ""
        except Exception as e:
            if self.logger:
                self.logger.warning("Memory board prompt build failed: %s", e)
            return ""

    def add_message(self, role, content, msg_type=None, **meta):
        if msg_type is None:
            if content is None:
                return
            if isinstance(content, str) and not content.strip():
                return

        final_content = content
        preserve_exact = bool(meta.get("turn_working_material", False))

        if role == "assistant" and isinstance(content, str):
            final_content = self._compress_assistant_tool_call(content)
            final_content = self._sanitize_action_blocks_for_history(final_content)

        if isinstance(final_content, (dict, list)) and not preserve_exact:
            final_content = self.material_tools.compact_structured_message_content(final_content)

        message = {"role": role, "content": final_content}
        if msg_type:
            message["type"] = msg_type
        message.update(meta)

        if isinstance(final_content, dict):
            message.setdefault("history_material_kind", self.material_tools.material_kind(final_content))
            message.setdefault("history_degrade_stage", 0)
            message.setdefault("history_added_seq", self._next_wm_seq())
        self.messages.append(message)

        if not preserve_exact:
            self._enforce_ordinary_history_pressure()

        if self.logger:
            preview = str(final_content)[:80].replace("\n", " ")
            self.logger.debug(
                "History+ (%s): type=%s turn=%s working=%s %s...",
                role,
                message.get("type", "plain"),
                message.get("turn_id", "-"),
                bool(message.get("turn_working_material")),
                preview,
            )

    def _compress_assistant_tool_call(self, content: str) -> str:
        try:
            if content.strip().startswith('{') and ('"content"' in content or '"file_content"' in content):
                data = json.loads(content)
                action = data.get("type") or data.get("action")
                body = data.get("content")
                field_name = "content"
                if not isinstance(body, str):
                    body = data.get("file_content")
                    field_name = "file_content"
                if action in ["create_file", "write_file", "write_file_block", "append_file_block", "edit_file", "replace"] and isinstance(body, str):
                    if isinstance(body, str) and len(body) > 200:
                        blob_hash = self._save_blob(body)
                        data.pop("content", None)
                        data.pop("file_content", None)
                        data[f"{field_name}_redacted"] = True
                        data[f"{field_name}_size"] = len(body)
                        data[f"{field_name}_blob_hash"] = blob_hash
                        return json.dumps(data, ensure_ascii=False)
        except Exception:
            pass
        return content

    def _sanitize_action_blocks_for_history(self, content: str) -> str:
        import re
        if not isinstance(content, str) or "<action" not in content:
            return content

        def _replace(match):
            action_type = (match.group(1) or "").strip().lower()
            body = match.group(2).strip()
            try:
                data = json.loads(body)
            except Exception:
                return match.group(0)
            if action_type in {"create_file", "write_file", "write_file_block", "append_file_block", "edit_file", "replace"} and isinstance(data, dict):
                payload = data.get("content")
                field_name = "content"
                if not isinstance(payload, str):
                    payload = data.get("file_content")
                    field_name = "file_content"
                if isinstance(payload, str) and len(payload) > 200:
                    blob_hash = self._save_blob(payload)
                    data.pop("content", None)
                    data.pop("file_content", None)
                    data[f"{field_name}_redacted"] = True
                    data[f"{field_name}_size"] = len(payload)
                    data[f"{field_name}_blob_hash"] = blob_hash
                    return f'<action type="{action_type}">\n{json.dumps(data, ensure_ascii=False, indent=2)}\n</action>'
            return match.group(0)

        pattern = re.compile(r'<action(?:\s+type="([^"]+)")?>(.*?)</action>', re.DOTALL | re.IGNORECASE)
        sanitized = re.sub(pattern, _replace, content)

        def _replace_file_content(match):
            body = match.group(1) or ""
            if len(body) <= 200:
                return match.group(0)
            blob_hash = self._save_blob(body)
            marker = f"[file_content omitted: {len(body)} chars, sha256:{blob_hash[:12]}]"
            return f"<file_content>{marker}</file_content>"

        file_content_pattern = re.compile(r"<file_content(?:\s+[^>]*)?>(.*?)</file_content>", re.DOTALL | re.IGNORECASE)
        return re.sub(file_content_pattern, _replace_file_content, sanitized)

    def _truncate_multiline_text(self, text: str, *, max_chars: int, max_lines: int) -> str:
        return self.material_tools.truncate_multiline_text(text, max_chars=max_chars, max_lines=max_lines)

    def _working_material_identity(self, content) -> str:
        return self.material_tools.working_material_identity(content)

    def _material_kind(self, content) -> str:
        return self.material_tools.material_kind(content)

    def _material_priority(self, msg: dict) -> int:
        kind = str(msg.get("material_kind") or msg.get("history_material_kind") or "generic")
        return self.material_tools.material_priority(kind)

    def _default_hops_for_content(self, content) -> int:
        kind = self._material_kind(content)
        if kind == "shell":
            return self.WM_SHELL_HOPS
        if kind in {"full_file", "chunk", "skeleton", "exact_symbol"}:
            return self.WM_DEFAULT_HOPS
        return 0

    def _expire_short_lived_working_material(self):
        expired = 0
        aged = 0
        for idx, msg in enumerate(list(self.messages)):
            if not msg.get("turn_working_material"):
                continue
            if str(msg.get("material_kind") or "") != "shell":
                continue
            hops = int(msg.get("protection_hops_remaining", 0) or 0)
            if hops <= 0:
                continue
            updated = dict(msg)
            updated["protection_hops_remaining"] = max(0, hops - 1)
            aged += 1

            if updated["protection_hops_remaining"] <= 0:
                updated["turn_working_material"] = False
                updated["type"] = "tool_result_history"
                content = updated.get("content")
                if isinstance(content, dict):
                    updated.setdefault("history_material_kind", self.material_tools.material_kind(content))
                    updated.setdefault("history_degrade_stage", 0)
                    updated.setdefault("history_added_seq", self._next_wm_seq())
                expired += 1

            self.messages[idx] = updated

        if (aged or expired) and self.logger:
            self.logger.info(
                "WorkingMaterial.age aged=%s shell_expired_to_history=%s",
                aged,
                expired,
            )

    def _is_effectively_empty_material(self, content) -> bool:
        if not isinstance(content, dict):
            return False
        tool = str(content.get("tool") or "")
        if tool not in {"read_file", "read_chunk", "extract_symbol", "extract_kotlin_function"}:
            return False
        data = self._preferred_working_material_text(content)
        return not data or not str(data).strip()

    def _preferred_working_material_text(self, payload: dict) -> str:
        return self.material_tools.preferred_text(payload)

    def _working_material_token_estimate(self, msg: dict) -> int:
        try:
            return self.count_tokens([msg])
        except Exception:
            return 0

    def _protected_working_material_budget_tokens(self) -> int:
        ordinary = [m for m in self.messages if not m.get("turn_working_material")]
        ordinary_tokens = self.count_tokens(ordinary) if ordinary else 0
        reserve = max(self.WM_MIN_PROTECTED_TOKENS, int(self.max_tokens * self.WM_PROTECTED_RESERVE_RATIO))
        share_cap = max(self.WM_MIN_PROTECTED_TOKENS, int(self.max_tokens * self.WM_MAX_PROTECTED_SHARE_RATIO))
        free_capacity = max(0, self.max_tokens - ordinary_tokens - reserve)
        return max(self.WM_MIN_PROTECTED_TOKENS, min(share_cap, free_capacity))

    def _protected_working_indices(self) -> list[int]:
        return [
            idx for idx, msg in enumerate(self.messages)
            if msg.get("turn_working_material") and int(msg.get("protection_hops_remaining", 0) or 0) > 0
        ]

    def _protected_working_material_tokens(self) -> int:
        return sum(self._working_material_token_estimate(self.messages[idx]) for idx in self._protected_working_indices())

    def _degradation_candidates(self) -> list[int]:
        candidates = self._protected_working_indices()
        candidates.sort(
            key=lambda i: (
                self._material_priority(self.messages[i]),
                int(self.messages[i].get("wm_last_touch_seq", 0) or 0),
                int(self.messages[i].get("wm_added_seq", 0) or 0),
            )
        )
        return candidates

    def _ordinary_structured_pressure_candidates(self) -> list[int]:
        candidates = []
        for idx, msg in enumerate(self.messages):
            if msg.get("turn_working_material"):
                continue
            content = msg.get("content")
            if not isinstance(content, dict):
                continue
            kind = str(msg.get("history_material_kind") or self._material_kind(content))
            if kind == "generic" and msg.get("role") != "system":
                continue
            stage = int(msg.get("history_degrade_stage", 0) or 0)
            if stage >= 2:
                continue
            candidates.append(idx)
        candidates.sort(
            key=lambda i: (
                self._material_priority(self.messages[i]),
                int(self.messages[i].get("history_degrade_stage", 0) or 0),
                int(self.messages[i].get("history_added_seq", 0) or 0),
            )
        )
        return candidates

    def _degrade_working_material_message(self, msg: dict, target_stage: int | None = None) -> dict:
        out = dict(msg)
        content = out.get("content") or {}
        current_stage = int(out.get("degrade_stage", 0) or 0)
        next_stage = target_stage if target_stage is not None else min(2, current_stage + 1)

        out["protection_hops_remaining"] = 0
        out["degrade_stage"] = next_stage
        kind = str(out.get("material_kind") or self._material_kind(content))
        out["content"] = self.material_tools.degrade_material(content, kind=kind, stage=next_stage, preserve_type="working material")

        degraded_content = out.get("content")
        if isinstance(degraded_content, str):
            if next_stage <= 1:
                out["type"] = "working_material_preview"
            else:
                out["type"] = "working_material_marker"
        elif isinstance(degraded_content, dict):
            out["type"] = "working_material_preview" if next_stage <= 1 else "working_material_marker"
        else:
            out["type"] = "working_material_marker"
        return out

    def _degrade_ordinary_message(self, msg: dict, target_stage: int | None = None) -> dict:
        out = dict(msg)
        content = out.get("content")
        if not isinstance(content, dict):
            return out
        current_stage = int(out.get("history_degrade_stage", 0) or 0)
        next_stage = target_stage if target_stage is not None else min(2, current_stage + 1)
        kind = str(out.get("history_material_kind") or self._material_kind(content))
        out["content"] = self.material_tools.degrade_material(content, kind=kind, stage=next_stage, preserve_type="history")
        out["history_degrade_stage"] = next_stage
        out["history_material_kind"] = kind
        return out

    def _enforce_working_material_caps(self):
        protected_indices = self._protected_working_indices()
        if not protected_indices:
            return

        protected_tokens = self._protected_working_material_tokens()
        protected_budget = self._protected_working_material_budget_tokens()
        full_file_indices = [idx for idx in protected_indices if self.messages[idx].get("material_kind") == "full_file"]

        def needs_pressure_relief() -> bool:
            return (
                protected_tokens > protected_budget
                or len(protected_indices) > self.WM_MAX_PROTECTED_ITEMS
                or len(full_file_indices) > self.WM_MAX_FULL_FILE_ITEMS
            )

        if not needs_pressure_relief():
            return

        for idx in self._degradation_candidates():
            if not needs_pressure_relief():
                break
            msg = dict(self.messages[idx])
            self.messages[idx] = self._degrade_working_material_message(msg, target_stage=1)
            protected_indices = self._protected_working_indices()
            protected_tokens = self._protected_working_material_tokens()
            full_file_indices = [j for j in protected_indices if self.messages[j].get("material_kind") == "full_file"]

        if self.logger:
            self.logger.info(
                "WorkingMaterial.pressure protected_tokens=%s protected_budget=%s protected_items=%s full_files=%s",
                protected_tokens,
                protected_budget,
                len(protected_indices),
                len(full_file_indices),
            )

    def _ordinary_pressure_trigger_tokens(self) -> int:
        return int(self.max_tokens * self.ORDINARY_PRESSURE_TRIGGER_RATIO)

    def _ordinary_pressure_target_tokens(self) -> int:
        return int(self.max_tokens * self.ORDINARY_PRESSURE_TARGET_RATIO)

    def _ordinary_structured_history_tokens(self) -> int:
        msgs = [
            m for m in self.messages
            if (not m.get("turn_working_material")) and isinstance(m.get("content"), dict)
        ]
        return self.count_tokens(msgs) if msgs else 0

    def _enforce_ordinary_history_pressure(self):
        if self.current_token_count < self._ordinary_pressure_trigger_tokens():
            return

        degraded = 0
        while (
            self.current_token_count > self._ordinary_pressure_target_tokens()
            and degraded < self.ORDINARY_MAX_DEGRADED_PER_PASS
        ):
            candidates = self._ordinary_structured_pressure_candidates()
            if not candidates:
                break
            idx = candidates[0]
            msg = dict(self.messages[idx])
            self.messages[idx] = self._degrade_ordinary_message(msg)
            degraded += 1

        if degraded and self.logger:
            self.logger.info(
                "OrdinaryHistory.pressure degraded=%s total_tokens=%s structured_tokens=%s",
                degraded,
                self.current_token_count,
                self._ordinary_structured_history_tokens(),
            )

    def start_turn(self, turn_id: int):
        self.current_turn_id = max(0, int(turn_id or 0))
        self.age_working_material()
        self._enforce_ordinary_history_pressure()

    def age_working_material(self):
        self._expire_short_lived_working_material()
        self._enforce_working_material_caps()

    def add_turn_working_material(self, content, *, msg_type="turn_working_material", turn_id=None, role="system"):
        tid = self.current_turn_id if turn_id is None else max(0, int(turn_id or 0))
        identity = self._working_material_identity(content)
        is_empty = self._is_effectively_empty_material(content)

        if identity and not is_empty:
            for idx in range(len(self.messages) - 1, max(-1, len(self.messages) - 21), -1):
                msg = self.messages[idx]
                if not msg.get("turn_working_material"):
                    continue
                if msg.get("working_material_id") != identity:
                    continue

                prev_payload = msg.get("content")
                prev_empty = self._is_effectively_empty_material(prev_payload)
                if prev_empty:
                    continue

                refreshed = dict(msg)
                refreshed["wm_last_touch_seq"] = self._next_wm_seq()
                refreshed["protection_hops_remaining"] = max(1, int(refreshed.get("protection_hops_remaining", 0) or 0))
                self.messages[idx] = refreshed
                if self.logger:
                    self.logger.info(
                        "WorkingMaterial.refresh turn=%s type=%s id=%s",
                        tid,
                        msg_type,
                        identity,
                    )
                self._enforce_working_material_caps()
                return False

        material_kind = self._material_kind(content)
        protection_hops = self._default_hops_for_content(content)
        seq = self._next_wm_seq()

        self.add_message(
            role,
            content,
            msg_type=msg_type,
            turn_working_material=True,
            turn_id=tid,
            working_material_id=identity,
            material_kind=material_kind,
            protection_hops_remaining=protection_hops,
            degrade_stage=0,
            wm_added_seq=seq,
            wm_last_touch_seq=seq,
        )
        self._enforce_working_material_caps()
        if self.logger:
            self.logger.info(
                "WorkingMaterial.add turn=%s type=%s id=%s kind=%s hops=%s",
                tid,
                msg_type,
                identity or "-",
                material_kind,
                protection_hops,
            )
        return True

    def add_transient_file_content(self, filename, version, content, turn_id=None):
        return self.add_turn_working_material(
            {
                "tool": "read_file",
                "path": filename,
                "filename": filename,
                "version": version,
                "file_version": version,
                "file_content": content,
                "output": content,
                "status": "success",
            },
            msg_type="turn_working_material",
            turn_id=turn_id,
        )

    def ensure_transient_file_content(self, filename, version, content, recent_window: int = 8, turn_id=None) -> bool:
        return bool(self.add_transient_file_content(filename, version, content, turn_id=turn_id))

    def _working_material_messages(self, turn_id=None):
        return [m for m in self.messages if m.get("turn_working_material")]

    def current_turn_working_material_token_count(self, turn_id=None) -> int:
        msgs = [
            m for m in self._working_material_messages(turn_id)
            if int(m.get("protection_hops_remaining", 0) or 0) > 0
        ]
        return self.count_tokens(msgs) if msgs else 0

    def add_file_version(self, filename, content, return_metadata=False):
        if content is None:
            return None if not return_metadata else {"version": None, "is_new_version": False, "blob_hash": None}
        if not isinstance(content, str):
            content = str(content)
        blob_hash = self._save_blob(content)
        version_list = self.files.setdefault(filename, [])
        if version_list and version_list[-1].get("blob_hash") == blob_hash:
            current_version = version_list[-1]["version"]
            version_list[-1]["timestamp"] = time.time()
            self.active_files.add(filename)
            return {"version": current_version, "is_new_version": False, "blob_hash": blob_hash} if return_metadata else current_version
        version_number = (version_list[-1]["version"] + 1) if version_list else 1
        version_list.append({"version": version_number, "blob_hash": blob_hash, "timestamp": time.time(), "size": len(content)})
        self.active_files.add(filename)
        if len(self.active_files) > self.MAX_ACTIVE_FILES:
            oldest = self._pick_oldest_active_file(exclude=filename)
            if oldest:
                self.active_files.discard(oldest)
        return {"version": version_number, "is_new_version": True, "blob_hash": blob_hash} if return_metadata else version_number

    def get_file_version_content(self, filename, version):
        for v in self.files.get(filename, []):
            if v["version"] == version:
                return self._load_blob(v["blob_hash"])
        return None

    def get_latest_file_version(self, filename):
        versions = self.files.get(filename) or []
        if not versions:
            return None
        latest = versions[-1]
        return latest.get("version")

    def _current_turn_readfile_keys(self, turn_id=None) -> set[tuple[str, str]]:
        keys: set[tuple[str, str]] = set()
        for msg in self.messages:
            if not msg.get("turn_working_material"):
                continue
            if int(msg.get("protection_hops_remaining", 0) or 0) <= 0:
                continue
            payload = msg.get("content")
            if not isinstance(payload, dict):
                continue
            if str(payload.get("tool") or "") != "read_file":
                continue
            path = str(payload.get("path") or payload.get("filename") or "")
            version = str(payload.get("version") or payload.get("file_version") or "")
            if path:
                keys.add((path, version))
        return keys

    def get_history_for_api(self):
        self._enforce_ordinary_history_pressure()

        api_history = []
        over_limit_pressure = self.current_token_count > self.max_tokens
        active_limit = self._effective_active_file_limit(over_limit_pressure)
        active_set = self._select_recent_active_files(active_limit)
        current_turn_readfile_keys = self._current_turn_readfile_keys(self.current_turn_id)

        workspace_parts = []
        workspace_emitted = []
        for filename, versions in self.files.items():
            if not versions:
                continue
            latest = versions[-1]
            version = latest["version"]
            version_str = str(version)
            if (filename, version_str) in current_turn_readfile_keys:
                if self.logger:
                    self.logger.info(
                        "APIContext.skip_workspace_duplicate path=%s version=%s source=protected_read_file",
                        filename,
                        version_str,
                    )
                continue

            content = self._load_blob(latest["blob_hash"])
            is_active = filename in active_set
            small_threshold = self.SKELETON_THRESHOLD if not over_limit_pressure else min(self.SKELETON_THRESHOLD, 400)
            is_small = len(content) < small_threshold
            if is_active or is_small:
                workspace_parts.append(f"<file_content path='{filename}' version='{version}'>\n{content}\n</file_content>")
                workspace_emitted.append((filename, version_str, "full"))
            else:
                skeleton = self.code_parser.get_skeleton(filename, content)
                workspace_parts.append(f"<file_skeleton path='{filename}' version='{version}'>\n{skeleton}\n</file_skeleton>\n")
                workspace_emitted.append((filename, version_str, "skeleton"))
        if workspace_parts:
            api_history.append({"role": "system", "content": "## CURRENT FILE STATE\n" + "\n".join(workspace_parts)})

        emitted_working_ids = set()
        for msg in self.messages:
            if msg.get("turn_working_material"):
                payload = msg.get("content")
                stage = int(msg.get("degrade_stage", 0) or 0)
                if isinstance(payload, dict):
                    tool = str(payload.get("tool") or "tool")
                    path = str(payload.get("path") or payload.get("filename") or "")
                    version = str(payload.get("version") or payload.get("file_version") or "")
                    dedup_key = (tool, path, version, str(msg.get("working_material_id") or ""), stage)
                    if dedup_key in emitted_working_ids:
                        continue
                    emitted_working_ids.add(dedup_key)

                    if int(msg.get("protection_hops_remaining", 0) or 0) <= 0:
                        content_text = msg.get("content")
                        if not isinstance(content_text, str):
                            content_text = json.dumps(content_text, ensure_ascii=False)
                        api_history.append({"role": "system", "content": content_text})
                        continue

                    if tool == "read_file":
                        f_content = payload.get("file_content") or payload.get("content") or payload.get("output") or ""
                        api_history.append({
                            "role": "system",
                            "content": f"SYSTEM RESULT (read_file):\n<file_content path='{path}' version='{version}'>\n{f_content}\n</file_content>",
                        })
                    elif tool == "read_chunk":
                        f_content = payload.get("file_content") or payload.get("content") or payload.get("output") or ""
                        start_line = payload.get("start_line")
                        end_line = payload.get("end_line")
                        if start_line is not None or end_line is not None:
                            range_attrs = f" start_line='{start_line}' end_line='{end_line}'"
                            tag_name = "file_chunk_lines"
                        else:
                            start_byte = payload.get("start_byte")
                            end_byte = payload.get("end_byte")
                            range_attrs = f" start_byte='{start_byte}' end_byte='{end_byte}'"
                            tag_name = "file_chunk"
                        api_history.append({
                            "role": "system",
                            "content": (
                                f"SYSTEM RESULT (read_chunk):\n"
                                f"<{tag_name} path='{path}' version='{version}'{range_attrs}>\n"
                                f"{f_content}\n"
                                f"</{tag_name}>"
                            ),
                        })
                    else:
                        lines = [f"SYSTEM RESULT ({tool}):"]
                        if path:
                            lines.append(f"path={path}")

                        preferred = self._preferred_working_material_text(payload)
                        if preferred:
                            lines.append(preferred)
                        else:
                            for key in ("output", "stdout", "stderr"):
                                value = payload.get(key)
                                if isinstance(value, str) and value:
                                    lines.append(value)

                        if payload.get("raw_output_truncated"):
                            lines.append(
                                f"[raw working material truncated at source: {payload.get('raw_output_chars')} / {payload.get('raw_output_total_chars')} chars]"
                            )

                        api_history.append({"role": "system", "content": "\n".join(lines)})
                else:
                    api_history.append({"role": "system", "content": str(payload)})
                continue

            if msg.get("type") == "file_context":
                continue

            content = msg.get("content", "")
            if not isinstance(content, str):
                content = json.dumps(content, ensure_ascii=False)
            if msg.get("role") == "assistant":
                stripped = content.lstrip()
                if stripped.startswith("TOOL_HISTORY ") or "TOOL_HISTORY {" in content or "\nTOOL_HISTORY {" in content:
                    continue
            api_history.append({"role": msg["role"], "content": content})

        if self.logger:
            self.logger.info(
                "APIContext.build workspace_files=%s protected_read_files=%s api_messages=%s",
                len(workspace_emitted),
                len(current_turn_readfile_keys),
                len(api_history),
            )
        return api_history

    def _effective_active_file_limit(self, over_limit_pressure: bool) -> int:
        if not over_limit_pressure:
            return self.MAX_ACTIVE_FILES
        return 1 if self.current_token_count > int(self.max_tokens * 1.5) else min(2, self.MAX_ACTIVE_FILES)

    def _select_recent_active_files(self, limit: int) -> set[str]:
        ranked = []
        for filename in self.active_files:
            versions = self.files.get(filename) or []
            ts = versions[-1]["timestamp"] if versions else 0
            ranked.append((ts, filename))
        ranked.sort(reverse=True)
        return {name for _, name in ranked[:max(0, limit)]}

    def _pick_oldest_active_file(self, exclude=None):
        oldest_name = None
        oldest_ts = None
        for filename in self.active_files:
            if exclude and filename == exclude:
                continue
            versions = self.files.get(filename) or []
            ts = versions[-1]["timestamp"] if versions else 0
            if oldest_ts is None or ts < oldest_ts:
                oldest_ts = ts
                oldest_name = filename
        return oldest_name

    def count_tokens(self, messages=None):
        msgs = messages or self.messages
        total = 0
        for m in msgs:
            c = m.get("content", "")
            total += len(c) if isinstance(c, str) else len(json.dumps(c, ensure_ascii=False))
        return total // 4

    @property
    def current_token_count(self):
        return self.count_tokens()

    def has_current_file_version(self, filename: str) -> bool:
        return bool(self.files.get(filename) or [])

    def was_recently_summarized(self, window_sec: int = 90) -> bool:
        return self._last_summary_at > 0 and (time.time() - self._last_summary_at) <= max(1, int(window_sec))

    def _recent_read_file_count(self, window: int = 10) -> int:
        count = 0
        for msg in self.messages[-max(1, int(window)):]:
            if not msg.get("turn_working_material"):
                continue
            if int(msg.get("protection_hops_remaining", 0) or 0) <= 0:
                continue
            payload = msg.get("content")
            if isinstance(payload, dict) and str(payload.get("tool") or "") in {"read_file", "read_chunk"}:
                count += 1
        return count

    def _recent_large_tool_result_count(self, window: int = 8) -> int:
        count = 0
        for msg in self.messages[-max(1, int(window)):]:
            if not msg.get("turn_working_material"):
                continue
            if int(msg.get("protection_hops_remaining", 0) or 0) <= 0:
                continue
            content = msg.get("content")
            if isinstance(content, dict):
                if content.get("history_compact") or content.get("truncated"):
                    count += 1
                    continue
                if int(content.get("result_count", 0) or 0) >= self.LARGE_RESULT_COUNT_HINT:
                    count += 1
                    continue
                preferred = self._preferred_working_material_text(content)
                if isinstance(preferred, str) and len(preferred) > self.MAX_STRUCTURED_TEXT_CHARS:
                    count += 1
        return count

    def _build_execution_snapshot(self, state=None) -> str:
        target = None
        task_kind = None
        if state is not None:
            sm = getattr(state, "state_machine", None)
            if sm is not None:
                target = getattr(sm, "target_file", None)
                task_kind = getattr(sm, "task_kind", None)
        recent_files = []
        for msg in reversed(self.messages):
            payload = msg.get("content")
            if not msg.get("turn_working_material") or not isinstance(payload, dict):
                continue
            if str(payload.get("tool") or "") not in {"read_file", "read_chunk"}:
                continue
            name = payload.get("path") or payload.get("filename")
            ver = payload.get("version") or payload.get("file_version")
            if name:
                token = f"{name}@v{ver}"
                if str(payload.get("tool") or "") == "read_chunk":
                    if payload.get("start_line") is not None and payload.get("end_line") is not None:
                        token += f"[{payload.get('start_line')},{payload.get('end_line')}]"
                    else:
                        token += f"[{payload.get('start_byte')},{payload.get('end_byte')})"
                if token not in recent_files:
                    recent_files.append(token)
            if len(recent_files) >= 6:
                break
        recent_files.reverse()
        protected_count = sum(
            1 for m in self.messages
            if m.get("turn_working_material") and int(m.get("protection_hops_remaining", 0) or 0) > 0
        )
        lines = ["EXECUTION SNAPSHOT"]
        if task_kind is not None:
            lines.append(f"task_kind={getattr(task_kind, 'value', task_kind)}")
        if target:
            lines.append(f"target_file={target}")
        if recent_files:
            lines.append("recent_read_files=" + ", ".join(recent_files))
        lines.append(f"protected_working_material={protected_count}")
        lines.append("do_not_reread_without_reason=true")
        return "\n".join(lines)

    async def check_and_summarize(self, ui=None, state=None):
        self._enforce_ordinary_history_pressure()

        tokens = self.count_tokens()
        now = time.time()
        prompt_threshold = int(self.max_tokens * self.SUMMARY_PROMPT_RATIO)
        emergency_threshold = int(self.max_tokens * self.EMERGENCY_SUMMARY_RATIO)
        working_material_tokens = self.current_turn_working_material_token_count()
        safe_working_material_budget = max(256, int(self.max_tokens * self.TURN_WORKING_MATERIAL_SAFE_RATIO))

        if tokens < prompt_threshold:
            self._next_summary_prompt_tokens = prompt_threshold
            self._next_emergency_summary_tokens = emergency_threshold
            return None

        if working_material_tokens > safe_working_material_budget:
            self._enforce_working_material_caps()
            if ui:
                await ui.print_error("Protected working material is too large to preserve safely. Use chunked reads, skeletons, or narrower tool output.")
            return {
                "reason": "turn_working_material_too_large",
                "error_code": "TURN_WORKING_MATERIAL_TOO_LARGE",
                "prompt": (
                    "SYSTEM: Protected working material is too large to preserve safely in context.\n"
                    "Do not request another huge full read/output immediately.\n"
                    "Use alternatives now: read_file_skeleton, read_chunk, narrower search_content, or narrower run_shell output.\n"
                    "Return EXACTLY ONE action or a direct answer."
                ),
            }

        sm = getattr(state, "state_machine", None) if state is not None else None
        current_task_kind = getattr(getattr(sm, "task_kind", None), "value", getattr(sm, "task_kind", None))
        in_inspection = sm is not None and current_task_kind == "INSPECTION"
        if in_inspection:
            defer_budget = max(0, int(getattr(sm.config, "SUMMARY_DEFER_OBSERVE_STEPS", 1)))
            min_reads = max(1, int(getattr(sm.config, "SUMMARY_MIN_READS_BEFORE_DEFER", 2)))
            if self._observe_summary_deferrals_remaining <= 0:
                self._observe_summary_deferrals_remaining = defer_budget
            has_large_recent_tool_result = self._recent_large_tool_result_count() > 0
            if not has_large_recent_tool_result and tokens < emergency_threshold and self._observe_summary_deferrals_remaining > 0 and self._recent_read_file_count() >= min_reads:
                self._observe_summary_deferrals_remaining -= 1
                if self.logger:
                    self.logger.info("Summary.defer reason=observe_recon tokens=%s remaining=%s", tokens, self._observe_summary_deferrals_remaining)
                return None

        if tokens >= emergency_threshold and tokens >= self._next_emergency_summary_tokens:
            if ui:
                await ui.print_system("History is near critical size. Running emergency compact...")
            await self.summarize(ui, window=True, state=state)
            cooldown = max(self.EMERGENCY_SUMMARY_COOLDOWN_MIN, self.max_tokens // 8)
            self._next_emergency_summary_tokens = self.count_tokens() + cooldown
            return None

        if self._last_summary_at > 0 and now - self._last_summary_at < self.SUMMARY_MIN_INTERVAL_SEC and tokens - self._last_summary_tokens < self.SUMMARY_MIN_TOKEN_GROWTH:
            return None
        if tokens < self._next_summary_prompt_tokens:
            return None

        if self.autosummarize_requires_confirmation and ui and hasattr(type(ui), "confirm_action") and callable(getattr(ui, "confirm_action", None)):
            response = await ui.confirm_action({"type": "summarize_history"})
            if response in (False, "later", None):
                cooldown = max(self.SUMMARY_PROMPT_COOLDOWN_MIN, self.max_tokens // 10)
                self._next_summary_prompt_tokens = tokens + cooldown
                return None

        await self.summarize(ui, window=True, state=state)
        return None

    async def summarize(self, ui=None, window=True, state=None, protect_turn_id=None):
        protected = []
        ordinary = []
        for msg in self.messages:
            if msg.get("turn_working_material") and int(msg.get("protection_hops_remaining", 0) or 0) > 0:
                protected.append(msg)
            else:
                ordinary.append(msg)

        if window and len(ordinary) > self.window_size:
            to_summarize = ordinary[:-self.window_size]
            keep_messages = ordinary[-self.window_size:]
        else:
            to_summarize = ordinary
            keep_messages = []
        if not to_summarize:
            return

        history_text = "\n".join(f"{m['role']}: {str(m['content'])[:200]}..." for m in to_summarize)
        active_intent_block = self._build_active_intent_summary_block(state)
        plan_board_block = self._build_plan_board_summary_block(state)
        memory_board_block = self._build_memory_board_summary_block(state)

        prompt_parts = [
            "Summarize conversation history into compact background working memory for continuing the same coding task.",
            "Be aggressively compact, factual, and continuation-oriented.",
            "Preserve only the operational state needed for correct next steps that is NOT already captured in the canonical intent/plan/memory boards.",
            "",
            "This summary is INTERNAL MEMORY, not a user-facing handoff.",
            "Do NOT treat it as a new task.",
            "Do NOT restate it as the next assistant response.",
            "Do NOT simulate another agent.",
            "",
            "IMPORTANT:",
            "- The ACTIVE INTENT BOARD, CURRENT PLAN BOARD, and MEMORY BOARD blocks below are canonical runtime state.",
            "- Do not summarize, rewrite, compress, absorb, or replace those canonical boards.",
            "- If compressed history conflicts with a canonical board, trust the canonical board.",
            "- The MEMORY BOARD block below is canonical durable memory.",
            "- Do not duplicate the full canonical boards verbatim unless a tiny amount is needed for continuity.",
            "- Preserve only tactical or transitional state that is still needed and is not already covered by the canonical boards.",
            "",
            "Preserve only high-value state. Keep:",
            "- ACTIVE GOAL: the current user-facing goal of the active session",
            "- ESTABLISHED FACTS: key already-proven facts that affect the answer or next change",
            "- CURRENT BEST ANSWER: the best current understanding so far, even if not final",
            "- ACTIVE PLAN / STRATEGY: the current plan or approach, but only the parts that still matter",
            "- EXECUTION STATE: what has already been done, what is pending, and what execution mode the work is in",
            "- PENDING CHECKS: unresolved checks that could materially change the answer or next edit",
            "- AVOID REGRESSION: things that must NOT be re-investigated without a new reason",
            "- IMPORTANT ERRORS / POLICY EVENTS: only if they still constrain the next step",
            "",
            "Compress heavily:",
            "- repetitive search attempts",
            "- repeated tool calls with similar arguments",
            "- broad/noisy search results",
            "- long file listings",
            "- verbose tool stdout/stderr",
            "- repeated policy/recovery messages that no longer matter",
            "",
            "Do NOT preserve raw long outputs. Do NOT preserve full code unless essential.",
            "Do NOT produce a generic recap. Produce compact background working memory for continuity.",
            "",
            "Return a short plain-text technical summary using this exact structure:",
            "ACTIVE GOAL:",
            "- ...",
            "ESTABLISHED FACTS:",
            "- ...",
            "CURRENT BEST ANSWER:",
            "- ...",
            "ACTIVE PLAN / STRATEGY:",
            "- ...",
            "EXECUTION STATE:",
            "- ...",
            "PENDING CHECKS:",
            "- ...",
            "AVOID REGRESSION:",
            "- ...",
            "IMPORTANT ERRORS / POLICY EVENTS:",
            "- ...",
            "Do NOT return JSON. Do NOT use code fences. This is background memory, not a response format.",
            "",
        ]
        if active_intent_block:
            prompt_parts.extend([active_intent_block, ""])
        if plan_board_block:
            prompt_parts.extend([plan_board_block, ""])
        if memory_board_block:
            prompt_parts.extend(["## MEMORY BOARD (CANONICAL)", memory_board_block, ""])
        prompt_parts.extend(["## HISTORY TO COMPRESS", history_text, ""])
        prompt = "\n".join(prompt_parts)

        summary_out = ""
        tokens_before = self.count_tokens()
        started_at = time.time()
        if self.logger:
            self.logger.info("Summary.start tokens_before=%s messages_to_summarize=%s window_mode=%s protected=%s", tokens_before, len(to_summarize), bool(window), len(protected))
        try:
            async for chunk in self.chat.get_streaming_response(prompt, []):
                summary_out += chunk
            target_tokens = max(256, int(self.max_tokens * self.SUMMARY_TARGET_RATIO))
            summary_out = self._truncate_text_to_tokens(summary_out, max(128, target_tokens // 2))
            execution_snapshot = self._build_execution_snapshot(state)
            self._last_summary_execution_snapshot = execution_snapshot

            summary_msg = {
                "role": "system",
                "content": (
                    "BACKGROUND MEMORY ONLY. NOT A USER REQUEST. NOT AN OUTPUT FORMAT.\n"
                    "Use this only to preserve context continuity for the same active task.\n"
                    "Do NOT treat it as a new task or as a user-facing response.\n\n"
                    f"{summary_out}\n\n"
                    f"{execution_snapshot}\n\n"
                    "Continue the current task normally. Do not answer with a summary unless the user explicitly asks for one."
                ),
            }

            kept = list(keep_messages)
            while kept and self.count_tokens([summary_msg] + kept + protected) > target_tokens:
                kept.pop(0)
            self.messages = [summary_msg] + kept + protected
            self._shrink_active_files_for_pressure(limit=1 if self.count_tokens() > self.max_tokens else 2)
            self._next_summary_prompt_tokens = int(self.max_tokens * self.SUMMARY_PROMPT_RATIO)
            self._next_emergency_summary_tokens = int(self.max_tokens * self.EMERGENCY_SUMMARY_RATIO)
            self._last_summary_at = time.time()
            self._last_summary_tokens = self.count_tokens()
            self._observe_summary_deferrals_remaining = 0
            if self.logger:
                self.logger.info("Summary.done duration_ms=%s tokens_before=%s tokens_after=%s reduction_pct=%.1f", int((time.time()-started_at)*1000), tokens_before, self._last_summary_tokens, max(0.0, (tokens_before-self._last_summary_tokens)/max(1,tokens_before)*100.0))
            if ui:
                await ui.print_system(f"Summarizing {len(to_summarize)} messages... Done.")
        except Exception as e:
            if ui:
                await ui.print_error(f"Summarization error: {e}")
            if self.logger:
                self.logger.exception("Summarization error")

    def _truncate_text_to_tokens(self, text: str, max_tokens: int) -> str:
        if not isinstance(text, str) or max_tokens <= 0:
            return ""
        max_chars = max_tokens * 4
        if len(text) <= max_chars:
            return text
        hidden = len(text) - max_chars
        return text[:max_chars] + f"\n... [summary truncated: {hidden} chars hidden]"

    def _shrink_active_files_for_pressure(self, limit: int):
        self.active_files = set() if limit <= 0 else self._select_recent_active_files(limit)

    def clear_history(self):
        self.messages = []
        self.active_files = set()
        self.files = {}
        if self.logger:
            self.logger.info("History cleared.")

    def remove_file_state(self, path_prefix: str) -> int:
        removed = 0
        for filename in list(self.files.keys()):
            if filename == path_prefix or filename.startswith(path_prefix):
                self.files.pop(filename, None)
                self.active_files.discard(filename)
                removed += 1
        return removed

    def clear_file_state(self):
        self.files = {}
        self.active_files = set()
