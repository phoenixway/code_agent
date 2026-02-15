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
        self.SUMMARY_PROMPT_RATIO = 1.15
        self.SUMMARY_PROMPT_COOLDOWN_MIN = 200
        self.EMERGENCY_SUMMARY_RATIO = 1.5
        self.EMERGENCY_SUMMARY_COOLDOWN_MIN = 500
        self.SUMMARY_TARGET_RATIO = 0.5
        self.SUMMARY_MIN_INTERVAL_SEC = 45
        self.SUMMARY_MIN_TOKEN_GROWTH = max(256, self.max_tokens // 16)
        self.disable_summary_prompts = False
        self._next_summary_prompt_tokens = int(self.max_tokens * self.SUMMARY_PROMPT_RATIO)
        self._next_emergency_summary_tokens = int(self.max_tokens * self.EMERGENCY_SUMMARY_RATIO)
        self._last_summary_at = 0.0
        self._last_summary_tokens = 0

    # =========================================================================
    # 1. BLOB STORAGE (Content-Addressable Storage)
    # =========================================================================

    def _save_blob(self, content: str) -> str:
        """Saves content to disk using SHA256 hash as filename."""
        if not content: return None
        
        content_bytes = content.encode('utf-8')
        blob_hash = hashlib.sha256(content_bytes).hexdigest()
        blob_path = self.blobs_dir / blob_hash
        
        if not blob_path.exists():
            with open(blob_path, "wb") as f:
                f.write(content_bytes)
        return blob_hash

    def _load_blob(self, blob_hash: str) -> str:
        """Retrieves content from disk by hash."""
        if not blob_hash: return ""
        blob_path = self.blobs_dir / blob_hash
        if blob_path.exists():
            try:
                with open(blob_path, "rb") as f:
                    return f.read().decode('utf-8')
            except Exception as e:
                if self.logger: self.logger.error(f"Blob load error {blob_hash}: {e}")
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
            # Check if it looks like JSON tool call
            if content.strip().startswith('{') and '"content"' in content:
                data = json.loads(content)
                action = data.get("type") or data.get("action")
                
                if action in ["create_file", "edit_file", "replace"] and "content" in data:
                    body = data["content"]
                    if len(body) > 200:
                        blob_hash = self._save_blob(body)
                        size = len(body)
                        data["content"] = (
                            f"[CONTENT_SAVED_TO_DISK]\n"
                            f"Size: {size} bytes | Hash: {blob_hash[:8]}\n"
                            f"NOTE: Content written to system. Use 'read_file' to view."
                        )
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
                    digest = hashlib.sha256(payload.encode("utf-8")).hexdigest()[:12]
                    preview = payload[:80].replace("\n", "\\n")
                    data["content"] = (
                        f"[content omitted: {len(payload)} chars, sha256:{digest}, preview:'{preview}']"
                    )
                    return f'<action type="{action_type}">\n{json.dumps(data, ensure_ascii=False, indent=2)}\n</action>'
            return match.group(0)

        pattern = re.compile(r'<action(?:\s+type="([^"]+)")?>(.*?)</action>', re.DOTALL | re.IGNORECASE)
        return re.sub(pattern, _replace, content)

    def add_transient_file_content(self, filename, version, content):
        """Adds a temporary message (read_file result) that isn't saved permanently."""
        self.add_message("system", {
            "filename": filename,
            "version": version,
            "content": content
        }, msg_type="transient_file_content")

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

        # Deduplicate identical content: do not create extra versions for the same blob.
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
        
        # Mark as active (LRU logic)
        self.active_files.add(filename)
        if len(self.active_files) > self.MAX_ACTIVE_FILES:
            # Simple eviction: remove one that isn't the current one
            for f in list(self.active_files):
                if f != filename:
                    self.active_files.remove(f)
                    break
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
        Logic:
        1. Parse linear history.
        2. Identify file references.
        3. Build 'System Workspace' (Full content vs Skeletons).
        4. Append Chat Log (skipping redundant transient files).
        5. Ensure the LAST read_file result is always visible.
        """
        api_history = []
        included_in_system_prompt = set()
        over_limit_pressure = self.current_token_count > self.max_tokens
        active_limit = self._effective_active_file_limit(over_limit_pressure)
        active_set = self._select_recent_active_files(active_limit)
        
        # --- A. BUILD SYSTEM WORKSPACE (Current Project State) ---
        workspace_parts = []
        
        for filename, versions in self.files.items():
            if not versions: continue
            
            latest = versions[-1]
            version = latest["version"]
            content = self._load_blob(latest["blob_hash"])
            
            # Logic: Full Content OR Skeleton?
            # Full if: Active OR Small size
            is_active = filename in active_set
            small_threshold = self.SKELETON_THRESHOLD if not over_limit_pressure else min(self.SKELETON_THRESHOLD, 400)
            is_small = len(content) < small_threshold
            
            if is_active or is_small:
                workspace_parts.append(
                    f"<file_content path='{filename}' version='{version}'>\n{content}\n</file_content>"
                )
            else:
                skeleton = self.code_parser.get_skeleton(filename, content)
                workspace_parts.append(
                    f"<file_skeleton path='{filename}' version='{version}'>\n{skeleton}\n</file_skeleton>\n"
                    f""
                )
            
            included_in_system_prompt.add(f"{filename}:{version}")

        if workspace_parts:
            sys_msg = "## CURRENT FILE STATE\n" + "\n".join(workspace_parts)
            api_history.append({"role": "system", "content": sys_msg})

        # --- B. PROCESS CHAT LOG ---
        
        last_msg_idx = len(self.messages) - 1
        
        for idx, msg in enumerate(self.messages):
            msg_type = msg.get("type")
            
            # Skip transient files (read_file results) IF they are already covered in System Workspace
            # UNLESS it's the very last message (Agent just read it, needs to see it now)
            if msg_type == "transient_file_content":
                if idx == last_msg_idx:
                    # Logic for the LAST message (Immediate feedback)
                    t_data = msg["content"]
                    f_name, f_ver, f_content = t_data["filename"], t_data["version"], t_data["content"]
                    
                    # Even for immediate feedback, check size
                    if len(f_content) > self.SKELETON_THRESHOLD * 2: # Very generous limit for immediate read
                         # Fallback to skeleton even for read if HUGE
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
                
                continue # Skip transient messages that are not the last one

            elif msg_type == "file_context":
                # Legacy support: skip, as we built System Workspace
                continue
            
            # Add normal messages
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

    # =========================================================================
    # 5. SUMMARIZATION & UTILS
    # =========================================================================

    def count_tokens(self, messages=None):
        """Approximate token count."""
        msgs = messages or self.messages
        total = 0
        for m in msgs:
            c = m.get("content", "")
            total += len(str(c))
        return total // 4

    @property
    def current_token_count(self):
        return self.count_tokens()

    async def check_and_summarize(self, ui=None):
        """Trigger summarization if limit reached."""
        tokens = self.count_tokens()
        if tokens <= self.max_tokens:
            self._next_summary_prompt_tokens = int(self.max_tokens * self.SUMMARY_PROMPT_RATIO)
            self._next_emergency_summary_tokens = int(self.max_tokens * self.EMERGENCY_SUMMARY_RATIO)
            return
        now = time.time()

        # Hard guard: if history is heavily overflown, summarize immediately.
        emergency_threshold = int(self.max_tokens * self.EMERGENCY_SUMMARY_RATIO)
        if tokens >= emergency_threshold and tokens >= self._next_emergency_summary_tokens:
            if ui:
                await ui.print_system("History is critically over limit. Running emergency compact...")
            await self.summarize(ui, window=True)
            cooldown = max(self.EMERGENCY_SUMMARY_COOLDOWN_MIN, self.max_tokens // 8)
            self._next_emergency_summary_tokens = self.count_tokens() + cooldown
            return

        if (
            self._last_summary_at > 0
            and now - self._last_summary_at < self.SUMMARY_MIN_INTERVAL_SEC
            and tokens - self._last_summary_tokens < self.SUMMARY_MIN_TOKEN_GROWTH
        ):
            return

        # Avoid prompting too early right after crossing the hard limit.
        if tokens < int(self.max_tokens * self.SUMMARY_PROMPT_RATIO):
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

        # Default mode: keep control in AI loop (no modal confirmation).
        await self.summarize(ui, window=True)

    async def summarize(self, ui=None, window=True):
        """Summarize old messages."""
        if window and len(self.messages) > self.window_size:
            to_summarize = self.messages[:-self.window_size]
            keep_messages = self.messages[-self.window_size:]
        else:
            to_summarize = self.messages
            keep_messages = []

        if not to_summarize: return

        # Compress text for prompt
        history_text = "\n".join(f"{m['role']}: {str(m['content'])[:200]}..." for m in to_summarize)

        prompt = (
            "Summarize conversation history JSON. Keep tasks/decisions.\n"
            f"{history_text}\n"
            "Format: {\"summary\": \"...\", \"pending\": [...]}"
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
            summary_msg = {"role": "system", "content": f"Previous conversation summary: {summary_out}"}

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
            if ui: await ui.print_error(f"Summarization error: {e}")

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
        if self.logger: self.logger.info("History cleared.")

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
