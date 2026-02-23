import unittest

from modules.agent.policy_engine import LoopPolicyInput, PolicyEngine, PreActionPolicyInput


class TestPolicyEngine(unittest.TestCase):
    def setUp(self):
        self.engine = PolicyEngine()

    def test_pre_action_denies_recover_repeated_fingerprint(self):
        decision = self.engine.evaluate_pre_action(
            PreActionPolicyInput(
                phase="RECOVER",
                cmd_type="read_file",
                path="a.txt",
                fingerprint="fp-1",
                target_file="a.txt",
                forbidden_recover_fingerprint="fp-1",
                has_cross_target_reason=False,
            )
        )
        self.assertFalse(decision.allow)
        self.assertEqual(decision.stop_reason, "recover_repeated_fingerprint")

    def test_pre_action_denies_cross_target_without_reason(self):
        decision = self.engine.evaluate_pre_action(
            PreActionPolicyInput(
                phase="OBSERVE",
                cmd_type="read_file",
                path="b.txt",
                fingerprint="fp-2",
                target_file="a.txt",
                forbidden_recover_fingerprint=None,
                has_cross_target_reason=False,
            )
        )
        self.assertFalse(decision.allow)
        self.assertEqual(decision.stop_reason, "cross_target_read_without_reason")

    def test_loop_returns_diagnostic_on_stagnation(self):
        decision = self.engine.evaluate_loop(
            LoopPolicyInput(
                stagnation_count=3,
                read_only_limit=3,
                diagnostic_attempts=0,
                max_diagnostics=1,
                invariant_violations=0,
                invariant_limit=1,
                diagnostic_prompt="diag",
                required_next_action_types=["search_content"],
            )
        )
        self.assertEqual(decision.decision, "MODEL_DIAGNOSTIC")
        self.assertEqual(decision.prompt, "diag")

    def test_pre_action_allows_cross_target_in_multi_file_scope(self):
        decision = self.engine.evaluate_pre_action(
            PreActionPolicyInput(
                phase="OBSERVE",
                cmd_type="read_file",
                path="b.txt",
                fingerprint="fp-3",
                target_file="a.txt",
                forbidden_recover_fingerprint=None,
                has_cross_target_reason=False,
                multi_file_scope=True,
            )
        )
        self.assertTrue(decision.allow)

    def test_loop_returns_handoff_after_diagnostics_exhausted(self):
        decision = self.engine.evaluate_loop(
            LoopPolicyInput(
                stagnation_count=3,
                read_only_limit=3,
                diagnostic_attempts=1,
                max_diagnostics=1,
                invariant_violations=0,
                invariant_limit=1,
                diagnostic_prompt="diag",
                required_next_action_types=["search_content"],
            )
        )
        self.assertEqual(decision.decision, "USER_HANDOFF")

    def test_pre_action_denies_readonly_when_multi_file_budget_exhausted(self):
        decision = self.engine.evaluate_pre_action(
            PreActionPolicyInput(
                phase="OBSERVE",
                cmd_type="read_file",
                path="a.txt",
                fingerprint="fp-4",
                target_file=None,
                forbidden_recover_fingerprint=None,
                has_cross_target_reason=False,
                multi_file_scope=True,
                block_readonly_until_state_change=True,
                allow_readonly_probe=False,
            )
        )
        self.assertFalse(decision.allow)
        self.assertEqual(decision.stop_reason, "multi_file_readonly_budget_exhausted")

    def test_pre_action_allows_new_readonly_probe_when_budget_exhausted(self):
        decision = self.engine.evaluate_pre_action(
            PreActionPolicyInput(
                phase="OBSERVE",
                cmd_type="read_file",
                path="fresh.txt",
                fingerprint="fp-5",
                target_file=None,
                forbidden_recover_fingerprint=None,
                has_cross_target_reason=False,
                multi_file_scope=True,
                block_readonly_until_state_change=True,
                allow_readonly_probe=True,
            )
        )
        self.assertTrue(decision.allow)


if __name__ == "__main__":
    unittest.main()
