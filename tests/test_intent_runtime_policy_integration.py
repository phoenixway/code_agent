import unittest
from types import SimpleNamespace

from modules.agent.intent_runtime import IntentRuntime


class DummyConfig:
    INTENT_RELABEL_GOAL_CORE_OVERLAP_THRESHOLD = 0.45
    INTENT_RELABEL_GOAL_SIMILARITY_THRESHOLD = 0.6
    INTENT_RELABEL_ACTION_OVERLAP_THRESHOLD = 0.6
    INTENT_RELABEL_PRESERVE_STEPS_ON_REFRESH = True


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


if __name__ == "__main__":
    unittest.main()
