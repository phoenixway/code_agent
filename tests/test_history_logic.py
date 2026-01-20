import unittest
from unittest.mock import MagicMock, AsyncMock, patch
import asyncio
from agent import AngelicaAgent

class TestHistoryLogic(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.ui = AsyncMock()
        
        with patch('agent.load_settings', return_value={}), \
             patch('agent.get_chat_provider'), \
             patch('agent.ToolManager'), \
             patch('agent.ContextManager'), \
             patch('agent.HistoryManager'), \
             patch('agent.SessionManager'), \
             patch('asyncio.create_task'):
            self.agent = AngelicaAgent(ui=self.ui)

        self.agent.history.add_message = MagicMock()
        self.agent.history.add_messages = MagicMock()
        self.agent.history.check_and_summarize = AsyncMock()
        self.agent.processor = MagicMock()
        self.agent.processor.process_single_action = AsyncMock()
        self.agent.parser = MagicMock()

    async def test_successful_execution_history(self):
        """Test history update on successful execution."""
        response = '<think>I should run a command.</think><action>{"type": "run_shell", "command": "ls"}</action>'
        self.agent.parser.parse.return_value = [
            MagicMock(type='thought', content='I should run a command.'),
            MagicMock(type='action', content={'type': 'run_shell', 'command': 'ls'})
        ]
        self.agent.processor.process_single_action.return_value = {"status": "success", "output": "file1.txt"}
        
        with patch.object(self.agent, 'get_response', new_callable=AsyncMock) as mock_get_response:
            mock_get_response.return_value = response
            await self.agent.process_user_input("test")

        self.agent.history.add_messages.assert_called_once()
        pending_history = self.agent.history.add_messages.call_args[0][0]
        
        self.assertEqual(len(pending_history), 3)
        self.assertEqual(pending_history[0]['content'], '<think>I should run a command.</think>')
        self.assertIn('<action>', pending_history[1]['content'])
        self.assertIn('SYSTEM RESULT', pending_history[2]['content'])

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
            mock_get_response.return_value = response
            await self.agent.process_user_input("test")

        self.agent.history.add_messages.assert_called_once()
        pending_history = self.agent.history.add_messages.call_args[0][0]
        
        self.assertEqual(len(pending_history), 3) # thought, action, system_result
        self.assertEqual(self.agent.processor.process_single_action.call_count, 1)

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

        self.agent.history.add_messages.assert_called_once()
        pending_history = self.agent.history.add_messages.call_args[0][0]
        
        self.assertEqual(len(pending_history), 2)
        self.assertEqual(pending_history[0]['content'], '<think>Just a thought.</think>')
        self.assertEqual(pending_history[1]['content'], 'Some text.')

if __name__ == "__main__":
    unittest.main()
