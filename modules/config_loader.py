# modules/config_loader.py
import os
import yaml
from pathlib import Path
from dotenv import load_dotenv

CONFIG_DIR = Path.home() / ".config" / "angelica-ai"
CONFIG_FILE = CONFIG_DIR / "config.yaml"
ENV_FILE = CONFIG_DIR / ".env"

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
            "max_history_tokens": 4000
        }
        with open(CONFIG_FILE, 'w') as f:
            yaml.dump(default, f)
            
    if ENV_FILE.exists():
        load_dotenv(ENV_FILE)
        
    with open(CONFIG_FILE, 'r') as f:
        return yaml.safe_load(f) or {}
