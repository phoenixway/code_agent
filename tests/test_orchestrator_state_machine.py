import unittest
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

from modules.agent.orchestrator import Orchestrator
from modules.agent.state_manager import AgentState
from modules.agent.state_machine import AgentStateMachine
from modules.parser import ResponseParser


class TestOrchestratorStateMachine(unittest.IsolatedAsyncioTestCase):
    async def test_orchestrator_injects_diagnostic_prompt_on_read_loop(self):
        ui = SimpleNamespace(
            print_error=AsyncMock(),
            print_system=AsyncMock(),
            start_thinking=AsyncMock(),
            stop_loading=AsyncMock(),
            confirm_continue=AsyncMock(return_value=False),
            confirm_loop_recovery=AsyncMock(return_value="stop"),
        )
        state = AgentState()
        config = SimpleNamespace(
            MAX_SESSION_SECONDS=120,
            MAX_CONSECUTIVE_CALLS=12,
            MAX_STEP_SECONDS=60,
            LOOP_ERROR_REPEAT_THRESHOLD=2,
            MALFORMED_ACTION_GRACE_STEPS=1,
            RECOVERABLE_ERROR_RETRY_BUDGET=2,
            CRITICAL_ERROR_RETRY_BUDGET=1,
            STATE_CHANGING_OPS={"edit_file", "write_file", "run_shell"},
            IMPLEMENT_STAGNATION_LIMIT=1,
            RESEARCH_STAGNATION_LIMIT=3,
            STAGNATION_MAX_DIAGNOSTICS=1,
        )
        state.state_machine = AgentStateMachine(config)

        history = SimpleNamespace(
            add_message=MagicMock(),
            check_and_summarize=AsyncMock(),
            current_token_count=0,
            max_tokens=4096,
        )

        responses = [
            '<action type="read_file">{"path":"a.txt"}</action>',
            '<action type="read_file">{"path":"a.txt"}</action>',
            "done",
        ]
        model_client = SimpleNamespace(
            get_streaming_response=AsyncMock(side_effect=responses)
        )
        parser = ResponseParser()

        async def dispatch_segments(segments, st):
            sys_results = []
            for seg in segments:
                if seg.type == "action":
                    result = {"status": "success", "output": "ok"}
                    st.record_action_result(seg.content, result)
                    st.state_machine.note_action(seg.content, result, config.STATE_CHANGING_OPS)
                    sys_results.append(f"SYSTEM RESULT for `{seg.content.get('type')}`: ok")
            return segments, sys_results, False

        agent = SimpleNamespace(
            ui=ui,
            state=state,
            history=history,
            model_client=model_client,
            action_dispatcher=SimpleNamespace(dispatch_segments=dispatch_segments),
            parser=parser,
            config=config,
            tool_manager=SimpleNamespace(get_tools_prompt=MagicMock(return_value="")),
            context_manager=SimpleNamespace(get_context_prompt=MagicMock(return_value="")),
            log=None,
        )

        orchestrator = Orchestrator(agent)
        await orchestrator.process("go on")

        # After repeated read-only action, next model call should be diagnostic.
        queries = [call.args[0] for call in model_client.get_streaming_response.await_args_list]
        self.assertTrue(any("SYSTEM_DIAGNOSTIC" in q for q in queries))


if __name__ == "__main__":
    unittest.main()
