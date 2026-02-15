import unittest
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

from modules.agent.orchestrator import Orchestrator
from modules.agent.planner import TaskBoardPlanner
from modules.agent.state_manager import AgentState
from modules.parser import ResponseParser


class TestOrchestratorPlanner(unittest.IsolatedAsyncioTestCase):
    async def test_injects_taskboard_snapshot_into_next_query(self):
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

        history = SimpleNamespace(
            add_message=MagicMock(),
            check_and_summarize=AsyncMock(),
            current_token_count=0,
            max_tokens=4096,
        )

        responses = [
            (
                '<taskboard>{"version":1,"goal":"Fix bug","planner_enabled":true,'
                '"active_step_id":"s1","steps":[{"id":"s1","title":"Read file","status":"in_progress"},'
                '{"id":"s2","title":"Edit file","status":"todo"}]}</taskboard>'
                '<action type="read_file">{"path":"a.txt"}</action>'
            ),
            "done",
        ]
        model_client = SimpleNamespace(get_streaming_response=AsyncMock(side_effect=responses))
        parser = ResponseParser()

        async def dispatch_segments(segments, _state):
            return segments, ["SYSTEM RESULT for `read_file`: ok"], False

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
            planner=TaskBoardPlanner(config),
            log=None,
        )

        orchestrator = Orchestrator(agent)
        await orchestrator.process("fix this issue")

        queries = [call.args[0] for call in model_client.get_streaming_response.await_args_list]
        self.assertEqual(len(queries), 2)
        self.assertIn("SYSTEM TASKBOARD SNAPSHOT", queries[1])

    async def test_always_mode_retries_when_taskboard_missing(self):
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
            PLANNER_MODE="always",
            PLANNER_MAX_STEPS=12,
            PLANNER_MAX_VISIBLE_STEPS=4,
            PLANNER_MAX_GOAL_CHARS=240,
            PLANNER_MAX_STEP_TITLE_CHARS=160,
            PLANNER_MAX_STEP_NOTES_CHARS=240,
            PLANNER_ALWAYS_MISSING_RETRY_LIMIT=2,
        )

        history = SimpleNamespace(
            add_message=MagicMock(),
            check_and_summarize=AsyncMock(),
            current_token_count=0,
            max_tokens=4096,
        )

        responses = [
            '<action type="read_file">{"path":"a.txt"}</action>',
            (
                '<taskboard>{"version":1,"goal":"Fix bug","planner_enabled":true,'
                '"active_step_id":"s1","steps":[{"id":"s1","title":"Read file","status":"in_progress"}]}</taskboard>'
                '<action type="read_file">{"path":"a.txt"}</action>'
            ),
            "done",
        ]
        model_client = SimpleNamespace(get_streaming_response=AsyncMock(side_effect=responses))
        parser = ResponseParser()

        async def dispatch_segments(segments, _state):
            return segments, ["SYSTEM RESULT for `read_file`: ok"], False

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
            planner=TaskBoardPlanner(config),
            log=None,
        )

        orchestrator = Orchestrator(agent)
        await orchestrator.process("fix this issue")

        queries = [call.args[0] for call in model_client.get_streaming_response.await_args_list]
        self.assertGreaterEqual(len(queries), 2)
        self.assertIn("planner_mode=always is enforced", queries[1])


if __name__ == "__main__":
    unittest.main()
