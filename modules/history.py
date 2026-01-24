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

    def add_message(self, role, content, msg_type=None):
        """Додає чисте повідомлення в історію"""
        if not content and not msg_type:
            return

        if isinstance(content, str):
            content = content.strip()
            if not content and not msg_type:
                return
        
        message = {"role": role, "content": content}
        if msg_type:
            message["type"] = msg_type

        self.messages.append(message)
        if self.logger:
            log_content = content
            if isinstance(content, dict):
                log_content = json.dumps(content)[:100]
            elif isinstance(content, str):
                log_content = content[:50]
            self.logger.debug(f"Added message: role={role}, type={msg_type}, content='{log_content}...'")

    def add_messages(self, messages):
        for msg in messages:
            self.add_message(msg["role"], msg.get("content"), msg.get("type"))

    # ------------------ Files ------------------

    def add_file_version(self, filename, content):
        """
        Додає нову версію файлу в self.files і повертає номер версії.
        """
        content = content.strip()
        if not content:
            return None
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
        return version_number

    def add_file_context_marker(self, filename, version):
        """Додає маркер-посилання на файл в історію повідомлень."""
        marker = {"filename": filename, "version": version}
        self.add_message("system", marker, msg_type="file_context")

    def add_transient_file_content(self, filename, version, content):
        """Додає тимчасове повідомлення з повним вмістом файлу."""
        transient_content = {
            "filename": filename,
            "version": version,
            "content": content
        }
        self.add_message("system", transient_content, msg_type="transient_file_content")

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
        messages_to_count = messages or self.get_history_for_api()
        tokenizer = getattr(self.chat, "get_tokenizer", lambda: None)()
        
        if not tokenizer:
            # Fallback to character-based estimation
            token_count = 0
            for m in messages_to_count:
                if isinstance(m.get('content'), str):
                    token_count += len(m['content'])
            return token_count // 4
        
        # Sum tokens for all messages
        return sum(len(tokenizer.encode(m["content"])) for m in messages_to_count if isinstance(m.get('content'), str))

    @property
    def current_token_count(self):
        """Повертає поточну кількість токенів в історії, яку буде надіслано в API."""
        return self.count_tokens()

    # ------------------ History for API ------------------

    def get_history_for_api(self):
        """
        Динамічно генерує історію для відправки в API.
        - "Очищує" старі тимчасові повідомлення з контентом файлів.
        - Включає контент файлів на основі маркерів `file_context` згідно з правилами.
        - Гарантує, що контент щойно запитаного файлу буде в кінці історії.
        """
        api_history = []
        included_files = {}  # {"filename": [v1, v2]}

        # 1. Основний прохід: будуємо чисту історію
        for msg in self.messages:
            msg_type = msg.get("type")

            if msg_type == "transient_file_content":
                # Ігноруємо ці повідомлення на основному проході.
                # Вони будуть оброблені в кінці, якщо потрібно.
                continue
            
            elif msg_type == "file_context":
                filename = msg["content"]["filename"]
                version = msg["content"]["version"]
                
                # Правило: не більше 2 версій одного файлу
                if len(included_files.get(filename, [])) >= 2:
                    continue
                
                # Правило: не включати ту саму версію двічі
                if version in included_files.get(filename, []):
                    continue

                file_content = self.get_file_version_content(filename, version)
                if file_content:
                    api_history.append({
                        "role": "system",
                        "content": (
                            f"The following file '{filename}' (version {version}) is in context:\n"
                            f"--- start of file ---\n"
                            f"{file_content}\n"
                            f"--- end of file ---"
                        )
                    })
                    included_files.setdefault(filename, []).append(version)
            
            else: # Звичайні повідомлення
                # Переконуємось, що content - це рядок
                content = msg.get('content', '')
                if not isinstance(content, str):
                    content = json.dumps(content, indent=2)

                api_history.append({
                    "role": msg["role"],
                    "content": content
                })

        # 2. Фінальна перевірка: задовольняємо очікування моделі
        last_message = self.messages[-1] if self.messages else None
        if last_message and last_message.get("type") == "transient_file_content":
            transient_content = last_message["content"]
            filename = transient_content["filename"]
            version = transient_content["version"]
            content = transient_content["content"]
            
            # Перевіряємо, чи цей контент вже не був доданий
            already_included = False
            for h_msg in reversed(api_history):
                if h_msg['content'].startswith(f"The following file '{filename}'"):
                    if f"(version {version})" in h_msg['content']:
                        already_included = True
                        break
            
            if not already_included:
                 api_history.append({
                    "role": "system",
                    "content": f"SYSTEM RESULT for `read_file`: File '{filename}' (version {version}) content:\n---\n{content}\n---"
                })

        return api_history
    
    def get_file_version_content(self, filename, version):
        """Допоміжна функція для отримання контенту конкретної версії файлу."""
        versions = self.files.get(filename, [])
        for v in versions:
            if v["version"] == version:
                return v["content"]
        return None


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