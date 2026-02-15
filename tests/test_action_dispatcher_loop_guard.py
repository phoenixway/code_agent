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


if __name__ == "__main__":
    unittest.main()
