import unittest
import asyncio
from unittest.mock import MagicMock, AsyncMock, patch
from agent import AngelicaAgent
from modules.parser import Segment

class TestLoopDetection(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.ui = MagicMock()
        # Ensure ALL async UI methods are AsyncMocks to prevent TypeError in create_task
        self.ui.print_error = AsyncMock()
        self.ui.print_system = AsyncMock()
        self.ui.start_thinking = AsyncMock()
        self.ui.stop_loading = AsyncMock()
        self.ui.start_action = AsyncMock()
        self.ui.print_message = AsyncMock()
        self.ui.print_plan = AsyncMock()
        self.ui.print_thought = AsyncMock()
        self.ui.print_confirmation = AsyncMock()
        self.ui.print_command_result = AsyncMock()
        # Stop loop after limits if reached
        self.ui.confirm_continue = AsyncMock(return_value=False)

        with patch('agent.load_settings', return_value={}), \
             patch('agent.get_chat_provider'), \
             patch('agent.ToolManager'), \
             patch('agent.ContextManager'), \
             patch('agent.HistoryManager') as HM, \
             patch('agent.SessionManager'):
            self.agent = AngelicaAgent(ui=self.ui)
            self.agent.history = HM.return_value
            self.agent.history.add_message = MagicMock()
            self.agent.history.get_history_for_api = MagicMock(return_value=[])
            self.agent.history.check_and_summarize = AsyncMock()

    async def test_loop_detection_trigger(self):
        """Test that repeating a failed action triggers a warning."""
        action_cmd = {"type": "run_shell", "command": "bad_cmd"}
        
        # We simulate the parser returning an action segment
        # But we need to vary what the parser returns based on the input response
        # So we better mock parser.parse to return segments based on input
        # OR just mock get_response and parser.parse behavior together.
        
        # Let's mock parser.parse to always return the SAME action for the "bad" response
        # and NO action for the "stop" response.
        
        def parse_side_effect(text):
            if "bad_cmd" in text:
                return [Segment('action', action_cmd)]
            return [Segment('text', "Stopping")]

        self.agent.parser.parse = MagicMock(side_effect=parse_side_effect)
        
        # Mock processor to always fail
        self.agent.processor.process_single_action = AsyncMock(return_value={"status": "failed", "output": "error"})
        
        # Mock AI response sequence:
        # 1. First attempt (fails)
        # 2. Second attempt (fails -> LOOP DETECTED)
        # 3. Third attempt (text only -> loop ends)
        self.agent.get_response = AsyncMock(side_effect=[
            '{"type": "run_shell", "command": "bad_cmd"}', 
            '{"type": "run_shell", "command": "bad_cmd"}',
            'I give up.'
        ])
        
        # Run the loop
        await self.agent.process_user_input("start task")
        
        # Verify warnings
        # The print_error should have been called when loop was detected
        self.ui.print_error.assert_called_with("⚠️ Loop detected: You are repeating the same action that just failed.")
        
        # Verify history injection
        self.agent.history.add_message.assert_any_call("system", "CRITICAL: ⚠️ Loop detected: You are repeating the same action that just failed. Change your strategy.")
        
        # The consecutive repeats should be at least 1 at some point, 
        # but might be reset if the last action (text) cleared it? 
        # Wait, text segment doesn't clear action fingerprint, but no action means no update?
        # Actually, in the code: "elif segment.type == 'action': ... else: self.consecutive_failed_repeats = 0"
        # Wait, the code I wrote:
        # Only updates `consecutive_failed_repeats` inside `elif segment.type == 'action':`.
        # So if the 3rd response has NO action, the counter remains what it was?
        # Let's check the code implementation in agent.py carefully.
        
        # In agent.py:
        # loop detection is INSIDE `elif segment.type == 'action':`
        # So if no action, no check, no reset?
        # That's fine for this test.
        
        # However, we want to ensure it triggered.
        self.assertEqual(self.ui.print_error.call_count, 1)

if __name__ == "__main__":
    unittest.main()