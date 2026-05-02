from types import SimpleNamespace
import unittest

from modules.agent.orchestration.runtime.policy import IntentGuard


class IntentGuardRetryRecoveryTests(unittest.TestCase):
    def setUp(self):
        self.guard = IntentGuard()

    def _state(
        self,
        *,
        active_intent=None,
        readonly_steps_this_turn=0,
        intent_required_until_activated=False,
        intent_required_reason="intent_required",
        has_retry_context=False,
        can_continue_current_intent_after_failure=False,
        last_error_code="",
        last_error_recoverable=False,
    ):
        return SimpleNamespace(
            active_intent=active_intent,
            readonly_steps_this_turn=readonly_steps_this_turn,
            intent_required_until_activated=intent_required_until_activated,
            intent_required_reason=intent_required_reason,
            has_retry_context=lambda: has_retry_context,
            can_continue_current_intent_after_failure=lambda: can_continue_current_intent_after_failure,
            last_error_code=last_error_code,
            last_error_recoverable=last_error_recoverable,
        )

    def test_recoverable_validation_error_does_not_force_new_intent_for_same_modify_recovery(self):
        """
        Real dump behavior:
        - edit_file failed with VALIDATION_ERROR / multiple_similar_blocks
        - next sensible steps are read_chunk/search_content/edit_file/write_file
        - agent should stay inside the SAME modify intent instead of being forced
          into retry_or_continuation_after_failure formal-intent churn.
        """
        state = self._state(
            active_intent=SimpleNamespace(
                intent_id="modify_sorting_and_dialog",
                intent_type="MODIFY",
                allowed_actions=["edit_file", "read_chunk", "search_content", "run_shell"],
            ),
            has_retry_context=True,
            can_continue_current_intent_after_failure=False,
            last_error_code="VALIDATION_ERROR",
            last_error_recoverable=True,
        )

        command = {
            "type": "read_chunk",
            "path": "app/src/main/java/com/romankozak/forwardappmobile/features/activitytracker/ActivityTrackerScreen.kt",
            "start_line": 1304,
            "end_line": 1320,
        }

        required, reason = self.guard.action_requires_intent(
            command,
            state,
            batch_size=1,
            current_user_input="Continue the same modification by reading the exact block after edit_file mismatch.",
        )

        self.assertFalse(required)
        self.assertEqual("", reason)

    def test_recoverable_validation_error_does_not_force_new_intent_for_search_content_under_same_modify_intent(self):
        state = self._state(
            active_intent=SimpleNamespace(
                intent_id="modify_sorting_and_dialog",
                intent_type="MODIFY",
                allowed_actions=["edit_file", "read_chunk", "search_content", "run_shell"],
            ),
            has_retry_context=True,
            can_continue_current_intent_after_failure=False,
            last_error_code="VALIDATION_ERROR",
            last_error_recoverable=True,
        )

        command = {
            "type": "search_content",
            "path": "app/src/main/java/com/romankozak/forwardappmobile/features/activitytracker/ActivityTrackerScreen.kt",
            "pattern": "EditRecordDialog",
        }

        required, reason = self.guard.action_requires_intent(
            command,
            state,
            batch_size=1,
            current_user_input="Continue the same modification by locating the exact UI block deterministically.",
        )

        self.assertFalse(required)
        self.assertEqual("", reason)

    def test_recoverable_validation_error_without_active_intent_still_requires_formal_retry_intent(self):
        state = self._state(
            active_intent=None,
            has_retry_context=True,
            can_continue_current_intent_after_failure=False,
            last_error_code="VALIDATION_ERROR",
            last_error_recoverable=True,
        )

        command = {
            "type": "search_content",
            "path": "app/src/main/java/com/romankozak/forwardappmobile/features/activitytracker/ActivityTrackerScreen.kt",
            "pattern": "EditRecordDialog",
        }

        required, reason = self.guard.action_requires_intent(
            command,
            state,
            batch_size=1,
            current_user_input="Continue after recoverable failure.",
        )

        self.assertTrue(required)
        self.assertEqual("retry_or_continuation_after_failure", reason)
