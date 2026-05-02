import unittest

from modules.agent.orchestration.parsers.visible_text import extract_visible_text_for_user


class VisibleTextTests(unittest.TestCase):
    def test_extract_visible_text_preserves_multiline_plain_answer(self):
        response = (
            "<think>\nNeed summary.\n</think>\n"
            "Ось розмір кожної підпапки:\n"
            "* 3.6G app\n"
            "* 28M core-data-models\n"
            "* 20M sync\n"
        )

        visible = extract_visible_text_for_user(response)

        self.assertEqual(
            "Ось розмір кожної підпапки:\n* 3.6G app\n* 28M core-data-models\n* 20M sync",
            visible,
        )

    def test_extract_visible_text_drops_control_only_response(self):
        response = (
            "<think>\nNeed summary.\n</think>\n"
            "<action>{\"type\":\"run_shell\",\"command\":\"du -sh *\"}</action>"
        )

        self.assertEqual("", extract_visible_text_for_user(response))


if __name__ == "__main__":
    unittest.main()
