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
            "permission_policy": "ask", 
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
            "shell_allowlist_prefixes": []
        }
        with open(CONFIG_FILE, 'w') as f:
            yaml.dump(default, f)
            
    if ENV_FILE.exists():
        load_dotenv(ENV_FILE)
        
    with open(CONFIG_FILE, 'r') as f:
        settings = yaml.safe_load(f) or {}
        
    # Migration: rename context_size to history_size if it exists
    changed = False
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
        "max_shell_command_length": 1000,
        "shell_blocklist": ["rm -rf /", "mkfs", ":(){ :|:& };:"],
        "shell_allowlist_prefixes": [],
    }
    for key, value in runtime_defaults.items():
        if key not in settings:
            settings[key] = value
            changed = True
            log.info(f"Config migration: added missing '{key}' with default value.")

    if changed:
        with open(CONFIG_FILE, 'w') as f:
            yaml.dump(settings, f, default_flow_style=False)
            
    return settings

def update_settings(updates: dict):
    """Updates the config.yaml file with the provided dictionary."""
    current_settings = load_settings()
    current_settings.update(updates)
    
    with open(CONFIG_FILE, 'w') as f:
        yaml.dump(current_settings, f, default_flow_style=False)
    
    return current_settings
