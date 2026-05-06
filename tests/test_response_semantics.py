import unittest
from types import SimpleNamespace

from modules.agent.orchestration.responses.response_semantics import ResponseSemantics


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

    def test_has_checkpoint_tags_and_memory_update_done(self):
        text = "<path scope=\"intent\">modules/x.py</path><subgoal action=\"mark_in_progress\" id=\"sg_1\" /><memory_update_done />"
        self.assertTrue(self.s.has_checkpoint_tags(text))
        self.assertTrue(self.s.has_memory_update_done(text))

    def test_literal_backticked_checkpoint_tags_do_not_count_as_real_checkpoint_tags(self):
        text = (
            "Пояснення про теги `"
            "<fact>` і `<finding>` у відповіді користувачу."
        )
        self.assertFalse(self.s.has_checkpoint_tags(text))
        self.assertFalse(self.s.has_memory_update_done("Literal `<memory_update_done />` mention only."))

    def test_valid_state_changing_review_before_action_accepts_subgoal_and_progress_bundle(self):
        text = (
            "<think>Verified generator path and planned the next command.</think>"
            "<subgoal action=\"mark_done\" id=\"sg_1\" reason=\"Path verified\" />"
            "<progress scope=\"intent\">Ready to execute the generator.</progress>"
            "<memory_update_done />"
            "<action>{\"type\":\"run_shell\",\"command\":\"python generate_bookmarks_app.py\"}</action>"
        )
        self.assertTrue(self.s.has_valid_state_changing_review_before_action(text))

    def test_valid_state_changing_review_before_action_requires_complete_think(self):
        text = (
            "<memory_review status=\"no_change\" scope=\"intent\" />"
            "<memory_update_done />"
            "<action>{\"type\":\"edit_file\",\"path\":\"a.py\"}</action>"
        )
        self.assertFalse(self.s.has_valid_state_changing_review_before_action(text))

    def test_valid_state_changing_review_before_action_requires_memory_update_done(self):
        text = (
            "<think>Verified edit target and reviewed current state.</think>"
            "<memory_review status=\"no_change\" scope=\"intent\" />"
            "<action>{\"type\":\"edit_file\",\"path\":\"a.py\"}</action>"
        )
        self.assertFalse(self.s.has_valid_state_changing_review_before_action(text))

    def test_is_reflection_only_repair_turn_accepts_tags_only(self):
        parsed = SimpleNamespace(has_action_segment=False, invalid_kind="missing_action_or_answer", visible_text="")
        text = "<finding scope=\"intent\">Found X</finding><decision scope=\"intent\">Do Y</decision><memory_update_done />"
        self.assertTrue(self.s.is_reflection_only_repair_turn(text, parsed, 0))

    def test_is_reflection_only_repair_turn_rejects_action_or_visible_prose(self):
        parsed = SimpleNamespace(has_action_segment=False, invalid_kind="missing_action_or_answer", visible_text="")
        self.assertFalse(self.s.is_reflection_only_repair_turn("<finding scope=\"intent\">X</finding> prose", parsed, 0))
        parsed_action = SimpleNamespace(has_action_segment=True, invalid_kind="", visible_text="")
        self.assertFalse(self.s.is_reflection_only_repair_turn("<finding scope=\"intent\">X</finding><action>{}</action>", parsed_action, 1))

    def test_is_reflection_only_repair_turn_rejects_compiler_ir_action_without_legacy_segment(self):
        parsed = SimpleNamespace(
            has_action_segment=False,
            invalid_kind="missing_action_or_answer",
            visible_text="",
            compiler_ir=SimpleNamespace(action_ops=[SimpleNamespace(payload={"type": "read_file"})]),
        )
        self.assertFalse(self.s.is_reflection_only_repair_turn("<finding scope=\"intent\">X</finding>", parsed, 0))

    def test_is_durable_state_repair_turn_accepts_marker_only_for_missing_memory_update_done(self):
        parsed = SimpleNamespace(has_action_segment=False, invalid_kind="missing_action_or_answer", visible_text="")
        self.assertTrue(
            self.s.is_durable_state_repair_turn(
                "<memory_update_done />",
                parsed,
                0,
                required_kind="missing_memory_update_done",
            )
        )

    def test_is_plaintext_answer_path_accepts_visible_text(self):
        parsed = SimpleNamespace(has_action_segment=False, invalid_kind="missing_action_or_answer", visible_text="Answer")
        self.assertTrue(self.s.is_plaintext_answer_path("Answer", parsed, 0))

    def test_is_plaintext_answer_path_rejects_action_and_non_missing_invalid_kind(self):
        parsed_action = SimpleNamespace(has_action_segment=True, invalid_kind="", visible_text="")
        self.assertFalse(self.s.is_plaintext_answer_path("<action>{}</action>", parsed_action, 1))
        parsed_invalid = SimpleNamespace(has_action_segment=False, invalid_kind="malformed_action", visible_text="")
        self.assertFalse(self.s.is_plaintext_answer_path("Answer", parsed_invalid, 0))

    def test_is_plaintext_answer_path_rejects_compiler_ir_action_without_legacy_segment(self):
        parsed = SimpleNamespace(
            has_action_segment=False,
            invalid_kind="missing_action_or_answer",
            visible_text="Answer",
            compiler_ir=SimpleNamespace(action_ops=[SimpleNamespace(payload={"type": "read_file"})]),
        )
        self.assertFalse(self.s.is_plaintext_answer_path("Answer", parsed, 0))

    def test_is_plaintext_answer_path_strips_think_and_memory_tags(self):
        parsed = SimpleNamespace(has_action_segment=False, invalid_kind="missing_action_or_answer", visible_text="")
        only_think_and_tag = "<think>one two three four five</think><finding scope=\"intent\">Found X</finding>"
        self.assertFalse(self.s.is_plaintext_answer_path(only_think_and_tag, parsed, 0))
        self.assertTrue(self.s.is_plaintext_answer_path(only_think_and_tag + "Final answer.", parsed, 0))

    def test_has_plain_think_prefix_detects_noncanonical_plain_think(self):
        self.assertTrue(self.s.has_plain_think_prefix("think\n! inspect\n→ read block\n<action>{}</action>"))
        self.assertTrue(self.s.has_plain_think_prefix("Thinking:\nNeed next step"))
        self.assertFalse(self.s.has_plain_think_prefix("<think>Need next step</think>"))

    def test_malformed_state_changing_think_allows_reasonably_long_compact_block(self):
        think_lines = "\n".join(
            [
                "! verified target file and current function boundary",
                "? need exact replacement span for the state update",
                "! existing tests already cover the happy path",
                "? need one guard for the empty branch",
                "→ edit the exact block and then run the focused test",
            ]
        )
        text = (
            f"<think>{think_lines}</think>"
            "<decision scope=\"intent\">Use one targeted edit.</decision>"
            "<memory_update_done />"
            "<action>{\"type\":\"edit_file\",\"path\":\"a.py\"}</action>"
        )
        self.assertFalse(self.s.has_malformed_state_changing_think_before_action(text))

    def test_malformed_state_changing_think_accepts_long_prose_block(self):
        think_text = "! verified state\n? gap\n→ " + ("A" * 1700)
        text = (
            f"<think>{think_text}</think>"
            "<decision scope=\"intent\">Still too large.</decision>"
            "<memory_update_done />"
            "<action>{\"type\":\"edit_file\",\"path\":\"a.py\"}</action>"
        )
        self.assertFalse(self.s.has_malformed_state_changing_think_before_action(text))


if __name__ == "__main__":
    unittest.main()
