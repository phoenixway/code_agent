import pytest
import asyncio
from unittest.mock import AsyncMock, MagicMock, patch

# Make sure the app module is in the path
import sys
import os
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from agent import AngelicaAgent
from modules.parser import Segment

# Mocked LLM response with a chain of actions
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

@pytest.fixture
def mock_agent():
    """Fixture to create a mocked AngelicaAgent instance."""
    with patch('agent.load_settings', return_value={}), \
         patch('agent.ToolManager'), \
         patch('agent.ContextManager'), \
         patch('agent.HistoryManager') as MockHistoryManager, \
         patch('agent.SessionManager'), \
         patch('agent.ResponseProcessor') as MockProcessor, \
         patch('agent.PermissionPolicy'), \
         patch('agent.get_chat_provider'):

        # Patch the problematic asyncio.create_task call during initialization
        with patch('asyncio.create_task'):
            agent = AngelicaAgent(ui=AsyncMock())
        
        agent.history = MockHistoryManager()
        agent.processor = MockProcessor()
        agent.history.add_message = MagicMock() # Mock the add_message method
        return agent

async def test_agent_truncates_on_failure(mock_agent):
    """
    Tests that the agent stops execution and truncates history when an action fails.
    """
    # 1. Configure Mocks
    # Mock the response from the LLM
    mock_agent.get_response = AsyncMock(return_value=MOCK_LLM_RESPONSE)

    # Mock the results from the tool processor
    async def process_action_side_effect(command):
        if command.get("type") == "read_file":
            return {"status": "success", "output": "File content here."}
        elif command.get("type") == "run_shell":
            return {"status": "failed", "output": "Error: command not found."}
        # The third action should not even be called, but we add a default
        # return just in case to make it obvious if the test logic is flawed.
        return {"status": "success", "output": "This should not have been executed."}

    mock_agent.processor.process_single_action = AsyncMock(side_effect=process_action_side_effect)

    # 2. Run the processing loop
    await mock_agent.process_user_input("Run the test scenario.")

    # 3. Assertions
    # A. Check that only the first two actions were attempted
    assert mock_agent.processor.process_single_action.call_count == 2
    first_call_args = mock_agent.processor.process_single_action.call_args_list[0].args[0]
    second_call_args = mock_agent.processor.process_single_action.call_args_list[1].args[0]
    assert first_call_args['type'] == 'read_file'
    assert second_call_args['type'] == 'run_shell'

    # B. Check that history was updated correctly with the truncated, reconstructed message
    # The agent should have called add_message for the user input, system prompt,
    # the reconstructed assistant message, and then the system results.
    # We are interested in the assistant's message.
    
    # Find the call that added the assistant's reconstructed message
    assistant_message_call = None
    system_result_calls = []
    for call in mock_agent.history.add_message.call_args_list:
        if call.args[0] == 'assistant':
            assistant_message_call = call
        if call.args[0] == 'system' and 'SYSTEM RESULT' in call.args[1]:
             system_result_calls.append(call)


    assert assistant_message_call is not None, "Agent did not save a reconstructed assistant message to history."

    reconstructed_text = assistant_message_call.args[1]
    
    # Verify the content of the reconstructed message
    assert "<think>" in reconstructed_text
    assert "\"type\": \"read_file\"" in reconstructed_text
    assert "\"type\": \"run_shell\"" in reconstructed_text
    # Crucially, the third "hallucinated" action should NOT be in the history
    assert "create_file" not in reconstructed_text
    assert "hallucination" not in reconstructed_text

    # C. Verify that system results for executed actions were added
    assert len(system_result_calls) == 2, "Incorrect number of system results saved to history."
    assert "File content here" in system_result_calls[0].args[1]
    assert "Error: command not found" in system_result_calls[1].args[1]
