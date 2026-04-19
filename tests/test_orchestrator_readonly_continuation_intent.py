import unittest
from types import SimpleNamespace

from modules.agent.orchestrator import Orchestrator
from modules.agent.orchestration.policy import IntentGuard


def _make_orchestrator(active_intent=None, readonly_steps_this_turn=0):
    state = SimpleNamespace(
        active_intent=active_intent,
        readonly_steps_this_turn=readonly_steps_this_turn,
        intent_required_until_activated=False,
        intent_required_reason="",
        has_retry_context=lambda: False,
        can_continue_current_intent_after_failure=lambda: True,
    )
    agent = SimpleNamespace(
        ui=SimpleNamespace(),
        state=state,
        history=SimpleNamespace(),
        model_client=SimpleNamespace(),
        action_dispatcher=SimpleNamespace(),
        parser=SimpleNamespace(),
        config=SimpleNamespace(),
    )
    orch = Orchestrator(agent)
    return orch, state


class OrchestratorReadOnlyContinuationIntentTests(unittest.TestCase):
    def setUp(self):
        self.guard = IntentGuard()

    def test_second_read_only_step_with_active_compatible_intent_does_not_require_new_intent(self):
        active_intent = SimpleNamespace(
            intent_id="investigate_activity_tracker",
            intent_type="INVESTIGATE",
            goal="Determine how to allow moving today's activity record to yesterday via the edit dialog",
            allowed_actions=["read_file", "read_chunk", "read_file_skeleton", "search_content", "run_shell"],
        )
        orch, state = _make_orchestrator(active_intent=active_intent, readonly_steps_this_turn=1)

        command = {
            "type": "read_file",
            "path": "core-data-models/src/main/java/com/romankozak/forwardappmobile/core/data/models/entities/ActivityRecord.kt",
        }

        required, reason = self.guard.action_requires_intent(
            command,
            state,
            batch_size=1,
            current_user_input=(
                "Потрібно дослідити поточну реалізацію edit dialog та пов'язані поля ActivityRecord, "
                "щоб зрозуміти як перенести запис на вчора."
            ),
        )

        self.assertFalse(required)
        self.assertEqual("", reason)

    def test_second_search_content_step_with_active_compatible_intent_does_not_require_new_intent(self):
        active_intent = SimpleNamespace(
            intent_id="investigate_activity_tracker",
            intent_type="INVESTIGATE",
            goal="Understand the edit dialog and related entity fields",
            allowed_actions=["read_chunk", "read_file_skeleton", "search_content"],
        )
        orch, state = _make_orchestrator(active_intent=active_intent, readonly_steps_this_turn=1)

        command = {
            "type": "search_content",
            "path": ".",
            "pattern": r"data class ActivityRecord\(",
        }

        required, reason = self.guard.action_requires_intent(
            command,
            state,
            batch_size=1,
            current_user_input="Need to continue the same investigation of activity tracker edit dialog and ActivityRecord fields.",
        )

        self.assertFalse(required)
        self.assertEqual("", reason)

    def test_second_read_only_step_without_active_intent_still_requires_intent(self):
        orch, state = _make_orchestrator(active_intent=None, readonly_steps_this_turn=1)

        command = {
            "type": "read_file",
            "path": "app/src/main/java/com/romankozak/forwardappmobile/features/activitytracker/ActivityTrackerViewModel.kt",
        }

        required, reason = self.guard.action_requires_intent(
            command,
            state,
            batch_size=1,
            current_user_input="Need to investigate activity tracker behavior and data flow.",
        )

        self.assertTrue(required)
        self.assertEqual("investigation_task_requires_formal_intent", reason)

    def test_incompatible_active_intent_does_not_force_new_intent_just_for_readonly_continuation(self):
        active_intent = SimpleNamespace(
            intent_id="search_only_intent",
            intent_type="INVESTIGATE",
            goal="Only perform narrow code search",
            allowed_actions=["search_content"],
        )
        orch, state = _make_orchestrator(active_intent=active_intent, readonly_steps_this_turn=1)

        command = {
            "type": "read_file",
            "path": "app/src/main/java/com/romankozak/forwardappmobile/features/activitytracker/ActivityTrackerViewModel.kt",
        }

        required, reason = self.guard.action_requires_intent(
            command,
            state,
            batch_size=1,
            current_user_input="Continue the same investigation.",
        )

        self.assertFalse(required)
        self.assertEqual("", reason)


if __name__ == "__main__":
    unittest.main()
