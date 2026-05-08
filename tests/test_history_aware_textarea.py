import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from modules.ui_components.history_aware_textarea import HistoryAwareTextArea


class TestHistoryAwareTextArea(unittest.TestCase):
    def test_add_entry_persists_multiline_as_single_history_item(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            history_file = Path(tmpdir) / "history.txt"

            with patch("modules.ui_components.history_aware_textarea.HISTORY_FILE", history_file):
                first = HistoryAwareTextArea()
                first.add_entry("line 1\nline 2\nline 3")

                second = HistoryAwareTextArea()

            self.assertEqual(second._history, ["line 1\nline 2\nline 3"])

