"""
modules/history.py

History manager with short-lived working material protection.

Key rules:
- tool returns may be stored as generic working material
- protection is short-lived (measured in agent hops), not whole turn/intent
- older working material degrades in stages:
  full -> skeleton/preview -> reread marker
- only a small number of recent materials stay fully protected
- get_history_for_api avoids duplicating the same read_file payload through both
  CURRENT FILE STATE and protected working material
"""

import hashlib
import json
import time
from pathlib import Path
from modules.code_parser import CodeParser


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

        # Short-lived working material policy.
        self.WM_DEFAULT_HOPS = 1
        self.WM_MAX_PROTECTED_ITEMS = 2
        self.WM_MAX_FULL_FILE_ITEMS = 1

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
            final_content = self._compact_structured_message_content(final_content)

        message = {"role": role, "content": final_content}
        if msg_type:
            message["type"] = msg_type
        message.update(meta)
        self.messages.append(message)

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
            if content.strip().startswith('{') and '"content"' in content:
                data = json.loads(content)
                action = data.get("type") or data.get("action")
                if action in ["create_file", "write_file", "edit_file", "replace"] and "content" in data:
                    body = data["content"]
                    if isinstance(body, str) and len(body) > 200:
                        blob_hash = self._save_blob(body)
                        data.pop("content", None)
                        data["content_redacted"] = True
                        data["content_size"] = len(body)
                        data["content_blob_hash"] = blob_hash
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
            if action_type in {"create_file", "write_file", "edit_file", "replace"} and isinstance(data, dict):
                payload = data.get("content")
                if isinstance(payload, str) and len(payload) > 200:
                    blob_hash = self._save_blob(payload)
                    data.pop("content", None)
                    data["content_redacted"] = True
                    data["content_size"] = len(payload)
                    data["content_blob_hash"] = blob_hash
                    return f'<action type="{action_type}">\n{json.dumps(data, ensure_ascii=False, indent=2)}\n</action>'
            return match.group(0)

        pattern = re.compile(r'<action(?:\s+type="([^"]+)")?>(.*?)</action>', re.DOTALL | re.IGNORECASE)
        return re.sub(pattern, _replace, content)

    def _truncate_multiline_text(self, text: str, *, max_chars: int, max_lines: int) -> str:
        if not isinstance(text, str):
            text = str(text)
        if not text:
            return text
        lines = text.splitlines()
        out = "\n".join(lines[:max_lines])
        if len(out) > max_chars:
            out = out[:max_chars].rstrip() + "\n...[truncated]"
        elif len(lines) > max_lines:
            out += "\n...[truncated]"
        return out

    def _compact_structured_message_content(self, content):
        try:
            if isinstance(content, list):
                return [self._compact_structured_message_content(item) for item in content]
            if not isinstance(content, dict):
                return content
            compact = dict(content)
            history_compact = bool(compact.get("history_compact", False))
            truncated = bool(compact.get("truncated", False))
            result_count = int(compact.get("result_count", 0) or 0)
            if isinstance(compact.get("output"), str):
                compact["output"] = self._truncate_multiline_text(
                    compact["output"],
                    max_chars=self.MAX_STRUCTURED_TEXT_CHARS,
                    max_lines=self.MAX_STRUCTURED_OUTPUT_LINES,
                )
            if isinstance(compact.get("stdout"), str):
                if history_compact or truncated or result_count >= self.LARGE_RESULT_COUNT_HINT:
                    compact["stdout"] = self._truncate_multiline_text(
                        compact["stdout"],
                        max_chars=self.MAX_STRUCTURED_STDOUT_CHARS,
                        max_lines=20,
                    )
                else:
                    compact["stdout"] = self._truncate_multiline_text(
                        compact["stdout"],
                        max_chars=self.MAX_STRUCTURED_TEXT_CHARS,
                        max_lines=self.MAX_STRUCTURED_OUTPUT_LINES,
                    )
            if isinstance(compact.get("stderr"), str):
                compact["stderr"] = self._truncate_multiline_text(
                    compact["stderr"],
                    max_chars=self.MAX_STRUCTURED_STDERR_CHARS,
                    max_lines=12,
                )
            return compact
        except Exception:
            return content

    def start_turn(self, turn_id: int):
        self.current_turn_id = max(0, int(turn_id or 0))
        self.age_working_material()

    def age_working_material(self):
        updated = []
        for msg in self.messages:
            if not msg.get("turn_working_material"):
                updated.append(msg)
                continue

            current = dict(msg)
            hops = int(current.get("protection_hops_remaining", 0) or 0)
            if hops > 0:
                current["protection_hops_remaining"] = hops - 1
                updated.append(current)
                continue

            updated.append(self._degrade_working_material_message(current))
        self.messages = updated
        self._enforce_working_material_caps()

    def _working_material_identity(self, content) -> str:
        try:
            if isinstance(content, dict):
                tool = str(content.get("tool") or "")
                path = str(content.get("path") or content.get("file_path") or content.get("filename") or "")
                version = str(content.get("version") or content.get("file_version") or "")
                start = str(content.get("start_byte") or "")
                end = str(content.get("end_byte") or "")
                chunk_id = str(content.get("chunk_id") or "")
                status = str(content.get("status") or "")
                command = str(content.get("command") or "") if tool == "run_shell" else ""
                core = content.get("file_content") or content.get("content") or content.get("output") or ""
                blob = hashlib.sha256(str(core).encode("utf-8")).hexdigest()[:16] if core else ""
                return f"{tool}|{path}|{version}|{start}|{end}|{chunk_id}|{status}|{command}|{blob}"
            raw = str(content)
            return hashlib.sha256(raw.encode("utf-8")).hexdigest()[:24]
        except Exception:
            return ""

    def _material_kind(self, content) -> str:
        if not isinstance(content, dict):
            return "generic"
        tool = str(content.get("tool") or "")
        if tool == "read_file":
            return "full_file"
        if tool == "read_chunk":
            return "chunk"
        if tool == "read_file_skeleton":
            return "skeleton"
        return "generic"

    def _default_hops_for_content(self, content) -> int:
        kind = self._material_kind(content)
        if kind in {"full_file", "chunk", "skeleton"}:
            return self.WM_DEFAULT_HOPS
        return 0

    def _is_effectively_empty_material(self, content) -> bool:
        if not isinstance(content, dict):
            return False
        tool = str(content.get("tool") or "")
        if tool not in {"read_file", "read_chunk"}:
            return False
        data = content.get("file_content") or content.get("content") or content.get("output") or ""
        return not data or not str(data).strip()

    def _enforce_working_material_caps(self):
        protected_indices = []
        full_file_indices = []
        for idx, msg in enumerate(self.messages):
            if not msg.get("turn_working_material"):
                continue
            hops = int(msg.get("protection_hops_remaining", 0) or 0)
            if hops <= 0:
                continue
            protected_indices.append(idx)
            if msg.get("material_kind") == "full_file":
                full_file_indices.append(idx)

        if len(protected_indices) > self.WM_MAX_PROTECTED_ITEMS:
            for idx in protected_indices[:-self.WM_MAX_PROTECTED_ITEMS]:
                msg = dict(self.messages[idx])
                msg["protection_hops_remaining"] = 0
                self.messages[idx] = self._degrade_working_material_message(msg, target_stage=1)

        if len(full_file_indices) > self.WM_MAX_FULL_FILE_ITEMS:
            for idx in full_file_indices[:-self.WM_MAX_FULL_FILE_ITEMS]:
                msg = dict(self.messages[idx])
                msg["protection_hops_remaining"] = 0
                self.messages[idx] = self._degrade_working_material_message(msg, target_stage=1)

    def add_turn_working_material(self, content, *, msg_type="turn_working_material", turn_id=None, role="system"):
        tid = self.current_turn_id if turn_id is None else max(0, int(turn_id or 0))
        identity = self._working_material_identity(content)
        is_empty = self._is_effectively_empty_material(content)

        if identity and not is_empty:
            for msg in reversed(self.messages[-20:]):
                if not msg.get("turn_working_material"):
                    continue
                if msg.get("working_material_id") != identity:
                    continue

                prev_payload = msg.get("content")
                prev_empty = self._is_effectively_empty_material(prev_payload)
                if prev_empty:
                    continue

                if self.logger:
                    self.logger.info(
                        "WorkingMaterial.skip_duplicate turn=%s type=%s id=%s",
                        tid,
                        msg_type,
                        identity,
                    )
                return False

        material_kind = self._material_kind(content)
        protection_hops = self._default_hops_for_content(content)

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

    def _degrade_working_material_message(self, msg: dict, target_stage: int | None = None) -> dict:
        out = dict(msg)
        content = out.get("content") or {}
        current_stage = int(out.get("degrade_stage", 0) or 0)
        next_stage = target_stage if target_stage is not None else min(2, current_stage + 1)

        out["protection_hops_remaining"] = 0
        out["degrade_stage"] = next_stage

        if isinstance(content, dict):
            tool = str(content.get("tool") or "tool")
            path = str(content.get("path") or content.get("filename") or "")
            version = content.get("version") or content.get("file_version")

            if tool == "read_file":
                full = content.get("file_content") or content.get("content") or content.get("output")
                if next_stage <= 1:
                    skeleton = None
                    if isinstance(full, str) and full:
                        try:
                            skeleton = self.code_parser.get_skeleton(path, full)
                        except Exception:
                            skeleton = None
                    if skeleton and skeleton.strip() and full and skeleton.strip() != str(full).strip():
                        out["content"] = (
                            f"Working material degraded: file `{path}` version `{version}` was read.\n"
                            f"Skeleton:\n{skeleton}\n\n"
                            "If exact content is needed again, reread via read_file."
                        )
                    else:
                        preview = self._truncate_multiline_text(str(full or ""), max_chars=1200, max_lines=40)
                        out["content"] = (
                            f"Working material degraded: file `{path}` version `{version}` was read.\n"
                            f"Preview:\n{preview}\n\n"
                            "If exact content is needed again, reread via read_file."
                        )
                    out["type"] = "working_material_skeleton"
                    return out

                out["content"] = (
                    f"Working material marker: file `{path}` version `{version}` was read earlier. "
                    "If exact content is needed again, reread via read_file."
                )
                out["type"] = "working_material_marker"
                return out

            if tool == "read_chunk":
                full = content.get("file_content") or content.get("content") or content.get("output")
                start_byte = content.get("start_byte")
                end_byte = content.get("end_byte")
                if next_stage <= 1:
                    preview = self._truncate_multiline_text(str(full or ""), max_chars=1000, max_lines=30)
                    out["content"] = (
                        f"Working material degraded: file chunk from `{path}` version `{version}` "
                        f"bytes [{start_byte}, {end_byte}) was read.\n"
                        f"Preview:\n{preview}\n\n"
                        "If exact chunk content is needed again, reread via read_chunk."
                    )
                    out["type"] = "working_material_preview"
                    return out

                out["content"] = (
                    f"Working material marker: file chunk from `{path}` version `{version}` "
                    f"bytes [{start_byte}, {end_byte}) was read earlier. "
                    "If exact chunk content is needed again, reread via read_chunk."
                )
                out["type"] = "working_material_marker"
                return out

            if tool == "read_file_skeleton":
                if next_stage <= 1:
                    preview = self._truncate_multiline_text(str(content.get("output") or ""), max_chars=1200, max_lines=40)
                    out["content"] = (
                        f"Working material degraded: skeleton for `{path}` was read.\n"
                        f"{preview}\n\n"
                        "If exact content is needed again, reread via read_file_skeleton or read_file."
                    )
                    out["type"] = "working_material_preview"
                    return out

                out["content"] = (
                    f"Working material marker: skeleton for `{path}` was read earlier. "
                    "If exact content is needed again, reread via read_file_skeleton or read_file."
                )
                out["type"] = "working_material_marker"
                return out

            preview = content.get("output") or content.get("stdout") or content.get("stderr") or ""
            if isinstance(preview, str):
                preview = self._truncate_multiline_text(preview, max_chars=800, max_lines=20)
            if next_stage <= 1:
                out["content"] = {
                    "tool": tool,
                    "path": path,
                    "note": "Working material degraded to compact preview.",
                    "output_preview": preview,
                }
                out["type"] = "working_material_preview"
                return out

            out["content"] = {
                "tool": tool,
                "path": path,
                "note": "Working material degraded to marker. Rerun the tool if exact content is needed.",
            }
            out["type"] = "working_material_marker"
            return out

        out["content"] = "Working material degraded. Rerun the tool if exact content is needed."
        out["type"] = "working_material_marker"
        return out

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
                        start_byte = payload.get("start_byte")
                        end_byte = payload.get("end_byte")
                        api_history.append({
                            "role": "system",
                            "content": (
                                f"SYSTEM RESULT (read_chunk):\n"
                                f"<file_chunk path='{path}' version='{version}' start_byte='{start_byte}' end_byte='{end_byte}'>\n"
                                f"{f_content}\n"
                                f"</file_chunk>"
                            ),
                        })
                    else:
                        lines = [f"SYSTEM RESULT ({tool}):"]
                        if path:
                            lines.append(f"path={path}")
                        for key in ("output", "stdout", "stderr"):
                            value = payload.get(key)
                            if isinstance(value, str) and value:
                                lines.append(value)
                        api_history.append({"role": "system", "content": "\n".join(lines)})
                else:
                    api_history.append({"role": "system", "content": str(payload)})
                continue

            if msg.get("type") == "file_context":
                continue

            content = msg.get("content", "")
            if not isinstance(content, str):
                content = json.dumps(content, ensure_ascii=False)
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
                if isinstance(content.get("output"), str) and len(content.get("output")) > self.MAX_STRUCTURED_TEXT_CHARS:
                    count += 1
        return count

    def _build_execution_snapshot(self, state=None) -> str:
        phase = None
        target = None
        if state is not None:
            sm = getattr(state, "state_machine", None)
            if sm is not None:
                phase = getattr(sm, "phase", None)
                target = getattr(sm, "target_file", None)
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
        if phase is not None:
            lines.append(f"phase={getattr(phase, 'value', phase)}")
        if target:
            lines.append(f"target_file={target}")
        if recent_files:
            lines.append("recent_read_files=" + ", ".join(recent_files))
        lines.append(f"protected_working_material={protected_count}")
        lines.append("do_not_reread_without_reason=true")
        return "\n".join(lines)

    async def check_and_summarize(self, ui=None, state=None):
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
            self.age_working_material()
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
        in_observe = sm is not None and getattr(sm.phase, "value", sm.phase) == "OBSERVE"
        if in_observe:
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
        prompt = (
            "Summarize conversation history for future continuation by a coding agent. "
            "Be aggressively compact. Preserve only high-value state.\n"
            "Keep:\n- user's actual goal and constraints\n- established facts and conclusions\n- files read/edited that still matter\n- active intent / current target / pending next step\n- important errors, defect detections, and recovery decisions\n\n"
            "Compress heavily:\n- repetitive search attempts\n- repeated tool calls with similar arguments\n- broad/noisy search results\n- long file listings\n- verbose tool stdout/stderr\n- repeated policy/recovery messages\n\n"
            "Do NOT preserve raw long outputs. Do NOT preserve full code unless essential.\n"
            "Return a short plain-text technical summary using this exact structure:\n"
            "Summary:\n- ...\n"
            "Established facts:\n- ...\n"
            "Pending next step:\n- ...\n"
            "Open questions:\n- ...\n"
            "Do NOT return JSON. Do NOT use code fences. This is background memory, not a response format.\n"
            f"{history_text}\n"
        )

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
                    "BACKGROUND MEMORY ONLY. NOT A USER REQUEST. NOT AN OUTPUT FORMAT.\n\n"
                    f"{summary_out}\n\n"
                    f"{execution_snapshot}\n\n"
                    "Continue the current task. Do not answer with a summary unless the user explicitly asks for one."
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