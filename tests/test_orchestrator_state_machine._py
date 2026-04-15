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

    async def test_orchestrator_retries_once_when_audit_marker_echoed_without_action(self):
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
        )

        history = SimpleNamespace(
            add_message=MagicMock(),
            check_and_summarize=AsyncMock(),
            current_token_count=0,
            max_tokens=4096,
        )
        model_client = SimpleNamespace(
            get_streaming_response=AsyncMock(
                side_effect=[
                    '<think>x</think>\n<previously_performed_action type="write_file" path="a.txt" />',
                    '<action type="search_content">{"path":"a.txt","pattern":"x"}</action>',
                    "done",
                ]
            )
        )
        parser = ResponseParser()

        async def dispatch_segments(segments, _st):
            sys_results = []
            for seg in segments:
                if seg.type == "action":
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

        queries = [call.args[0] for call in model_client.get_streaming_response.await_args_list]
        self.assertGreaterEqual(len(queries), 2)
        self.assertIn("Do not output audit markers", queries[1])
        self.assertIn("multiple separate <action>...</action> blocks are allowed", queries[1])
        self.assertIn("JSON array of read-only action objects", queries[1])
        self.assertNotIn("Return EXACTLY ONE valid <action> JSON block", queries[1])
        ui.print_error.assert_not_awaited()

    async def test_orchestrator_malformed_action_recovery_allows_read_only_batching(self):
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
        )
        history = SimpleNamespace(
            add_message=MagicMock(),
            check_and_summarize=AsyncMock(),
            current_token_count=0,
            max_tokens=4096,
        )
        model_client = SimpleNamespace(
            get_streaming_response=AsyncMock(
                side_effect=[
                    '<action>[{"path":"a.txt"}]</action>',
                    '<action type="read_file">{"path":"a.txt"}</action>',
                    "done",
                ]
            )
        )
        parser = ResponseParser()

        async def dispatch_segments(segments, _st):
            if any(seg.type == "action" for seg in segments):
                return segments, ["SYSTEM RESULT for `read_file`: ok"], False
            return segments, [], False

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

        queries = [call.args[0] for call in model_client.get_streaming_response.await_args_list]
        self.assertGreaterEqual(len(queries), 2)
        self.assertIn("Return only valid <action> content for the next step.", queries[1])
        self.assertIn("multiple separate <action>...</action> blocks are allowed", queries[1])
        self.assertIn("JSON array of read-only action objects", queries[1])
        self.assertIn("For any state-changing step, return only one valid <action>.", queries[1])
        self.assertNotIn("Return EXACTLY ONE valid <action> JSON block", queries[1])

    async def test_orchestrator_stops_after_second_audit_marker_echo_without_action(self):
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
        )

        history = SimpleNamespace(
            add_message=MagicMock(),
            check_and_summarize=AsyncMock(),
            current_token_count=0,
            max_tokens=4096,
        )
        model_client = SimpleNamespace(
            get_streaming_response=AsyncMock(
                side_effect=[
                    '<previously_performed_action type="edit_file" path="a.txt" />',
                    '<previously_performed_action type="edit_file" path="a.txt" />',
                ]
            )
        )
        parser = ResponseParser()

        async def dispatch_segments(_segments, _st):
            return [], [], False

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

        ui.print_error.assert_awaited()

    async def test_health_metrics_count_actions_from_parsed_segments(self):
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
        )

        history = SimpleNamespace(
            add_message=MagicMock(),
            check_and_summarize=AsyncMock(),
            current_token_count=0,
            max_tokens=4096,
        )
        model_client = SimpleNamespace(
            get_streaming_response=AsyncMock(
                side_effect=[
                    '<action type="search_content">{"path":"a.txt","pattern":"x"}</action>',
                    "done",
                ]
            )
        )
        parser = ResponseParser()
        log = SimpleNamespace(info=MagicMock(), debug=MagicMock(), warning=MagicMock())

        async def dispatch_segments(segments, _st):
            if any(seg.type == "action" for seg in segments):
                processed = [SimpleNamespace(type="text", content='<previously_performed_action type="search_content" path="a.txt" />')]
                return processed, ["SYSTEM RESULT for `search_content`: ok"], False
            return segments, [], False

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
            log=log,
        )

        orchestrator = Orchestrator(agent)
        await orchestrator.process("go on")

        health_calls = [str(c.args[0]) for c in log.info.call_args_list if c.args and "Health.iteration" in str(c.args[0])]
        self.assertTrue(any("actions_in_step=1" in msg for msg in health_calls))
        self.assertTrue(any("batch_actions_executed=" in msg for msg in health_calls))

    async def test_orchestrator_retries_once_after_malformed_read_file_payload(self):
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
        )
        history = SimpleNamespace(
            add_message=MagicMock(),
            check_and_summarize=AsyncMock(),
            current_token_count=0,
            max_tokens=4096,
        )
        model_client = SimpleNamespace(
            get_streaming_response=AsyncMock(
                side_effect=[
                    '<action type="read_file">{"command":"oops"}</action>',
                    '<action type="read_file">{"path":"a.txt"}</action>',
                    "done",
                ]
            )
        )
        parser = ResponseParser()

        async def dispatch_segments(segments, st):
            for seg in segments:
                if seg.type == "action" and seg.content.get("type") == "read_file" and not seg.content.get("path"):
                    st.pending_loop_stop_info = {
                        "reason": "malformed_read_file_payload",
                        "recoverable": True,
                        "error_code": "MALFORMED_READ_FILE_PAYLOAD",
                        "next_actions": ["read_file"],
                        "command": seg.content.copy(),
                    }
                    return segments, ["SYSTEM RESULT for `read_file`: SYSTEM: Invalid read_file payload."], True
            if any(seg.type == "action" for seg in segments):
                return segments, ["SYSTEM RESULT for `read_file`: ok"], False
            return segments, [], False

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

        queries = [call.args[0] for call in model_client.get_streaming_response.await_args_list]
        self.assertGreaterEqual(len(queries), 2)
        self.assertIn("Return EXACTLY ONE valid read_file action now", queries[1])

    async def test_orchestrator_nudges_model_to_batch_after_repeated_single_read_only_steps(self):
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
            MAX_CONSECUTIVE_CALLS=20,
            MAX_STEP_SECONDS=60,
            LOOP_ERROR_REPEAT_THRESHOLD=2,
            MALFORMED_ACTION_GRACE_STEPS=1,
            RECOVERABLE_ERROR_RETRY_BUDGET=2,
            CRITICAL_ERROR_RETRY_BUDGET=1,
            STATE_CHANGING_OPS={"edit_file", "write_file", "run_shell"},
        )
        history = SimpleNamespace(
            add_message=MagicMock(),
            check_and_summarize=AsyncMock(),
            current_token_count=0,
            max_tokens=4096,
        )
        model_client = SimpleNamespace(
            get_streaming_response=AsyncMock(
                side_effect=[
                    '<action type="read_file">{"path":"a.txt"}</action>',
                    '<action type="read_file">{"path":"b.txt"}</action>',
                    '<action type="read_file">{"path":"c.txt"}</action>',
                    "done",
                ]
            )
        )
        parser = ResponseParser()

        async def dispatch_segments(segments, _st):
            if any(seg.type == "action" for seg in segments):
                return segments, ["SYSTEM RESULT for `read_file`: ok"], False
            return segments, [], False

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
        await orchestrator.process("scan multiple files")

        queries = [call.args[0] for call in model_client.get_streaming_response.await_args_list]
        self.assertGreaterEqual(len(queries), 4)
        self.assertIn("return a compact batch of 3-5 read-only <action> blocks", queries[3].lower())


if __name__ == "__main__":
    unittest.main()
