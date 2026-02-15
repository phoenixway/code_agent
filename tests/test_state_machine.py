import unittest
from types import SimpleNamespace

from modules.agent.state_machine import AgentStateMachine, DecisionType


class TestStateMachine(unittest.TestCase):
    def setUp(self):
        self.config = SimpleNamespace(
            IMPLEMENT_STAGNATION_LIMIT=3,
            RESEARCH_STAGNATION_LIMIT=6,
            STAGNATION_MAX_DIAGNOSTICS=1,
            INVARIANT_VIOLATION_LIMIT=1,
        )
        self.sm = AgentStateMachine(self.config)
        self.read_cmd = {"type": "read_file", "path": "a.txt"}
        self.read_ok = {"status": "success", "output": "ok"}
        self.state_ops = {"edit_file", "write_file", "run_shell"}

    def test_implementation_mode_triggers_diagnostic_then_handoff(self):
        self.sm.start_turn("fix this bug")

        # First read gives new information, then same reads cause stagnation.
        self.sm.note_action(self.read_cmd, self.read_ok, self.state_ops)
        for _ in range(3):
            self.sm.note_action(self.read_cmd, self.read_ok, self.state_ops)

        first = self.sm.decide()
        self.assertEqual(first.decision, DecisionType.MODEL_DIAGNOSTIC)
        self.assertIn("SYSTEM_DIAGNOSTIC", first.prompt)

        second = self.sm.decide()
        self.assertEqual(second.decision, DecisionType.USER_HANDOFF)

    def test_research_mode_allows_longer_readonly_exploration(self):
        self.sm.start_turn("analyze project architecture deeply")

        self.sm.note_action(self.read_cmd, self.read_ok, self.state_ops)
        for _ in range(4):
            self.sm.note_action(self.read_cmd, self.read_ok, self.state_ops)

        decision = self.sm.decide()
        self.assertEqual(decision.decision, DecisionType.CONTINUE)

    def test_new_path_resets_stagnation(self):
        self.sm.start_turn("fix UI bug")

        self.sm.note_action(self.read_cmd, self.read_ok, self.state_ops)
        self.sm.note_action(self.read_cmd, self.read_ok, self.state_ops)
        self.assertGreaterEqual(self.sm.stagnation_count, 1)

        self.sm.note_action({"type": "read_file", "path": "b.txt"}, self.read_ok, self.state_ops)
        self.assertEqual(self.sm.stagnation_count, 0)

    def test_apply_success_resets_stagnation(self):
        self.sm.start_turn("fix code")
        self.sm.note_action(self.read_cmd, self.read_ok, self.state_ops)
        self.sm.note_action(self.read_cmd, self.read_ok, self.state_ops)
        self.assertGreaterEqual(self.sm.stagnation_count, 1)

        self.sm.note_action(
            {"type": "edit_file", "path": "a.txt", "search_text": "x", "replace_text": "y"},
            {"status": "success", "output": "applied"},
            self.state_ops,
        )
        self.assertEqual(self.sm.stagnation_count, 0)

    def test_progress_score_keeps_exploration_alive(self):
        self.sm.start_turn("analyze module boundaries")
        for idx in range(8):
            self.sm.note_action(
                {"type": "read_file", "path": f"module_{idx}.py"},
                self.read_ok,
                self.state_ops,
            )
            self.assertEqual(self.sm.stagnation_count, 0)

        self.assertEqual(self.sm.decide().decision, DecisionType.CONTINUE)

    def test_pre_action_policy_blocks_cross_target_read_without_reason(self):
        self.sm.start_turn("fix this bug")
        self.sm.note_action(
            {"type": "edit_file", "path": "a.txt", "search_text": "x", "replace_text": "y"},
            {"status": "success", "output": "ok"},
            self.state_ops,
        )
        pre = self.sm.pre_action_policy({"type": "read_file", "path": "b.txt"})
        self.assertFalse(pre.allow)
        self.assertEqual(pre.stop_reason, "cross_target_read_without_reason")

    def test_pre_action_policy_allows_cross_target_with_reason(self):
        self.sm.start_turn("fix this bug")
        self.sm.note_action(
            {"type": "edit_file", "path": "a.txt", "search_text": "x", "replace_text": "y"},
            {"status": "success", "output": "ok"},
            self.state_ops,
        )
        pre = self.sm.pre_action_policy(
            {"type": "read_file", "path": "b.txt", "reason": "because symbol moved"}
        )
        self.assertTrue(pre.allow)

    def test_recover_forbids_repeating_last_fingerprint(self):
        self.sm.start_turn("fix bug")
        failing_cmd = {"type": "edit_file", "path": "a.txt", "search_text": "x", "replace_text": "y"}
        self.sm.note_action(
            failing_cmd,
            {"status": "error", "output": "failed"},
            self.state_ops,
        )
        pre = self.sm.pre_action_policy(failing_cmd)
        self.assertFalse(pre.allow)
        self.assertEqual(pre.stop_reason, "recover_repeated_fingerprint")


if __name__ == "__main__":
    unittest.main()
