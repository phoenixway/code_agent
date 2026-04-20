from types import SimpleNamespace
import unittest

from modules.agent.orchestration.recovery import RecoveryCoordinator
from modules.agent.orchestration.prompting import OrchestratorPromptBuilder
from modules.agent.state_manager import AgentState


class RecoveryCoordinatorValidationErrorFlowTests(unittest.IsolatedAsyncioTestCase):
    def _make_agent(self):
        async def confirm_loop_recovery(_message):
            return "retry_recovery"

        async def print_system(_message):
            return None

        state = SimpleNamespace(
            active_intent=SimpleNamespace(
                intent_id="modify_sorting_and_dialog",
                intent_type="MODIFY",
                goal="Modify EditRecordDialog after recoverable edit mismatch.",
                allowed_actions=["edit_file", "read_chunk", "search_content", "run_shell"],
            ),
            confirmation_count=0,
            add_confirmation=lambda n: None,
            require_intent=lambda reason: None,
            pending_loop_stop_info=None,
            set_retry_budgets=lambda *args, **kwargs: None,
            last_error_code="VALIDATION_ERROR",
            last_error_message="Search block not found",
        )
        config = SimpleNamespace(
            INTENT_REQUIRE_ON_DEFECT=True,
            RECOVERABLE_ERROR_RETRY_BUDGET=2,
            CRITICAL_ERROR_RETRY_BUDGET=1,
        )
        ui = SimpleNamespace(
            confirm_continue=None,
            confirm_loop_recovery=confirm_loop_recovery,
            print_system=print_system,
        )
        agent = SimpleNamespace(
            ui=ui,
            state=state,
            config=config,
            log=None,
            memory_board_store=None,
        )
        return agent

    async def test_recoverable_validation_error_produces_recovery_query_not_stop(self):
        agent = self._make_agent()
        prompt_builder = OrchestratorPromptBuilder(agent)
        recovery = RecoveryCoordinator(agent, prompt_builder)

        stop_info = {
            "reason": "repeating_failure",
            "recoverable": True,
            "error_code": "VALIDATION_ERROR",
            "next_actions": ["read_file", "search_content", "edit_file", "write_file"],
        }

        decision = await recovery.handle_dispatch_stop(stop_info, sm=None)

        self.assertTrue(decision.handled)
        self.assertFalse(decision.stop_loop)
        self.assertTrue(decision.clear_pending_stop)
        self.assertIsInstance(decision.next_query, str)
        self.assertIn("Retry inside the SAME current intent contract.", decision.next_query)
        self.assertIn("Do not emit a new <intent> block.", decision.next_query)

    async def test_repeating_recoverable_validation_error_under_active_intent_stays_in_same_contract(self):
        agent = self._make_agent()
        prompt_builder = OrchestratorPromptBuilder(agent)
        recovery = RecoveryCoordinator(agent, prompt_builder)

        stop_info = {
            "reason": "repeating_failure",
            "recoverable": True,
            "error_code": "VALIDATION_ERROR",
            "next_actions": ["read_chunk", "search_content", "edit_file", "write_file"],
            "error_details": {
                "mismatch_type": "indentation_or_partial_block_mismatch",
            },
        }

        decision = await recovery.handle_dispatch_stop(stop_info, sm=None)

        self.assertTrue(decision.handled)
        self.assertFalse(decision.stop_loop)
        self.assertTrue(decision.clear_pending_stop)
        self.assertIn("Retry inside the SAME current intent contract.", decision.next_query)
        self.assertIn("Do not emit a new <intent> block.", decision.next_query)
        self.assertIn("retrieve the exact current target block from file content", decision.next_query)
        self.assertIn("copy search_text verbatim", decision.next_query)

    async def test_repeated_malformed_read_chunk_payload_forces_different_action(self):
        config = SimpleNamespace(
            INTENT_REQUIRE_ON_DEFECT=True,
            RECOVERABLE_ERROR_RETRY_BUDGET=2,
            CRITICAL_ERROR_RETRY_BUDGET=1,
        )
        state = AgentState(config)
        state.pending_loop_stop_info = {"reason": "malformed_read_chunk_payload"}
        state.pending_loop_stop_info = {"reason": "malformed_read_chunk_payload"}
        state.intent_runtime.active_intent = SimpleNamespace(
            intent_id="investigate_dialog",
            intent_type="INVESTIGATE",
            goal="Find the exact dialog implementation before editing",
            allowed_actions=["read_chunk", "search_content", "read_file_skeleton", "run_shell"],
        )
        state.set_retry_budgets(2, 1)
        state.last_error_code = "MALFORMED_READ_CHUNK_PAYLOAD"
        state.last_error_message = "read_chunk requires top-level integer line fields"

        agent = SimpleNamespace(
            ui=SimpleNamespace(confirm_continue=None, confirm_loop_recovery=None, print_system=None),
            state=state,
            config=config,
            log=None,
            memory_board_store=None,
        )
        prompt_builder = OrchestratorPromptBuilder(agent)
        recovery = RecoveryCoordinator(agent, prompt_builder)

        decision = await recovery.handle_dispatch_stop(
            {"reason": "malformed_read_chunk_payload", "recoverable": True},
            sm=None,
        )

        self.assertTrue(decision.handled)
        self.assertTrue(decision.clear_pending_stop)
        self.assertIn("Do NOT output read_chunk again", decision.next_query)
        self.assertIn("search_content", decision.next_query)
        self.assertNotIn("Return EXACTLY ONE valid read_chunk action now.", decision.next_query)
