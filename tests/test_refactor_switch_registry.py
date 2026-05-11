import os
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch

try:
    import tomllib
except ImportError:
    # For Python < 3.11
    import toml as tomllib

from modules.agent.orchestration.config.switch_registry import get_switch, _load_registry


class TestSwitchRegistry(unittest.TestCase):
    def setUp(self):
        # Clear the cache and environment before each test
        _load_registry.cache_clear()
        self._old_switch_registry_env = os.environ.pop("ANGELICA_REFACTOR_SWITCH_REGISTRY", None)
        self.temp_dir = TemporaryDirectory()

    def tearDown(self):
        # Clear the cache and restore environment after each test
        if self._old_switch_registry_env is None:
            os.environ.pop("ANGELICA_REFACTOR_SWITCH_REGISTRY", None)
        else:
            os.environ["ANGELICA_REFACTOR_SWITCH_REGISTRY"] = self._old_switch_registry_env
        _load_registry.cache_clear()
        self.temp_dir.cleanup()

    def test_get_switch_default_registry_returns_legacy(self):
        """The default registry should return 'legacy' for a known switch."""
        # This test uses the actual default registry file on disk.
        value = get_switch("board_checkpoint.plan_checkpoint_only")
        self.assertEqual(value, "legacy")
        value_recovery = get_switch("recovery.compiler_invalid_kind_mapping")
        self.assertEqual(value_recovery, "legacy")
        value_memory = get_switch("board_memory.memory_checkpoint_only")
        self.assertEqual(value_memory, "legacy")
        value_memory_with_text = get_switch("board_memory.memory_checkpoint_with_text")
        self.assertEqual(value_memory_with_text, "legacy")

    def test_get_switch_override_registry_returns_compiler(self):
        """An override registry file should be loaded when the env var is set."""
        override_content = '[board_checkpoint]\nplan_checkpoint_only = "compiler"\n'
        override_path = Path(self.temp_dir.name) / "override.toml"
        override_path.write_text(override_content)

        os.environ["ANGELICA_REFACTOR_SWITCH_REGISTRY"] = str(override_path)
        _load_registry.cache_clear()
        value = get_switch("board_checkpoint.plan_checkpoint_only")
        self.assertEqual(value, "compiler")

    def test_get_switch_missing_override_file_falls_back(self):
        """If the override file is missing, it should fall back to legacy-safe behavior."""
        os.environ["ANGELICA_REFACTOR_SWITCH_REGISTRY"] = "nonexistent.toml"
        _load_registry.cache_clear()
        # Falls back to an empty registry, so get_switch returns its default 'legacy'
        value = get_switch("board_checkpoint.plan_checkpoint_only")
        self.assertEqual(value, "legacy")

    def test_get_switch_malformed_override_file_falls_back(self):
        """If the override file is malformed, it should fall back to legacy-safe behavior."""
        malformed_path = Path(self.temp_dir.name) / "malformed.toml"
        malformed_path.write_text("not = [valid")

        os.environ["ANGELICA_REFACTOR_SWITCH_REGISTRY"] = str(malformed_path)
        _load_registry.cache_clear()
        # Falls back to an empty registry, so get_switch returns its default 'legacy'
        value = get_switch("board_checkpoint.plan_checkpoint_only")
        self.assertEqual(value, "legacy")

    def test_get_switch_returns_default_for_missing_key(self):
        """If a key is missing from the registry, it should return the default 'legacy'."""
        override_content = '[board_checkpoint]\nsome_other_key = "compiler"\n'
        override_path = Path(self.temp_dir.name) / "override.toml"
        override_path.write_text(override_content)

        os.environ["ANGELICA_REFACTOR_SWITCH_REGISTRY"] = str(override_path)
        _load_registry.cache_clear()
        value = get_switch("board_checkpoint.plan_checkpoint_only")
        self.assertEqual(value, "legacy")

    def test_get_switch_returns_default_for_invalid_value(self):
        """If a switch has an invalid value, it should return the default 'legacy'."""
        override_content = '[board_checkpoint]\nplan_checkpoint_only = "invalid_value"\n'
        override_path = Path(self.temp_dir.name) / "override.toml"
        override_path.write_text(override_content)

        os.environ["ANGELICA_REFACTOR_SWITCH_REGISTRY"] = str(override_path)
        _load_registry.cache_clear()
        value = get_switch("board_checkpoint.plan_checkpoint_only")
        self.assertEqual(value, "legacy")

    def test_loader_is_cached(self):
        """The registry loader should be cached to avoid repeated file I/O."""
        # We spy on tomllib.load, which is inside the cached function.
        # This correctly tests the caching behavior of _load_registry.
        with patch("modules.agent.orchestration.config.switch_registry.tomllib.load", wraps=tomllib.load) as wrapped_load:
            # This test uses the real default registry file, which must exist.
            get_switch("some.key")
            get_switch("another.key")
            wrapped_load.assert_called_once()

    def test_cache_clearing_works_with_env_override(self):
        """The cache should be clearable, allowing env var changes to take effect."""
        # This test uses real files and spies on tomllib.load to verify caching.
        with patch("modules.agent.orchestration.config.switch_registry.tomllib.load", wraps=tomllib.load) as wrapped_load:
            # First call, no env var, uses default registry. This will call tomllib.load.
            value = get_switch("board_checkpoint.plan_checkpoint_only")
            self.assertEqual(value, "legacy")
            wrapped_load.assert_called_once()

            # Second call, should be cached. tomllib.load is not called again.
            value = get_switch("board_checkpoint.plan_checkpoint_only")
            self.assertEqual(value, "legacy")
            wrapped_load.assert_called_once()

            # Third call, with env var and cache cleared. This will call tomllib.load again.
            override_content = '[board_checkpoint]\nplan_checkpoint_only = "compiler"\n'
            override_path = Path(self.temp_dir.name) / "override.toml"
            override_path.write_text(override_content)
            os.environ["ANGELICA_REFACTOR_SWITCH_REGISTRY"] = str(override_path)
            _load_registry.cache_clear()

            value = get_switch("board_checkpoint.plan_checkpoint_only")
            self.assertEqual(value, "compiler")

            self.assertEqual(wrapped_load.call_count, 2)


if __name__ == "__main__":
    unittest.main()
