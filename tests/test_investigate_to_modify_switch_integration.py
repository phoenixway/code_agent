import unittest

from modules.agent.intent_runtime import IntentRuntime
from modules.agent.policy_engine import PolicyEngine, PreActionPolicyInput


class DummyConfig:
    INTENT_RELABEL_GOAL_CORE_OVERLAP_THRESHOLD = 0.45
    INTENT_RELABEL_GOAL_SIMILARITY_THRESHOLD = 0.6
    INTENT_RELABEL_ACTION_OVERLAP_THRESHOLD = 0.6
    INTENT_RELABEL_PRESERVE_STEPS_ON_REFRESH = True


class InvestigateToModifySwitchIntegrationTests(unittest.TestCase):
    def setUp(self):
        self.config = DummyConfig()
        self.runtime = IntentRuntime(self.config)
        self.policy = PolicyEngine()

    def test_runtime_switches_active_intent_from_investigate_to_modify(self):
        investigate_payload = {
            "intent_id": "activity_tracker_analysis",
            "intent_type": "INVESTIGATE",
            "goal": "Determine how to allow moving an activity record to yesterday via the edit dialog",
            "allowed_actions": ["read_chunk", "search_content", "read_file_skeleton"],
            "safe_steps_limit": 4,
            "retry_limit": 2,
            "mode": "activate",
            "switch_reason": "user_requested_new_task",
            "switch_explanation": "initial investigation",
        }
        ok, msg = self.runtime.apply_payload(investigate_payload)
        self.assertTrue(ok, msg)
        self.assertEqual("INVESTIGATE", self.runtime.active_intent.intent_type)

        modify_payload = {
            "intent_id": "activity_tracker_doc_write",
            "intent_type": "MODIFY",
            "goal": "Write documentation file with findings about activity record date editing",
            "allowed_actions": ["read_file", "write_file", "create_file"],
            "safe_steps_limit": 2,
            "retry_limit": 1,
            "mode": "replace",
            "switch_reason": "work_type_changed",
            "switch_explanation": "user asked to save findings into docs",
        }
        ok, msg = self.runtime.apply_payload(modify_payload)

        self.assertTrue(ok, msg)
        self.assertIsNotNone(self.runtime.active_intent)
        self.assertEqual("MODIFY", self.runtime.active_intent.intent_type)
        self.assertEqual("activity_tracker_doc_write", self.runtime.active_intent.intent_id)
        self.assertIn("write_file", self.runtime.active_intent.allowed_actions)
        self.assertIn("create_file", self.runtime.active_intent.allowed_actions)

    def test_modify_intent_should_allow_write_even_if_phase_is_stale_observe(self):
        investigate_payload = {
            "intent_id": "activity_tracker_analysis",
            "intent_type": "INVESTIGATE",
            "goal": "Determine how to allow moving an activity record to yesterday via the edit dialog",
            "allowed_actions": ["read_chunk", "search_content", "read_file_skeleton"],
            "safe_steps_limit": 4,
            "retry_limit": 2,
            "mode": "activate",
            "switch_reason": "user_requested_new_task",
            "switch_explanation": "initial investigation",
        }
        ok, msg = self.runtime.apply_payload(investigate_payload)
        self.assertTrue(ok, msg)

        modify_payload = {
            "intent_id": "activity_tracker_doc_write",
            "intent_type": "MODIFY",
            "goal": "Write documentation file with findings about activity record date editing",
            "allowed_actions": ["read_file", "write_file", "create_file"],
            "safe_steps_limit": 2,
            "retry_limit": 1,
            "mode": "replace",
            "switch_reason": "work_type_changed",
            "switch_explanation": "user asked to save findings into docs",
        }
        ok, msg = self.runtime.apply_payload(modify_payload)
        self.assertTrue(ok, msg)
        self.assertEqual("MODIFY", self.runtime.active_intent.intent_type)

        # Simulate the observed bug:
        # active intent already switched to MODIFY, but outer orchestration/state-machine
        # still reports stale OBSERVE phase allowances from the previous investigation flow.
        ctx = PreActionPolicyInput(
            phase="OBSERVE",
            cmd_type="write_file",
            path="docs/activity-tracker-edit-createdat-analysis.md",
            fingerprint="write_file|docs/activity-tracker-edit-createdat-analysis.md",
            target_file="docs/activity-tracker-edit-createdat-analysis.md",
            forbidden_recover_fingerprint=None,
            has_cross_target_reason=False,
            phase_allows_action=False,
            phase_allowed_next_actions=[
                "find_files",
                "git_diff",
                "list_directory",
                "read_chunk",
                "read_file",
                "read_file_skeleton",
                "run_shell",
                "search_content",
                "search_files",
            ],
            observe_budget_exhausted=False,
            broad_recon_budget_exhausted=False,
            task_kind="MODIFICATION",
            already_read_current_version=False,
            reread_reason_ok=False,
            reread_after_summary=False,
            active_intent_type=self.runtime.active_intent.intent_type,
            active_intent_step_count=self.runtime.active_intent.step_count,
            active_intent_safe_steps_limit=self.runtime.active_intent.safe_steps_limit,
        )

        decision = self.policy.evaluate_pre_action(ctx)

        # This is the intended behavior we want after the bugfix:
        # once MODIFY intent is active and explicitly allows write_file,
        # stale OBSERVE gating must not keep blocking the write.
        self.assertTrue(
            decision.allow,
            f"Expected MODIFY intent to allow write_file despite stale OBSERVE phase, got stop_reason={decision.stop_reason!r}",
        )


if __name__ == "__main__":
    unittest.main()
