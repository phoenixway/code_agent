# modules/history.py
import json
import time

class HistoryManager:
    """
    HistoryManager для code-agent:
    - зберігає повідомлення (user/assistant/system)
    - зберігає файли коду з версіями
    - підтримує token counting, sliding window, summary через LLM
    """

    def __init__(self, chat_provider, logger=None, max_tokens=4000, window_size=50, max_file_versions=5):
        self.messages = []         # raw chat messages
        self.files = {}            # {"filename": [{"version": int, "content": str, "timestamp": float}, ...]}
        self.chat = chat_provider
        self.logger = logger
        self.max_tokens = max_tokens
        self.window_size = window_size  # останні N повідомлень залишаються без summary
        self.max_file_versions = max_file_versions

    # ------------------ Messages ------------------

    def add_message(self, role, content):
        """Додає чисте повідомлення в історію"""
        if not content or not isinstance(content, str):
            return
        content = content.strip()
        if not content:
            return
        self.messages.append({"role": role, "content": content})
        if self.logger:
            self.logger.debug(f"Added message: role={role}, content='{content[:50]}...'")

    def add_messages(self, messages):
        for msg in messages:
            self.add_message(msg["role"], msg["content"])

    # ------------------ Files ------------------

    def add_file_version(self, filename, content):
        """Додає нову версію файлу"""
        content = content.strip()
        if not content:
            return
        version_list = self.files.setdefault(filename, [])
        version_number = (version_list[-1]["version"] + 1) if version_list else 1
        version_list.append({
            "version": version_number,
            "content": content,
            "timestamp": time.time()
        })
        # Trim old versions
        if len(version_list) > self.max_file_versions:
            version_list[:] = version_list[-self.max_file_versions:]
        if self.logger:
            self.logger.debug(f"Added file version: {filename} v{version_number}")

    def get_latest_file_content(self, filename):
        """Повертає останню версію файлу"""
        versions = self.files.get(filename)
        if versions:
            return versions[-1]["content"]
        return None

    def get_file_history(self, filename):
        """Повертає список всіх версій файлу"""
        return self.files.get(filename, [])

    # ------------------ Token counting ------------------

    def count_tokens(self, messages=None):
        """Підрахунок токенів історії"""
        messages = messages or self.messages
        tokenizer = getattr(self.chat, "get_tokenizer", lambda: None)()
        if not tokenizer:
            return sum(len(m["content"]) for m in messages) // 4
        return sum(len(tokenizer.encode(m["content"])) for m in messages)

    # ------------------ History for API ------------------

    def get_history_for_api(self):
        return self.messages

    # ------------------ Summarization ------------------

    async def check_and_summarize(self, ui=None):
        """Перевірка токенів і запуск summary при перевищенні max_tokens"""
        if self.count_tokens() > self.max_tokens:
            confirm = True
            if ui and hasattr(ui, "confirm_action"):
                confirm = await ui.confirm_action({"type": "summarize_history"})
            if confirm:
                await self.summarize(ui, window=True)

    async def summarize(self, ui=None, window=True):
        """
        Структуроване summary історії та файлів.
        Якщо window=True, summarize старі повідомлення, залишаючи останні window_size.
        """
        if window and len(self.messages) > self.window_size:
            to_summarize = self.messages[:-self.window_size]
            keep_messages = self.messages[-self.window_size:]
        else:
            to_summarize = self.messages
            keep_messages = []

        if not to_summarize:
            return

        # Формуємо історію чатів
        history_text = "\n".join(f"{m['role']}: {m['content']}" for m in to_summarize)

        # Формуємо список файлів та змін
        file_changes = {}
        for fname, versions in self.files.items():
            file_changes[fname] = [
                {"version": v["version"], "content_snippet": v["content"][:200]}
                for v in versions
            ]

        prompt = (
            "Summarize the following conversation history and code changes in JSON format, "
            "keeping key facts, decisions, pending tasks, and latest code snippets.\n\n"
            f"Chat history:\n{history_text}\n\n"
            f"Files:\n{json.dumps(file_changes, indent=2)}\n\n"
            "Output JSON example:\n"
            "{\n"
            '  "summary": "...",\n'
            '  "decisions": ["..."],\n'
            '  "pending_tasks": ["..."],\n'
            '  "file_summaries": {"filename": "..."}\n'
            "}"
        )

        if ui and hasattr(ui, "print_system"):
            await ui.print_system(f"Summarizing {len(to_summarize)} messages and {len(file_changes)} files...")

        summary = ""
        try:
            async for chunk in self.chat.get_streaming_response(prompt, []):
                summary += chunk
            try:
                json_summary = json.loads(summary)
                summary_text = json.dumps(json_summary, indent=2)
            except Exception:
                summary_text = summary  # fallback if JSON invalid

            # Замінюємо старі повідомлення на одне system повідомлення зі summary
            self.messages = [{"role": "system", "content": f"Previous conversation summary: {summary_text}"}] + keep_messages

            if ui and hasattr(ui, "print_system"):
                await ui.print_system("History summarized successfully.")
            if self.logger:
                self.logger.debug("History summarized successfully.")
        except Exception as e:
            if ui and hasattr(ui, "print_error"):
                await ui.print_error(f"Failed to summarize history: {str(e)}")
            elif self.logger:
                self.logger.error(f"Failed to summarize history: {str(e)}")