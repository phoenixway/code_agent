import unittest
from types import SimpleNamespace

from modules.agent.intent_runtime import IntentRuntime


class DummyConfig:
    INTENT_RELABEL_GOAL_CORE_OVERLAP_THRESHOLD = 0.45
    INTENT_RELABEL_GOAL_SIMILARITY_THRESHOLD = 0.6
    INTENT_RELABEL_ACTION_OVERLAP_THRESHOLD = 0.6
    INTENT_RELABEL_PRESERVE_STEPS_ON_REFRESH = True
    INTENT_REUSE_EXTENSION_STEPS = 4
    INTENT_MAX_SAFE_STEPS = 8
    INTENT_DEFAULT_SAFE_STEPS = 4
    INTENT_DEFAULT_RETRY_LIMIT = 2


class IntentRuntimePolicyIntegrationTests(unittest.TestCase):
    def setUp(self):
        self.runtime = IntentRuntime(DummyConfig())
        active_payload = {
            "intent_id": "activity_tracker_edit",
            "intent_type": "INVESTIGATE",
            "goal": "Determine how to move today's record to yesterday via edit dialog",
            "allowed_actions": ["read_chunk", "search_content", "read_file_skeleton"],
            "safe_steps_limit": 4,
            "retry_limit": 2,
            "mode": "activate",
            "switch_reason": "user_requested_new_task",
            "switch_explanation": "initial activation",
        }
        ok, msg = self.runtime.apply_payload(active_payload)
        self.assertTrue(ok, msg)

    def test_apply_payload_rejects_same_lineage_cosmetic_relabel(self):
        payload = {
            "intent_id": "investigate_dialog",
            "intent_type": "INVESTIGATE",
            "goal": "Determine how to move today's record to yesterday via edit dialog",
            "allowed_actions": ["read_chunk", "search_content", "read_file_skeleton"],
            "safe_steps_limit": 4,
            "retry_limit": 2,
            "mode": "activate",
            "switch_reason": "user_requested_new_task",
            "switch_explanation": "cosmetic relabel",
        }

        ok, msg = self.runtime.apply_payload(payload)

        self.assertFalse(ok)
        self.assertEqual("suspect_intent_relabel_repeat", msg)
        self.assertEqual("policy_rejected", self.runtime.last_transition_info.get("transition"))
        self.assertEqual(
            "suspect_intent_relabel_repeat",
            self.runtime.last_transition_info.get("reason"),
        )
        self.assertEqual(
            "suspect_intent_relabel_repeat",
            self.runtime.last_transition_info.get("message_key"),
        )

    def test_apply_payload_rejects_same_active_contract_reactivation(self):
        payload = {
            "intent_id": "activity_tracker_edit",
            "intent_type": "INVESTIGATE",
            "goal": "Determine how to move today's record to yesterday via edit dialog",
            "allowed_actions": ["read_chunk", "search_content", "read_file_skeleton"],
            "safe_steps_limit": 4,
            "retry_limit": 2,
            "mode": "activate",
            "switch_reason": "user_requested_new_task",
            "switch_explanation": "repeat same active contract",
        }

        ok, msg = self.runtime.apply_payload(payload)

        self.assertFalse(ok)
        self.assertEqual("unnecessary_intent_reactivation_or_replace", msg)
        self.assertEqual("policy_rejected", self.runtime.last_transition_info.get("transition"))
        self.assertEqual(
            "unnecessary_intent_reactivation_or_replace",
            self.runtime.last_transition_info.get("reason"),
        )
        self.assertEqual(
            "unnecessary_intent_reactivation_or_replace",
            self.runtime.last_transition_info.get("message_key"),
        )

    def test_apply_payload_rejects_goal_drift_and_marks_policy_rejected(self):
        payload = {
            "intent_id": "activity_tracker_edit",
            "intent_type": "INVESTIGATE",
            "goal": "read dialog lines",
            "allowed_actions": ["read_chunk", "search_content"],
            "safe_steps_limit": 4,
            "retry_limit": 2,
            "mode": "activate",
            "switch_reason": "user_requested_new_task",
            "switch_explanation": "local probe only",
        }

        ok, msg = self.runtime.apply_payload(payload)

        self.assertFalse(ok)
        self.assertEqual("intent_goal_too_local_or_underspecified", msg)

    def test_apply_payload_accepts_goal_that_starts_local_but_has_real_user_facing_outcome(self):
        runtime = IntentRuntime(DummyConfig())
        payload = {
            "intent_id": "picker_past_values",
            "intent_type": "INVESTIGATE",
            "goal": "Locate the date-time picker dialog used in EditRecordDialog for activity tracker start time, understand its past-value restriction, and add an optional EnablePastValues flag.",
            "allowed_actions": ["read_chunk", "read_file_skeleton", "extract_symbol", "search_content", "search_files", "list_directory", "run_shell"],
            "safe_steps_limit": 6,
            "retry_limit": 2,
            "mode": "activate",
            "switch_reason": "user_requested_new_task",
            "switch_explanation": "Investigate picker restriction and enable past values flag.",
        }

        ok, msg = runtime.apply_payload(payload)

        self.assertTrue(ok, msg)
        self.assertEqual("picker_past_values", runtime.active_intent.intent_id)

    def test_modify_payload_with_read_only_allowed_actions_is_upgraded_for_editing(self):
        payload = {
            "intent_id": "activity_tracker_modify",
            "intent_type": "MODIFY",
            "goal": "Change activity tracker sorting to use startTime",
            "allowed_actions": ["read_chunk", "search_content"],
            "safe_steps_limit": 4,
            "retry_limit": 2,
            "mode": "replace",
            "switch_reason": "work_type_changed",
            "switch_explanation": "move from investigation to modification",
        }

        ok, msg = self.runtime.apply_payload(payload)

        self.assertTrue(ok, msg)
        self.assertEqual("MODIFY", self.runtime.active_intent.intent_type)
        self.assertIn("edit_file", self.runtime.active_intent.allowed_actions)
        self.assertIn("write_file", self.runtime.active_intent.allowed_actions)
        self.assertIn("create_file", self.runtime.active_intent.allowed_actions)

    def test_extract_kotlin_function_is_retained_as_known_allowed_action(self):
        payload = {
            "intent_id": "activity_tracker_extract",
            "intent_type": "INVESTIGATE",
            "goal": "Extract the exact Kotlin function implementation for EditRecordDialog",
            "allowed_actions": ["extract_kotlin_function", "search_content"],
            "safe_steps_limit": 4,
            "retry_limit": 2,
            "mode": "replace",
            "switch_reason": "current_intent_no_longer_fits",
            "switch_explanation": "switch to exact function extraction",
        }

        ok, msg = self.runtime.apply_payload(payload)

        self.assertTrue(ok, msg)
        self.assertIn("extract_kotlin_function", self.runtime.active_intent.allowed_actions)

    def test_extract_symbol_is_retained_as_known_allowed_action(self):
        payload = {
            "intent_id": "activity_tracker_extract_symbol",
            "intent_type": "INVESTIGATE",
            "goal": "Extract the exact Kotlin symbol implementation for EditRecordDialog",
            "allowed_actions": ["extract_symbol", "search_content"],
            "safe_steps_limit": 4,
            "retry_limit": 2,
            "mode": "replace",
            "switch_reason": "current_intent_no_longer_fits",
            "switch_explanation": "switch to exact symbol extraction",
        }

        ok, msg = self.runtime.apply_payload(payload)

        self.assertTrue(ok, msg)
        self.assertIn("extract_symbol", self.runtime.active_intent.allowed_actions)

    def test_modify_payload_with_read_only_run_shell_is_still_upgraded_for_editing(self):
        payload = {
            "intent_id": "activity_tracker_modify",
            "intent_type": "MODIFY",
            "goal": "Change activity tracker sorting to use startTime",
            "allowed_actions": [
                "read_file",
                "read_file_skeleton",
                "read_chunk",
                "search_content",
                "search_files",
                "run_shell",
                "list_directory",
            ],
            "safe_steps_limit": 6,
            "retry_limit": 2,
            "mode": "replace",
            "switch_reason": "work_type_changed",
            "switch_explanation": "move from investigation to modification",
        }

        ok, msg = self.runtime.apply_payload(payload)

        self.assertTrue(ok, msg)
        self.assertEqual("MODIFY", self.runtime.active_intent.intent_type)
        self.assertIn("edit_file", self.runtime.active_intent.allowed_actions)
        self.assertIn("write_file", self.runtime.active_intent.allowed_actions)
        self.assertIn("create_file", self.runtime.active_intent.allowed_actions)
        self.assertIn("run_shell", self.runtime.active_intent.allowed_actions)

    def test_reuse_after_current_intent_exhausted_refreshes_budget_and_clears_requirement(self):
        self.runtime.active_intent.step_count = self.runtime.active_intent.safe_steps_limit + 1
        self.runtime.require_intent("exhausted_intent_requires_reuse_or_completion")

        payload = {
            "intent_id": "activity_tracker_edit",
            "mode": "reuse",
            "requested_steps": 4,
            "switch_reason": "current_intent_exhausted",
            "goal": "Determine how to move today's record to yesterday via edit dialog",
        }

        ok, msg = self.runtime.apply_payload(payload)

        self.assertTrue(ok, msg)
        self.assertEqual("intent_reused_with_step_refresh", msg)
        self.assertFalse(self.runtime.intent_required_until_activated)
        self.assertEqual("intent_reused_with_step_refresh", self.runtime.last_transition_info.get("transition"))
        self.assertGreater(self.runtime.active_intent.user_step_extension, 0)


if __name__ == "__main__":
    unittest.main()
