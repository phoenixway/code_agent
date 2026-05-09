import unittest
from unittest.mock import patch

from modules.agent.orchestration.config.switch_registry import get_switch, _load_registry


class TestSwitchRegistry(unittest.TestCase):
    def setUp(self):
        # Clear the cache before each test
        _load_registry.cache_clear()

    def tearDown(self):
        # Clear the cache after each test
        _load_registry.cache_clear()

    @patch("modules.agent.orchestration.config.switch_registry.tomllib.load")
    @patch("modules.agent.orchestration.config.switch_registry.Path.exists")
    def test_get_switch_loads_and_returns_value(self, mock_exists, mock_load):
        mock_exists.return_value = True
        mock_load.return_value = {
            "board_checkpoint": {
                "plan_checkpoint_only": "compiler"
            }
        }

        value = get_switch("board_checkpoint.plan_checkpoint_only")
        self.assertEqual(value, "compiler")

    @patch("modules.agent.orchestration.config.switch_registry.Path.exists")
    def test_get_switch_returns_default_for_missing_file(self, mock_exists):
        mock_exists.return_value = False
        value = get_switch("board_checkpoint.plan_checkpoint_only")
        self.assertEqual(value, "legacy")

    @patch("modules.agent.orchestration.config.switch_registry.tomllib.load")
    @patch("modules.agent.orchestration.config.switch_registry.Path.exists")
    def test_get_switch_returns_default_for_missing_key(self, mock_exists, mock_load):
        mock_exists.return_value = True
        mock_load.return_value = {"board_checkpoint": {}}
        value = get_switch("board_checkpoint.plan_checkpoint_only")
        self.assertEqual(value, "legacy")

    @patch("modules.agent.orchestration.config.switch_registry.tomllib.load")
    @patch("modules.agent.orchestration.config.switch_registry.Path.exists")
    def test_get_switch_returns_default_for_invalid_value(self, mock_exists, mock_load):
        mock_exists.return_value = True
        mock_load.return_value = {
            "board_checkpoint": {
                "plan_checkpoint_only": "invalid_value"
            }
        }
        value = get_switch("board_checkpoint.plan_checkpoint_only")
        self.assertEqual(value, "legacy")

    @patch("modules.agent.orchestration.config.switch_registry.tomllib.load")
    @patch("modules.agent.orchestration.config.switch_registry.Path.exists")
    def test_loader_is_cached(self, mock_exists, mock_load):
        mock_exists.return_value = True
        mock_load.return_value = {}

        get_switch("some.key")
        get_switch("another.key")

        mock_load.assert_called_once()


if __name__ == "__main__":
    unittest.main()
