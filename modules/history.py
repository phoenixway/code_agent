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
from pathlib import Path
from modules.code_parser import CodeParser

class HistoryManager:
    def __init__(self, chat_provider, logger=None, max_tokens=4000, storage_dir=".angelica", window_size=50):
        self.chat = chat_provider
        self.logger = logger
        self.max_tokens = max_tokens
        self.window_size = window_size
        
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
        if not content and not msg_type: return

        final_content = content

        # COMPRESSION: If Assistant wrote a file, replace body with a Stub
        if role == "assistant" and isinstance(content, str):
            final_content = self._compress_assistant_tool_call(content)
        
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

    def add_file_version(self, filename, content):
        """Saves new file version via Blob and updates context."""
        content = content.strip()
        if not content: return None
        
        blob_hash = self._save_blob(content)
        
        version_list = self.files.setdefault(filename, [])
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
        
        # --- A. BUILD SYSTEM WORKSPACE (Current Project State) ---
        workspace_parts = []
        
        for filename, versions in self.files.items():
            if not versions: continue
            
            latest = versions[-1]
            version = latest["version"]
            content = self._load_blob(latest["blob_hash"])
            
            # Logic: Full Content OR Skeleton?
            # Full if: Active OR Small size
            is_active = filename in self.active_files
            is_small = len(content) < self.SKELETON_THRESHOLD
            
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
        if self.count_tokens() > self.max_tokens:
            confirm = True
            if ui and hasattr(ui, "confirm_action"):
                confirm = await ui.confirm_action({"type": "summarize_history"})
            if confirm:
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

        if ui: await ui.print_system(f"Summarizing {len(to_summarize)} messages...")

        summary_out = ""
        try:
            async for chunk in self.chat.get_streaming_response(prompt, []):
                summary_out += chunk
            
            summary_msg = {"role": "system", "content": f"SUMMARY: {summary_out}"}
            self.messages = [summary_msg] + keep_messages
            
            if ui: await ui.print_system("✅ History summarized.")
            
        except Exception as e:
            if ui: await ui.print_error(f"Summarization error: {e}")

    def clear_history(self):
        """Clear RAM history only."""
        self.messages = []
        self.active_files = set()
        self.files = {} 
        if self.logger: self.logger.info("History cleared.")
