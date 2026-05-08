import logging
import yaml
from pathlib import Path
from dotenv import load_dotenv

CONFIG_DIR = Path.home() / ".config" / "angelica-ai"
CONFIG_FILE = CONFIG_DIR / "config.yaml"
ENV_FILE = CONFIG_DIR / ".env"
log = logging.getLogger(__name__)


def load_settings():
    if not CONFIG_DIR.exists():
        CONFIG_DIR.mkdir(parents=True, exist_ok=True)

    if not CONFIG_FILE.exists():
        default = {
            "default_model": "gemini-1.5-pro",
            "available_models": [
                "gemini-1.5-pro",
                "ollama/qwen:4b",
                "claude-3-opus-20240229",
                "gpt-4"
            ],
            "ollama_base_url": "http://127.0.0.1:11434",
            "permission_policy": "ask",
            "system_prompt_directory": str((Path(__file__).with_name("default_system_prompt.md").parent).resolve()),
            "current_system_prompt_path": str(Path(__file__).with_name("default_system_prompt.md").resolve()),
            "max_history_tokens": 4000,
            "history_size": "small",
            "autosummarize_requires_confirmation": False,
            "max_consecutive_calls": 12,
            "max_step_seconds": 120,
            "max_session_seconds": 900,
            "allow_side_effect_tools": True,
            "max_shell_command_length": 1000,
            "shell_blocklist": [
                "rm -rf /",
                "mkfs",
                ":(){ :|:& };:"
            ],
            "shell_allowlist_prefixes": [],
            "planner_enabled": False,
            "planner_mode": "auto",
            "planner_max_steps": 12,
            "planner_max_visible_steps": 4,
            "planner_always_missing_retry_limit": 2,
            "vertexai": {
                "project_id": "",
                "location": "us-central1",
                "publisher": "google",
                "use_adc": True,
            },
        }
        try:
            with open(CONFIG_FILE, "w") as f:
                yaml.dump(default, f, default_flow_style=False)
        except OSError as exc:
            log.warning("Failed to create default config at '%s': %s", CONFIG_FILE, exc)

    if ENV_FILE.exists():
        load_dotenv(ENV_FILE)

    with open(CONFIG_FILE, "r") as f:
        settings = yaml.safe_load(f) or {}

    changed = False

    # Migration: rename context_size -> history_size
    if "context_size" in settings and "history_size" not in settings:
        settings["history_size"] = settings.pop("context_size")
        changed = True
        log.info("Config migration: renamed 'context_size' to 'history_size'.")

    runtime_defaults = {
        "max_consecutive_calls": 12,
        "max_step_seconds": 120,
        "max_session_seconds": 900,
        "autosummarize_requires_confirmation": False,
        "allow_side_effect_tools": True,
        "auto_allow_read_only_actions": True,
        "auto_allow_safe_shell_read_only": True,
        "debug_log_keypresses": False,
        "system_prompt_directory": str((Path(__file__).with_name("default_system_prompt.md").parent).resolve()),
        "current_system_prompt_path": str(Path(__file__).with_name("default_system_prompt.md").resolve()),
        "max_shell_command_length": 1000,
        "shell_blocklist": ["rm -rf /", "mkfs", ":(){ :|:& };:"],
        "shell_allowlist_prefixes": [],
        "planner_enabled": False,
        "planner_mode": "auto",
        "planner_max_steps": 12,
        "planner_max_visible_steps": 4,
        "planner_max_goal_chars": 240,
        "planner_max_step_title_chars": 160,
        "planner_max_step_notes_chars": 240,
        "planner_always_missing_retry_limit": 2,
        "ollama_base_url": "http://127.0.0.1:11434",
        "vertexai": {
            "project_id": "",
            "location": "us-central1",
            "publisher": "google",
            "use_adc": True,
        },
    }

    for key, value in runtime_defaults.items():
        if key not in settings:
            settings[key] = value
            changed = True
            log.info(f"Config migration: added missing '{key}' with default value.")

    vertex_defaults = runtime_defaults["vertexai"]
    vertex_settings = settings.get("vertexai")
    if not isinstance(vertex_settings, dict):
        settings["vertexai"] = dict(vertex_defaults)
        changed = True
        log.info("Config migration: normalized 'vertexai' settings block.")
    else:
        for key, value in vertex_defaults.items():
            if key not in vertex_settings:
                vertex_settings[key] = value
                changed = True
                log.info(f"Config migration: added missing 'vertexai.{key}' with default value.")

    # Normalize ollama_base_url for backward compatibility:
    # allow users to mistakenly store full endpoint ".../api/chat"
    raw_ollama_url = str(settings.get("ollama_base_url", "http://127.0.0.1:11434")).strip()
    normalized_ollama_url = raw_ollama_url.rstrip("/")
    if normalized_ollama_url.endswith("/api/chat"):
        normalized_ollama_url = normalized_ollama_url[:-9].rstrip("/")

    if settings.get("ollama_base_url") != normalized_ollama_url:
        settings["ollama_base_url"] = normalized_ollama_url
        changed = True
        log.info("Config migration: normalized 'ollama_base_url' to base host URL without '/api/chat'.")

    if changed:
        try:
            with open(CONFIG_FILE, "w") as f:
                yaml.dump(settings, f, default_flow_style=False)
        except OSError as exc:
            log.warning("Failed to persist config migration to '%s': %s", CONFIG_FILE, exc)

    return settings


def update_settings(updates: dict):
    """Updates the config.yaml file with the provided dictionary."""
    current_settings = load_settings()
    current_settings.update(updates)

    # Keep ollama_base_url normalized on update as well
    if "ollama_base_url" in current_settings:
        raw_ollama_url = str(current_settings["ollama_base_url"]).strip().rstrip("/")
        if raw_ollama_url.endswith("/api/chat"):
            raw_ollama_url = raw_ollama_url[:-9].rstrip("/")
        current_settings["ollama_base_url"] = raw_ollama_url

    with open(CONFIG_FILE, "w") as f:
        yaml.dump(current_settings, f, default_flow_style=False)

    return current_settings
