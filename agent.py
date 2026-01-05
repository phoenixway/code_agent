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
from modules.chat import get_chat_provider, ProviderAPIError
from modules.tui_ui import TuiUI

class AngelicaAgent:
    def __init__(self, ui=None):
        """Initializes the agent with settings and necessary managers."""
        self.ui = ui
        self.settings = load_settings()
        self.files = FileModule()
        self.context_manager = ContextManager(self.files)
        self.MAX_CONSECUTIVE_CALLS = 3 # Safeguard against loops
        self.current_task = None # To hold the current running task
        self.is_awaiting_model_selection = False # State for model selection UI
        
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
        
        self.history = HistoryManager(self.chat, logger=self.comm_log, max_tokens=self.settings.get("max_history_tokens", 4000))
        self.session_manager = SessionManager(CONFIG_DIR, self.history, self.context_manager, self.ui)
        
        # HACK: Disable 'ask' policy in TUI mode for now, as it's blocking.
        policy_mode = self.settings.get("permission_policy", "ask")
        if isinstance(ui, TuiUI) and policy_mode == "ask":
            policy_mode = "always" 
            
        self.policy = PermissionPolicy(self.ui, policy_mode)
        self.processor = ResponseProcessor(self.ui, self.files, self.chat, self.policy)

    def _parse_output(self, text: str):
        thoughts = []
        command = None
        
        # 1. Extract thoughts first to isolate them
        thought_end_pattern = r'</(?:think|thought|thinking)>'
        last_match = None
        # Find the last thought tag to handle multiple thought blocks
        for match in re.finditer(thought_end_pattern, text, re.IGNORECASE | re.DOTALL):
            last_match = match
        
        if last_match:
            end_pos = last_match.end()
            thought_block = text[:end_pos]
            text = text[end_pos:] # The rest of the text after the last thought

            cleaned_thought = re.sub(r'</?(?:think|thought|thinking)>', '', thought_block, flags=re.IGNORECASE).strip()
            if cleaned_thought:
                thoughts.append(cleaned_thought)

        # The remaining text is now either a command, plain text, or both.
        remaining_text = text.strip()

        # 2. Look for a command, prioritizing explicit ```json blocks
        json_block_match = re.search(r'```json\s*(\{.*?\})\s*```', remaining_text, re.DOTALL)
        if json_block_match:
            json_str = json_block_match.group(1).strip()
            try:
                data = json.loads(json_str)
                if isinstance(data, dict) and "type" in data:
                    command = data
                    # Remove the JSON block for the final plain text
                    remaining_text = remaining_text.replace(json_block_match.group(0), '', 1).strip()
            except json.JSONDecodeError:
                # If it's a malformed JSON block, treat it as plain text
                pass
        
        # 3. If no command yet, check if the entire remaining text is a JSON object
        if not command and remaining_text.startswith('{') and remaining_text.endswith('}'):
            try:
                data = json.loads(remaining_text)
                if isinstance(data, dict) and "type" in data:
                    command = data
                    # The entire text was a command, so there's no plain text left
                    remaining_text = ""
            except json.JSONDecodeError:
                # It looked like JSON but wasn't valid, so treat it as plain text
                pass

        # 4. Whatever is left is plain text; clean it up.
        plain_text = re.sub(r'</?(?:think|thought|thinking|tool_code|tool_call|json|code|text|message)\b.*?>', '', remaining_text, flags=re.IGNORECASE)
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
            
        self.comm_log.info(f"INCOMING FROM AI (RAW): '{repr(full_text)}'")
        return full_text

    async def switch_model(self, model_name: str):
        """Switches the chat model and re-initializes the history."""
        self.comm_log.info(f"--- Attempting to switch model to: {model_name} ---")

        # Normalize names for comparison (e.g., "ollama/qwen:4b" vs "qwen:4b")
        current_normalized = self.chat.model_name.split('/')[-1]
        selected_normalized = model_name.split('/')[-1]

        if current_normalized == selected_normalized:
            self.comm_log.info(f"Model '{model_name}' is already active. Aborting switch.")
            await self.ui.print_system(f"Model {model_name} is already active.")
            return

        await self.ui.print_system(f"Switching to model: {model_name}...")
        
        self.comm_log.info(f"Calling get_chat_provider for '{model_name}'.")
        new_chat_provider = get_chat_provider(model_name)
        
        if new_chat_provider is None:
            self.comm_log.error(f"Failed to initialize chat provider for '{model_name}'.")
            await self.ui.print_error(f"Failed to initialize model: {model_name}")
            await self.ui.update_header(f"Model: {self.chat.model_name}")
        else:
            self.comm_log.info(f"Successfully initialized new provider: {new_chat_provider.model_name}.")
            self.chat = new_chat_provider
            self.history = HistoryManager(self.chat, logger=self.comm_log, max_tokens=self.settings.get("max_history_tokens", 4000))
            
            # CRITICAL: Update references in the processor
            self.processor.chat = self.chat
            self.processor.ui = self.ui
            
            self.comm_log.info("Agent's chat, history, and processor have been updated.")
            await self.ui.print_system(f"✅ Switched to model: {self.chat.model_name}")
            await self.ui.update_header(f"Model: {self.chat.model_name}")

    async def interrupt(self):
        """Cancels the current running task."""
        if self.current_task and not self.current_task.done():
            self.current_task.cancel()

    async def process_user_input(self, user_input):
        self.history.add_message("user", user_input)
        
        context_info = self.context_manager.get_context_prompt()
        current_query = user_input + ("\n\n" + context_info if context_info else "")


        active_loop = True
        consecutive_ai_calls = 0 # Initialize counter

        try:
            await self.ui.start_thinking()
            while active_loop:
                consecutive_ai_calls += 1 # Increment for each loop turn
                if consecutive_ai_calls > self.MAX_CONSECUTIVE_CALLS:
                    await self.ui.stop_loading()
                    should_continue = await self.ui.confirm_continue(
                        "The agent has performed several actions in a row.\nDo you want to continue?"
                    )
                    if not should_continue:
                        await self.ui.print_system("🛑 Operation stopped by user.")
                        active_loop = False
                        break
                    else:
                        consecutive_ai_calls = 1 # Reset counter and continue
                        await self.ui.start_thinking()
                
                # Create a task to be able to cancel it
                self.current_task = asyncio.create_task(self.get_response(current_query))
                response = await self.current_task
                
                self.comm_log.info(f"LOG_PROCESS_USER_INPUT_PRE_HISTORY: '{repr(response)}'")
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
                        # Прибираємо \n після двокрапки
                        output_text = result.get('output', '').strip()
                        system_msg = f"SYSTEM RESULT: {output_text}"
                        
                        await self.ui.print_command_result(output_text)
                        self.history.add_message("system", system_msg)
                        
                        current_query = system_msg # Set query for the next loop
                
                elif plain_text.strip():
                    await self.ui.print_message(plain_text.strip(), role="assistant")
                    active_loop = False

            await self.history.check_and_summarize(self.ui)
        except asyncio.CancelledError:
            # This is expected when the task is cancelled, so we don't need to re-raise
            # The interrupt() method already printed a message.
            pass
        finally:
            self.current_task = None # Clear the task reference
            await self.ui.stop_loading()