import sys
import json
import re
import select
import termios
import tty
from datetime import datetime

# Importing custom modules based on the project structure 
from modules.config_loader import load_settings, CONFIG_DIR
from modules.ui import UI
from modules.files import FileModule
from modules.context import ContextManager
from modules.history import HistoryManager
from modules.session import SessionManager
from modules.processor import ResponseProcessor
from modules.policy import PermissionPolicy
from modules.chat import get_chat_provider

class AngelicaAgent:
    def __init__(self):
        """Initializes the agent with settings and necessary managers[cite: 1, 2]."""
        self.settings = load_settings()
        self.ui = UI()
        self.files = FileModule()
        self.context_manager = ContextManager(self.files)
        self.log_file = "communication.log"
        
        # Setup AI provider and history 
        model_name = self.settings.get("default_model", "ollama/qwen3:4b")
        self.chat = get_chat_provider(model_name)
        
        self.history = HistoryManager(self.chat, max_tokens=self.settings.get("max_history_tokens", 4000))
        self.session_manager = SessionManager(CONFIG_DIR, self.history, self.context_manager, self.ui)
        self.policy = PermissionPolicy(self.settings.get("permission_policy", "ask"))
        self.processor = ResponseProcessor(self.ui, self.files, self.chat, self.policy)

    def _log_communication(self, direction, content):
        """Logs incoming and outgoing messages for debugging[cite: 3]."""
        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        with open(self.log_file, "a", encoding="utf-8") as f:
            f.write(f"\n{'='*60}\n[{timestamp}] {direction}\n{'-'*60}\n{content}\n{'='*60}\n")

    def _is_esc_pressed(self):
        """Checks if the Escape key was pressed without blocking[cite: 3, 4]."""
        if select.select([sys.stdin], [], [], 0) == ([sys.stdin], [], []):
            char = sys.stdin.read(1)
            if char == '\x1b': return True
        return False

    def _parse_output(self, text):
        """
        Parses AI output into:
        1. Thoughts (inside <think> tags) [cite: 5, 7]
        2. A single JSON command (raw JSON outside markdown)
        3. Plain text message (if no command is found) [cite: 20]
        """
        thoughts = []
        command = None
        plain_text = ""

        # 1. Extract thought blocks [cite: 5, 6]
        closing_tags = ["</think>", "</thought>", "</thinking>"]
        tag_used = None
        for tag in closing_tags:
            if tag in text:
                tag_used = tag
                break
        
        content_after_thoughts = text
        if tag_used:
            parts = text.split(tag_used, 1)
            thought_part = parts[0]
            # Clean opening tags [cite: 7]
            thought_part = re.sub(r'<(?:thought|thinking|think)>', '', thought_part, flags=re.IGNORECASE)
            thoughts.append(thought_part.strip())
            content_after_thoughts = parts[1].strip()
        
        # 2. Search for the first valid JSON object in the remaining text [cite: 10, 11]
        json_matches = re.findall(r'(\{.*?\})', content_after_thoughts, re.DOTALL)
        for candidate in json_matches:
            try:
                data = json.loads(candidate)
                if isinstance(data, dict) and "type" in data:
                    command = data
                    break 
            except:
                continue

        # 3. If no command is present, treat the non-thought content as plain text [cite: 20, 21]
        if not command:
            plain_text = re.sub(r'<(?:thought|thinking|think)>.*?</(?:thought|thinking|think)>', '', text, flags=re.DOTALL | re.IGNORECASE).strip()
            if not tag_used and not thoughts:
                plain_text = text.strip()
        
        return thoughts, command, plain_text

    def get_quiet_response(self, query):
        """Fetches AI response while showing a status spinner in the UI[cite: 12, 13]."""
        full_text = ""
        old_attr = termios.tcgetattr(sys.stdin)
        tty.setcbreak(sys.stdin.fileno())
        try:
            self._log_communication("OUTGOING TO AI", query)
            with self.ui.console.status("[bold cyan]🤖 Angelica is thinking...") as status:
                for chunk in self.chat.get_streaming_response(query, self.history.get_history_for_api()):
                    if self._is_esc_pressed():
                        self.ui.print_system("\n🛑 Operation cancelled by user.")
                        break
                    full_text += chunk
            self._log_communication("INCOMING FROM AI", full_text)
            return full_text
        finally:
            termios.tcsetattr(sys.stdin, termios.TCSADRAIN, old_attr)

    def run(self):
        """Main agent loop handling input and the command execution lifecycle[cite: 15, 17, 24]."""
        self.ui.print_system("✨ Angelica-AI is ready.")
        
        while True:
            try:
                # Display current context stats [cite: 15, 16]
                stats = self.context_manager.get_stats()
                user_input = input(f"\n❯ You [Files:{stats[0]} | ~{stats[1]}tk] > ").strip()
                
                if not user_input: continue
                if user_input.startswith("/exit"): break

                self.history.add_message("user", user_input)
                current_query = self.context_manager.get_context_prompt() + user_input
                
                active_loop = True
                while active_loop:
                    response = self.get_quiet_response(current_query)
                    if not response: break
                    
                    self.history.add_message("assistant", response)
                    thoughts, command, plain_text = self._parse_output(response)

                    # 1. Output AI thoughts in gray italic [cite: 18, 19]
                    for thought in thoughts:
                        self.ui.console.print(f"[grey37][italic]💭 {thought.strip()}[/italic][/grey37]")

                    # 2. Command Execution Lifecycle
                    if command:
                        active_loop = False # Default to stopping unless control is requested
                        
                        # Phase: Before Execution
                        if command.get("before_execution"):
                            self.ui.console.print(f"\n[bold cyan]🤖 Plan:[/] {command['before_execution']}")

                        # Phase: During Execution (Spinner)
                        status_msg = command.get("during_execution", "Processing action...")
                        with self.ui.console.status(f"[bold yellow]{status_msg}"):
                            result = self.processor.process_single_action(command) # [cite: 23]
                        
                        # Phase: After Execution
                        if command.get("after_execution") and result.get("status") != "failed":
                            self.ui.console.print(f"[bold green]✅ {command['after_execution']}[/]")
                        
                        # Loopback logic: return control if requested OR if action failed [cite: 24]
                        if result.get("status") == "failed" or command.get("return_control") is True:
                            active_loop = True
                            current_query = f"System Result ({result.get('status')}):\n{result.get('output')}"
                            self.history.add_message("system", current_query)
                    
                    # 3. Text output (only if no command was issued) [cite: 21]
                    elif plain_text.strip():
                        # Clean technical markers from text if any [cite: 20]
                        display_text = re.sub(r'\{.*?\}', '', plain_text, flags=re.DOTALL).strip()
                        if display_text:
                            self.ui.console.print(f"\n[bold white]🤖 Angelica:[/]\n{display_text}")
                        active_loop = False

                self.history.check_and_summarize(self.ui)

            except KeyboardInterrupt:
                break
            except Exception as e:
                self.ui.print_error(f"Critical Error: {e}") [cite: 25]

if __name__ == "__main__":
    agent = AngelicaAgent()
    agent.run()