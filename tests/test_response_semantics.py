import unittest
from types import SimpleNamespace

from modules.agent.orchestration.response_semantics import ResponseSemantics


class ResponseSemanticsTests(unittest.TestCase):
    def setUp(self):
        self.s = ResponseSemantics()

    def test_has_substantial_think_counts_five_or_more_words_inside_think(self):
        self.assertTrue(self.s.has_substantial_think("<think>one two three four five</think>"))
        self.assertFalse(self.s.has_substantial_think("<think>one two three four</think>"))
        self.assertFalse(self.s.has_substantial_think("one two three four five"))

    def test_reflection_tag_count(self):
        text = "<finding scope=\"intent\">A</finding><decision scope=\"intent\">B</decision>"
        self.assertEqual(2, self.s.reflection_tag_count(text))

    def test_substantial_think_without_reflection_detects_missing_tag_before_action(self):
        text = "<think>one two three four five six</think><action>{}</action>"
        self.assertTrue(self.s.substantial_think_without_reflection(text))

    def test_substantial_think_without_reflection_accepts_tag_before_action(self):
        text = "<think>one two three four five six</think><finding scope=\"intent\">Useful</finding><action>{}</action>"
        self.assertFalse(self.s.substantial_think_without_reflection(text))

    def test_substantial_think_without_reflection_stops_at_intent_boundary(self):
        text = "<think>one two three four five six</think><intent>{}</intent><finding scope=\"intent\">Late</finding>"
        self.assertTrue(self.s.substantial_think_without_reflection(text))

    def test_is_reflection_only_repair_turn_accepts_tags_only(self):
        parsed = SimpleNamespace(has_action_segment=False, invalid_kind="missing_action_or_answer", visible_text="")
        text = "<finding scope=\"intent\">Found X</finding><decision scope=\"intent\">Do Y</decision>"
        self.assertTrue(self.s.is_reflection_only_repair_turn(text, parsed, 0))

    def test_is_reflection_only_repair_turn_rejects_action_or_visible_prose(self):
        parsed = SimpleNamespace(has_action_segment=False, invalid_kind="missing_action_or_answer", visible_text="")
        self.assertFalse(self.s.is_reflection_only_repair_turn("<finding scope=\"intent\">X</finding> prose", parsed, 0))
        parsed_action = SimpleNamespace(has_action_segment=True, invalid_kind="", visible_text="")
        self.assertFalse(self.s.is_reflection_only_repair_turn("<finding scope=\"intent\">X</finding><action>{}</action>", parsed_action, 1))

    def test_is_plaintext_answer_path_accepts_visible_text(self):
        parsed = SimpleNamespace(has_action_segment=False, invalid_kind="missing_action_or_answer", visible_text="Answer")
        self.assertTrue(self.s.is_plaintext_answer_path("Answer", parsed, 0))

    def test_is_plaintext_answer_path_rejects_action_and_non_missing_invalid_kind(self):
        parsed_action = SimpleNamespace(has_action_segment=True, invalid_kind="", visible_text="")
        self.assertFalse(self.s.is_plaintext_answer_path("<action>{}</action>", parsed_action, 1))
        parsed_invalid = SimpleNamespace(has_action_segment=False, invalid_kind="malformed_action", visible_text="")
        self.assertFalse(self.s.is_plaintext_answer_path("Answer", parsed_invalid, 0))

    def test_is_plaintext_answer_path_strips_think_and_memory_tags(self):
        parsed = SimpleNamespace(has_action_segment=False, invalid_kind="missing_action_or_answer", visible_text="")
        only_think_and_tag = "<think>one two three four five</think><finding scope=\"intent\">Found X</finding>"
        self.assertFalse(self.s.is_plaintext_answer_path(only_think_and_tag, parsed, 0))
        self.assertTrue(self.s.is_plaintext_answer_path(only_think_and_tag + "Final answer.", parsed, 0))

    def test_has_plain_think_prefix_detects_noncanonical_plain_think(self):
        self.assertTrue(self.s.has_plain_think_prefix("think\n! inspect\n→ read block\n<action>{}</action>"))
        self.assertTrue(self.s.has_plain_think_prefix("Thinking:\nNeed next step"))
        self.assertFalse(self.s.has_plain_think_prefix("<think>Need next step</think>"))


if __name__ == "__main__":
    unittest.main()
