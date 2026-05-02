import unittest
from types import SimpleNamespace

from modules.agent.orchestration.responses.response_guards import ResponseGuardPolicy
from modules.agent.orchestration.responses.response_semantics import ResponseSemantics


class ResponseGuardPolicyTests(unittest.TestCase):
    def setUp(self):
        self.state = SimpleNamespace(
            consecutive_memory_checkpoint_only_count=2,
            consecutive_nonproductive_thinking_count=0,
            last_nonproductive_thinking_reason="",
            think_reflection_repair_pending=False,
            terminal_plaintext_completion_pending=True,
            terminal_plaintext_completion_text="buffer",
        )
        self.g = ResponseGuardPolicy(self.state)
        self.s = ResponseSemantics()

    def test_memory_checkpoint_streak_reads_state(self):
        self.assertEqual(2, self.g.memory_checkpoint_streak())

    def test_nonproductive_thinking_streak_reads_state(self):
        self.state.consecutive_nonproductive_thinking_count = 3
        self.assertEqual(3, self.g.nonproductive_thinking_streak())

    def test_set_nonproductive_thinking_state_increments_and_resets(self):
        self.assertEqual(1, self.g.set_nonproductive_thinking_state(True, "reason_a"))
        self.assertEqual(1, self.state.consecutive_nonproductive_thinking_count)
        self.assertEqual("reason_a", self.state.last_nonproductive_thinking_reason)
        self.assertEqual(2, self.g.set_nonproductive_thinking_state(True, "reason_b"))
        self.assertEqual("reason_b", self.state.last_nonproductive_thinking_reason)
        self.assertEqual(0, self.g.set_nonproductive_thinking_state(False))
        self.assertEqual("", self.state.last_nonproductive_thinking_reason)

    def test_reflection_repair_pending_accessors(self):
        self.assertFalse(self.g.reflection_repair_pending())
        self.g.set_reflection_repair_pending(True)
        self.assertTrue(self.g.reflection_repair_pending())

    def test_clear_terminal_plaintext_completion(self):
        self.g.clear_terminal_plaintext_completion()
        self.assertFalse(self.state.terminal_plaintext_completion_pending)
        self.assertEqual("", self.state.terminal_plaintext_completion_text)

    def test_nonproductive_thinking_turn_true_for_substantial_think_without_valid_output(self):
        parsed = SimpleNamespace(has_action_segment=False)
        self.assertTrue(
            self.g.is_nonproductive_thinking_turn(
                self.s,
                "<think>one two three four five six</think>",
                parsed,
                0,
                plaintext_answer_path=False,
            )
        )

    def test_nonproductive_thinking_turn_false_for_valid_outputs_or_special_repairs(self):
        parsed_no_action = SimpleNamespace(has_action_segment=False)
        parsed_action = SimpleNamespace(has_action_segment=True)
        base = "<think>one two three four five six</think>"

        cases = [
            (parsed_action, 1, False, False, False, False, False),
            (parsed_no_action, 0, True, False, False, False, False),
            (parsed_no_action, 0, False, True, False, False, False),
            (parsed_no_action, 0, False, False, True, False, False),
            (parsed_no_action, 0, False, False, False, True, False),
            (parsed_no_action, 0, False, False, False, False, True),
        ]
        for parsed, count, plaintext, intent_handled, mem_action, mem_text, repair in cases:
            self.assertFalse(
                self.g.is_nonproductive_thinking_turn(
                    self.s,
                    base,
                    parsed,
                    count,
                    plaintext_answer_path=plaintext,
                    intent_transition_handled=intent_handled,
                    memory_checkpoint_and_action=mem_action,
                    memory_checkpoint_and_text=mem_text,
                    reflection_only_repair=repair,
                )
            )


if __name__ == "__main__":
    unittest.main()
