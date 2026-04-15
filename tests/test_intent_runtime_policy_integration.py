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
        self.assertEqual("suspect_intent_goal_drift", msg)
        self.assertEqual("policy_rejected", self.runtime.last_transition_info.get("transition"))
        self.assertEqual(
            "suspect_intent_goal_drift",
            self.runtime.last_transition_info.get("reason"),
        )


if __name__ == "__main__":
    unittest.main()
