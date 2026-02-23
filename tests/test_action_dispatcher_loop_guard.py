import unittest
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

from modules.agent.action_dispatcher import ActionDispatcher
from modules.agent.state_manager import AgentState
from modules.agent.state_machine import AgentStateMachine


class TestActionDispatcherLoopGuard(unittest.IsolatedAsyncioTestCase):
    async def test_state_machine_policy_denies_cross_target_read(self):
        ui = SimpleNamespace(
            print_edit_file_start=AsyncMock(return_value=object()),
            start_action=AsyncMock(),
            update_edit_file_result=AsyncMock(),
            print_tool_call=AsyncMock(),
            print_plan=AsyncMock(),
            print_command_result=AsyncMock(),
            print_confirmation=AsyncMock(),
            print_shell_start=AsyncMock(return_value=object()),
            update_shell_result=AsyncMock(),
            print_read_file_start=AsyncMock(return_value=object()),
            update_read_file_result=AsyncMock(),
        )
        processor = SimpleNamespace(process_single_action=AsyncMock(return_value={"status": "success", "output": "ok"}))
        config = SimpleNamespace(
            STATE_CHANGING_OPS={"edit_file", "create_file", "run_shell"},
            LOOP_ERROR_REPEAT_THRESHOLD=2,
            READ_ONLY_REPEAT_THRESHOLD=3,
            RECOVERABLE_ERROR_RETRY_BUDGET=2,
            CRITICAL_ERROR_RETRY_BUDGET=1,
            IMPLEMENT_STAGNATION_LIMIT=2,
            RESEARCH_STAGNATION_LIMIT=4,
            STAGNATION_MAX_DIAGNOSTICS=1,
            INVARIANT_VIOLATION_LIMIT=1,
        )
        agent = SimpleNamespace(ui=ui, processor=processor, config=config, log=None)
        dispatcher = ActionDispatcher(agent)
        state = AgentState()
        state.state_machine = AgentStateMachine(config)
        state.state_machine.start_turn("fix bug")
        state.state_machine.note_action(
            {"type": "edit_file", "path": "a.txt", "search_text": "x", "replace_text": "y"},
            {"status": "success", "output": "ok"},
            config.STATE_CHANGING_OPS,
        )

        command = {"type": "read_file", "path": "b.txt"}
        _cmd_copy, result_text, should_stop = await dispatcher._execute_action(command, state)

        self.assertTrue(should_stop)
        self.assertIn("Target file is pinned", result_text)
        processor.process_single_action.assert_not_called()
        self.assertEqual(state.pending_loop_stop_info.get("reason"), "cross_target_read_without_reason")

    async def test_repeated_read_file_no_progress_stops(self):
        ui = SimpleNamespace(
            print_edit_file_start=AsyncMock(return_value=object()),
            start_action=AsyncMock(),
            update_edit_file_result=AsyncMock(),
            print_tool_call=AsyncMock(),
            print_plan=AsyncMock(),
            print_command_result=AsyncMock(),
            print_confirmation=AsyncMock(),
            print_shell_start=AsyncMock(return_value=object()),
            update_shell_result=AsyncMock(),
            print_read_file_start=AsyncMock(return_value=object()),
            update_read_file_result=AsyncMock(),
        )
        processor = SimpleNamespace(
            process_single_action=AsyncMock(
                return_value={"status": "success", "output": "Read file 'a.txt' and added to history as v1."}
            )
        )
        config = SimpleNamespace(
            STATE_CHANGING_OPS={"edit_file", "create_file", "run_shell"},
            LOOP_ERROR_REPEAT_THRESHOLD=2,
            READ_ONLY_REPEAT_THRESHOLD=3,
            RECOVERABLE_ERROR_RETRY_BUDGET=2,
            CRITICAL_ERROR_RETRY_BUDGET=1,
        )
        agent = SimpleNamespace(ui=ui, processor=processor, config=config, log=None)
        dispatcher = ActionDispatcher(agent)
        state = AgentState()
        state.record_action_result = MagicMock(
            return_value={
                "status": "success",
                "error_code": None,
                "recoverable": False,
                "next_actions": [],
                "same_error_repeats": 0,
                "same_action_repeats": 3,
            }
        )

        command = {"type": "read_file", "path": "a.txt"}
        _cmd_copy, result_text, should_stop = await dispatcher._execute_action(command, state)

        self.assertTrue(should_stop)
        self.assertIn("Repeated read_file calls detected", result_text)
        self.assertEqual(state.pending_loop_stop_info.get("reason"), "repeating_no_progress")

    async def test_repeated_search_no_match_stops(self):
        ui = SimpleNamespace(
            print_edit_file_start=AsyncMock(return_value=object()),
            start_action=AsyncMock(),
            update_edit_file_result=AsyncMock(),
            print_tool_call=AsyncMock(),
            print_plan=AsyncMock(),
            print_command_result=AsyncMock(),
            print_confirmation=AsyncMock(),
            print_shell_start=AsyncMock(return_value=object()),
            update_shell_result=AsyncMock(),
            print_read_file_start=AsyncMock(return_value=object()),
            update_read_file_result=AsyncMock(),
        )
        processor = SimpleNamespace(
            process_single_action=AsyncMock(
                return_value={"status": "success", "output": "No matches found."}
            )
        )
        config = SimpleNamespace(
            STATE_CHANGING_OPS={"edit_file", "create_file", "run_shell"},
            LOOP_ERROR_REPEAT_THRESHOLD=2,
            READ_ONLY_REPEAT_THRESHOLD=3,
            RECOVERABLE_ERROR_RETRY_BUDGET=2,
            CRITICAL_ERROR_RETRY_BUDGET=1,
        )
        agent = SimpleNamespace(ui=ui, processor=processor, config=config, log=None)
        dispatcher = ActionDispatcher(agent)
        state = AgentState()
        state.record_action_result = MagicMock(
            return_value={
                "status": "success",
                "error_code": None,
                "recoverable": False,
                "next_actions": [],
                "same_error_repeats": 0,
                "same_action_repeats": 3,
            }
        )

        command = {"type": "search_content", "path": "a.txt", "pattern": "foo"}
        _cmd_copy, result_text, should_stop = await dispatcher._execute_action(command, state)

        self.assertTrue(should_stop)
        self.assertIn("Repeated search_content calls returned no matches", result_text)
        self.assertEqual(state.pending_loop_stop_info.get("error_code"), "SEARCH_NO_MATCH_LOOP")

    async def test_read_file_nested_command_payload_is_normalized(self):
        ui = SimpleNamespace(
            print_edit_file_start=AsyncMock(return_value=object()),
            start_action=AsyncMock(),
            update_edit_file_result=AsyncMock(),
            print_tool_call=AsyncMock(),
            print_plan=AsyncMock(),
            print_command_result=AsyncMock(),
            print_confirmation=AsyncMock(),
            print_shell_start=AsyncMock(return_value=object()),
            update_shell_result=AsyncMock(),
            print_read_file_start=AsyncMock(return_value=object()),
            update_read_file_result=AsyncMock(),
        )
        processor = SimpleNamespace(process_single_action=AsyncMock(return_value={"status": "success", "output": "ok"}))
        config = SimpleNamespace(
            STATE_CHANGING_OPS={"edit_file", "create_file", "run_shell"},
            LOOP_ERROR_REPEAT_THRESHOLD=2,
            READ_ONLY_REPEAT_THRESHOLD=3,
            RECOVERABLE_ERROR_RETRY_BUDGET=2,
            CRITICAL_ERROR_RETRY_BUDGET=1,
        )
        agent = SimpleNamespace(ui=ui, processor=processor, config=config, log=None)
        dispatcher = ActionDispatcher(agent)
        state = AgentState()

        command = {
            "type": "read_file",
            "command": '{"path":"a.txt","before_execution":"b","during_execution":"d","after_execution":"a"}',
        }
        cmd_copy, result_text, should_stop = await dispatcher._execute_action(command, state)

        self.assertFalse(should_stop)
        self.assertIn("SYSTEM RESULT for `read_file`", result_text)
        self.assertEqual(cmd_copy.get("path"), "a.txt")
        processor.process_single_action.assert_awaited()

    async def test_read_file_without_path_is_blocked_with_recovery_hint(self):
        ui = SimpleNamespace(
            print_edit_file_start=AsyncMock(return_value=object()),
            start_action=AsyncMock(),
            update_edit_file_result=AsyncMock(),
            print_tool_call=AsyncMock(),
            print_plan=AsyncMock(),
            print_command_result=AsyncMock(),
            print_confirmation=AsyncMock(),
            print_shell_start=AsyncMock(return_value=object()),
            update_shell_result=AsyncMock(),
            print_read_file_start=AsyncMock(return_value=object()),
            update_read_file_result=AsyncMock(),
        )
        processor = SimpleNamespace(process_single_action=AsyncMock(return_value={"status": "success", "output": "ok"}))
        config = SimpleNamespace(
            STATE_CHANGING_OPS={"edit_file", "create_file", "run_shell"},
            LOOP_ERROR_REPEAT_THRESHOLD=2,
            READ_ONLY_REPEAT_THRESHOLD=3,
            RECOVERABLE_ERROR_RETRY_BUDGET=2,
            CRITICAL_ERROR_RETRY_BUDGET=1,
        )
        agent = SimpleNamespace(ui=ui, processor=processor, config=config, log=None)
        dispatcher = ActionDispatcher(agent)
        state = AgentState()

        command = {"type": "read_file", "command": "not-json"}
        _cmd_copy, result_text, should_stop = await dispatcher._execute_action(command, state)

        self.assertTrue(should_stop)
        self.assertIn("Invalid read_file payload", result_text)
        self.assertEqual(state.pending_loop_stop_info.get("reason"), "malformed_read_file_payload")
        processor.process_single_action.assert_not_called()

    async def test_repeated_read_only_run_shell_stops(self):
        ui = SimpleNamespace(
            print_edit_file_start=AsyncMock(return_value=object()),
            start_action=AsyncMock(),
            update_edit_file_result=AsyncMock(),
            print_tool_call=AsyncMock(),
            print_plan=AsyncMock(),
            print_command_result=AsyncMock(),
            print_confirmation=AsyncMock(),
            print_shell_start=AsyncMock(return_value=object()),
            update_shell_result=AsyncMock(),
            print_read_file_start=AsyncMock(return_value=object()),
            update_read_file_result=AsyncMock(),
        )
        processor = SimpleNamespace(
            process_single_action=AsyncMock(
                return_value={"status": "success", "output": "line1\nline2"}
            )
        )
        config = SimpleNamespace(
            STATE_CHANGING_OPS={"edit_file", "create_file", "run_shell"},
            LOOP_ERROR_REPEAT_THRESHOLD=2,
            READ_ONLY_REPEAT_THRESHOLD=3,
            RECOVERABLE_ERROR_RETRY_BUDGET=2,
            CRITICAL_ERROR_RETRY_BUDGET=1,
        )
        agent = SimpleNamespace(ui=ui, processor=processor, config=config, log=None)
        dispatcher = ActionDispatcher(agent)
        state = AgentState()
        state.record_action_result = MagicMock(
            return_value={
                "status": "success",
                "error_code": None,
                "recoverable": False,
                "next_actions": [],
                "same_error_repeats": 0,
                "same_action_repeats": 3,
            }
        )

        command = {"type": "run_shell", "command": "cat a.txt"}
        _cmd_copy, result_text, should_stop = await dispatcher._execute_action(command, state)

        self.assertTrue(should_stop)
        self.assertIn("Repeated read-only run_shell commands detected", result_text)
        self.assertEqual(state.pending_loop_stop_info.get("error_code"), "READONLY_SHELL_LOOP")

    async def test_blocks_repeated_action_after_malformed_recovery(self):
        ui = SimpleNamespace(
            print_edit_file_start=AsyncMock(return_value=object()),
            start_action=AsyncMock(),
            update_edit_file_result=AsyncMock(),
            print_tool_call=AsyncMock(),
            print_plan=AsyncMock(),
            print_command_result=AsyncMock(),
            print_confirmation=AsyncMock(),
            print_shell_start=AsyncMock(return_value=object()),
            update_shell_result=AsyncMock(),
            print_read_file_start=AsyncMock(return_value=object()),
            update_read_file_result=AsyncMock(),
        )
        processor = SimpleNamespace(process_single_action=AsyncMock(return_value={"status": "success", "output": "ok"}))
        config = SimpleNamespace(
            STATE_CHANGING_OPS={"edit_file", "create_file", "run_shell"},
            LOOP_ERROR_REPEAT_THRESHOLD=2,
            READ_ONLY_REPEAT_THRESHOLD=3,
            RECOVERABLE_ERROR_RETRY_BUDGET=2,
            CRITICAL_ERROR_RETRY_BUDGET=1,
        )
        agent = SimpleNamespace(ui=ui, processor=processor, config=config, log=None)
        dispatcher = ActionDispatcher(agent)
        state = AgentState()

        command = {"type": "read_file", "path": "a.txt"}
        state.forbid_next_action_fingerprint(state.get_action_fingerprint(command))
        _cmd_copy, result_text, should_stop = await dispatcher._execute_action(command, state)

        self.assertTrue(should_stop)
        self.assertIn("repeating the previous action immediately after malformed-action recovery", result_text)
        processor.process_single_action.assert_not_called()
        self.assertEqual(state.pending_loop_stop_info.get("reason"), "repeating_no_progress")

    async def test_repeated_edit_validation_mismatch_stops_early(self):
        ui = SimpleNamespace(
            print_edit_file_start=AsyncMock(return_value=object()),
            start_action=AsyncMock(),
            update_edit_file_result=AsyncMock(),
            print_tool_call=AsyncMock(),
            print_plan=AsyncMock(),
            print_command_result=AsyncMock(),
            print_confirmation=AsyncMock(),
            print_shell_start=AsyncMock(return_value=object()),
            update_shell_result=AsyncMock(),
            print_read_file_start=AsyncMock(return_value=object()),
            update_read_file_result=AsyncMock(),
        )
        processor = SimpleNamespace(
            process_single_action=AsyncMock(
                return_value={
                    "status": "error",
                    "error_code": "VALIDATION_ERROR",
                    "recoverable": True,
                    "output": "Search block not found. Ensure whitespace and indentation match exactly.",
                }
            )
        )
        config = SimpleNamespace(
            STATE_CHANGING_OPS={"edit_file", "create_file", "run_shell"},
            LOOP_ERROR_REPEAT_THRESHOLD=2,
            RECOVERABLE_ERROR_RETRY_BUDGET=2,
            CRITICAL_ERROR_RETRY_BUDGET=1,
        )
        agent = SimpleNamespace(ui=ui, processor=processor, config=config, log=None)

        dispatcher = ActionDispatcher(agent)
        state = AgentState()
        state.record_action_result = MagicMock(
            return_value={
                "status": "error",
                "error_code": "VALIDATION_ERROR",
                "recoverable": True,
                "next_actions": [],
                "same_error_repeats": 2,
            }
        )

        command = {
            "type": "edit_file",
            "path": "a.txt",
            "search_text": "old",
            "replace_text": "new",
        }
        _cmd_copy, result_text, should_stop = await dispatcher._execute_action(command, state)

        self.assertTrue(should_stop)
        self.assertIn("Repeated edit_file search mismatch detected", result_text)
        self.assertIsNotNone(state.pending_loop_stop_info)
        self.assertEqual(state.pending_loop_stop_info.get("reason"), "repeating_failure")

    async def test_dispatch_persists_text_audit_instead_of_action_json(self):
        ui = SimpleNamespace(
            print_edit_file_start=AsyncMock(return_value=object()),
            start_action=AsyncMock(),
            update_edit_file_result=AsyncMock(),
            print_tool_call=AsyncMock(),
            print_plan=AsyncMock(),
            print_command_result=AsyncMock(),
            print_confirmation=AsyncMock(),
            print_shell_start=AsyncMock(return_value=object()),
            update_shell_result=AsyncMock(),
            print_read_file_start=AsyncMock(return_value=object()),
            update_read_file_result=AsyncMock(),
            print_thought=AsyncMock(),
            print_message=AsyncMock(),
        )
        processor = SimpleNamespace(process_single_action=AsyncMock(return_value={"status": "success", "output": "ok"}))
        config = SimpleNamespace(
            STATE_CHANGING_OPS={"edit_file", "create_file", "write_file", "run_shell"},
            LOOP_ERROR_REPEAT_THRESHOLD=2,
            READ_ONLY_REPEAT_THRESHOLD=3,
            RECOVERABLE_ERROR_RETRY_BUDGET=2,
            CRITICAL_ERROR_RETRY_BUDGET=1,
        )
        history = SimpleNamespace(_save_blob=MagicMock(return_value="blob1234567890"))
        agent = SimpleNamespace(ui=ui, processor=processor, config=config, history=history, log=None)
        dispatcher = ActionDispatcher(agent)
        state = AgentState()

        segments = [
            SimpleNamespace(
                type="action",
                content={"type": "write_file", "path": "a.txt", "content": "x" * 500},
            )
        ]
        processed, system_results, should_stop = await dispatcher.dispatch_segments(segments, state)

        self.assertFalse(should_stop)
        self.assertEqual(len(system_results), 1)
        self.assertEqual(processed[0].type, "text")
        self.assertIn("<previously_performed_action", processed[0].content)
        self.assertIn('type="write_file"', processed[0].content)
        self.assertIn('path="a.txt"', processed[0].content)
        self.assertIn('content="REDACTED', processed[0].content)

    async def test_dispatch_executes_multiple_read_only_actions_in_batch(self):
        ui = SimpleNamespace(
            print_edit_file_start=AsyncMock(return_value=object()),
            start_action=AsyncMock(),
            update_edit_file_result=AsyncMock(),
            print_tool_call=AsyncMock(),
            print_plan=AsyncMock(),
            print_command_result=AsyncMock(),
            print_confirmation=AsyncMock(),
            print_shell_start=AsyncMock(return_value=object()),
            update_shell_result=AsyncMock(),
            print_read_file_start=AsyncMock(return_value=object()),
            update_read_file_result=AsyncMock(),
            print_thought=AsyncMock(),
            print_message=AsyncMock(),
        )
        processor = SimpleNamespace(process_single_action=AsyncMock(return_value={"status": "success", "output": "ok"}))
        config = SimpleNamespace(
            STATE_CHANGING_OPS={"edit_file", "create_file", "write_file"},
            LOOP_ERROR_REPEAT_THRESHOLD=2,
            READ_ONLY_REPEAT_THRESHOLD=3,
            RECOVERABLE_ERROR_RETRY_BUDGET=2,
            CRITICAL_ERROR_RETRY_BUDGET=1,
            MAX_READONLY_BATCH_ACTIONS=4,
        )
        history = SimpleNamespace(_save_blob=MagicMock(return_value="blob123"))
        agent = SimpleNamespace(ui=ui, processor=processor, config=config, history=history, log=None)
        dispatcher = ActionDispatcher(agent)
        state = AgentState()

        segments = [
            SimpleNamespace(type="action", content={"type": "read_file", "path": "a.txt"}),
            SimpleNamespace(type="action", content={"type": "search_content", "path": "b.txt", "pattern": "x"}),
        ]
        processed, system_results, should_stop = await dispatcher.dispatch_segments(segments, state)

        self.assertFalse(should_stop)
        self.assertEqual(processor.process_single_action.await_count, 2)
        self.assertEqual(len(processed), 2)
        self.assertTrue(any("[BATCH 1/2]" in msg for msg in system_results))
        self.assertTrue(any("[BATCH 2/2]" in msg for msg in system_results))

    async def test_dispatch_limits_read_only_batch_size(self):
        ui = SimpleNamespace(
            print_edit_file_start=AsyncMock(return_value=object()),
            start_action=AsyncMock(),
            update_edit_file_result=AsyncMock(),
            print_tool_call=AsyncMock(),
            print_plan=AsyncMock(),
            print_command_result=AsyncMock(),
            print_confirmation=AsyncMock(),
            print_shell_start=AsyncMock(return_value=object()),
            update_shell_result=AsyncMock(),
            print_read_file_start=AsyncMock(return_value=object()),
            update_read_file_result=AsyncMock(),
            print_thought=AsyncMock(),
            print_message=AsyncMock(),
        )
        processor = SimpleNamespace(process_single_action=AsyncMock(return_value={"status": "success", "output": "ok"}))
        config = SimpleNamespace(
            STATE_CHANGING_OPS={"edit_file", "create_file", "write_file"},
            LOOP_ERROR_REPEAT_THRESHOLD=2,
            READ_ONLY_REPEAT_THRESHOLD=3,
            RECOVERABLE_ERROR_RETRY_BUDGET=2,
            CRITICAL_ERROR_RETRY_BUDGET=1,
            MAX_READONLY_BATCH_ACTIONS=2,
        )
        history = SimpleNamespace(_save_blob=MagicMock(return_value="blob123"))
        agent = SimpleNamespace(ui=ui, processor=processor, config=config, history=history, log=None)
        dispatcher = ActionDispatcher(agent)
        state = AgentState()

        segments = [
            SimpleNamespace(type="action", content={"type": "read_file", "path": "a.txt"}),
            SimpleNamespace(type="action", content={"type": "read_file", "path": "b.txt"}),
            SimpleNamespace(type="action", content={"type": "read_file", "path": "c.txt"}),
        ]
        _processed, system_results, _should_stop = await dispatcher.dispatch_segments(segments, state)

        self.assertEqual(processor.process_single_action.await_count, 2)
        self.assertTrue(any("Read-only batch limited to 2 actions" in msg for msg in system_results))
        self.assertTrue(any("Skipped by batch policy" in msg for msg in system_results))

    async def test_dispatch_mixed_batch_executes_only_first_state_changing_action(self):
        ui = SimpleNamespace(
            print_edit_file_start=AsyncMock(return_value=object()),
            start_action=AsyncMock(),
            update_edit_file_result=AsyncMock(),
            print_tool_call=AsyncMock(),
            print_plan=AsyncMock(),
            print_command_result=AsyncMock(),
            print_confirmation=AsyncMock(),
            print_shell_start=AsyncMock(return_value=object()),
            update_shell_result=AsyncMock(),
            print_read_file_start=AsyncMock(return_value=object()),
            update_read_file_result=AsyncMock(),
            print_thought=AsyncMock(),
            print_message=AsyncMock(),
        )
        processor = SimpleNamespace(process_single_action=AsyncMock(return_value={"status": "success", "output": "ok"}))
        config = SimpleNamespace(
            STATE_CHANGING_OPS={"edit_file", "create_file", "write_file"},
            LOOP_ERROR_REPEAT_THRESHOLD=2,
            READ_ONLY_REPEAT_THRESHOLD=3,
            RECOVERABLE_ERROR_RETRY_BUDGET=2,
            CRITICAL_ERROR_RETRY_BUDGET=1,
            MAX_READONLY_BATCH_ACTIONS=4,
        )
        history = SimpleNamespace(_save_blob=MagicMock(return_value="blob123"))
        agent = SimpleNamespace(ui=ui, processor=processor, config=config, history=history, log=None)
        dispatcher = ActionDispatcher(agent)
        state = AgentState()

        segments = [
            SimpleNamespace(type="action", content={"type": "read_file", "path": "a.txt"}),
            SimpleNamespace(type="action", content={"type": "edit_file", "path": "a.txt", "search_text": "x", "replace_text": "y"}),
            SimpleNamespace(type="action", content={"type": "read_file", "path": "b.txt"}),
        ]
        _processed, system_results, _should_stop = await dispatcher.dispatch_segments(segments, state)

        self.assertEqual(processor.process_single_action.await_count, 1)
        called_cmd = processor.process_single_action.await_args.args[0]
        self.assertEqual(called_cmd.get("type"), "edit_file")
        self.assertTrue(any("Mixed batch detected" in msg for msg in system_results))

    def test_error_repeat_counter_survives_read_only_success(self):
        state = AgentState()
        failing_edit = {
            "type": "edit_file",
            "path": "a.txt",
            "search_text": "x",
            "replace_text": "y",
        }
        read_step = {"type": "read_file", "path": "a.txt"}

        first = state.record_action_result(
            failing_edit,
            {
                "status": "error",
                "error_code": "VALIDATION_ERROR",
                "recoverable": True,
                "output": "Search block not found",
            },
        )
        self.assertEqual(first["same_error_repeats"], 1)

        state.record_action_result(read_step, {"status": "success", "output": "ok"})
        self.assertEqual(state.consecutive_same_error_count, 1)

        second = state.record_action_result(
            failing_edit,
            {
                "status": "error",
                "error_code": "VALIDATION_ERROR",
                "recoverable": True,
                "output": "Search block not found",
            },
        )
        self.assertEqual(second["same_error_repeats"], 2)

    def test_history_sanitization_uses_safe_redacted_format(self):
        ui = SimpleNamespace(
            print_edit_file_start=AsyncMock(return_value=object()),
            start_action=AsyncMock(),
            update_edit_file_result=AsyncMock(),
            print_tool_call=AsyncMock(),
            print_plan=AsyncMock(),
            print_command_result=AsyncMock(),
            print_confirmation=AsyncMock(),
            print_shell_start=AsyncMock(return_value=object()),
            update_shell_result=AsyncMock(),
            print_read_file_start=AsyncMock(return_value=object()),
            update_read_file_result=AsyncMock(),
        )
        processor = SimpleNamespace(process_single_action=AsyncMock(return_value={"status": "success", "output": "ok"}))
        config = SimpleNamespace(
            STATE_CHANGING_OPS={"edit_file", "create_file", "write_file", "run_shell"},
            LOOP_ERROR_REPEAT_THRESHOLD=2,
            READ_ONLY_REPEAT_THRESHOLD=3,
            RECOVERABLE_ERROR_RETRY_BUDGET=2,
            CRITICAL_ERROR_RETRY_BUDGET=1,
        )
        history = SimpleNamespace(_save_blob=MagicMock(return_value="blob123"))
        agent = SimpleNamespace(ui=ui, processor=processor, config=config, history=history, log=None)
        dispatcher = ActionDispatcher(agent)

        command = {"type": "create_file", "path": "a.txt", "content": "x" * 500}
        safe = dispatcher._sanitize_command_for_history(command)

        self.assertNotIn("content", safe)
        self.assertTrue(safe.get("content_redacted"))
        self.assertEqual(safe.get("content_size"), 500)
        self.assertEqual(safe.get("content_blob_hash"), "blob123")


if __name__ == "__main__":
    unittest.main()
