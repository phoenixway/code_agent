from pathlib import Path


DEFAULT_SYSTEM_PROMPT_PATH = Path(__file__).with_name("default_system_prompt.md")


def _load_default_system_prompt() -> str:
    return DEFAULT_SYSTEM_PROMPT_PATH.read_text(encoding="utf-8").rstrip()


DEFAULT_SYSTEM_PROMPT = _load_default_system_prompt()
