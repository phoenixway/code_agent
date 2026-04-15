import unittest
from unittest.mock import MagicMock, AsyncMock, patch
from agent import AngelicaAgent

class TestHistoryLogic(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.ui = MagicMock()
        self.ui.stop_loading = AsyncMock()
        self.ui.start_thinking = AsyncMock()
        self.ui.start_action = AsyncMock()
        self.ui.print_thought = AsyncMock()
        self.ui.print_message = AsyncMock()
        self.ui.print_tool_call = AsyncMock()
        self.ui.print_plan = AsyncMock()
        self.ui.print_confirmation = AsyncMock()
        self.ui.print_command_result = AsyncMock()
        self.ui.print_shell_start = AsyncMock(return_value=MagicMock())
        self.ui.update_shell_result = AsyncMock()
        self.ui.print_read_file_start = AsyncMock(return_value=MagicMock())
        self.ui.update_read_file_result = AsyncMock()
        self.ui.print_edit_file_start = AsyncMock(return_value=MagicMock())
        self.ui.update_edit_file_result = AsyncMock()
        self.ui.print_error = AsyncMock()
        self.ui.print_system = AsyncMock()
        
        with patch('agent.load_settings', return_value={}), \
             patch('agent.get_chat_provider'), \
             patch('agent.ToolManager'), \
             patch('agent.ContextManager'), \
             patch('agent.HistoryManager'), \
             patch('agent.SessionManager'), \
             patch('agent.AngelicaAgent.set_history_size', return_value=None):
            self.agent = AngelicaAgent(ui=self.ui)

        self.agent.history.add_message = MagicMock()
        self.agent.history.check_and_summarize = AsyncMock()
        self.agent.processor = MagicMock()
        self.agent.processor.process_single_action = AsyncMock()
        self.agent.parser = MagicMock()
        self.agent.parser.reconstruct = MagicMock(return_value="<think>stub</think>")
        self.ui.confirm_continue = AsyncMock(return_value=False)

    async def test_successful_execution_history(self):
        """Test history update on successful execution."""
        response = '<think>I should run a command.</think><action>{"type": "run_shell", "command": "ls"}</action>'
        self.agent.parser.parse.return_value = [
            MagicMock(type='thought', content='I should run a command.'),
            MagicMock(type='action', content={'type': 'run_shell', 'command': 'ls'})
        ]
        self.agent.processor.process_single_action.return_value = {"status": "success", "output": "file1.txt"}
        
        with patch.object(self.agent, 'get_response', new_callable=AsyncMock) as mock_get_response:
            mock_get_response.side_effect = [response, ""]
            await self.agent.process_user_input("test")

        self.assertEqual(self.agent.processor.process_single_action.call_count, 1)
        system_calls = [
            call for call in self.agent.history.add_message.call_args_list
            if call.args and call.args[0] == "system"
        ]
        self.assertTrue(any("SYSTEM RESULT for `run_shell`" in call.args[1] for call in system_calls))

    async def test_failed_execution_history(self):
        """Test history update on failed execution."""
        response = '<think>Thinking...</think><action>{"type": "cmd1"}</action><action>{"type": "cmd2"}</action>'
        self.agent.parser.parse.return_value = [
            MagicMock(type='thought', content='Thinking...'),
            MagicMock(type='action', content={'type': 'cmd1'}),
            MagicMock(type='action', content={'type': 'cmd2'})
        ]
        self.agent.processor = MagicMock()
        self.agent.processor.process_single_action = AsyncMock(return_value={"status": "failed", "output": "error"})
        
        with patch.object(self.agent, 'get_response', new_callable=AsyncMock) as mock_get_response:
            mock_get_response.side_effect = [response, ""]
            await self.agent.process_user_input("test")

        self.assertEqual(self.agent.processor.process_single_action.call_count, 1)
        system_calls = [
            call for call in self.agent.history.add_message.call_args_list
            if call.args and call.args[0] == "system"
        ]
        self.assertTrue(any("SYSTEM RESULT for `cmd1`" in call.args[1] for call in system_calls))

    async def test_no_action_history(self):
        """Test history update for response with no actions."""
        response = '<think>Just a thought.</think>Some text.'
        self.agent.parser.parse.return_value = [
            MagicMock(type='thought', content='Just a thought.'),
            MagicMock(type='text', content='Some text.')
        ]
        
        with patch.object(self.agent, 'get_response', new_callable=AsyncMock) as mock_get_response:
            mock_get_response.return_value = response
            await self.agent.process_user_input("test")

        self.agent.processor.process_single_action.assert_not_called()
        assistant_calls = [
            call for call in self.agent.history.add_message.call_args_list
            if call.args and call.args[0] == "assistant"
        ]
        self.assertEqual(len(assistant_calls), 1)

if __name__ == "__main__":
    unittest.main()
