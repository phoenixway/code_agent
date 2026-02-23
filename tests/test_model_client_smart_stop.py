import unittest
from types import SimpleNamespace
from unittest.mock import patch

from modules.agent.model_client import ModelClient


class TestModelClientSmartStop(unittest.TestCase):
    def _make_client(self):
        cfg = SimpleNamespace(default_model="dummy")
        with patch("modules.agent.model_client.get_chat_provider", return_value=SimpleNamespace()):
            client = ModelClient(cfg)
        client._smart_stop_trailing_text_limit = 20
        return client

    def test_does_not_stop_on_single_action_without_trailing_text(self):
        client = self._make_client()
        text = '<action type="read_file">{"path":"a.txt"}</action>'
        self.assertFalse(client._should_smart_stop(text))

    def test_does_not_stop_for_multi_action_batch(self):
        client = self._make_client()
        text = (
            '<action type="read_file">{"path":"a.txt"}</action>\n'
            '<action type="read_file">{"path":"b.txt"}</action>'
        )
        self.assertFalse(client._should_smart_stop(text))

    def test_stops_on_long_non_action_trailing_text(self):
        client = self._make_client()
        text = (
            '<action type="read_file">{"path":"a.txt"}</action>\n'
            "Пояснюю далі дуже довго поза action блоком."
        )
        self.assertTrue(client._should_smart_stop(text))

    def test_does_not_stop_when_action_block_is_unclosed(self):
        client = self._make_client()
        text = '<action type="read_file">{"path":"a.txt"}'
        self.assertFalse(client._should_smart_stop(text))

    def test_format_comm_block_trims_outer_newlines(self):
        client = self._make_client()
        block = client._format_comm_block("OUTGOING", "\n\npayload\n\n")
        self.assertEqual(block, "--- OUTGOING ---\npayload")


if __name__ == "__main__":
    unittest.main()
