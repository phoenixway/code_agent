"""
modules/history.py

Ultimate History Manager:
1. CAS (Content-Addressable Storage): Saves disk space & RAM via deduplication (Blobs).
2. Smart Context: Dynamic switching between Full Content and Skeletons based on usage frequency.
3. Tool Compression: 'Hides' the code written by the agent in the chat history to save tokens.
4. Transient Handling: Ensures `read_file` results are visible immediately but don't clog history later.
5. Summarization: Long-term memory management.
"""

import json
import time
import hashlib
import os
import re
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

        # --- STORAGE SETUP ---
        self.storage_root = Path(storage_dir)
        self.blobs_dir = self.storage_root / "blobs"
        self.blobs_dir.mkdir(parents=True, exist_ok=True)

        # --- STATE ---
        self.messages = []         # Linear chat log
        self.files = {}            # {filename: [{version, blob_hash, timestamp}, ...]}
        self.active_files = set()  # Files explicitly edited/read recently

        # --- TOOLS ---
        self.code_parser = CodeParser()

        # --- CONSTANTS ---
        self.SKELETON_THRESHOLD = 2000  # Bytes. Larger files get skeletonized unless active.
        self.MAX_ACTIVE_FILES = 5       # Keep top N files in "Full Content" mode in system prompt.
        self.MAX_RECENT_TRANSIENT_SKELETON_CONTEXT = 6

        # Summarization now starts BEFORE overflow.
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

        # History compaction guards
        self.MAX_STRUCTURED_TEXT_CHARS = 2500
        self.MAX_STRUCTURED_STDOUT_CHARS = 1200
        self.MAX_STRUCTURED_STDERR_CHARS = 800
        self.MAX_STRUCTURED_OUTPUT_LINES = 40
        self.LARGE_RESULT_COUNT_HINT = 80

    # =========================================================================
    # 1. BLOB STORAGE (Content-Addressable Storage)
    # =========================================================================

    def _save_blob(self, content: str) -> str:
        """Saves content to disk using SHA256 hash as filename."""
        if not content:
            return None

        content_bytes = content.encode('utf-8')
        blob_hash = hashlib.sha256(content_bytes).hexdigest()
        blob_path = self.blobs_dir / blob_hash

        # blobs_dir may be removed between turns (cleanup, concurrent process).
        # Ensure it exists right before writing.
        try:
            self.blobs_dir.mkdir(parents=True, exist_ok=True)
        except Exception as e:
            if self.logger:
                self.logger.error(f"Blob dir ensure error {self.blobs_dir}: {e}")

        if not blob_path.exists():
            with open(blob_path, "wb") as f:
                f.write(content_bytes)
        return blob_hash

    def _load_blob(self, blob_hash: str) -> str:
        """Retrieves content from disk by hash."""
        if not blob_hash:
            return ""
        blob_path = self.blobs_dir / blob_hash
        if blob_path.exists():
            try:
                with open(blob_path, "rb") as f:
                    return f.read().decode('utf-8')
            except Exception as e:
                if self.logger:
                    self.logger.error(f"Blob load error {blob_hash}: {e}")
        return ""

    # =========================================================================
    # 2. MESSAGE MANAGEMENT & COMPRESSION
    # =========================================================================

    def add_message(self, role, content, msg_type=None):
        """Adds a message with intelligent compression for tool outputs."""
        if msg_type is None:
            if content is None:
                return
            if isinstance(content, str) and not content.strip():
                return

        final_content = content

        # COMPRESSION: If Assistant wrote a file, replace body with a Stub
        if role == "assistant" and isinstance(content, str):
            final_content = self._compress_assistant_tool_call(content)
            final_content = self._sanitize_action_blocks_for_history(final_content)

        # COMPRESSION: Structured tool/system payloads can silently flood history.
        if isinstance(final_content, (dict, list)):
            final_content = self._compact_structured_message_content(final_content)

        message = {"role": role, "content": final_content}
        if msg_type:
            message["type"] = msg_type

        self.messages.append(message)

        if self.logger:
            preview = str(final_content)[:60].replace('\n', ' ')
            self.logger.debug(f"History+ ({role}): {preview}...")

    def _compress_assistant_tool_call(self, content: str) -> str:
        """Parses assistant JSON. If create/edit_file, offloads content to Blob."""
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
        """Sanitize large create/edit action payloads in <action> blocks."""
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
        truncated_lines = lines[:max_lines]
        out = "\n".join(truncated_lines)
        if len(out) > max_chars:
            out = out[:max_chars].rstrip() + "\n...[truncated]"
        elif len(lines) > max_lines:
            out += "\n...[truncated]"
        return out

    def _compact_structured_message_content(self, content):
        """
        Prevent giant tool results from silently inflating history.
        Especially important for search tool outputs that may already be previewed in `output`
        but still carry huge `stdout`.
        """
        try:
            if isinstance(content, list):
                return [self._compact_structured_message_content(item) for item in content]

            if not isinstance(content, dict):
                return content

            compact = dict(content)

            # If the producer already marked this as compact/truncated, trust that and keep history tiny.
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

            # Legacy or ad-hoc giant text fields
            for key in list(compact.keys()):
                value = compact.get(key)
                if isinstance(value, str) and key not in {"output", "stdout", "stderr", "content"} and len(value) > self.MAX_STRUCTURED_TEXT_CHARS:
                    compact[key] = self._truncate_multiline_text(
                        value,
                        max_chars=self.MAX_STRUCTURED_TEXT_CHARS,
                        max_lines=self.MAX_STRUCTURED_OUTPUT_LINES,
                    )

            return compact
        except Exception:
            return content

    def add_transient_file_content(self, filename, version, content):
        """Adds a temporary message (read_file result) that isn't saved permanently."""
        self.add_message("system", {
            "filename": filename,
            "version": version,
            "content": content
        }, msg_type="transient_file_content")

    def ensure_transient_file_content(self, filename, version, content, recent_window: int = 8) -> bool:
        """
        Ensure transient read_file content is available in recent history.
        Returns True if a new transient message was added, False if already present.
        """
        if not filename or version is None:
            return False
        window = max(1, int(recent_window))
        for msg in reversed(self.messages[-window:]):
            if msg.get("type") != "transient_file_content":
                continue
            data = msg.get("content") or {}
            if (
                data.get("filename") == filename
                and data.get("version") == version
                and data.get("content") == content
            ):
                return False
        self.add_transient_file_content(filename, version, content)
        return True

    # =========================================================================
    # 3. FILE STATE MANAGEMENT
    # =========================================================================

    def add_file_version(self, filename, content, return_metadata=False):
        """Saves new file version via Blob and updates context with dedup for identical content."""
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
            if return_metadata:
                return {"version": current_version, "is_new_version": False, "blob_hash": blob_hash}
            return current_version

        version_number = (version_list[-1]["version"] + 1) if version_list else 1
        version_list.append({
            "version": version_number,
            "blob_hash": blob_hash,
            "timestamp": time.time(),
            "size": len(content)
        })

        self.active_files.add(filename)
        if len(self.active_files) > self.MAX_ACTIVE_FILES:
            oldest = self._pick_oldest_active_file(exclude=filename)
            if oldest:
                self.active_files.discard(oldest)
        if return_metadata:
            return {"version": version_number, "is_new_version": True, "blob_hash": blob_hash}
        return version_number

    def get_file_version_content(self, filename, version):
        """Helper to get content for specific version."""
        versions = self.files.get(filename, [])
        for v in versions:
            if v["version"] == version:
                return self._load_blob(v["blob_hash"])
        return None

    # =========================================================================
    # 4. API CONTEXT GENERATION (THE BRAIN)
    # =========================================================================

    def get_history_for_api(self):
        """
        Dynamically constructs the context window.
        """
        api_history = []
        included_in_system_prompt = set()
        over_limit_pressure = self.current_token_count > self.max_tokens
        active_limit = self._effective_active_file_limit(over_limit_pressure)
        active_set = self._select_recent_active_files(active_limit)

        workspace_parts = []
        file_render_mode = {}

        for filename, versions in self.files.items():
            if not versions:
                continue

            latest = versions[-1]
            version = latest["version"]
            content = self._load_blob(latest["blob_hash"])

            is_active = filename in active_set
            small_threshold = self.SKELETON_THRESHOLD if not over_limit_pressure else min(self.SKELETON_THRESHOLD, 400)
            is_small = len(content) < small_threshold

            if is_active or is_small:
                workspace_parts.append(
                    f"<file_content path='{filename}' version='{version}'>\n{content}\n</file_content>"
                )
                file_render_mode[filename] = "full"
            else:
                skeleton = self.code_parser.get_skeleton(filename, content)
                workspace_parts.append(
                    f"<file_skeleton path='{filename}' version='{version}'>\n{skeleton}\n</file_skeleton>\n"
                    f""
                )
                file_render_mode[filename] = "skeleton"

            included_in_system_prompt.add(f"{filename}:{version}")

        if workspace_parts:
            sys_msg = "## CURRENT FILE STATE\n" + "\n".join(workspace_parts)
            api_history.append({"role": "system", "content": sys_msg})

        last_msg_idx = len(self.messages) - 1
        recent_transient_indices = self._recent_transient_indices()

        for idx, msg in enumerate(self.messages):
            msg_type = msg.get("type")

            if msg_type == "transient_file_content":
                t_data = msg["content"]
                f_name, f_ver, f_content = t_data["filename"], t_data["version"], t_data["content"]
                show_for_immediate_feedback = idx == last_msg_idx
                show_for_recent_skeleton_context = (
                    idx in recent_transient_indices
                    and file_render_mode.get(f_name) == "skeleton"
                )
                if show_for_immediate_feedback or show_for_recent_skeleton_context:
                    if len(f_content) > self.SKELETON_THRESHOLD * 2:
                        skel = self.code_parser.get_skeleton(f_name, f_content)
                        content_str = (
                            f"SYSTEM RESULT (read_file):\n"
                            f"<file_skeleton path='{f_name}' version='{f_ver}'>\n{skel}\n</file_skeleton>\n"
                            f"NOTE: File is huge. Showing signatures."
                        )
                    else:
                        content_str = (
                            f"SYSTEM RESULT (read_file):\n"
                            f"<file_content path='{f_name}' version='{f_ver}'>\n{f_content}\n</file_content>"
                        )
                    api_history.append({"role": "system", "content": content_str})

                continue

            elif msg_type == "file_context":
                continue

            content = msg.get('content', '')
            if not isinstance(content, str):
                content = json.dumps(content, ensure_ascii=False)

            api_history.append({"role": msg["role"], "content": content})

        return api_history

    def _effective_active_file_limit(self, over_limit_pressure: bool) -> int:
        if not over_limit_pressure:
            return self.MAX_ACTIVE_FILES
        tokens = self.current_token_count
        if tokens > int(self.max_tokens * 1.5):
            return 1
        return min(2, self.MAX_ACTIVE_FILES)

    def _select_recent_active_files(self, limit: int) -> set[str]:
        if limit <= 0:
            return set()
        ranked = []
        for filename in self.active_files:
            versions = self.files.get(filename) or []
            ts = versions[-1]["timestamp"] if versions else 0
            ranked.append((ts, filename))
        ranked.sort(reverse=True)
        return {name for _, name in ranked[:limit]}

    def _pick_oldest_active_file(self, exclude: str | None = None) -> str | None:
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

    def _recent_transient_indices(self) -> set[int]:
        indices = []
        for idx in range(len(self.messages) - 1, -1, -1):
            msg = self.messages[idx]
            if msg.get("type") == "transient_file_content":
                indices.append(idx)
                if len(indices) >= self.MAX_RECENT_TRANSIENT_SKELETON_CONTEXT:
                    break
        return set(indices)

    # =========================================================================
    # 5. SUMMARIZATION & UTILS
    # =========================================================================

    def count_tokens(self, messages=None):
        """Approximate token count."""
        msgs = messages or self.messages
        total = 0
        for m in msgs:
            c = m.get("content", "")
            if isinstance(c, str):
                total += len(c)
            else:
                total += len(json.dumps(c, ensure_ascii=False))
        return total // 4

    @property
    def current_token_count(self):
        return self.count_tokens()

    def has_current_file_version(self, filename: str) -> bool:
        versions = self.files.get(filename) or []
        return bool(versions)

    def was_recently_summarized(self, window_sec: int = 90) -> bool:
        if self._last_summary_at <= 0:
            return False
        return (time.time() - self._last_summary_at) <= max(1, int(window_sec))

    def _recent_read_file_count(self, window: int = 10) -> int:
        count = 0
        for msg in self.messages[-max(1, int(window)):]:
            if msg.get("type") == "transient_file_content":
                count += 1
        return count

    def _recent_large_tool_result_count(self, window: int = 8) -> int:
        count = 0
        for msg in self.messages[-max(1, int(window)):]:
            content = msg.get("content")
            if isinstance(content, dict):
                if content.get("history_compact") or content.get("truncated"):
                    count += 1
                    continue
                if int(content.get("result_count", 0) or 0) >= self.LARGE_RESULT_COUNT_HINT:
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
            if msg.get("type") == "transient_file_content":
                data = msg.get("content") or {}
                name = data.get("filename")
                ver = data.get("version")
                if name:
                    token = f"{name}@v{ver}"
                    if token not in recent_files:
                        recent_files.append(token)
                if len(recent_files) >= 6:
                    break
        recent_files.reverse()
        lines = ["EXECUTION SNAPSHOT"]
        if phase is not None:
            lines.append(f"phase={getattr(phase, 'value', phase)}")
        if target:
            lines.append(f"target_file={target}")
        if recent_files:
            lines.append("recent_read_files=" + ", ".join(recent_files))
        lines.append("do_not_reread_without_reason=true")
        return "\n".join(lines)

    async def check_and_summarize(self, ui=None, state=None):
        """Trigger summarization before hard overflow when possible."""
        tokens = self.count_tokens()
        now = time.time()

        prompt_threshold = int(self.max_tokens * self.SUMMARY_PROMPT_RATIO)
        emergency_threshold = int(self.max_tokens * self.EMERGENCY_SUMMARY_RATIO)

        if tokens < prompt_threshold:
            self._next_summary_prompt_tokens = prompt_threshold
            self._next_emergency_summary_tokens = emergency_threshold
            return

        sm = getattr(state, "state_machine", None) if state is not None else None
        in_observe = sm is not None and getattr(sm.phase, "value", sm.phase) == "OBSERVE"

        if in_observe:
            defer_budget = max(0, int(getattr(sm.config, "SUMMARY_DEFER_OBSERVE_STEPS", 1)))
            min_reads = max(1, int(getattr(sm.config, "SUMMARY_MIN_READS_BEFORE_DEFER", 2)))
            if self._observe_summary_deferrals_remaining <= 0:
                self._observe_summary_deferrals_remaining = defer_budget

            has_large_recent_tool_result = self._recent_large_tool_result_count() > 0
            if (
                not has_large_recent_tool_result
                and tokens < emergency_threshold
                and self._observe_summary_deferrals_remaining > 0
                and self._recent_read_file_count() >= min_reads
            ):
                self._observe_summary_deferrals_remaining -= 1
                if self.logger:
                    self.logger.info(
                        "Summary.defer reason=observe_recon tokens=%s remaining=%s",
                        tokens,
                        self._observe_summary_deferrals_remaining,
                    )
                return

        if tokens >= emergency_threshold and tokens >= self._next_emergency_summary_tokens:
            if ui:
                await ui.print_system("History is near critical size. Running emergency compact...")
            await self.summarize(ui, window=True, state=state)
            cooldown = max(self.EMERGENCY_SUMMARY_COOLDOWN_MIN, self.max_tokens // 8)
            self._next_emergency_summary_tokens = self.count_tokens() + cooldown
            return

        if (
            self._last_summary_at > 0
            and now - self._last_summary_at < self.SUMMARY_MIN_INTERVAL_SEC
            and tokens - self._last_summary_tokens < self.SUMMARY_MIN_TOKEN_GROWTH
        ):
            return

        if tokens < self._next_summary_prompt_tokens:
            return

        if self.autosummarize_requires_confirmation:
            confirm = True
            can_confirm = (
                ui
                and hasattr(type(ui), "confirm_action")
                and callable(getattr(ui, "confirm_action", None))
            )
            if can_confirm:
                response = await ui.confirm_action({"type": "summarize_history"})
                if response in (False, "later", None):
                    confirm = False
                elif isinstance(response, str):
                    confirm = response.lower().strip() in {"summarize", "yes", "allow", "ok", "confirm", "true"}
            if not confirm:
                cooldown = max(self.SUMMARY_PROMPT_COOLDOWN_MIN, self.max_tokens // 10)
                self._next_summary_prompt_tokens = tokens + cooldown
                return

        await self.summarize(ui, window=True, state=state)

    async def summarize(self, ui=None, window=True, state=None):
        """Summarize old messages."""
        if window and len(self.messages) > self.window_size:
            to_summarize = self.messages[:-self.window_size]
            keep_messages = self.messages[-self.window_size:]
        else:
            to_summarize = self.messages
            keep_messages = []

        if not to_summarize:
            return

        history_text = "\n".join(f"{m['role']}: {str(m['content'])[:200]}..." for m in to_summarize)

        prompt = (
            "Summarize conversation history JSON for a coding agent. "
            "Be aggressively compact. Preserve only high-value state.\n"
            "Keep:\n"
            "- user's actual goal and constraints\n"
            "- established facts and conclusions\n"
            "- files read/edited that still matter\n"
            "- active intent / current target / pending next step\n"
            "- important errors, defect detections, and recovery decisions\n"
            "\n"
            "Compress heavily:\n"
            "- repetitive search attempts\n"
            "- repeated tool calls with similar arguments\n"
            "- broad/noisy search results\n"
            "- long file listings\n"
            "- verbose tool stdout/stderr\n"
            "- repeated policy/recovery messages\n"
            "\n"
            "When many similar tool attempts happened, collapse them into one line such as:\n"
            "- 'Repeated search_content on concat_into in project root; too broad/noisy; later narrowed to modules with no matches.'\n"
            "\n"
            "Do NOT preserve raw long outputs. Do NOT preserve full code unless essential.\n"
            "Return strict JSON: {\"summary\": \"...\", \"pending\": [...], \"established_facts\": [...], \"open_questions\": [...]}\n"
            f"{history_text}\n"
        )

        summary_count = len(to_summarize)
        progress_widget = None
        progress_text = f"Summarizing {summary_count} messages..."
        if ui:
            start_progress = getattr(ui, "start_system_progress", None)
            if callable(start_progress):
                try:
                    progress_widget = await start_progress(progress_text)
                except Exception:
                    progress_widget = None
            if progress_widget is None:
                await ui.print_system(progress_text)

        summary_out = ""
        tokens_before = self.count_tokens()
        started_at = time.time()
        if self.logger:
            self.logger.info(
                "Summary.start "
                f"tokens_before={tokens_before} "
                f"messages_to_summarize={summary_count} "
                f"window_mode={bool(window)}"
            )
        try:
            async for chunk in self.chat.get_streaming_response(prompt, []):
                summary_out += chunk

            target_tokens = max(256, int(self.max_tokens * self.SUMMARY_TARGET_RATIO))
            summary_out = self._truncate_text_to_tokens(summary_out, max(128, target_tokens // 2))
            execution_snapshot = self._build_execution_snapshot(state)
            self._last_summary_execution_snapshot = execution_snapshot
            summary_msg = {"role": "system", "content": f"Previous conversation summary: {summary_out}\n\n{execution_snapshot}"}

            kept = list(keep_messages)
            while kept and self.count_tokens([summary_msg] + kept) > target_tokens:
                kept.pop(0)
            if self.count_tokens([summary_msg] + kept) > target_tokens:
                kept = []
            self.messages = [summary_msg] + kept
            self._shrink_active_files_for_pressure(limit=1 if self.count_tokens() > self.max_tokens else 2)
            self._next_summary_prompt_tokens = int(self.max_tokens * self.SUMMARY_PROMPT_RATIO)
            self._next_emergency_summary_tokens = int(self.max_tokens * self.EMERGENCY_SUMMARY_RATIO)
            self._last_summary_at = time.time()
            self._last_summary_tokens = self.count_tokens()
            self._observe_summary_deferrals_remaining = 0

            tokens_after = self._last_summary_tokens
            duration_ms = int((time.time() - started_at) * 1000)
            reduction_pct = 0.0
            if tokens_before > 0:
                reduction_pct = max(0.0, (tokens_before - tokens_after) / tokens_before * 100.0)
            if self.logger:
                self.logger.info(
                    "Summary.done "
                    f"duration_ms={duration_ms} "
                    f"tokens_before={tokens_before} "
                    f"tokens_after={tokens_after} "
                    f"reduction_pct={reduction_pct:.1f}"
                )

            if ui:
                update_progress = getattr(ui, "update_system_progress", None)
                done_text = f"{progress_text} Done."
                if progress_widget is not None and callable(update_progress):
                    await update_progress(progress_widget, done_text)
                else:
                    await ui.print_system(done_text)

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
        if limit <= 0:
            self.active_files = set()
            return
        self.active_files = self._select_recent_active_files(limit)

    def clear_history(self):
        """Clear RAM history only."""
        self.messages = []
        self.active_files = set()
        self.files = {}
        if self.logger:
            self.logger.info("History cleared.")

    def remove_file_state(self, path_prefix: str) -> int:
        """Remove tracked file-state entries matching an exact path or prefix."""
        removed = 0
        for filename in list(self.files.keys()):
            if filename == path_prefix or filename.startswith(path_prefix):
                self.files.pop(filename, None)
                self.active_files.discard(filename)
                removed += 1
        return removed

    def clear_file_state(self):
        """Remove all tracked file-state entries without touching chat messages."""
        self.files = {}
        self.active_files = set()