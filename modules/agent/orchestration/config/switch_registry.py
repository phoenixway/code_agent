"""
Central registry for semantic runtime refactor authority switches.
"""
import functools
from pathlib import Path

try:
    import tomllib
except ImportError:
    # For Python < 3.11
    import toml as tomllib


@functools.lru_cache(maxsize=1)
def _load_registry():
    """Loads the switch registry from TOML, with caching."""
    registry_path = Path(__file__).parent / "refactor_switches.toml"
    if not registry_path.exists():
        return {}
    try:
        with open(registry_path, "rb") as f:
            return tomllib.load(f)
    except Exception:
        # In case of parsing errors, default to legacy behavior.
        return {}


def get_switch(key: str, default: str = "legacy") -> str:
    """
    Gets the value of a refactor switch from the central registry.

    Args:
        key: The switch key, e.g., "board_checkpoint.plan_checkpoint_only".
        default: The fallback value if the key is not found.

    Returns:
        The switch value ("legacy", "compiler", "shadow") or the default.
    """
    registry = _load_registry()
    parts = key.split(".")
    if not parts:
        return default

    value = registry
    for part in parts:
        if not isinstance(value, dict) or part not in value:
            return default
        value = value[part]

    if not isinstance(value, str) or value not in {"legacy", "compiler", "shadow"}:
        return default

    return value
