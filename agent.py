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
        thoughts = []
        command = None
        remaining_text = text

        # 1. Покращений пошук блоків думок (шукаємо всі збіги)
        thought_pattern = r'<(?:think|thought|thinking)>(.*?)</(?:think|thought|thinking)>'
        thought_matches = re.findall(thought_pattern, remaining_text, re.DOTALL | re.IGNORECASE)
        
        if thought_matches:
            for m in thought_matches:
                thoughts.append(m.strip())
            # Видаляємо всі знайдені блоки думок з тексту
            remaining_text = re.sub(thought_pattern, '', remaining_text, flags=re.DOTALL | re.IGNORECASE).strip()
        
        # 2. Обробка випадку, коли модель забула відкрити тег, але закрила його (або закрила кілька разів)
        if "</think>" in remaining_text:
            # Беремо все до ОСТАННЬОГО закриваючого тегу як думки
            parts = remaining_text.rsplit("</think>", 1)
            raw_thoughts = parts[0].replace("<think>", "").strip()
            if raw_thoughts:
                thoughts.append(raw_thoughts)
            remaining_text = parts[1].strip()

        # 3. Пошук JSON (шукаємо перший валідний об'єкт)
        json_match = re.search(r'(\{.*?\})', remaining_text, re.DOTALL)
        if json_match:
            try:
                data = json.loads(json_match.group(1))
                if isinstance(data, dict) and "type" in data:
                    command = data
                    # Видаляємо JSON з фінального тексту, щоб він не дублювався
                    remaining_text = remaining_text.replace(json_match.group(1), "").strip()
            except: 
                pass

        # 4. Фінальне очищення тексту від залишків тегів, які модель могла вигадати
        plain_text = re.sub(r'<(?:think|thought|thinking|tool_call)>.*?</(?:think|thought|thinking|tool_call)>', '', remaining_text, flags=re.DOTALL | re.IGNORECASE).strip()
        
        # Видаляємо маркер "Text Message:", якщо модель його додала за інерцією з інструкцій
        plain_text = re.sub(r'^Text Message:\s*', '', plain_text, flags=re.IGNORECASE).strip()
            
        return thoughts, command, plain_text
    def get_quiet_response(self, query):
        full_text = ""
        old_attr = termios.tcgetattr(sys.stdin)
        tty.setcbreak(sys.stdin.fileno())
        try:
            self._log_communication("OUTGOING TO AI", query)
            
            # Add \n at the beginning of the status message
            print("")  # Move to a new line before status
            with self.ui.console.status("[bold cyan]🤖 Angelica is thinking...") as status:
                for chunk in self.chat.get_streaming_response(query, self.history.get_history_for_api()):
                    if self._is_esc_pressed():
                        self.ui.print_system("\n🛑 Operation cancelled.")
                        break
                    full_text += chunk
            
            self._log_communication("INCOMING FROM AI", full_text)
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

                # 1. Додаємо в історію ТІЛЬКИ ТУТ
                self.history.add_message("user", user_input)
                
                # 2. Формуємо початковий query. 
                # Якщо є файли в контексті, передаємо їх як системну інструкцію.
                # Саме повідомлення користувача вже є в історії, тому query може бути порожнім 
                # або містити лише контекст.
                context_info = self.context_manager.get_context_prompt()
                current_query = context_info if context_info else ""

                active_loop = True
                while active_loop:
                    # Якщо history вже містить user_input, деякі провайдери 
                    # вимагають, щоб query не дублював останнє повідомлення.
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
                        
                        # Логіка повернення контролю (Loopback)
                        if result.get("status") == "failed" or command.get("return_control") is True:
                            active_loop = True
                            # Тепер query використовується для передачі результату дії
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