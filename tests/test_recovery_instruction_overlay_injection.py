import unittest
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

from modules.agent.orchestration import Orchestrator
from modules.agent.planner import TaskBoardPlanner
from modules.agent.state_manager import AgentState
from modules.parser import ResponseParser


class RecoveryInstructionOverlayInjectionTests(unittest.IsolatedAsyncioTestCase):
    async def test_pipeline_adds_recovery_instruction_overlay_to_injected_messages(self):
        ui = SimpleNamespace(
            print_error=AsyncMock(),
            print_system=AsyncMock(),
            start_thinking=AsyncMock(),
            stop_loading=AsyncMock(),
            confirm_continue=AsyncMock(return_value=False),
            confirm_loop_recovery=AsyncMock(return_value="stop"),
            print_plan=AsyncMock(),
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
            IMPLEMENT_STAGNATION_LIMIT=2,
            RESEARCH_STAGNATION_LIMIT=4,
            STAGNATION_MAX_DIAGNOSTICS=1,
            INVARIANT_VIOLATION_LIMIT=1,
            PLANNER_ENABLED=True,
            PLANNER_MODE="auto",
            PLANNER_MAX_STEPS=12,
            PLANNER_MAX_VISIBLE_STEPS=4,
            PLANNER_MAX_GOAL_CHARS=240,
            PLANNER_MAX_STEP_TITLE_CHARS=160,
            PLANNER_MAX_STEP_NOTES_CHARS=240,
            PLANNER_ALWAYS_MISSING_RETRY_LIMIT=2,
        )

        recovery_overlay = [
            {
                "role": "system",
                "content": "## CURRENT RECOVERY INSTRUCTIONS\nRetry search_content with literal=true.",
            }
        ]
        history = SimpleNamespace(
            add_message=MagicMock(),
            check_and_summarize=AsyncMock(),
            current_token_count=0,
            max_tokens=4096,
            build_recovery_instruction_injected_messages=MagicMock(return_value=recovery_overlay),
        )

        async def next_response(*args, **kwargs):
            return "Final answer."

        model_client = SimpleNamespace(get_streaming_response=AsyncMock(side_effect=next_response))
        parser = ResponseParser()

        agent = SimpleNamespace(
            ui=ui,
            state=state,
            history=history,
            model_client=model_client,
            action_dispatcher=SimpleNamespace(dispatch_segments=AsyncMock()),
            parser=parser,
            config=config,
            tool_manager=SimpleNamespace(get_tools_prompt=MagicMock(return_value="")),
            context_manager=SimpleNamespace(get_context_prompt=MagicMock(return_value="")),
            planner=TaskBoardPlanner(config),
            memory_board_store=None,
            memory_board_engine=None,
            log=None,
        )

        orchestrator = Orchestrator(agent)
        ctx = SimpleNamespace(
            current_query="fix this issue",
            malformed_action_retries=0,
            audit_marker_retries=0,
            consecutive_calls=0,
            active_loop=True,
            tools_prompt="",
            ctx_prompt="",
        )

        await orchestrator.pipeline._run_model_step(ctx)

        history.build_recovery_instruction_injected_messages.assert_called_once_with(state=state)
        calls = model_client.get_streaming_response.await_args_list
        self.assertEqual(1, len(calls))
        injected_messages = calls[0].kwargs.get("injected_messages") or ()
        injected_text = "\n".join(str(msg.get("content", "")) for msg in injected_messages if isinstance(msg, dict))
        self.assertIn("CURRENT RECOVERY INSTRUCTIONS", injected_text)
        self.assertIn("Retry search_content with literal=true.", injected_text)


if __name__ == "__main__":
    unittest.main()
