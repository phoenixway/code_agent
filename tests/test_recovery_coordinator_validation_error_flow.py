from types import SimpleNamespace
import unittest

from modules.agent.orchestration.recovery import RecoveryCoordinator
from modules.agent.orchestration.prompting import OrchestratorPromptBuilder


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
        self.assertIn("Retry with recovery strategy.", decision.next_query)