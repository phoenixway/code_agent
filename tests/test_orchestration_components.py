import unittest
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

from modules.agent.orchestration.lifecycle import TurnLifecycle
from modules.agent.orchestration.parsing import IntentResponseParser
from modules.agent.orchestration.policy import IntentGuard
from modules.agent.orchestration.prompting import OrchestratorPromptBuilder
from modules.agent.orchestration.recovery import RecoveryCoordinator, StopHandlingDecision


class _Segment:
    def __init__(self, seg_type: str, content=None):
        self.type = seg_type
        self.content = content


class IntentGuardTests(unittest.TestCase):
    def setUp(self):
        self.guard = IntentGuard()

    def test_allowed_action_under_active_intent_does_not_require_new_intent(self):
        state = SimpleNamespace(
            active_intent=SimpleNamespace(allowed_actions=["read_file"]),
            intent_required_until_activated=False,
            readonly_steps_this_turn=1,
            has_retry_context=lambda: False,
            can_continue_current_intent_after_failure=lambda: True,
        )

        required, reason = self.guard.action_requires_intent(
            {"type": "read_file", "path": "a.py"},
            state,
            batch_size=1,
            current_user_input="Need to investigate the file structure.",
        )

        self.assertFalse(required)
        self.assertEqual("", reason)

    def test_second_read_only_step_without_intent_requires_intent(self):
        state = SimpleNamespace(
            active_intent=None,
            intent_required_until_activated=False,
            readonly_steps_this_turn=1,
            has_retry_context=lambda: False,
            can_continue_current_intent_after_failure=lambda: True,
        )

        required, reason = self.guard.action_requires_intent(
            {"type": "read_file", "path": "a.py"},
            state,
            batch_size=1,
            current_user_input="Need to investigate the file structure.",
        )

        self.assertTrue(required)
        self.assertEqual("investigation_task_requires_formal_intent", reason)


class IntentResponseParserTests(unittest.TestCase):
    def setUp(self):
        self.parser = IntentResponseParser()

    def test_extract_intent_update_and_strip_returns_clean_text_and_payload(self):
        clean_text, payload, error = self.parser.extract_intent_update_and_strip(
            '<intent>{"goal":"inspect","allowed_actions":["read_file"]}</intent>\n<action>{"type":"read_file","path":"a.py"}</action>'
        )

        self.assertEqual('<action>{"type":"read_file","path":"a.py"}</action>', clean_text)
        self.assertEqual("inspect", payload["goal"])
        self.assertIsNone(error)

    def test_needs_action_or_answer_recovery_when_only_thought_present(self):
        needs = self.parser.needs_action_or_answer_recovery(
            "<think>analyzing</think>",
            [_Segment("thought", "analyzing")],
        )

        self.assertTrue(needs)

    def test_intent_only_response_detected(self):
        is_intent_only = self.parser.is_intent_only_response(
            '<intent>{"goal":"inspect"}</intent>',
            [_Segment("intent", {"goal": "inspect"})],
        )

        self.assertTrue(is_intent_only)


class TurnLifecycleTests(unittest.TestCase):
    def test_start_turn_initializes_state_machine_and_history(self):
        sm = SimpleNamespace(
            start_turn=MagicMock(),
            intent_runtime=None,
        )
        state = SimpleNamespace(
            state_machine=sm,
            intent_runtime=SimpleNamespace(),
            clear_intent_requirement=MagicMock(),
            start_turn_runtime=MagicMock(),
            current_turn_id=3,
        )
        history = SimpleNamespace(
            add_message=MagicMock(),
            start_turn=MagicMock(),
        )
        agent = SimpleNamespace(
            state=state,
            history=history,
            log=None,
        )

        lifecycle = TurnLifecycle(agent)
        returned_sm = lifecycle.start_turn("inspect this")

        self.assertIs(returned_sm, sm)
        history.add_message.assert_called_once_with("user", "inspect this")
        sm.start_turn.assert_called_once_with("inspect this")
        state.clear_intent_requirement.assert_called_once()
        state.start_turn_runtime.assert_called_once()
        history.start_turn.assert_called_once_with(3)


class RecoveryCoordinatorTests(unittest.IsolatedAsyncioTestCase):
    async def test_handle_dispatch_stop_returns_structured_decision_for_malformed_read_file(self):
        ui = SimpleNamespace(
            confirm_continue=AsyncMock(),
            confirm_loop_recovery=AsyncMock(),
            print_system=AsyncMock(),
        )
        state = SimpleNamespace(
            last_error_code=None,
            last_error_message=None,
            set_retry_budgets=MagicMock(),
        )
        config = SimpleNamespace(
            RECOVERABLE_ERROR_RETRY_BUDGET=2,
            CRITICAL_ERROR_RETRY_BUDGET=1,
        )
        agent = SimpleNamespace(ui=ui, state=state, config=config)
        prompt_builder = OrchestratorPromptBuilder(
            SimpleNamespace(
                state=SimpleNamespace(active_intent=None),
                config=SimpleNamespace(),
                memory_board_store=None,
                log=None,
            )
        )

        coordinator = RecoveryCoordinator(agent, prompt_builder)
        decision = await coordinator.handle_dispatch_stop(
            {"reason": "malformed_read_file_payload", "recoverable": True},
            sm=None,
        )

        self.assertIsInstance(decision, StopHandlingDecision)
        self.assertTrue(decision.handled)
        self.assertTrue(decision.clear_pending_stop)
        self.assertIn("Your last read_file call used invalid payload.", decision.next_query)

    async def test_handle_dispatch_stop_returns_retry_query_for_repeating_failure(self):
        ui = SimpleNamespace(
            confirm_continue=AsyncMock(),
            confirm_loop_recovery=AsyncMock(return_value="retry_recovery"),
            print_system=AsyncMock(),
        )
        state = SimpleNamespace(
            last_error_code=None,
            last_error_message=None,
            set_retry_budgets=MagicMock(),
        )
        config = SimpleNamespace(
            RECOVERABLE_ERROR_RETRY_BUDGET=2,
            CRITICAL_ERROR_RETRY_BUDGET=1,
        )
        agent = SimpleNamespace(ui=ui, state=state, config=config)
        prompt_builder = OrchestratorPromptBuilder(
            SimpleNamespace(
                state=SimpleNamespace(active_intent=None),
                config=SimpleNamespace(),
                memory_board_store=None,
                log=None,
            )
        )

        coordinator = RecoveryCoordinator(agent, prompt_builder)
        decision = await coordinator.handle_dispatch_stop(
            {"reason": "repeating_failure", "next_actions": ["search_content"]},
            sm=SimpleNamespace(on_user_recovery_choice=MagicMock()),
        )

        self.assertTrue(decision.handled)
        self.assertTrue(decision.clear_pending_stop)
        self.assertIn("Retry with recovery strategy.", decision.next_query)


if __name__ == "__main__":
    unittest.main()
