import asyncio
import unittest
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

from modules.agent.orchestrator import Orchestrator
from modules.agent.state_manager import AgentState
from modules.parser import Segment


class TestOrchestratorInterrupt(unittest.IsolatedAsyncioTestCase):
    async def test_interrupt_cancels_active_dispatch_task(self):
        ui = SimpleNamespace(
            print_error=AsyncMock(),
            print_system=AsyncMock(),
            start_thinking=AsyncMock(),
            stop_loading=AsyncMock(),
            confirm_continue=AsyncMock(return_value=False),
            confirm_loop_recovery=AsyncMock(return_value="stop"),
        )
        state = AgentState()

        history = SimpleNamespace(
            add_message=MagicMock(),
            check_and_summarize=AsyncMock(),
            current_token_count=0,
            max_tokens=4096,
        )

        dispatcher_started = asyncio.Event()
        dispatcher_cancelled = asyncio.Event()

        async def blocking_dispatch(_segments, _state):
            dispatcher_started.set()
            try:
                await asyncio.sleep(30)
            except asyncio.CancelledError:
                dispatcher_cancelled.set()
                raise
            return [], [], False

        model_client = SimpleNamespace(
            get_streaming_response=AsyncMock(
                return_value='<action>{"type":"run_shell","command":"sleep 30"}</action>'
            )
        )
        parser = SimpleNamespace(
            parse=MagicMock(return_value=[Segment("action", {"type": "run_shell", "command": "sleep 30"})]),
            reconstruct=MagicMock(return_value=""),
        )

        config = SimpleNamespace(
            MAX_SESSION_SECONDS=120,
            MAX_CONSECUTIVE_CALLS=10,
            MAX_STEP_SECONDS=60,
            LOOP_ERROR_REPEAT_THRESHOLD=2,
            MALFORMED_ACTION_GRACE_STEPS=1,
            RECOVERABLE_ERROR_RETRY_BUDGET=2,
            CRITICAL_ERROR_RETRY_BUDGET=1,
        )

        agent = SimpleNamespace(
            ui=ui,
            state=state,
            history=history,
            model_client=model_client,
            action_dispatcher=SimpleNamespace(dispatch_segments=blocking_dispatch),
            parser=parser,
            config=config,
            tool_manager=SimpleNamespace(get_tools_prompt=MagicMock(return_value="")),
            context_manager=SimpleNamespace(get_context_prompt=MagicMock(return_value="")),
            log=None,
        )

        orchestrator = Orchestrator(agent)
        main_task = asyncio.create_task(orchestrator.process("compile"))

        await asyncio.wait_for(dispatcher_started.wait(), timeout=2)
        self.assertIsNotNone(state.current_task)
        self.assertFalse(state.current_task.done())

        state.current_task.cancel()
        await asyncio.wait_for(main_task, timeout=2)

        self.assertTrue(dispatcher_cancelled.is_set())
        ui.stop_loading.assert_awaited()


if __name__ == "__main__":
    unittest.main()
