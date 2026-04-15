import unittest
from types import SimpleNamespace

from modules.agent.orchestrator import Orchestrator


def _make_orchestrator(active_intent):
    agent = SimpleNamespace(
        ui=SimpleNamespace(),
        state=SimpleNamespace(active_intent=active_intent),
        history=SimpleNamespace(),
        model_client=SimpleNamespace(),
        action_dispatcher=SimpleNamespace(),
        parser=SimpleNamespace(),
        config=SimpleNamespace(),
    )
    return Orchestrator(agent)


class OrchestratorAllowedActionsStabilityTests(unittest.TestCase):
    def setUp(self):
        self.orch = _make_orchestrator(
            SimpleNamespace(
                intent_id="activity_tracker_edit",
                intent_type="INVESTIGATE",
                goal="determine how to allow moving today's activity to yesterday via the edit dialog in ActivityTrackerScreen",
                allowed_actions=["read_chunk", "read_file", "search_content"],
            )
        )

    def test_current_intent_recovery_keeps_read_only_actions_stable_after_soft_limit(self):
        stop_info = {
            "reason": "intent_step_limit_soft_exceeded",
            "recoverable": True,
            "next_actions": ["read_chunk", "read_file", "search_content"],
        }

        out = self.orch._build_orchestrated_recovery_prompt(stop_info)

        self.assertIn("Allowed actions under the CURRENT intent: read_chunk, read_file, search_content.", out)
        self.assertIn("Current intent goal remains the same", out)
        self.assertNotIn("Allowed next actions: search_content, edit_file, write_file.", out)

    def test_user_approved_more_steps_keeps_same_current_intent_actions(self):
        stop_info = {
            "reason": "user_approved_more_steps_after_hard_limit",
            "recoverable": True,
            "next_actions": ["read_chunk", "read_file", "search_content"],
        }

        out = self.orch._build_orchestrated_recovery_prompt(stop_info)

        self.assertIn("Allowed actions under the CURRENT intent: read_chunk, read_file, search_content.", out)
        self.assertIn("User approved a small additional step budget for the CURRENT intent.", out)
        self.assertIn("Return EXACTLY ONE valid next <action> now.", out)
        self.assertNotIn("Allowed next actions: search_content, edit_file, write_file.", out)

    def test_same_intent_action_not_allowed_in_phase_should_not_jump_to_write_actions(self):
        stop_info = {
            "reason": "action_not_allowed_in_phase",
            "recoverable": True,
            "next_actions": ["search_content", "edit_file", "write_file"],
        }

        out = self.orch._build_orchestrated_recovery_prompt(stop_info)

        self.assertNotIn("Allowed next actions: search_content, edit_file, write_file.", out)
        self.assertNotIn("Required next actions: search_content, edit_file, write_file.", out)
        self.assertIn("Allowed actions under the CURRENT intent: read_chunk, read_file, search_content.", out)

    def test_blocked_action_keep_current_intent_reuses_current_read_family(self):
        stop_info = {
            "reason": "intent_blocked_action_signature",
            "recoverable": True,
            "message_key": "blocked_action_keep_current_intent",
            "next_actions": ["read_chunk", "read_file", "search_content"],
        }

        out = self.orch._build_orchestrated_recovery_prompt(stop_info)

        self.assertIn("Allowed actions under the CURRENT intent: read_chunk, read_file, search_content.", out)
        self.assertIn("The current intent remains valid and its goal remains the same.", out)
        self.assertNotIn("Allowed next actions: search_content, edit_file, write_file.", out)

    def test_modify_phase_may_offer_write_actions_after_real_intent_switch(self):
        self.orch = _make_orchestrator(
            SimpleNamespace(
                intent_id="activity_tracker_doc_write",
                intent_type="MODIFY",
                goal="write documentation file with findings",
                allowed_actions=["search_content", "edit_file", "write_file"],
            )
        )
        stop_info = {
            "reason": "action_not_allowed_in_phase",
            "recoverable": True,
            "next_actions": ["search_content", "edit_file", "write_file"],
        }

        out = self.orch._build_orchestrated_recovery_prompt(stop_info)

        self.assertIn("Required next actions: search_content, edit_file, write_file.", out)


if __name__ == "__main__":
    unittest.main()
