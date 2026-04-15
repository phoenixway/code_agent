import unittest
from unittest.mock import AsyncMock, MagicMock, patch

from agent import AngelicaAgent


MOCK_LLM_RESPONSE = """
<think>
I need to read a file, then run a command, and then do something else.
</think>
<action>
{
    "type": "read_file",
    "file_path": "/etc/hosts",
    "return_control": false
}
</action>
<action>
{
    "type": "run_shell",
    "command": "this_will_fail",
    "return_control": true
}
</action>
<action>
{
    "type": "create_file",
    "file_path": "/should/not/happen",
    "content": "hallucination"
}
</action>
"""


class TestAgentTruncation(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        ui = MagicMock()
        ui.stop_loading = AsyncMock()
        ui.start_thinking = AsyncMock()
        ui.start_action = AsyncMock()
        ui.print_thought = AsyncMock()
        ui.print_message = AsyncMock()
        ui.print_tool_call = AsyncMock()
        ui.print_plan = AsyncMock()
        ui.print_confirmation = AsyncMock()
        ui.print_command_result = AsyncMock()
        ui.print_shell_start = AsyncMock(return_value=MagicMock())
        ui.update_shell_result = AsyncMock()
        ui.print_read_file_start = AsyncMock(return_value=MagicMock())
        ui.update_read_file_result = AsyncMock()
        ui.print_edit_file_start = AsyncMock(return_value=MagicMock())
        ui.update_edit_file_result = AsyncMock()
        ui.print_error = AsyncMock()
        ui.print_system = AsyncMock()
        ui.confirm_continue = AsyncMock(return_value=False)

        with patch("agent.load_settings", return_value={}), \
             patch("agent.ToolManager"), \
             patch("agent.ContextManager"), \
             patch("agent.HistoryManager") as MockHistoryManager, \
             patch("agent.SessionManager"), \
             patch("agent.ResponseProcessor") as MockProcessor, \
             patch("agent.PermissionPolicy"), \
             patch("agent.get_chat_provider"), \
             patch("agent.AngelicaAgent.set_history_size", return_value=None):
            self.agent = AngelicaAgent(ui=ui)

        self.agent.history = MockHistoryManager()
        self.agent.processor = MockProcessor()
        self.agent.history.add_message = MagicMock()

    async def test_agent_truncates_on_failure(self):
        self.agent.get_response = AsyncMock(side_effect=[MOCK_LLM_RESPONSE, ""])

        async def process_action_side_effect(command):
            if command.get("type") == "read_file":
                return {"status": "success", "output": "File content here."}
            if command.get("type") == "run_shell":
                return {"status": "failed", "output": "Error: command not found."}
            return {"status": "success", "output": "This should not have been executed."}

        self.agent.processor.process_single_action = AsyncMock(side_effect=process_action_side_effect)

        await self.agent.process_user_input("Run the test scenario.")

        self.assertEqual(self.agent.processor.process_single_action.call_count, 2)
        first_call_args = self.agent.processor.process_single_action.call_args_list[0].args[0]
        second_call_args = self.agent.processor.process_single_action.call_args_list[1].args[0]
        self.assertEqual(first_call_args["type"], "read_file")
        self.assertEqual(second_call_args["type"], "run_shell")

        assistant_message_call = None
        system_result_calls = []
        for call in self.agent.history.add_message.call_args_list:
            if call.args[0] == "assistant":
                assistant_message_call = call
            if call.args[0] == "system" and "SYSTEM RESULT" in call.args[1]:
                system_result_calls.append(call)

        self.assertIsNotNone(
            assistant_message_call,
            "Agent did not save a reconstructed assistant message to history.",
        )

        reconstructed_text = assistant_message_call.args[1]
        self.assertIn("<think>", reconstructed_text)
        self.assertIn('<action type="read_file">', reconstructed_text)
        self.assertIn('<action type="run_shell">', reconstructed_text)
        self.assertNotIn("create_file", reconstructed_text)
        self.assertNotIn("hallucination", reconstructed_text)

        self.assertEqual(len(system_result_calls), 2, "Incorrect number of system results saved to history.")
        self.assertIn("File content here", system_result_calls[0].args[1])
        self.assertIn("Error: command not found", system_result_calls[1].args[1])


if __name__ == "__main__":
    unittest.main()
