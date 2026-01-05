import json
import re
import logging
import asyncio

# Importing custom modules
from modules.config_loader import load_settings, CONFIG_DIR
from modules.files import FileModule
from modules.context import ContextManager
from modules.history import HistoryManager
from modules.session import SessionManager
from modules.processor import ResponseProcessor
from modules.policy import PermissionPolicy
from modules.chat import get_chat_provider
from modules.tui_ui import TuiUI

class AngelicaAgent:
    def __init__(self, ui):
        """Initializes the agent with settings and necessary managers."""
        self.ui = ui
        self.settings = load_settings()
        self.files = FileModule()
        self.context_manager = ContextManager(self.files)
        
        # Setup communication logger
        self.comm_log = logging.getLogger('communication')
        self.comm_log.setLevel(logging.INFO)
        handler = logging.FileHandler("communication.log", encoding="utf-8")
        handler.setFormatter(logging.Formatter('%(asctime)s - %(message)s'))
        self.comm_log.addHandler(handler)

        # Setup AI provider and history 
        model_name = self.settings.get("default_model", "ollama/qwen:4b")
        self.chat = get_chat_provider(model_name)
        
        if self.chat is None:
            # Handle the case where provider initialization failed
            error_message = f"Failed to initialize chat provider for model: {model_name}. Please check your API keys and configuration."
            self.ui.print_message(error_message, role="system")
            return # Exit __init__ if chat provider is not available
        
        self.history = HistoryManager(self.chat, max_tokens=self.settings.get("max_history_tokens", 4000))
        self.session_manager = SessionManager(CONFIG_DIR, self.history, self.context_manager, self.ui)
        
        # HACK: Disable 'ask' policy in TUI mode for now, as it's blocking.
        policy_mode = self.settings.get("permission_policy", "ask")
        if isinstance(ui, TuiUI) and policy_mode == "ask":
            policy_mode = "always" 
            
        self.policy = PermissionPolicy(self.ui, policy_mode)
        self.processor = ResponseProcessor(self.ui, self.files, self.chat, self.policy)

    def _parse_output(self, text):
        thoughts = []
        command = None
        
        # 1. Extract and parse command (JSON)
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
        thought_end_pattern = r'</(?:think|thought|thinking)>'
        last_match = None
        for match in re.finditer(thought_end_pattern, text, re.IGNORECASE | re.DOTALL):
            last_match = match
        
        if last_match:
            end_pos = last_match.end()
            thought_block = text[:end_pos]
            text = text[end_pos:]

            cleaned_thought = re.sub(r'</?(?:think|thought|thinking)>', '', thought_block, flags=re.IGNORECASE).strip()
            if cleaned_thought:
                thoughts.append(cleaned_thought)

        # 3. Clean up plain text
        plain_text = re.sub(r'</?(?:think|thought|thinking|tool_code|tool_call|json|code|text|message)\b.*?>', '', text, flags=re.IGNORECASE)
        plain_text = re.sub(r'^Text Message:\s*', '', plain_text, flags=re.IGNORECASE).strip()
        
        return thoughts, command, plain_text

    async def get_response(self, query):
        full_text = ""
        self.comm_log.info(f"OUTGOING TO AI:\n{query}")
        
        if self.chat is None:
            error_message = "Chat provider is not initialized. Cannot get response."
            await self.ui.print_message(error_message, role="system")
            return error_message # Return error message to indicate failure

        try:
            async for chunk in self.chat.get_streaming_response(query, self.history.get_history_for_api()):
                full_text += chunk
        except ProviderAPIError as e:
            error_message = f"System Message: Chat provider error: {e}"
            await self.ui.print_message(error_message, role="system")
            self.comm_log.error(f"Chat provider error: {e}")
            return error_message # Return error message to indicate failure
            
        self.comm_log.info(f"INCOMING FROM AI:\n{full_text}")
        return full_text

    async def process_user_input(self, user_input):
        self.history.add_message("user", user_input)
        
        context_info = self.context_manager.get_context_prompt()
        current_query = context_info if context_info else ""

        active_loop = True
        try:
            await self.ui.start_thinking()
            while active_loop:
                response = await self.get_response(current_query)
                if not response: 
                    active_loop = False
                    break
                
                self.history.add_message("assistant", response)
                thoughts, command, plain_text = self._parse_output(response)

                for thought in thoughts:
                    await self.ui.print_thought(thought)

                if command:
                    active_loop = False
                    if command.get("before_execution"):
                        await self.ui.print_plan(command['before_execution'])
                    
                    status_msg = command.get("during_execution", "Processing...")
                    await self.ui.start_action(status_msg)
                    
                    result = self.processor.process_single_action(command)
                    
                    if command.get("after_execution") and result.get("status") != "failed":
                        await self.ui.print_confirmation(command['after_execution'])
                    
                    if result.get("status") == "failed" or command.get("return_control") is True:
                        active_loop = True
                        current_query = f"SYSTEM RESULT:\n{result.get('output')}"
                        await self.ui.print_command_result(result.get('output'))
                        self.history.add_message("system", current_query)
                
                elif plain_text.strip():
                    await self.ui.print_message(plain_text, role="assistant")
                    active_loop = False

            await self.history.check_and_summarize(self.ui)
        finally:
            await self.ui.stop_loading()