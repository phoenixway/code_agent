import sys
import json
import re
import select
import termios
import tty
from datetime import datetime
import logging

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
        """Initializes the agent with settings and necessary managers."""
        self.settings = load_settings()
        self.ui = UI()
        self.files = FileModule()
        self.context_manager = ContextManager(self.files)
        
        # Setup communication logger
        self.comm_log = logging.getLogger('communication')
        self.comm_log.setLevel(logging.INFO)
        handler = logging.FileHandler("communication.log", encoding="utf-8")
        handler.setFormatter(logging.Formatter('%(asctime)s - %(message)s'))
        self.comm_log.addHandler(handler)

        # Setup AI provider and history 
        model_name = self.settings.get("default_model", "ollama/qwen3:4b")
        self.chat = get_chat_provider(model_name)
        
        self.history = HistoryManager(self.chat, max_tokens=self.settings.get("max_history_tokens", 4000))
        self.session_manager = SessionManager(CONFIG_DIR, self.history, self.context_manager, self.ui)
        self.policy = PermissionPolicy(self.ui, self.settings.get("permission_policy", "ask"))
        self.processor = ResponseProcessor(self.ui, self.files, self.chat, self.policy)

    def _is_esc_pressed(self):
        """Checks if the Escape key was pressed without blocking."""
        if select.select([sys.stdin], [], [], 0) == ([sys.stdin], [], []):
            char = sys.stdin.read(1)
            if char == '\x1b': return True
        return False

    def _parse_output(self, text):
        thoughts = []
        command = None
        
        # 1. Extract and parse command (JSON)
        command_json = None
        json_match = re.search(r'```json\s*(\{.*?\})\s*```|(\{.*?\})', text, re.DOTALL)
        if json_match:
            potential_json = json_match.group(1) or json_match.group(2)
            try:
                data = json.loads(potential_json)
                if isinstance(data, dict) and "type" in data:
                    command = data
                    text = text.replace(json_match.group(0), '', 1)
            except json.JSONDecodeError:
                pass

        # 2. Extract thoughts
        thought_pattern = r'<(?:think|thought|thinking)>(.*?)</(?:think|thought|thinking)>'
        thought_matches = re.findall(thought_pattern, text, re.DOTALL | re.IGNORECASE)
        if thought_matches:
            for thought in thought_matches:
                thoughts.append(thought.strip())
            text = re.sub(thought_pattern, '', text, flags=re.DOTALL | re.IGNORECASE)

        # 3. Clean up and get plain text
        plain_text = re.sub(r'</?(?:think|thought|thinking|tool_code|tool_call|json|code|text|message)\b.*?>', '', text, flags=re.IGNORECASE)
        plain_text = re.sub(r'^Text Message:\s*', '', plain_text, flags=re.IGNORECASE).strip()
        
        return thoughts, command, plain_text

    def get_quiet_response(self, query):
        full_text = ""
        old_attr = termios.tcgetattr(sys.stdin)
        tty.setcbreak(sys.stdin.fileno())
        try:
            self.comm_log.info(f"OUTGOING TO AI:\n{query}")
            
            print("")
            with self.ui.console.status("[bold cyan]🤖 Angelica is thinking...") as status:
                for chunk in self.chat.get_streaming_response(query, self.history.get_history_for_api()):
                    if self._is_esc_pressed():
                        self.ui.print_system("\n🛑 Operation cancelled.")
                        break
                    full_text += chunk
            
            self.comm_log.info(f"INCOMING FROM AI:\n{full_text}")
            return full_text
        finally:
            termios.tcsetattr(sys.stdin, termios.TCSADRAIN, old_attr)


    def run(self):
        self.ui.print_system("✨ Angelica-AI is ready.")
        
        while True:
            try:
                stats = self.context_manager.get_stats()
                user_input = input(f"\n❯ You [Files:{stats[0]} | ~{stats[1]}tk] > ").strip()
                
                if not user_input: continue
                if user_input.startswith("/exit"): break

                self.history.add_message("user", user_input)
                
                context_info = self.context_manager.get_context_prompt()
                current_query = context_info if context_info else ""

                active_loop = True
                while active_loop:
                    response = self.get_quiet_response(current_query)
                    if not response: break
                    
                    self.history.add_message("assistant", response)
                    thoughts, command, plain_text = self._parse_output(response)

                    for thought in thoughts:
                        if thought.strip():
                            self.ui.console.print(f"[grey37][italic]💭 {thought.strip()}[/italic][/grey37]")

                    if command:
                        active_loop = False 
                        if command.get("before_execution"):
                            self.ui.console.print(f"\n[bold cyan]🤖 Plan:[/] {command['before_execution']}")

                        status_msg = command.get("during_execution", "Processing...")
                        with self.ui.console.status(f"[bold yellow]{status_msg}"):
                            result = self.processor.process_single_action(command)
                        
                        if command.get("after_execution") and result.get("status") != "failed":
                            self.ui.console.print(f"[bold green]✅ {command['after_execution']}[/]")
                        
                        if result.get("status") == "failed" or command.get("return_control") is True:
                            active_loop = True
                            current_query = f"SYSTEM RESULT:\n{result.get('output')}"
                            self.history.add_message("system", current_query)
                    
                    elif plain_text.strip():
                        self.ui.console.print(f"\n[bold white]🤖 Angelica:[/]\n{plain_text}")
                        active_loop = False

                self.history.check_and_summarize(self.ui)

            except KeyboardInterrupt: break
            except Exception as e: self.ui.print_error(f"Error: {e}")

if __name__ == "__main__":
    agent = AngelicaAgent()
    agent.run()