import unittest

from modules.history import HistoryManager


class DummyChatProvider:
    pass


class HistoryToolHistoryFilterTests(unittest.TestCase):
    def test_tool_history_assistant_markers_are_not_sent_back_to_model(self):
        history = HistoryManager(DummyChatProvider(), max_tokens=4000)
        history.add_message("user", "Investigate sorting bug")
        history.add_message(
            "assistant",
            'TOOL_HISTORY {"type":"read_chunk","path":"a.txt","start_line":1,"end_line":20}',
        )
        history.add_message("system", "SYSTEM RESULT for `read_chunk`: ok")

        api_history = history.get_history_for_api()
        rendered = [msg["content"] for msg in api_history]

        self.assertIn("Investigate sorting bug", rendered)
        self.assertIn("SYSTEM RESULT for `read_chunk`: ok", rendered)
        self.assertFalse(any(text.lstrip().startswith("TOOL_HISTORY ") for text in rendered))

    def test_tool_history_embedded_after_think_is_not_sent_back_to_model(self):
        history = HistoryManager(DummyChatProvider(), max_tokens=4000)
        history.add_message("user", "Continue investigation")
        history.add_message(
            "assistant",
            '<think>Need the next step</think>\nTOOL_HISTORY {"type":"search_content","path":"a.txt"}',
        )
        history.add_message("system", "SYSTEM RESULT for `search_content`: 2 hits")

        api_history = history.get_history_for_api()
        rendered = [msg["content"] for msg in api_history]

        self.assertIn("Continue investigation", rendered)
        self.assertIn("SYSTEM RESULT for `search_content`: 2 hits", rendered)
        self.assertFalse(any("TOOL_HISTORY {" in text for text in rendered))


if __name__ == "__main__":
    unittest.main()
